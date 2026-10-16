import copy
import datetime as dt
import json

import pytest
from pydantic import ValidationError

from marine_agent import planner, providers, travel, mobility, islands, enrichment
from test_core import snapshot


def test_daily_hours_and_children(snapshot):
    _, date = snapshot
    second = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()
    plan = planner.build_plan(dict(start_date=date, days=2, activity='none', party_type='group', adults=15,
        child_count=2, child_ages=[3, 12], daily_times=[dict(date=date,start='15:00',end='18:00'),
                                                     dict(date=second,start='08:00',end='12:00')]))
    assert plan['trip']['child_count'] == 2
    for day in plan['days']:
        assert all(day['day_start'] <= i['start'] < i['end'] <= day['day_end'] for i in day['items'])
    with pytest.raises(ValidationError):
        planner.Trip(start_date=date, child_count=2, child_ages=[6])
    assert planner.Trip(start_date=date, child_ages=[6]).child_count == 1


def test_daily_validation_and_lock_bounds(snapshot):
    _, date = snapshot
    with pytest.raises(ValidationError):
        planner.Trip(start_date=date, daily_times=[dict(date=date,start='18:00',end='09:00')])
    with pytest.raises(ValidationError):
        planner.Trip(start_date=date, daily_times=[dict(date=date,start='14:00',end='18:00')],
            locked=[dict(date=date,start='10:00',end='11:00',title='고정')])
    assert planner.Trip(start_date=date, day_start='16:00',day_end='18:00')


def test_visit_count_excludes_meals_and_shortage(snapshot):
    data, date = snapshot
    one = planner.build_plan(dict(start_date=date,days=1,visits_per_day=1,activity='none'))['days'][0]
    assert one['actual_visits'] == 1
    assert any(i['kind'] == 'break' for i in one['items'])
    crowded = planner.build_plan(dict(start_date=date,days=1,visits_per_day=6,activity='none',day_start='15:00',day_end='17:00'))['days'][0]
    assert crowded['actual_visits'] < 6 and crowded['warnings']


def test_food_categories_and_nearby_radius(snapshot):
    data, date = snapshot
    data['places'] += [dict(contentid='f'+str(i), title=code,contenttypeid='39',mapy='37.43',mapx='126.42',cat3=code)
                       for i,code in enumerate(['A05020100','A05020200','A05020300','A05020400','A05020700','A05020900'])]
    assert len(travel.food_candidates('영종·용유')) == 5
    assert [p['cuisine'] for p in travel.food_candidates('영종·용유',['chinese'])] == ['chinese']
    assert len(travel.food_candidates('영종·용유',cafe=True)) == 1
    assert travel.food_candidates('영종·용유',near=(37.56,126.61),radius_km=1) == []
    day = planner.build_plan(dict(start_date=date,days=1,activity='none',cuisines=['korean']))['days'][0]
    meals = [i for i in day['items'] if i['kind'] == 'meal']
    assert meals and all(i['cuisine'] == 'korean' for i in meals)
    assert day['actual_visits'] == 2
    assert planner.validate_schedule([day])


def test_food_unavailable_routes_keep_break(snapshot, monkeypatch):
    data,date=snapshot
    data['places'].append(dict(contentid='9',title='식당',contenttypeid='39',mapy='37.43',mapx='126.42',cat3='A05020100'))
    monkeypatch.setattr(mobility,'route_between',lambda *a,**kw:dict(status='unavailable'))
    day=planner.build_plan(dict(start_date=date,days=1,activity='none'))['days'][0]
    assert not any(i['kind']=='meal' for i in day['items'])
    assert any(i['kind']=='break' for i in day['items'])


def test_walk_route_failure_never_falls_back_to_car(snapshot, monkeypatch):
    _,date=snapshot
    modes=[]
    def route(*args,**kwargs):
        modes.append(kwargs.get('mode'))
        return dict(status='unavailable')
    monkeypatch.setattr(enrichment,'road_route',route)
    day=planner.build_plan(dict(start_date=date,days=1,activity='none',transport='walk'))['days'][0]
    assert day['actual_visits']==1
    assert modes and set(modes)=={'walk'}


def test_transit_without_key_is_explicit(monkeypatch):
    monkeypatch.setenv('TRANSIT_PROVIDER','odsay')
    monkeypatch.delenv('ODSAY_API_KEY',raising=False)
    assert not mobility.capabilities()['transit']
    assert mobility.transit_route({}, {})['status']=='not_configured'


def test_index_conservative_and_missing(snapshot):
    data,date=snapshot
    rows=[dict(sareaDtlNm='인천내륙',predcYmd=date,predcNoonSeCd=p,totalIndex=g) for p,g in [('오전','좋음'),('오후','나쁨')]]
    data['marine']['seatrip']=dict(rows=rows,source='https://www.data.go.kr/data/15142491/openapi.do')
    am=travel.sea_outlook('영종·용유',date,'09:00','12:00')
    all_day=travel.sea_outlook('영종·용유',date,'09:00','18:00')
    assert am['grade']=='좋음' and all_day['grade']=='나쁨'
    rows.pop()
    missing=travel.sea_outlook('영종·용유',date,'09:00','18:00')
    assert missing['grade'] is None
    assert travel.overall_outlook([dict(travel_index=am),dict(travel_index=missing)])['grade'] is None
    assert travel.sea_outlook('island',date,'09:00','18:00')['grade'] is None


def manifest(date):
    return dict(id='test-island',title='검증 테스트 섬',reviewed_at=dt.datetime.now(providers.KST).isoformat(),
        mainland_port=dict(title='출발항',lat=37.4,lon=126.5),island_port=dict(title='섬항',lat=37.43,lon=126.42),
        place_ids=['0','1','2','3'],checkin_minutes=40,
        crossings=[dict(date=date,direction=d,departure=a,arrival=b,vessel='테스트선',status='scheduled',source_url='https://www.komsa.or.kr/')
                   for d,a,b in [('outbound','10:00','11:00'),('return','16:00','17:00')]])


def test_ferry_roundtrip_buffers_and_cancellation(snapshot,monkeypatch,tmp_path):
    _,date=snapshot
    monkeypatch.setattr(islands,'DATA',tmp_path)
    row=manifest(date)
    (tmp_path/'reviewed_islands.json').write_text(json.dumps([row]),encoding='utf-8')
    assert islands.resolve('test-island').title=='검증 테스트 섬'
    monkeypatch.setattr(enrichment,'road_route',lambda *a,**kw:dict(status='available',duration_s=60,distance_m=100))
    plan=planner.build_plan(dict(start_date=date,days=1,activity='none',island_id='test-island'))
    day=plan['days'][0]
    assert sum(i['kind']=='ferry' for i in day['items'])==2
    assert day['transport']=='walk'
    assert planner.validate_schedule([day])
    assert all('11:15'<=i['start']<i['end']<='15:20' for i in day['items'] if i['kind']=='tourism')
    row['crossings'][1]['status']='cancelled'
    (tmp_path/'reviewed_islands.json').write_text(json.dumps([row]),encoding='utf-8')
    with pytest.raises(ValueError,match='王復|왕복'):
        islands.day_crossings(islands.resolve('test-island'),date,'09:00','18:00')


def test_unreviewed_or_expired_island_is_unavailable(snapshot,monkeypatch,tmp_path):
    _,date=snapshot
    monkeypatch.setattr(islands,'DATA',tmp_path)
    with pytest.raises(ValueError):islands.resolve('missing')
    row=manifest(date);row['reviewed_at']=(dt.datetime.now(providers.KST)-dt.timedelta(days=2)).isoformat()
    (tmp_path/'reviewed_islands.json').write_text(json.dumps([row]),encoding='utf-8')
    assert islands.reviewed()==[]
    from fastapi.testclient import TestClient
    from marine_agent.app import app
    response=TestClient(app).post('/api/plan',json=dict(start_date=date,days=1,island_id='missing'))
    assert response.status_code==422 and '검증' in response.json()['detail']


def test_odsay_sections_and_errors_never_expose_key(monkeypatch):
    monkeypatch.setenv('TRANSIT_PROVIDER','odsay')
    monkeypatch.setenv('ODSAY_API_KEY','synthetic-test-key')
    monkeypatch.setattr(enrichment,'cached',lambda *a:None)
    monkeypatch.setattr(enrichment,'remember',lambda key,value,seconds:value)
    class Response:
        def raise_for_status(self):pass
        def json(self):return dict(result=dict(path=[dict(pathType=2,info=dict(totalTime=35,totalDistance=6000,payment=1500),
            subPath=[dict(trafficType=3,sectionTime=5),dict(trafficType=2,sectionTime=30,startName='출발',endName='도착',lane=[dict(busNo='10')])])]))
    class Client:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get(self,url,params):
            assert url.endswith('/searchPubTransPathT') and params['SX']==126.4
            return Response()
    monkeypatch.setattr(mobility.httpx,'Client',Client)
    point=dict(lat=37.4,lon=126.4)
    result=mobility.transit_route(point,point)
    assert result['duration_s']==2100 and result['sections'][1]['lines']==['10']
    assert result['geometry'] is None and not result['schedule_verified']
    assert 'synthetic-test-key' not in json.dumps(result)
    monkeypatch.setattr(Client,'get',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('https://example/?apiKey=synthetic-test-key')))
    result=mobility.transit_route(point,point)
    assert result['status']=='unavailable' and 'synthetic-test-key' not in json.dumps(result)


def test_komsa_official_filters_and_success_code(monkeypatch):
    from marine_agent import ferries
    monkeypatch.setenv('KOMSA_API_KEY','synthetic-key')
    calls=[]
    raw=json.dumps(dict(response=dict(header=dict(resultCode='200'),body=dict(totalCount=1,items=dict(item=[dict(psnshp_nm='테스트선')])))))
    monkeypatch.setattr(providers,'get',lambda url,params:(calls.append((url,params)) or raw))
    result=ferries.schedules('2026-10-16','테스트선')
    assert len(result['rows'])==1
    assert calls[0][1]['rlvtYmd']=='20261016' and calls[0][1]['psnshpNm']=='테스트선'
    assert 'synthetic-key' not in json.dumps(result)
