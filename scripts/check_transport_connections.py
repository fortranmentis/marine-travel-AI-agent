"""Explicit authenticated transport probes, sanitized public evidence only."""
import argparse
import datetime as dt
import json
from pathlib import Path
import httpx
from marine_agent import transport_api as api,public_transport as transit,ferry_api


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ai',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];report=dict(checked_at=dt.datetime.now(api.KST).isoformat(),services=[])
    def record(service,operation,value):
        item=dict(service=service,operation=operation,status=value['status'],result_code=value.get('result_code'),
            count=value.get('count'),returned_count=len(value.get('rows',[])),source_url=value.get('source_url'))
        report['services'].append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    today=dt.datetime.now(api.KST).date()
    record('komsa','get-oprt-schd-info-v2',api.request('komsa','get-oprt-schd-info-v2',dict(rlvtYmd=today.strftime('%Y%m%d'),psnshpNm='코리아피스')))
    record('ship','GetPsnshipTrminlList',api.request('ship','GetPsnshipTrminlList'))
    nearby=transit.nearby(37.47636,126.61694);record('stops','getCrdntPrxmtSttnList',nearby)
    assert nearby['rows'],'No stop available for live probe'
    stop=nearby['rows'][0];arrivals=transit.stop(stop['city_code'],stop['id']);record('bus_arrivals','getSttnAcctoArvlPrearngeInfoList',arrivals)
    if arrivals['rows']:
        detail=transit.route(stop['city_code'],arrivals['rows'][0]['route_id'])
        record('bus_routes','getRouteInfoIem',detail['info']);record('bus_routes','getRouteAcctoThrghSttnList',detail['stops'])
        record('bus_positions','getRouteAcctoBusLcList',detail['positions'])
    stations=transit.stations('인천');record('subway','GetKwrdFndSubwaySttnList',stations)
    station=next(r for r in stations['rows'] if r['title']=='인천')
    timetable=transit.subway(station['id'],today.isoformat(),'U')
    record('subway','GetSubwaySttnAcctoSchdulList',timetable['times']);record('subway','GetSubwaySttnExitAcctoBusRouteList',timetable['exits'])
    future=(today+dt.timedelta(days=1)).isoformat()
    ferries=ferry_api.timetables('인천남서',future)
    report['ferry_reference']=dict(date=future,status=ferries['status'],rows=len(ferries['rows']),pairs=ferries['pair_count'],
        departure_matches=sum(r.get('departure_matched',False) for r in ferries['rows']),
        arrival_quality_flags=sum(bool(r['quality_flags']) for r in ferries['rows']),roundtrip_verified=ferries['roundtrip_verified'])
    assert ferries['rows'] and not ferries['roundtrip_verified']
    assert all(dt.datetime.fromisoformat(r['departure']).date().isoformat()==future for r in ferries['rows'])
    (root/'.tmp'/'transport-ferry-live.json').write_text(json.dumps(ferries,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.ai:
        with httpx.Client(base_url='http://127.0.0.1:8001',timeout=240,trust_env=False) as client:
            response=client.post('/api/chat',json=dict(message=f'{future} 인천남서 덕적도 배편 시간표를 API로 조회하고, 인천역 좌표 위도 37.47636 경도 126.61694 주변 버스정류소도 도구로 조회해줘. 참고 정보와 미검증 항목을 구분해줘.'))
            response.raise_for_status();value=response.json();report['ai_status']=value['status'];report['ai_trace']=value['trace']
            assert {'get_ferry_timetable','get_nearby_transport'}<={r['tool'] for r in value['trace'] if r['status']=='ok'}
    report['notes']=['Counts are one-time live observations, not nationwide availability.','TAGO arrival and terminal-address issues prevent automatic verified round trips.','Live positions/arrivals do not verify future journeys.']
    (root/'reports'/'transport-connections.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved sanitized report: reports/transport-connections.json',flush=True)


if __name__=='__main__':main()
