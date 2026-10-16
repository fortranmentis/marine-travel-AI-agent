import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from marine_agent import planner, providers, regions, travel, enrichment, plans
from marine_agent.app import app


@pytest.fixture
def national(monkeypatch):
    date=(dt.datetime.now(providers.KST).date()+dt.timedelta(days=1)).isoformat()
    c=dict(collected_at=dt.datetime.now(providers.KST).isoformat(),scope='coastal',tourism_source='TourAPI',
        administrative={'32':[dict(code='1',name='강릉시'),dict(code='2',name='고성군')],
                        '36':[dict(code='3',name='고성군')]},
        places=[dict(contentid=id,title=title,contenttypeid=type,areacode=area,sigungucode=city,mapy=str(lat),mapx=str(lon))
                for id,title,type,area,city,lat,lon in [
                    ('2773046','사천진항','12','32','1',37.84,128.87),
                    ('2','문화시설','14','32','1',37.841,128.871),
                    ('3','다른 관광지','12','32','1',37.842,128.872),
                    ('4','식당','39','32','1',37.841,128.871),
                    ('5','동명 군 강원','12','32','2',38.3,128.4),
                    ('2652453','동명 군 경남','12','36','3',34.9,128.4)]],
        marine={'seatrip':dict(source='official',rows=[dict(sareaDtlNm=area,predcYmd=date,predcNoonSeCd=period,totalIndex=grade,
                                               lat=lat,lot=lon)
                    for area,grade,lat,lon in [('강릉','나쁨',37.76,128.96),('인천내륙','좋음',37.46,126.58),('인천북서','좋음',37.95,124.66)]
                    for period in ['오전','오후']])})
    c['places'][3]['cat3']='A05020100'
    monkeypatch.setattr(providers,'catalog',lambda:c)
    monkeypatch.setattr(providers,'weather_for_place',lambda *a:dict(status='no_forecast'))
    monkeypatch.setattr(enrichment,'road_route',lambda *a,**kw:dict(status='available',duration_s=60,distance_m=100))
    monkeypatch.setattr(enrichment,'photo_for',lambda *a:dict(status='unavailable'))
    monkeypatch.setattr(enrichment,'food_details',lambda *a:dict(status='unavailable'))
    return c,date


def test_administrative_join_does_not_mix_same_county_names(national):
    c,_=national
    ids={p['id'] for p in planner.tourism_candidates('고성')}
    assert ids=={'2652453'}
    assert not planner.in_region(37.4,126.7,'unknown')
    assert not regions.matches(dict(c['places'][0],sigungucode='2'),'강릉',c)
    assert planner.coords(dict(mapy='nan',mapx='128')) is None
    assert planner.coords(dict(mapy='0',mapx='0')) is None


def test_national_defaults_and_offshore_gate(national):
    _,date=national
    assert planner.Trip(region='강릉',start_date=date).activity=='seatrip'
    assert planner.Trip(start_date=date).activity=='mudflat'
    with pytest.raises(ValidationError):planner.Trip(region='강릉',activity='mudflat',start_date=date)
    assert planner.Trip(region='인천북서',start_date=date).region=='인천북서'
    with pytest.raises(ValidationError):planner.Trip(region='없는 지역',start_date=date)


def test_exact_forecast_name_and_feed_freshness(national):
    c,date=national
    result=planner.marine_conditions('강릉','seatrip',date)
    assert {r['sareaDtlNm'] for r in result['rows']}=={'강릉'}
    assert travel.sea_outlook('강릉',date,'09:00','18:00')['grade']=='나쁨'
    c['marine']['seatrip']['collected_at']=(dt.datetime.now(providers.KST)-dt.timedelta(days=1)).isoformat()
    assert travel.sea_outlook('강릉',date,'09:00','18:00')['grade'] is None
    assert planner.marine_conditions('강릉','seatrip',date)['status']=='stale'


def test_daily_source_outlook_is_not_missing_half_day(national):
    c,date=national
    day=(dt.date.fromisoformat(date)+dt.timedelta(days=2)).isoformat()
    c['marine']['seatrip']['rows'].append(dict(sareaDtlNm='강릉',predcYmd=day,predcNoonSeCd='일',totalIndex='나쁨'))
    value=travel.sea_outlook('강릉',day,'09:00','18:00')
    assert value['status']=='available' and value['grade']=='나쁨'
    assert value['temporal_resolution']=='daily' and len(value['rows'])==1
    assert '오전·오후 구분 없음' in value['aggregation']
    assert travel.sea_outlook('강릉',day,'15:00','17:00')['temporal_resolution']=='daily'
    overview=regions.overview(day)
    assert next(r for r in overview['regions'] if r['id']=='강릉')['outlook']['grade']=='나쁨'
    assert next(r for r in overview['regions'] if r['id']=='속초')['outlook']['grade'] is None


def test_bad_sea_index_prioritizes_culture_without_boat_slots(national):
    _,date=national
    plan=planner.build_plan(dict(region='강릉',start_date=date,days=1,visits_per_day=1,cafes=False))
    day=plan['days'][0]
    assert next(i for i in day['items'] if i['kind']=='tourism')['id']=='2'
    assert day['search_reference']['id']=='2773046'
    assert day['travel_index']['area']=='강릉'
    assert any('문화시설' in w for w in day['warnings'])
    assert not any(i['kind'] in ('marine','ferry') for i in day['items'])


def test_unknown_road_access_is_not_a_national_visit(national,monkeypatch):
    _,date=national
    store=plans.PlanStore()
    original=store.register(planner.build_plan(dict(region='강릉',start_date=date,days=1,visits_per_day=1,cafes=False)))
    slot=next(i for i in original['days'][0]['items'] if i['kind']=='tourism')
    monkeypatch.setattr(enrichment,'road_route',lambda *a,**kw:dict(status='unsupported_ferry'))
    plan=planner.build_plan(dict(region='강릉',start_date=date,days=1))
    assert plan['days'][0]['actual_visits']==0
    assert plan['days'][0]['warnings']
    with pytest.raises(plans.PlanError):store.replace(original['plan_id'],1,slot['slot_id'],'3')
    assert store.get(original['plan_id'],1)==original


def test_region_api_exposes_all_outlooks_but_gates_unloaded_tourism(national):
    _,date=national
    response=TestClient(app).get('/api/regions',params=dict(date=date))
    assert response.status_code==200
    result=response.json()
    assert len(result['regions'])==29
    by_id={r['id']:r for r in result['regions']}
    assert by_id['강릉']['planning_enabled']
    assert not by_id['부산북동']['planning_enabled']
    assert not by_id['인천북서']['planning_enabled'] and by_id['인천북서']['outlook']['grade']=='좋음'
    assert TestClient(app).get('/api/places',params=dict(region='bogus')).status_code==422
    assert TestClient(app).get('/api/regions',params=dict(date='bad')).status_code==422
    future=(dt.date.fromisoformat(date)+dt.timedelta(days=30)).isoformat()
    missing=regions.overview(future)
    assert all(r['outlook']['grade'] is None for r in missing['regions'])


def test_coastal_collection_is_atomic_and_preserves_old_feed_dates(monkeypatch,tmp_path):
    target=tmp_path/'catalog.json'
    old_date=(dt.datetime.now(providers.KST)-dt.timedelta(days=1)).isoformat()
    target.write_text(json.dumps(dict(collected_at=old_date,marine={'mudflat':dict(rows=[],source='old')})),encoding='utf-8')
    monkeypatch.setattr(providers,'CATALOG',target)
    monkeypatch.setattr(providers,'DATA',tmp_path)
    monkeypatch.setattr(regions,'AREA_NAMES',{'2':'인천','32':'강원'})
    monkeypatch.setattr(providers,'service',lambda *a:dict(endpoint='https://example.invalid/KorService2',key='synthetic-key'))
    monkeypatch.setattr(providers,'marine_schema',lambda *a:(dict(host='example.invalid',paths={'/seatrip':{}}),'official'))
    batches=iter([[dict(code='2',name='인천'),dict(code='32',name='강원')],[],[dict(contentid='1')],
                  [dict(code='1',name='강릉시')],[dict(contentid='2')],[dict(sareaDtlNm='강릉')]])
    monkeypatch.setattr(providers,'fetch_pages',lambda *a,**kw:next(batches))
    providers.sync_catalog(scope='coastal')
    value=json.loads(target.read_text(encoding='utf-8'))
    assert len(value['places'])==2 and value['scope']=='coastal'
    assert value['marine']['mudflat']['collected_at']==old_date
    assert value['marine']['seatrip']['collected_at']!=old_date
    original=target.read_bytes()
    monkeypatch.setattr(providers,'fetch_pages',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('failed')))
    with pytest.raises(RuntimeError):providers.sync_catalog(scope='coastal')
    assert target.read_bytes()==original
