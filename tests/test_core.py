import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from marine_agent import planner, providers, agent
from marine_agent.app import app


@pytest.fixture
def snapshot(monkeypatch):
    today = dt.datetime.now(providers.KST).date()
    date = (today + dt.timedelta(days=1)).isoformat()
    data = dict(collected_at=dt.datetime.now(providers.KST).isoformat(), tourism_source='test-source',
                places=[dict(contentid=str(i), title=f'관광지{i}', contenttypeid='14',
                             mapy='37.43', mapx='126.42', addr1='인천 중구') for i in range(4)],
                marine={'mudflat': dict(source='test-marine', rows=[dict(mdftExpcnVlgNm='테스트마을',
                    predcYmd=date, lat=37.43, lot=126.42, totalIndex='좋음', mdftExprnBgngTm='14:00', mdftExprnEndTm='17:00')])})
    monkeypatch.setattr(providers, 'catalog', lambda: data)
    monkeypatch.setattr(providers, 'weather_for_place', lambda *a: dict(status='no_forecast', forecasts={}))
    return data, date


def test_marine_window_and_no_overlap(snapshot):
    _, date = snapshot
    plan = planner.build_plan(dict(start_date=date, child_ages=[6]))
    assert plan['marine_scheduled']
    marine = next(i for i in plan['days'][0]['items'] if i['kind'] == 'marine')
    assert '14:00' <= marine['start'] < marine['end'] <= '17:00'
    assert planner.validate_schedule(plan['days'])
    assert plan['status'] == 'provisional'


@pytest.mark.parametrize('index,closed', [('나쁨', False), ('보통', False), (None, False), ('좋음', True)])
def test_bad_unknown_closed_never_scheduled(snapshot, index, closed):
    data, date = snapshot
    row = data['marine']['mudflat']['rows'][0]
    row['totalIndex'] = index
    if closed:
        row['opnStat'] = '폐장'
    assert not planner.build_plan(dict(start_date=date))['marine_scheduled']


def test_no_forecast_not_favorable(snapshot):
    _, date = snapshot
    plan = planner.build_plan(dict(start_date=(dt.date.fromisoformat(date) + dt.timedelta(days=20)).isoformat()))
    assert not plan['marine_scheduled']
    assert plan['days'][0]['marine']['status'] == 'no_forecast'


def test_fixed_reservation_and_exclusion(snapshot):
    _, date = snapshot
    locked = dict(date=date, start='14:00', end='17:00', title='예약한 일정')
    plan = planner.build_plan(dict(start_date=date, locked=[locked], excluded_ids=['0']))
    assert any(i['title'] == locked['title'] and i['start'] == '14:00' for i in plan['days'][0]['items'])
    assert not any(i.get('id') == '0' for day in plan['days'] for i in day['items'])
    assert not plan['marine_scheduled']


def test_invalid_fixed_reservations(snapshot):
    _, date = snapshot
    lock = dict(date=date, start='14:00', end='15:00', title='예약')
    with pytest.raises(ValidationError):
        planner.Trip(start_date=date, locked=[lock, lock])


def test_partial_page_rejected(monkeypatch):
    responses = iter([{'response': {'header': {'resultCode': '00'}, 'body': {'totalCount': 2, 'items': {'item': [{'id':'1'}]}}}},
                      {'response': {'header': {'resultCode': '00'}, 'body': {'totalCount': 2, 'items': {}}}}])
    monkeypatch.setattr(providers, 'get', lambda *a: json.dumps(next(responses)))
    with pytest.raises(RuntimeError, match='Incomplete'):
        providers.fetch_pages('https://example.com', {})


def test_duplicate_page_rejected(monkeypatch):
    value = {'response': {'header': {'resultCode':'00'}, 'body': {'totalCount':3, 'items': {'item':[{'id':'1'}]}}}}
    monkeypatch.setattr(providers, 'get', lambda *a: json.dumps(value))
    with pytest.raises(RuntimeError, match='Repeated'):
        providers.fetch_pages('https://example.com', {})


def test_failed_sync_preserves_snapshot(snapshot, monkeypatch, tmp_path):
    target = tmp_path / 'catalog.json'
    target.write_text('original')
    monkeypatch.setattr(providers, 'CATALOG', target)
    monkeypatch.setattr(providers, 'DATA', tmp_path)
    monkeypatch.setattr(providers, 'service', lambda *a: {'endpoint':'https://example.com','key':'test'})
    batches = iter([[{'name':'인천','code':'2'}], [{'contentid':'1'}]])
    monkeypatch.setattr(providers, 'fetch_pages', lambda *a, **k: next(batches))
    monkeypatch.setattr(providers, 'marine_schema', lambda *a: (_ for _ in ()).throw(RuntimeError('unavailable')))
    with pytest.raises(RuntimeError, match='incomplete'):
        providers.sync_catalog()
    assert target.read_text() == 'original'


def test_grid_reference():
    assert providers.weather_grid(37.579871, 126.989352) == (60, 127)


def test_api_validation_and_render(snapshot):
    _, date = snapshot
    client = TestClient(app)
    assert client.get('/').status_code == 200
    assert client.post('/api/plan', json={'start_date':date,'days':9}).status_code == 422
    assert client.post('/api/plan', json={'start_date':date,'child_ages':[6]}).json()['status'] == 'provisional'


def test_agent_rejects_unknown_tool_and_recovers(snapshot, monkeypatch):
    replies = iter([{'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'run_shell','arguments':{'cmd':'bad'}}}]}},
                    {'message':{'role':'assistant','content':'확인 필요'}}])
    class Response:
        def raise_for_status(self): pass
        def json(self): return next(replies)
    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, *a, **k): return Response()
    monkeypatch.setattr(agent.httpx, 'Client', Client)
    result = agent.chat('도구 검사')
    assert result['trace'] == [{'tool':'run_shell','status':'rejected'}]


def test_agent_failure_returns_rule_draft(snapshot, monkeypatch):
    _, date = snapshot
    def unavailable(*a, **k): raise RuntimeError('down')
    monkeypatch.setattr(agent.httpx, 'Client', unavailable)
    result = agent.chat('일정', trip=planner.Trip(start_date=date))
    assert result['status'] == 'degraded'
    assert result['plan']['status'] == 'provisional'


def test_lunch_shifts_marine_slot_instead_of_dropping_it(snapshot):
    data, date = snapshot
    row = data['marine']['mudflat']['rows'][0]
    row.update(mdftExprnBgngTm='12:10', mdftExprnEndTm='15:10')
    plan = planner.build_plan(dict(start_date=date))
    slot = next(i for i in plan['days'][0]['items'] if i['kind'] == 'marine')
    assert slot['start'] == '13:30'
    assert slot['end'] == '14:30'


def test_short_marine_window_and_day_bounds(snapshot):
    data, date = snapshot
    data['marine']['mudflat']['rows'][0].update(mdftExprnBgngTm='14:00', mdftExprnEndTm='14:50')
    plan = planner.build_plan(dict(start_date=date, day_start='10:00', day_end='15:00'))
    assert not plan['marine_scheduled']
    assert all('10:00' <= i['start'] < i['end'] <= '15:00' for d in plan['days'] for i in d['items'])


def test_rain_prevents_marine_slot(snapshot, monkeypatch):
    _, date = snapshot
    monkeypatch.setattr(providers, 'weather_for_place', lambda *a: dict(status='available', forecasts={'1500':{'PTY':'1','WSD':'2'}}))
    assert not planner.build_plan(dict(start_date=date))['marine_scheduled']


def test_stale_snapshot_is_rejected(snapshot):
    data, date = snapshot
    data['collected_at'] = (dt.datetime.now(providers.KST) - dt.timedelta(days=2)).isoformat()
    with pytest.raises(ValueError, match='24시간'):
        planner.build_plan(dict(start_date=date))


def test_chat_preserves_trusted_locks(snapshot, monkeypatch):
    _, date = snapshot
    trip = planner.Trip(start_date=date)
    replies = iter([{'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'build_itinerary','arguments':trip.model_dump(mode='json')}}]}},
                    {'message':{'role':'assistant','content':'초안입니다.'}}])
    class Response:
        def raise_for_status(self): pass
        def json(self): return next(replies)
    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, *a, **k): return Response()
    monkeypatch.setattr(agent.httpx, 'Client', Client)
    lock = planner.Lock(date=date, start='14:00', end='17:00', title='고정 예약')
    result = agent.chat('관광지를 바꿔줘', locked=[lock], excluded_ids=['0'])
    assert result['plan']['trip']['locked'][0]['title'] == '고정 예약'
    assert '0' in result['plan']['trip']['excluded_ids']


def test_weather_failure_does_not_claim_forecast(snapshot, monkeypatch):
    _, date = snapshot
    def unavailable(*a): raise RuntimeError('unavailable')
    monkeypatch.setattr(providers, 'weather_for_place', unavailable)
    plan = planner.build_plan(dict(start_date=date))
    assert plan['days'][0]['weather']['status'] == 'unavailable'
    assert plan['status'] == 'provisional'


def test_locked_place_is_not_scheduled_twice(snapshot):
    _, date = snapshot
    plan = planner.build_plan(dict(start_date=date, locked=[dict(date=date, start='10:00', end='11:30', title='관광지0')]))
    items = [item for day in plan['days'] for item in day['items']]
    assert sum(item['title'] == '관광지0' for item in items) == 1
    assert not any(item.get('id') == '0' for item in items)
