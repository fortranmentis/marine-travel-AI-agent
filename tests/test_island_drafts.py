import copy
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from marine_agent import island_drafts as drafts, providers, planner, enrichment, regions, plans, browser_ferries
from marine_agent.app import app
from marine_agent import travel


@pytest.fixture
def coastal_islands(monkeypatch):
    today=dt.datetime.now(providers.KST).date().isoformat()
    rows=[]
    for n,(region,profile) in enumerate(drafts.PROFILES.items()):
        for i,identity in enumerate(dict.fromkeys(profile['ids'])):
            rows.append(dict(contentid=identity,title=profile['title']+str(i),contenttypeid='12',
                areacode=regions.get(region)['area_code'],mapy=str(35+n*.1+i*.001),mapx=str(126+i*.001)))
    data=dict(collected_at=dt.datetime.now(providers.KST).isoformat(),places=rows,tourism_source='TourAPI',
        marine={'seatrip':dict(rows=[dict(sareaDtlNm=r,predcYmd=today,predcNoonSeCd=p,totalIndex='좋음')
            for r in drafts.PROFILES for p in ('오전','오후')])})
    monkeypatch.setattr(providers,'catalog',lambda:data)
    monkeypatch.setattr(providers,'weather_for_place',lambda *a:dict(status='no_forecast'))
    monkeypatch.setattr(enrichment,'road_route',lambda *a,**k:dict(status='available',duration_s=120,distance_m=100))
    monkeypatch.setattr(enrichment,'photo_for',lambda *a:dict(status='unavailable'))
    monkeypatch.setattr(browser_ferries,'live',lambda *a:dict(status='unavailable',rows=[],reason='offline fixture'))
    return today,data


@pytest.mark.parametrize('region',list(drafts.PROFILES))
def test_five_scopes_generate_only_their_exact_island_visits(coastal_islands,region):
    today,_=coastal_islands
    profile=drafts.PROFILES[region]
    result=planner.build_plan(dict(region=region,start_date=today,days=1,activity='seatrip',cafes=False))
    assert result['days'][0]['actual_visits']>=1
    visits=[i for d in result['days'] for i in d['items'] if i['kind']=='tourism']
    assert all(i['id'] in profile['ids'] for i in visits)
    assert result['days'][0]['travel_index']['area']==region
    assert result['island_access']['island']==profile['title']
    assert not any(i['kind']=='ferry' for d in result['days'] for i in d['items'])
    assert result['status']==('conditional_island' if profile['access']=='ferry' else 'provisional')
    assert planner.validate_schedule(result['days'])
    rows=regions.overview(today)['regions']
    assert next(r for r in rows if r['id']==region)['planning_enabled']


def test_future_ferry_never_reuses_today_and_normal_does_not_confirm_roundtrip(monkeypatch):
    today=dt.datetime.now(providers.KST).date();calls=[]
    rows=[dict(licensed_route=route,origin=port,arrival=None,operation='正常') for route,port in
          [('인천-덕적','인천'),('인천-덕적','덕적'),('인천-백령','인천')]]
    monkeypatch.setattr(browser_ferries,'live',lambda *a:(calls.append(a) or dict(status='available',rows=copy.deepcopy(rows),as_of='source')))
    value=drafts.access_info('인천남서',today.isoformat())
    assert len(value['rows'])==2 and not value['roundtrip_verified'] and not value['arrival_verified']
    assert value['status']=='unconfirmed'
    future=drafts.access_info('인천남서',(today+dt.timedelta(days=1)).isoformat())
    assert future['rows']==[] and future['operation_status']=='date_unsupported' and len(calls)==1
    assert drafts.access_info('신안북동',today.isoformat())['mode']=='bridge' and len(calls)==1


def test_island_api_keeps_unknown_access_and_pdf_warning(coastal_islands,monkeypatch):
    today,_=coastal_islands
    monkeypatch.setattr(plans,'store',plans.PlanStore())
    result=TestClient(app).post('/api/plan',json=dict(region='인천남서',start_date=today,days=1,activity='none',cafes=False))
    assert result.status_code==200
    value=result.json();assert value['status']=='conditional_island'
    assert not value['island_access']['mainland_access_verified']
    assert value['island_access']['operation_status']=='unavailable'
    assert value['routes'] and any('왕복 배편 미확정' in w for w in value['days'][0]['warnings'])


def test_other_islands_fixed_visits_and_replacement_cannot_leak(coastal_islands,monkeypatch):
    today,_=coastal_islands
    with pytest.raises(ValueError,match='고정 방문'):
        planner.build_plan(dict(region='인천남서',start_date=today,days=1,
            locked=[dict(date=today,start='10:00',end='11:30',title='백령',id='1932853')]))
    store=plans.PlanStore();value=store.register(planner.build_plan(dict(region='인천남서',start_date=today,days=1,visits_per_day=1)))
    slot=next(i for i in value['days'][0]['items'] if i['kind']=='tourism')
    with pytest.raises(plans.PlanError):store.replace(value['plan_id'],1,slot['slot_id'],'1932853')
    assert store.get(value['plan_id'],1)==value
    alternative=value['days'][0]['alternatives'][0]
    changed=store.replace(value['plan_id'],1,slot['slot_id'],alternative['id'])
    assert changed['revision']==2 and changed['island_access']==value['island_access']
    assert store.undo(value['plan_id'],2)['island_access']==value['island_access']


def test_nearby_unmapped_food_and_other_island_attractions_do_not_join(coastal_islands):
    today,data=coastal_islands
    reference=next(p for p in data['places'] if p['contentid']=='780350')
    data['places'].append(dict(reference,contentid='999999',title='다른 섬 식당',contenttypeid='39',cat3='A05020100'))
    assert travel.food_candidates('인천남서')==[]
    candidates=planner.tourism_candidates('인천남서')
    assert {r['id'] for r in candidates}==set(drafts.PROFILES['인천남서']['ids'])
