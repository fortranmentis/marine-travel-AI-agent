import copy
import datetime as dt
import json

from fastapi.testclient import TestClient
import pytest

from marine_agent import transport_api as api,public_transport as transit,ferry_api as ferry,island_drafts,agent
from marine_agent.app import app


def response(rows=(),status='available',**kw):
    return dict(status=status,rows=list(rows),count=len(rows),source_url='https://www.data.go.kr/data/15098523/openapi.do',**kw)


def test_credentials_parse_only_allowlisted_bases_and_old_new_labels(tmp_path,monkeypatch):
    file=tmp_path/'keys.txt'
    file.write_text('bus\nEnd Point : '+api.BASES['stops']+'\n인증키 : fake%2Bkey\n\n'
        'malicious\nEnd Point : https://example.invalid/\n인증키 : secret\n',encoding='utf-8')
    monkeypatch.setenv('TRANSPORT_CREDENTIALS_FILE',str(file))
    assert api.credentials()=={'stops':'fake+key'}
    assert api.availability()['stops'] and not api.availability()['ship']
    with pytest.raises(ValueError):api.request('ship','https://evil.invalid')
    with pytest.raises(ValueError):api.request('ship','GetPortList',{'serviceKey':'override'})


def test_decode_singleton_missing_zero_count_and_xml_error():
    obj=dict(response=dict(header=dict(resultCode='00'),body=dict(items=dict(item=dict(nodeId='001')),totalCount=1)))
    assert api.decode(json.dumps(obj))['rows']==[{'nodeId':'001'}]
    obj['response']['body']['totalCount']=0
    assert api.decode(json.dumps(obj))['total']==0
    assert api.decode('<error><returnReasonCode>30</returnReasonCode></error>')['code']=='30'
    assert api.decode('<r><resultCode>00</resultCode></r>')['code']=='unexpected_xml'


def test_request_cache_clone_and_sanitized_failure(monkeypatch):
    monkeypatch.setattr(api,'credentials',lambda:{'ship':'never-print-me'})
    calls=[]
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get(self,*a,**kw):
            calls.append(kw)
            class Result:
                status_code=200
                text=json.dumps({'response':{'header':{'resultCode':'00'},'body':{'items':{'item':[{'nodeId':'01'}]},'totalCount':1}}})
            return Result()
    monkeypatch.setattr(api.httpx,'Client',Client)
    first=api.request('ship','GetPortList');first['rows'].clear()
    second=api.request('ship','GetPortList')
    assert second['rows'] and second['cached'] and len(calls)==1
    assert 'never-print-me' not in json.dumps(second)
    api._cache.clear()
    monkeypatch.setattr(Client,'get',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('never-print-me')))
    assert 'never-print-me' not in json.dumps(api.request('ship','GetPortList'))


def test_pagination_rejects_repeated_rows_and_changed_totals(monkeypatch):
    monkeypatch.setattr(api,'request',lambda *a,**k:dict(response([{'id':'x'}]),count=2))
    assert api.pages('ship','GetPortList')['status']=='incomplete'
    rows=iter([dict(response([{'id':'1'}]),count=2),dict(response([{'id':'2'}]),count=3)])
    monkeypatch.setattr(api,'request',lambda *a,**k:next(rows))
    assert api.pages('ship','GetPortList')['rows']==[]


def raw_sailing(origin='인천',destination='덕적도_진리',departure='202610170800',arrival='202610170930',vessel='코리아피스호'):
    return dict(depPlaceNm=origin,arrPlaceNm=destination,depPlandTime=departure,arrPlandTime=arrival,vihicleNm=vessel,charge=27000)


def test_ferry_dates_shared_arrival_and_reversed_times():
    a=raw_sailing();b=dict(a,arrPlaceNm='다른섬')
    rows,bad=ferry.normalize(response([a,b]),'인천','덕적도_진리','2026-10-17')
    assert rows[0]['quality_flags']==['shared_arrival_across_destinations']
    assert not rows[0]['arrival_verified']
    assert ferry.normalize(response([a]),'인천','덕적도_진리','2026-10-18')[0]==[]
    assert ferry.normalize(response([dict(a,arrPlandTime='202610170700')]),'인천','덕적도_진리','2026-10-17')[1]==1


def test_ferry_reconcile_exact_alias_ports_time_and_cancellation():
    row=ferry.normalize(response([raw_sailing()]),'인천','덕적도_진리','2026-10-17')[0][0]
    proof=dict(rlvt_ymd='20261017',sail_tm='800',psnshp_nm='코리아피스',oport_nm='인천',dest_nm='덕적',nvg_se_nm='비운')
    value=ferry.reconcile(row,response([proof]),'2026-10-17','인천','덕적')
    assert value['operation_status']=='not_operating' and not value['arrival_verified']
    proof['sail_tm']='830'
    assert ferry.reconcile(row,response([proof]),'2026-10-17','인천','덕적')['operation_status']=='unmatched'


def test_reference_pairs_never_become_verified_or_enable_scheduling(monkeypatch):
    def pages(service,operation,params=None,**kw):
        if operation=='GetPortList':return response([dict(nodeId='SEA10100',nodeNm='인천'),dict(nodeId='SEA10110',nodeNm='덕적도_진리')])
        if operation=='GetShipOpratInfoList':
            return response([raw_sailing()]) if params['depNodeId']=='SEA10100' else response([raw_sailing('덕적도_진리','인천','202610171600','202610171730')])
        return response([dict(rlvt_ymd='20261017',sail_tm=t,psnshp_nm='코리아피스',oport_nm=o,dest_nm=d,nvg_se_nm='정상') for t,o,d in [('800','인천','덕적'),('1600','덕적','인천')]])
    monkeypatch.setattr(api,'pages',pages)
    value=ferry.timetables('인천남서','2026-10-17')
    assert len(value['pairs'])==1 and not value['pairs'][0]['usable_for_planning'] and not value['roundtrip_verified']
    monkeypatch.setattr(api,'availability',lambda:{'ship':True,'komsa':True})
    access=island_drafts.access_info('인천남서','2026-10-17')
    assert access['timetable']['pairs'] and not access['roundtrip_verified'] and access['rows']==[]


def test_missing_port_source_has_stable_unverified_response(monkeypatch):
    monkeypatch.setattr(api,'pages',lambda *a,**kw:response([],'unavailable'))
    value=ferry.timetables('인천남서','2026-10-17')
    assert value['pair_count']==0 and value['date']=='2026-10-17' and not value['usable_for_planning']


def test_nearby_uses_finite_points_distance_and_preserves_ids(monkeypatch):
    monkeypatch.setattr(api,'pages',lambda *a,**k:response([
        dict(citycode=23,nodeid='ICB0001',nodenm='가까운 역',gpslati=37.47,gpslong=126.61),
        dict(citycode=23,nodeid='ICB0002',nodenm='오류 좌표',gpslati=38,gpslong=127),
        dict(citycode=23,nodeid='ICB0003',nodenm='결측',gpslati='nan',gpslong=126)]))
    value=transit.nearby(37.47,126.61)
    assert value['rows'][0]['id']=='ICB0001' and len(value['rows'])==1 and value['rejected_rows']==2


def test_live_bus_arrival_zero_is_not_missing_and_not_future_schedule(monkeypatch):
    monkeypatch.setattr(api,'pages',lambda *a,**k:response([dict(arrtime=0,nodeid='001',routeid='R1',routeno='2'),dict(arrtime=-1,nodeid='001',routeid='R1',routeno='2')]))
    result=transit.stop('23','001')
    assert len(result['rows'])==1 and result['rows'][0]['seconds']==0 and '미래' in result['note']


def test_subway_day_type_next_day_and_missing_times(monkeypatch):
    calls=[]
    def pages(service,op,params,**kw):
        calls.append(params)
        return response([dict(depTime='250100',endSubwayStationNm='종점'),dict(depTime=None),dict(depTime='bad')]) if 'Schdul' in op else response([],'no_data')
    monkeypatch.setattr(api,'pages',pages)
    value=transit.subway('MTR001','2026-10-17','D')
    assert value['day_type']=='02' and not value['schedule_verified']
    assert value['times']['rows']==[dict(departure='25:01',destination='종점',service_day_offset=1)]
    assert calls[0]['upDownTypeCode']=='D'


def test_api_input_validation_and_new_model_tools(monkeypatch):
    client=TestClient(app)
    assert client.get('/api/transport/nearby?lat=nan&lon=126').status_code==422
    assert client.get('/api/transport/stops/abc?city=wrong').status_code==422
    assert client.get('/api/ferries/timetable?region=bogus&date=2026-10-17').status_code==422
    assert client.get('/api/transport/subway/MTR1?date=bad').status_code==422
    assert client.get('/api/transport/subway?keyword=%20%20').status_code==422
    monkeypatch.setattr(transit,'nearby',lambda *a:response([],'no_data'))
    value=client.get('/api/transport/nearby?lat=37.4&lon=126.6')
    assert value.status_code==200 and value.headers['cache-control']=='no-store'
    assert {'get_nearby_transport','get_ferry_timetable'}<=set(agent.TOOLS)
