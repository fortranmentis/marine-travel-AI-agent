import json

import pytest
from fastapi.testclient import TestClient

from marine_agent import browser_transit as bt, mobility, enrichment, planner, plans, progress
from marine_agent.browser_transit_worker import normalize, minutes
from test_core import snapshot

A = dict(lat=37.47636, lon=126.61694, title='인천역')
B = dict(lat=37.4739, lon=126.6008, title='월미공원')
URL = bt.route_url(A, B)


def bus_card():
    return dict(duration='12분', fare='1,500원', time_label='오전 10:05 도착',
        timeline=['도보1분', '간선버스5분', '도보6분'], later=False, unsupported=False,
        steps=[dict(station='인천역(차이나타운)', label='간선', lines=['2', '10']),
               dict(station='GS칼텍스', label='하차', lines=[])])


def test_screen_bus_and_subway_transfer_normalization():
    card = bus_card()
    result = normalize([card], URL, '2026-10-16T09:51:00+09:00')
    assert result['duration_s'] == 720 and result['walking_minutes'] == 7
    assert result['sections'][1]['start'] == '인천역(차이나타운)'
    assert result['sections'][1]['end'] == 'GS칼텍스'
    assert result['sections'][1]['lines'] == ['2', '10']
    assert result['fare'] == 1500 and result['distance_m'] is None
    assert result['geometry'] is None and not result['schedule_verified']
    card.update(duration='38분', fare='', timeline=['도보6분', '수도권4호선7분', '도보2분', '수도권2호선21분'],
        steps=[dict(station=s, label=l) for s,l in [('서울역','4호선'),('동대문역사문화공원역','2호선'),('잠실역','하차')]])
    result = normalize([card], URL)
    assert result['status'] == 'available' and result['transfers'] == 1
    assert result['sections'][1]['lines'] == ['4호선'] and result['fare'] is None


@pytest.mark.parametrize('updates', [dict(later=True), dict(unsupported=True), dict(duration='0분'),
    dict(duration='nan'), dict(timeline=['도보12분']), dict(timeline=['여객선12분']),
    dict(timeline=['간선버스700분']), dict(steps=[]), dict(steps=[dict(station='')])])
def test_incomplete_later_and_unsupported_routes_fail_closed(updates):
    card = bus_card(); card.update(updates)
    assert normalize([card], URL)['status'] == 'unavailable'


def test_duration_units_and_invalid_values():
    assert minutes('1시간 12분') == 72 and minutes('2시간') == 120
    for value in ('', '12', '-1분', '25시간', '미확인', '약12분'):
        with pytest.raises(ValueError): minutes(value)


@pytest.fixture
def isolated(monkeypatch):
    bt._cache.clear()
    monkeypatch.setenv('TRANSIT_PROVIDER', 'playwright')
    calls = []
    monkeypatch.setattr(bt, 'run_worker', lambda a,b,t: (calls.append((a,b,t)) or normalize([bus_card()], bt.route_url(a,b))))
    monkeypatch.setattr(mobility.httpx, 'Client', lambda *a,**kw: pytest.fail('No transit API call is allowed'))
    yield calls
    bt._cache.clear()


def test_browser_is_default_and_no_transit_api_fallback(isolated, monkeypatch):
    monkeypatch.delenv('TRANSIT_PROVIDER')
    assert mobility.transit_provider() == 'playwright'
    assert mobility.transit_route(A,B)['status'] == 'available'
    assert len(isolated) == 1
    bt._cache.clear()
    monkeypatch.setattr(bt, 'run_worker', lambda *a: (_ for _ in ()).throw(RuntimeError('secret-provider-error')))
    result = mobility.transit_route(A,B)
    assert result['status'] == 'unavailable' and 'secret-provider-error' not in json.dumps(result)


def test_cache_is_directional_bounded_and_future_time_is_not_applied(isolated):
    first = bt.route(A,B,'2026-10-17T12:00:00+09:00')
    second = bt.route(A,B,'2026-10-18T12:00:00+09:00')
    assert not first['cached'] and second['cached'] and len(isolated) == 1
    assert first['requested_departure_at'] != second['requested_departure_at']
    assert not second['departure_time_applied'] and not second['schedule_verified']
    second['sections'][0]['mode'] = 'tampered'
    assert bt.route(A,B)['sections'][0]['mode'] == 'walk'
    bt.route(B,A)
    assert len(isolated) == 2


def test_request_budget_and_deadline_preserve_explicit_failures(isolated):
    @bt.budgeted
    def many():
        return [bt.route(A, dict(B, title=f'장소{i}')) for i in range(8)]
    results = many()
    assert len(isolated) == 6 and all(r['status'] == 'unavailable' for r in results[6:])
    bt._cache.clear()
    token = bt._budget.set(dict(remaining=6, deadline=0))
    try:
        assert bt.route(A,B)['status'] == 'unavailable'
        assert len(isolated) == 6
    finally:
        bt._budget.reset(token)


def test_coordinate_validation_never_launches_browser(isolated):
    for invalid in ({},dict(A,lat=float('nan')),dict(A,lon=0),dict(A,lat=95)):
        assert bt.route(invalid,B)['status'] == 'unavailable'
    assert isolated == []
    assert '%2F' in bt.route_url(dict(A,title='장소/이름'),B)


def test_route_api_and_date_context(isolated):
    from marine_agent.app import app
    client = TestClient(app)
    response = client.post('/api/transit/route',json=dict(origin=A,destination=B,departure_at='2026-10-18T12:00:00+09:00'))
    assert response.status_code == 200 and not response.json()['departure_time_applied']
    assert client.post('/api/transit/route',json=dict(origin=dict(A,lat=0),destination=B)).status_code == 422
    day = dict(date='2026-10-18',transport='transit',items=[dict(A,slot_id='a',kind='tourism',start='10:00',end='11:00'),
        dict(B,slot_id='b',kind='tourism',start='11:05',end='12:00')])
    result = enrichment.day_route(day)
    assert not result['distance_complete'] and result['total_distance_m'] == 0
    assert result['legs'][0]['requested_departure_at'] == '2026-10-18T11:00:00+09:00'
    assert not result['legs'][0]['fits_schedule']


def test_browser_failures_keep_a_provisional_draft(snapshot, isolated, monkeypatch):
    _, date = snapshot
    monkeypatch.setattr(bt,'run_worker',lambda *a:bt.failure('synthetic unavailable'))
    monkeypatch.setattr(enrichment,'road_route',lambda *a,**kw:dict(status='unavailable'))
    store=plans.PlanStore()
    result=store.register(planner.build_plan(dict(start_date=date,days=1,activity='none',transport='transit')))
    day=result['days'][0]
    assert day['actual_visits'] == 1 and day['warnings']
    assert any('출발시각' in w for w in day['warnings'])


def test_failed_browser_route_preserves_revision_on_replacement(snapshot, isolated, monkeypatch):
    _, date = snapshot
    draft=planner.build_plan(dict(start_date=date,days=1,activity='none',transport='car'))
    draft['trip']['transport']='transit'
    for day in draft['days']: day['transport']='transit'
    monkeypatch.setattr(bt,'run_worker',lambda *a:bt.failure('synthetic unavailable'))
    monkeypatch.setattr(enrichment,'road_route',lambda *a,**kw:dict(status='unavailable'))
    store=plans.PlanStore(); result=store.register(draft)
    day=result['days'][0]
    slot=next(i for i in day['items'] if i['kind']=='tourism')
    with pytest.raises(plans.PlanError,match='인접 이동 경로'):
        store.replace(result['plan_id'],1,slot['slot_id'],day['alternatives'][0]['id'])
    assert store.get(result['plan_id'],1)==result


def test_short_transit_leg_uses_explicit_walking_graph_before_browser(isolated, monkeypatch):
    modes=[]
    monkeypatch.setattr(enrichment,'road_route',lambda a,b,mode=None:(modes.append(mode) or dict(status='available',duration_s=300,distance_m=400)))
    result=mobility.route_between(A,dict(A,lat=A['lat']+0.001),'transit')
    assert result['mode']=='walk' and modes==['walk'] and isolated==[]
    monkeypatch.setattr(enrichment,'road_route',lambda *a,**kw:dict(status='unavailable'))
    assert mobility.route_between(A,A,'transit')['status']=='unavailable'
    assert isolated==[]


def test_browser_progress_precedes_result(isolated):
    events=[]
    with progress.reporting(events.append):
        result=bt.route(A,B)
    assert events and '대중교통' in events[0]['message'] and result['status']=='available'
