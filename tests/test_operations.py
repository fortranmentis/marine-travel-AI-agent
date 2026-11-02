import datetime as dt
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from marine_agent import runs,jobs,providers,progress,planner
from marine_agent.app import app


def snapshot(monkeypatch,tmp_path,age=0):
 at=runs.now();path=tmp_path/'catalog.json'
 value=dict(collected_at=at.isoformat(),tourism_collected_at=(at-dt.timedelta(days=age)).isoformat(),places=[dict(contentid='1',title='관광지',contenttypeid='12')],marine={'seatrip':dict(collected_at=at.isoformat(),rows=[dict(predcYmd=at.strftime('%Y%m%d'),sareaDtlNm='강릉',totalIndex='좋음')]),'mudflat':dict(collected_at='2020-01-01T00:00:00+09:00',rows=[])})
 path.write_text(json.dumps(value),encoding='utf-8');monkeypatch.setattr(providers,'CATALOG',path);monkeypatch.setattr(providers,'DATA',tmp_path)
 return value,path


def test_run_repeated_tools_privacy_and_warning():
 with runs.execution('ai_plan') as run:
  progress.emit('data','private dialogue serviceKey=SECRET')
  for _ in range(2):
   progress.emit('data','sensitive args',event='tool',tool='get_weather',coordinates=[1,2])
   progress.emit('data','raw response',event='tool',tool='get_weather',state='completed',count=2)
  progress.emit('fallback','secret failure',event='fallback')
  summary=run.finish('success')
 value=runs.detail(run.id)
 tools=[s for s in value['steps'] if s['tool']]
 assert len(tools)==2 and tools[0]['id']!=tools[1]['id']
 assert tools[0]['parent_id'] and value['status']=='warning'
 raw=json.dumps(value)
 assert all(word not in raw for word in ['SECRET','private','coordinates','raw response'])
 assert summary['run_id']==run.id


def test_retention_recovery_and_fail_soft(monkeypatch,tmp_path):
 old=runs.create('ai_plan');active=runs.create('rules_plan',status='running')
 with runs.db() as c:c.execute("UPDATE runs SET status='success',finished_at=? WHERE id=?",((runs.now()-dt.timedelta(days=8)).isoformat(),old))
 runs.maintenance(recover=True)
 assert runs.detail(old) is None and runs.detail(active)['status']=='interrupted'
 monkeypatch.setenv('RUNS_DB_PATH',str(tmp_path))
 with runs.execution('ai_plan') as execution:
  progress.emit('input','okay',state='completed');summary=execution.finish('success')
 assert summary['status']=='success' and not runs.health()['available']


def test_operations_auth_scope_and_invalid_jobs(monkeypatch):
 monkeypatch.setenv('OPS_TOKEN','operator');monkeypatch.setenv('SYNC_TOKEN','scheduler')
 c=TestClient(app)
 assert c.get('/api/ops/runs').status_code==401
 assert c.get('/api/ops/runs',headers={'Authorization':'Bearer scheduler'}).status_code==401
 assert c.get('/internal/sync-status',headers={'Authorization':'Bearer operator'}).status_code==401
 assert c.post('/internal/jobs',headers={'Authorization':'Bearer scheduler'},json={'kind':'shell','command':'bad'}).status_code==422
 assert c.get('/api/ops/runs',headers={'Authorization':'Bearer operator'}).status_code==200
 monkeypatch.setenv('OPS_TOKEN','');assert c.get('/api/ops/status').status_code==503


def test_schedule_catchup_cooldown_attempt_limit(monkeypatch,tmp_path):
 value,path=snapshot(monkeypatch,tmp_path,age=10)
 at=runs.now().replace(hour=12,minute=0,second=0,microsecond=0)
 value['marine']['seatrip']['collected_at']=(at-dt.timedelta(days=1)).isoformat();path.write_text(json.dumps(value))
 assert jobs.snapshot_status(at)['seatrip_sync']['due']
 for i in range(3):
  key=runs.create('seatrip_sync',scheduled=True)
  with runs.db() as c:c.execute("UPDATE runs SET status='failed',started_at=?,finished_at=? WHERE id=?",((at-dt.timedelta(hours=2,minutes=i)).isoformat(),at.isoformat(),key))
 state=jobs.snapshot_status(at)
 assert not state['seatrip_sync']['due'] and state['seatrip_sync']['attempts_today']==3
 assert state['tourism_sync']['due'] and state['tourism_sync']['blocked']


def test_job_dedup_and_retry_validation(monkeypatch,tmp_path):
 snapshot(monkeypatch,tmp_path)
 class NoThread:
  def __init__(self,*a,**kw):pass
  def start(self):pass
 monkeypatch.setattr(jobs.threading,'Thread',NoThread)
 first=jobs.submit('seatrip_sync');second=jobs.submit('tourism_sync')
 assert first['job_id']==second['job_id'] and second['deduplicated']
 with runs.db() as c:c.execute("UPDATE runs SET status='failed' WHERE id=?",(first['job_id'],))
 retry=jobs.submit('seatrip_sync',parent=first['job_id'])
 assert runs.detail(retry['job_id'])['parent_run_id']==first['job_id']
 assert runs.detail(retry['job_id'])['attempt']==2


def test_seatrip_only_atomic_and_empty_preserves(monkeypatch,tmp_path):
 previous,path=snapshot(monkeypatch,tmp_path)
 monkeypatch.setattr(providers,'marine_schema',lambda *a:({'host':'example.invalid','paths':{'/forecast':{}}},'official'))
 monkeypatch.setattr(providers,'service',lambda *a:{'key':'synthetic'})
 from marine_agent import regions
 monkeypatch.setattr(regions,'SPECS',{'강릉':{'forecast_area':'강릉'}})
 rows=[dict(sareaDtlNm='강릉',predcYmd=runs.now().strftime('%Y%m%d'),totalIndex='좋음')]
 monkeypatch.setattr(providers,'fetch_pages',lambda *a,**kw:rows)
 providers.sync_component('seatrip_sync');result=json.loads(path.read_text())
 assert result['tourism_collected_at']==previous['tourism_collected_at'] and result['places']==previous['places']
 assert result['marine']['mudflat']==previous['marine']['mudflat']
 before=path.read_bytes();monkeypatch.setattr(providers,'fetch_pages',lambda *a,**kw:[])
 with pytest.raises(RuntimeError):providers.sync_component('seatrip_sync')
 assert path.read_bytes()==before


def test_tourism_only_preserves_forecasts(monkeypatch,tmp_path):
 previous,path=snapshot(monkeypatch,tmp_path)
 from marine_agent import regions
 monkeypatch.setattr(regions,'AREA_NAMES',{'2':'인천'})
 monkeypatch.setattr(providers,'service',lambda *a:{'endpoint':'https://example.invalid','key':'synthetic'})
 batches=iter([[dict(code='2')],[],[dict(contentid='2',title='새 관광지',contenttypeid='12')]])
 monkeypatch.setattr(providers,'fetch_pages',lambda *a,**kw:next(batches))
 providers.sync_component('tourism_sync');result=json.loads(path.read_text())
 assert result['marine']==previous['marine'] and result['places'][0]['contentid']=='2'


def test_cli_and_service_share_catalog_lock(monkeypatch,tmp_path):
 from filelock import FileLock,Timeout
 snapshot(monkeypatch,tmp_path)
 with FileLock(str(tmp_path/'catalog.lock')):
  with pytest.raises(Timeout):providers.sync_component('seatrip_sync')


def test_recorded_api_execution_survives_client_reload(monkeypatch,tmp_path):
 monkeypatch.setenv('OPS_TOKEN','operator')
 from marine_agent import plans
 monkeypatch.setattr(planner,'build_plan',lambda trip:{'days':[]})
 monkeypatch.setattr(plans.store,'register',lambda plan:plan)
 trip={'region':'강릉','start_date':runs.now().date().isoformat(),'days':1,'activity':'seatrip'}
 result=TestClient(app).post('/api/plan',json=trip)
 assert result.status_code==200
 run_id=result.json()['execution']['run_id']
 detail=TestClient(app).get('/api/ops/runs/'+run_id,headers={'Authorization':'Bearer operator'})
 assert detail.status_code==200 and detail.json()['status']=='success'
 # The legacy non-stream endpoint must also distinguish degraded model results.
 import importlib
 app_module=importlib.import_module('marine_agent.app')
 from marine_agent import agent
 marker=tmp_path/'present.json';marker.write_text('{}')
 monkeypatch.setattr(app_module,'CATALOG',marker)
 monkeypatch.setattr(agent,'chat',lambda *a,**kw:dict(status='degraded',answer='fallback',plan=None,trace=[]))
 degraded=TestClient(app).post('/api/chat',json={'message':'hello'})
 assert degraded.status_code==200 and degraded.json()['execution']['status']=='warning'



def test_missing_catalog_bootstrap_and_recent_failure_cooldown(monkeypatch,tmp_path):
 monkeypatch.setattr(providers,'CATALOG',tmp_path/'absent.json')
 at=runs.now().replace(hour=0,minute=1)
 assert all(s['due'] for s in jobs.snapshot_status(at).values())
 key=runs.create('seatrip_sync',scheduled=True)
 with runs.db() as c:c.execute("UPDATE runs SET status='failed',started_at=?,finished_at=? WHERE id=?",(at.isoformat(),at.isoformat(),key))
 assert not jobs.snapshot_status(at+dt.timedelta(minutes=10))['seatrip_sync']['due']
 assert jobs.snapshot_status(at+dt.timedelta(minutes=31))['seatrip_sync']['due']


def test_partial_forecast_catalog_does_not_mark_tourism_fresh(monkeypatch,tmp_path):
 value,path=snapshot(monkeypatch,tmp_path)
 value['places']=[];value.pop('tourism_collected_at');path.write_text(json.dumps(value))
 assert not jobs.snapshot_status()['tourism_sync']['fresh']


def test_full_job_failure_and_fail_soft_recording(monkeypatch,tmp_path):
 snapshot(monkeypatch,tmp_path)
 def fail(kind):
  progress.emit('collect','key=DO_NOT_STORE')
  raise RuntimeError('serviceKey=DO_NOT_STORE')
 monkeypatch.setattr(providers,'sync_component',fail)
 key=runs.create('seatrip_sync');jobs.work('seatrip_sync',key)
 d=runs.detail(key)
 assert d['status']=='failed' and any(s['state']=='failed' for s in d['steps'])
 assert 'DO_NOT_STORE' not in json.dumps(d)
