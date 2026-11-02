"""Executable scenario contract; all forecasts, reviews and routes are synthetic."""
import datetime as dt
import json
from pathlib import Path

import pytest
from marine_agent import planner, providers, rules, mobility, plans, enrichment, travel
from test_core import snapshot
from test_v02 import draft
from test_v03 import manifest

SCENARIOS = json.loads((Path(__file__).parents[1]/'docs/planning-scenarios.json').read_text(encoding='utf-8'))


def review(id,date,environment='indoor',**extra):
    return dict(id=id,environment=environment,source_url='https://example.org/venue',
                checked_at=dt.datetime.now(providers.KST).isoformat(),valid_until=date,**extra)


def forecast(date, wet_from=24, **override):
    return dict(status='available',date=date,issue_at=dt.datetime.now(providers.KST).isoformat(),
                forecasts={f'{h:02d}00':dict(PTY='1' if h>=wet_from else '0',POP='90' if h>=wet_from else '0',WSD='2',**override) for h in range(24)})


@pytest.mark.parametrize('scenario',SCENARIOS,ids=lambda s:s['id'])
def test_scenario_contract(scenario,snapshot):
    _,date=snapshot
    value=scenario['input']; fact=value['review']; extra={k:v for k,v in fact.items() if k not in ('closed','hours')}
    if fact.get('closed'):extra['closed_dates']=[date]
    if 'hours' in fact:extra['hours']={date:fact['hours']}
    trip=planner.Trip(start_date=date,activity='none',**value['trip']) if 'activity' not in value['trip'] else planner.Trip(start_date=date,**value['trip'])
    weather=dict(status='available',forecasts={f'{h:02d}00':value['weather'] for h in range(24)})
    result=rules.assess({'id':'0'},trip,date,*value['time'],weather,{'0':review('0',date,value['environment'],**extra)})
    assert result['allowed']==scenario['expected']['allowed']
    assert result['codes']==scenario['expected']['codes']
    if value['weather'].get('POP')=='80':assert result['rank']==(0 if value['environment']=='indoor' else 1)
    if not value['weather']:assert not result['weather']['complete']


@pytest.fixture
def policy_world(snapshot,monkeypatch):
    _,date=snapshot
    facts={str(i):review(str(i),date,'outdoor' if i==0 else 'indoor') for i in range(4)}
    monkeypatch.setattr(rules,'reviewed_venues',lambda:facts)
    monkeypatch.setattr(mobility,'route_between',lambda *a,**kw:dict(status='available',duration_s=60,distance_m=100))
    monkeypatch.setattr(providers,'weather_for_place',lambda *a:forecast(date,13))
    return date,facts


def tourism(day):return [i for i in day['items'] if i['kind']=='tourism']
def codes(day):return {d['code'] for d in day['rule_summary']['decisions']}


def test_morning_outdoor_afternoon_indoor(policy_world):
    date,_=policy_world
    day=planner.build_plan(dict(start_date=date,days=1,activity='none',transport='walk'))['days'][0]
    visits=tourism(day)
    assert visits[0]['id']=='0' and visits[0]['end']<='12:00'
    assert len(visits)==2 and visits[1]['start']>='13:00'
    assert visits[1]['rule_evidence']['environment']=='indoor'
    assert 'rain' in codes(day) and day['transport']=='walk'


def test_no_indoor_does_not_invent_or_fill(policy_world,monkeypatch):
    date,facts=policy_world
    facts.clear()
    monkeypatch.setattr(providers,'weather_for_place',lambda *a:forecast(date,0))
    day=planner.build_plan(dict(start_date=date,days=1,activity='none',visits_per_day=5))['days'][0]
    assert not tourism(day) and day['actual_visits']==0
    assert 'rain_indoor_required' in codes(day)
    assert any(i['kind']=='break' for i in day['items'])
    assert any('5곳 중 0곳' in w for w in day['warnings'])


def test_locked_rain_closed_reservation_preserved(policy_world):
    date,facts=policy_world
    facts['0']['closed_dates']=[date]
    day=planner.build_plan(dict(start_date=date,days=1,activity='none',locked=[dict(date=date,start='14:00',end='15:00',title='관광지0',id='0')]))['days'][0]
    lock=next(i for i in day['items'] if i['kind']=='locked')
    assert (lock['id'],lock['start'],lock['end'])==('0','14:00','15:00')
    assert 'locked_conflict' in codes(day)


@pytest.mark.parametrize('mode',['walk','car'])
def test_unavailable_and_too_long_route_reduce_visits(policy_world,monkeypatch,mode):
    date,_=policy_world
    for route,code in [(dict(status='unavailable'),'route_unavailable'),(dict(status='available',duration_s=999999,distance_m=100),'route_time')]:
        monkeypatch.setattr(mobility,'route_between',lambda *a,**kw:route)
        day=planner.build_plan(dict(start_date=date,days=1,activity='none',transport=mode,visits_per_day=5))['days'][0]
        assert len(tourism(day))<=1 and code in codes(day)


def test_walk_rain_budget_and_no_implicit_transport_switch(policy_world,monkeypatch):
    date,_=policy_world
    monkeypatch.setattr(providers,'weather_for_place',lambda *a:forecast(date,0))
    monkeypatch.setattr(mobility,'route_between',lambda *a,**kw:dict(status='available',duration_s=120,distance_m=900))
    day=planner.build_plan(dict(start_date=date,days=1,activity='none',transport='walk',visits_per_day=5))['days'][0]
    assert len(tourism(day))==1 and 'walk_budget' in codes(day) and day['transport']=='walk'


def test_child_rest_group_and_short_day(policy_world):
    date,_=policy_world
    day=planner.build_plan(dict(start_date=date,days=1,activity='none',child_ages=[3,8],visits_per_day=6,day_start='10:00',day_end='15:00'))['days'][0]
    assert all(planner.minutes(i['end'])-planner.minutes(i['start'])==60 for i in tourism(day))
    assert any(i['kind']=='rest' and planner.minutes(i['end'])-planner.minutes(i['start'])==30 for i in day['items'])
    assert 'child_rest' in codes(day) and 'child_checks' in codes(day) and day['actual_visits']<6
    assert all('10:00'<=i['start']<i['end']<='15:00' for i in day['items'])
    assert planner.validate_schedule([day])
    group=planner.build_plan(dict(start_date=date,days=1,activity='none',party_type='group',adults=10))['days'][0]
    assert 'group_buffer' in codes(group)


def test_stale_and_partial_weather_not_sunny(policy_world,monkeypatch):
    date,_=policy_world
    wx=forecast(date,0);wx['issue_at']=(dt.datetime.now(providers.KST)-dt.timedelta(days=2)).isoformat()
    assert rules.weather_window(wx,540,1080)['status']=='unknown'
    monkeypatch.setattr(providers,'weather_for_place',lambda *a:wx)
    day=planner.build_plan(dict(start_date=date,days=1,activity='none'))['days'][0]
    assert 'weather_incomplete' in codes(day)
    assert 'rain' not in codes(day)
    assert rules.weather_window(dict(status='available',forecasts={'1000':{'PTY':'0'}}),570,690)['complete'] is False


def test_hour_interval_boundary_and_invalid_values():
    wx=dict(status='available',forecasts={'1000':{'PTY':'1'},'1100':{'PTY':'0'},'bad':{}})
    assert rules.weather_window(wx,630,660)['rain']
    assert not rules.weather_window(wx,660,690)['rain']
    assert rules.number('NaN') is None and rules.number(-999) is None


def test_review_provenance_expiry_bad_hours_and_auth_url(snapshot,monkeypatch,tmp_path):
    _,date=snapshot;monkeypatch.setattr(rules,'DATA',tmp_path)
    path=tmp_path/'reviewed_venues.json'
    fact=review('0',date)
    path.write_text(json.dumps([fact]),encoding='utf-8')
    assert '0' in rules.reviewed_venues()
    for extra in [dict(source_url='https://example.org/?key=secret'),dict(hours={date:[['12:99','15:00']]}),dict(checked_at='2000-01-01T00:00:00+09:00')]:
        path.write_text(json.dumps([dict(fact,**extra)]),encoding='utf-8')
        assert rules.reviewed_venues()=={}


def test_food_closed_keeps_lunch_and_optional_cafe_does_not_overfill(policy_world,monkeypatch):
    date,facts=policy_world
    facts['99']=review('99',date,closed_dates=[date])
    candidate=dict(id='99',title='식당',lat=37.43,lon=126.42)
    monkeypatch.setattr(travel,'food_candidates',lambda *a,**kw:[candidate])
    day=planner.build_plan(dict(start_date=date,days=1,activity='none',cafes=True))['days'][0]
    assert not any(i['kind'] in ('meal','cafe') for i in day['items'])
    assert any(i['kind']=='break' and i['start']=='12:00' for i in day['items'])
    assert planner.validate_schedule([day])


def test_replacement_rechecks_weather_and_preserves_revision(draft,monkeypatch):
    date=draft['days'][0]['date']
    draft['days'][0]['weather']=forecast(date,0)
    monkeypatch.setattr(rules,'reviewed_venues',lambda:{})
    store=plans.PlanStore();before=store.register(draft)
    with pytest.raises(plans.PlanError,match='날씨'):
        store.replace(before['plan_id'],1,before['days'][0]['items'][0]['slot_id'],'3')
    assert store.get(before['plan_id'],1)==before


def test_reviewed_ferry_missing_or_cancelled_return_blocks(snapshot,monkeypatch,tmp_path):
    from marine_agent import islands
    _,date=snapshot;monkeypatch.setattr(islands,'DATA',tmp_path)
    fact=manifest(date)
    for status in ('unknown','cancelled'):
        fact['crossings'][1]['status']=status
        (tmp_path/'reviewed_islands.json').write_text(json.dumps([fact]),encoding='utf-8')
        with pytest.raises(islands.IslandUnavailable,match='왕복'):
            planner.build_plan(dict(start_date=date,days=1,activity='none',island_id='test-island'))
