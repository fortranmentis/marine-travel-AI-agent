"""Local graph service contract: synthetic weather/routes, real SQLite checkpoints."""
import copy
import json
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient
from marine_agent import journeys, planner, plans, providers, runs, agent, mobility
from marine_agent.app import app
from test_core import snapshot

@pytest.fixture
def world(snapshot,monkeypatch):
    _,date=snapshot
    monkeypatch.setattr(providers,'weather_for_place',lambda *a:dict(status='available',forecasts={f'{h:02d}00':{'PTY':'1'} for h in range(24)}))
    monkeypatch.setattr(mobility,'capabilities',lambda:dict(transit=True))
    monkeypatch.setattr(mobility,'route_between',lambda *a,**kw:dict(status='available',duration_s=60,distance_m=100))
    return dict(start_date=date,region='영종·용유',days=1,activity='none',transport='walk',visits_per_day=3,
        locked=[dict(date=date,start='14:00',end='15:00',title='예약 시간')])

def events(response):
    assert response.status_code==200,response.text
    return [json.loads(line) for line in response.text.splitlines() if line]

def start(client,trip,use_ai=False):
    ev=events(client.post('/api/journeys/stream',json=dict(trip=trip,use_ai=use_ai)))
    ticket=next(e for e in ev if e['type']=='journey')
    result=next(e['result'] for e in ev if e['type']=='result')
    return ticket,result,ev

def headers(ticket):return {'X-Journey-Token':ticket['token']}

def resume(client,ticket,result,choice):
    return client.post(f'/api/journeys/{ticket["id"]}/resume/stream',headers=headers(ticket),json=dict(revision=result['journey']['revision'],choice=choice))

def test_wait_resume_bounded_replans_and_fixed_booking(world):
    c=TestClient(app);ticket,first,ev=start(c,world)
    assert first['status']=='waiting' and first['journey']['status']=='pending'
    assert first['attempts']==1 and first['decision']['options']==['keep','fewer','transit']
    assert any(e.get('tool')=='journey_validate' for e in ev)
    second=next(e['result'] for e in events(resume(c,ticket,first,'fewer')) if e['type']=='result')
    assert second['plan']['trip']['visits_per_day']==2 and second['attempts']==2
    assert resume(c,ticket,first,'keep').status_code==409
    third=next(e['result'] for e in events(resume(c,ticket,second,'transit')) if e['type']=='result')
    assert third['journey']['status']=='completed' and third['attempts']==3
    assert third['plan']['trip']['transport']=='transit'
    assert any(i['title']=='예약 시간' and i['start']=='14:00' for i in third['plan']['days'][0]['items'])
    assert resume(c,ticket,third,'keep').status_code==409
    detail=runs.detail(third['execution']['run_id'])
    assert detail['parent_run_id']==second['execution']['run_id']

def test_keep_rechecks_fresh_weather(world,monkeypatch):
    c=TestClient(app);ticket,first,_=start(c,world)
    monkeypatch.setattr(providers,'weather_for_place',lambda *a:dict(status='available',forecasts={f'{h:02d}00':{'PTY':'0'} for h in range(24)}))
    final=next(e['result'] for e in events(resume(c,ticket,first,'keep')) if e['type']=='result')
    assert final['journey']['status']=='completed' and final['attempts']==2
    assert final['plan']['days'][0]['weather']['forecasts']['1000']['PTY']=='0'

def test_token_not_in_trace_and_session_requires_owner(world):
    c=TestClient(app);ticket,result,ev=start(c,world)
    url=f'/api/journeys/{ticket["id"]}'
    assert c.get(url).status_code==401
    assert c.get(url,headers={'X-Journey-Token':'bad'}).status_code==401
    fetched=c.get(url,headers=headers(ticket));assert fetched.status_code==200
    assert fetched.headers['cache-control']=='no-store'
    assert ticket['token'] not in fetched.text
    assert ticket['token'] not in json.dumps(runs.detail(result['execution']['run_id']))
    public=[e for e in ev if e['type']!='journey']
    assert ticket['token'] not in json.dumps(public)
    with sqlite3.connect(journeys.path()) as db:
        assert ticket['token'] not in repr(db.execute('SELECT * FROM journeys').fetchall())

def test_restart_restores_checkpoint_plan_revision_media_routes_and_undo(world,monkeypatch):
    c=TestClient(app);ticket,first,_=start(c,world)
    saved=copy.deepcopy(first['plan'])
    monkeypatch.setattr(plans,'store',plans.PlanStore(persistent=True))
    restored=c.get(f'/api/journeys/{ticket["id"]}',headers=headers(ticket)).json()['result']
    assert restored['plan']==saved
    final=next(e['result'] for e in events(resume(c,ticket,restored,'keep')) if e['type']=='result')
    assert final['journey']['status']=='completed'
    # Complete plans remain usable by the existing PDF/lock endpoints after a fresh store.
    monkeypatch.setattr(plans,'store',plans.PlanStore(persistent=True))
    plan=plans.store.get(final['plan']['plan_id'],1)
    assert plan['media']==final['plan']['media'] and plan['routes']==final['plan']['routes']

def test_changed_pending_plan_rejected(world):
    c=TestClient(app);ticket,result,_=start(c,world)
    p=result['plan'];lock=next(i for i in p['days'][0]['items'] if i['kind']=='locked')
    # The legacy lock endpoint is still compatible, but invalidates the pending graph revision.
    edited=plans.store.set_lock(p['plan_id'],1,lock['slot_id'],False) if lock.get('original_kind') else None
    if edited is None:
        candidate=copy.deepcopy(p);plans.store.commit(candidate,1,None)
    assert resume(c,ticket,result,'keep').status_code==409

def test_invalid_choice_does_not_consume_checkpoint(world):
    c=TestClient(app);world['transport']='car';world['visits_per_day']=1
    ticket,result,_=start(c,world)
    assert result['decision']['options']==['keep']
    assert resume(c,ticket,result,'transit').status_code==422
    assert c.get(f'/api/journeys/{ticket["id"]}',headers=headers(ticket)).json()['journey']['revision']==1
    assert any(e['type']=='result' for e in events(resume(c,ticket,result,'keep')))

def test_failure_retry_and_startup_interruption(world,monkeypatch):
    c=TestClient(app);original=planner.build_plan
    monkeypatch.setattr(planner,'build_plan',lambda *a:(_ for _ in ()).throw(RuntimeError('PRIVATE provider payload')))
    ev=events(c.post('/api/journeys/stream',json=dict(trip=world,use_ai=False)))
    ticket=ev[0];assert any(e['type']=='error' for e in ev) and 'PRIVATE' not in json.dumps(ev)
    failed=c.get(f'/api/journeys/{ticket["id"]}',headers=headers(ticket)).json()
    assert failed['journey']['status']=='failed'
    monkeypatch.setattr(planner,'build_plan',original)
    retry=events(c.post(f'/api/journeys/{ticket["id"]}/resume/stream',headers=headers(ticket),json=dict(revision=1,choice='retry')))
    result=next(e['result'] for e in retry if e['type']=='result')
    with journeys.database() as db:db.execute("UPDATE journeys SET status='running' WHERE id=?",(ticket['id'],))
    journeys.maintenance(recover=True)
    interrupted=c.get(f'/api/journeys/{ticket["id"]}',headers=headers(ticket)).json()
    assert interrupted['journey']['status']=='interrupted'
    result=next(e['result'] for e in events(resume(c,ticket,result,'retry')) if e['type']=='result')
    assert result['journey']['status']=='pending' and result['attempts']==1

def test_expiry_removes_checkpoints_and_plan_payload(world):
    c=TestClient(app);ticket,result,_=start(c,world)
    with journeys.database() as db:db.execute('UPDATE journeys SET expires=?',(time.time()-1,))
    with plans.store.database() as db:db.execute('UPDATE plans SET expires=?',(time.time()-1,))
    journeys.maintenance()
    assert c.get(f'/api/journeys/{ticket["id"]}',headers=headers(ticket)).status_code==410
    with sqlite3.connect(journeys.path()) as db:
        assert db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM writes').fetchone()[0]==0
    with pytest.raises(plans.PlanError):plans.store.get(result['plan']['plan_id'],1)

def test_qwen_first_build_only_and_transit_requires_explicit_choice(world,monkeypatch):
    calls=[]
    def fake(message,trip=None,**kw):
        calls.append(trip.transport)
        return dict(plan=planner.build_plan(trip),answer='검토용',trace=[],status='ok')
    monkeypatch.setattr(agent,'chat',fake)
    c=TestClient(app);ticket,result,_=start(c,world,True)
    assert calls==['walk'] and result['plan']['trip']['transport']=='walk'
    final=next(e['result'] for e in events(resume(c,ticket,result,'transit')) if e['type']=='result')
    assert calls==['walk'] and final['plan']['trip']['transport']=='transit'

def test_busy_request_allocates_no_session(world):
    from marine_agent.app import generation_lock
    generation_lock.acquire()
    try:assert TestClient(app).post('/api/journeys/stream',json=dict(trip=world)).status_code==429
    finally:generation_lock.release()
    with journeys.database() as db:assert db.execute('SELECT COUNT(*) FROM journeys').fetchone()[0]==0

def test_stable_plan_key_registration_and_persistent_conflicts(snapshot):
    _,date=snapshot
    draft=planner.build_plan(dict(start_date=date,days=1,activity='none'))
    a=plans.PlanStore(persistent=True);original=a.register(draft,plan_id='a'*32)
    b=plans.PlanStore(persistent=True)
    assert b.register(draft,plan_id='a'*32)==original
    changed=b.commit(copy.deepcopy(original),1,original)
    with pytest.raises(plans.PlanError):a.commit(copy.deepcopy(original),1,None)
    a=plans.PlanStore(persistent=True)
    assert a.undo(changed['plan_id'],2)['days']==original['days']

def test_bounded_session_storage(world,monkeypatch):
    monkeypatch.setattr(journeys,'CAPACITY',1)
    c=TestClient(app);ticket,_,_=start(c,world);start(c,world)
    assert c.get(f'/api/journeys/{ticket["id"]}',headers=headers(ticket)).status_code==410
    with journeys.database() as db:assert db.execute('SELECT COUNT(*) FROM journeys').fetchone()[0]==1

def test_failed_replan_preserves_previous_registered_plan(world,monkeypatch):
    c=TestClient(app);ticket,result,_=start(c,world)
    before=copy.deepcopy(result['plan'])
    monkeypatch.setattr(planner,'build_plan',lambda *a:(_ for _ in ()).throw(RuntimeError('provider down')))
    ev=events(resume(c,ticket,result,'fewer'))
    assert any(e['type']=='error' for e in ev)
    recovered=c.get(f'/api/journeys/{ticket["id"]}',headers=headers(ticket)).json()
    assert recovered['journey']['status']=='failed'
    assert recovered['result']['plan']==before
    assert plans.store.get(before['plan_id'],1)==before


def test_evicted_plan_does_not_offer_resume_for_a_missing_itinerary(world):
    c=TestClient(app);ticket,result,_=start(c,world)
    with plans.store.database() as db:db.execute('DELETE FROM plans WHERE id=?',(result['plan']['plan_id'],))
    recovered=c.get(f'/api/journeys/{ticket["id"]}',headers=headers(ticket)).json()
    assert recovered['journey']['status']=='expired'
    assert recovered['result']['plan'] is None and recovered['result']['decision'] is None
