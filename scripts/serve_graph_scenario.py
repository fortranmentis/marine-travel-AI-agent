"""Opt-in localhost UI fixture: synthetic rain/venues/routes, real graph + SQLite.
Run: python -m scripts.serve_graph_scenario. Never use this as real travel data.
"""
import datetime as dt
import json
import os
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]/'.tmp'/'graph-scenario'
    root.mkdir(parents=True,exist_ok=True)
    for key,value in dict(MARINE_DATA_DIR=str(root),RUNS_DB_PATH=str(root/'runs.sqlite3'),
        PLANS_DB_PATH=str(root/'plans.sqlite3'),JOURNEYS_DB_PATH=str(root/'journeys.sqlite3'),
        LANGFUSE_ENABLED='false',TRANSPORT_CREDENTIALS_FILE='',MARINE_CREDENTIALS_FILE='').items():os.environ[key]=value
    from marine_agent import providers,enrichment,mobility,planner
    from marine_agent.app import app
    from starlette.responses import HTMLResponse
    @app.middleware('http')
    async def fixture_label(request,call_next):
        response=await call_next(request)
        if request.url.path=='/':
            body=b''.join([chunk async for chunk in response.body_iterator]).decode('utf-8')
            body=body.replace('<body>','<body><div style="position:fixed;bottom:0;left:0;right:0;z-index:10000;padding:8px;background:#fff2ce;color:#5e4900;text-align:center">검증용 합성 예보·관광지·경로 · 실제 여행 자료가 아닙니다</div>')
            return HTMLResponse(body)
        return response
    import uvicorn
    now=dt.datetime.now(providers.KST);date=(now.date()+dt.timedelta(days=1)).isoformat()
    catalog=dict(collected_at=now.isoformat(),tourism_collected_at=now.isoformat(),tourism_source='검증용 합성 관광정보',scope='coastal',
        places=[dict(contentid=str(9000000+i),title=f'[검증용] 실내 전시관 {i}',contenttypeid='14',mapy='37.43',mapx=str(126.42+i*.001),addr1='검증용 장소 · 실제 관광지 아님',areacode='2') for i in range(1,5)],
        marine={})
    (root/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False),encoding='utf-8')
    reviews=[dict(id=p['contentid'],environment='indoor',source_url='https://example.org/synthetic-venue',checked_at=now.isoformat(),valid_until=date) for p in catalog['places']]
    (root/'reviewed_venues.json').write_text(json.dumps(reviews),encoding='utf-8')
    providers.catalog=lambda:catalog
    providers.weather_for_place=lambda *a:dict(status='available',date=date,issue_at=now.isoformat(),source='검증용 합성 예보',warnings_checked=False,
        forecasts={f'{h:02d}00':dict(PTY='1',POP='90',WSD='2',TMP='15') for h in range(24)})
    enrichment.photo_for=lambda *a:dict(status='unavailable')
    enrichment.road_route=lambda a,b,**kw:dict(status='available',duration_s=60,distance_m=900,geometry=None,mode=kw.get('mode','car'),source='검증용 합성 경로')
    mobility.route_between=lambda a,b,mode='car',**kw:dict(status='available',duration_s=60,distance_m=900,geometry=None,mode=mode,source='검증용 합성 경로')
    mobility.capabilities=lambda:dict(car=True,walk=True,transit=True,transit_provider='synthetic',transit_reason='검증용 합성 경로')
    original=planner.build_plan
    def build(trip):
        result=original(trip)
        result['notices'].insert(0,'[검증용] 모든 관광지·기상·이동 자료는 합성 데이터입니다. 실제 여행에 사용하지 마세요.')
        for day in result['days']:day['warnings'].insert(0,'[검증용 합성 예보] 우천·도보 제약에 따른 선택·재개 동작을 확인하는 화면입니다.')
        return result
    planner.build_plan=build
    uvicorn.run(app,host='127.0.0.1',port=8002,log_level='warning')

if __name__=='__main__':main()
