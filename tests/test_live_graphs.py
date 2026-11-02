import datetime as dt
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from marine_agent import runs,progress,observability,operations
from marine_agent.live import LiveFeed,feed
from marine_agent.app import app


def test_bounded_feed_gap_clients_and_heartbeat():
 f=LiveFeed(capacity=2,max_clients=1)
 assert f.acquire() and not f.acquire()
 for i in range(3):f.publish({'i':i})
 cursor,events,gap=f.read(0,timeout=0)
 assert cursor==3 and gap and [e['i'] for _,e in events]==[1,2]
 assert f.read(cursor,timeout=0)==(3,[],False)
 f.release();assert f.acquire();f.release()
 assert 'event: update' in f.encode('update',{'state':'완료'},3)


def test_live_records_are_allowlisted_and_finished_once():
 before=feed.cursor()
 with runs.execution('ai_plan') as r:
  progress.emit('data','private serviceKey=SECRET',raw={'prompt':'SECRET'})
  progress.emit('data','secret',event='tool',tool='get_weather',arguments={'key':'SECRET'})
  progress.emit('data','secret',event='tool',tool='get_weather',state='completed')
  r.finish('success');r.finish('success')
 _,events,_=feed.read(before,0)
 raw=json.dumps(events)
 assert 'SECRET' not in raw and 'arguments' not in raw and 'prompt' not in raw
 assert sum(e['type']=='finished' for _,e in events)==1
 assert any(e['type']=='step' and e['step']['parent_id'] for _,e in events)


def test_sse_auth_and_connection_limit(monkeypatch):
 monkeypatch.setenv('OPS_TOKEN','admin');monkeypatch.setenv('SYNC_TOKEN','sync')
 c=TestClient(app)
 assert c.get('/api/ops/events').status_code==401
 assert c.get('/api/ops/events',headers={'Authorization':'Bearer sync'}).status_code==401
 monkeypatch.setattr(feed,'max_clients',0)
 assert c.get('/api/ops/events',headers={'Authorization':'Bearer admin'}).status_code==429


class Observation:
 def __init__(self,identity,kwargs):self.id=identity;self.kwargs=kwargs;self.updates=[];self.ended=0
 def update(self,**kw):self.updates.append(kw)
 def end(self):self.ended+=1
class Client:
 def __init__(self):self.rows=[]
 def start_observation(self,**kw):
  obs=Observation(str(len(self.rows)),kw);self.rows.append(obs);return obs


def test_langfuse_trace_ids_parentage_usage_and_no_content(monkeypatch):
 c=Client();monkeypatch.setattr(observability,'get_client',lambda:c)
 with runs.execution('ai_plan') as r:
  progress.emit('data','SECRET')
  progress.emit('data','PRIVATE PROMPT',event='provider',provider='Ollama')
  progress.emit('data','PRIVATE OUTPUT',event='provider',provider='Ollama',state='completed',usage={'input':10,'output':20,'secret':999})
  r.finish('success')
 assert c.rows[0].kwargs['trace_context']['trace_id']==r.id
 child=next(o for o in c.rows if o.kwargs.get('as_type')=='generation')
 assert child.kwargs['trace_context']['trace_id']==r.id
 assert child.kwargs['trace_context']['parent_span_id']==c.rows[1].id
 assert child.updates[-1]['usage_details']=={'input':10,'output':20}
 payload=json.dumps([dict(kwargs=o.kwargs,updates=o.updates) for o in c.rows])
 assert 'PRIVATE' not in payload and 'SECRET' not in payload and 'input' not in child.kwargs and 'output' not in child.kwargs


def test_langfuse_outage_does_not_fail_execution(monkeypatch):
 class Broken:
  def start_observation(self,**kw):raise RuntimeError('secret URL')
 monkeypatch.setattr(observability,'get_client',lambda:Broken())
 with runs.execution('rules_plan') as r:
  progress.emit('input','okay',state='completed');result=r.finish('success')
 assert result['status']=='success' and runs.detail(r.id)['status']=='success'
 assert observability.status()['last_error_code']=='langfuse_span_failed'


def test_expiry_queue_survives_local_history_pruning_and_retries(monkeypatch):
 c=Client();monkeypatch.setattr(observability,'get_client',lambda:c)
 with runs.execution('ai_plan') as r:r.finish('success')
 past=(runs.now()-dt.timedelta(days=8)).isoformat()
 with runs.db() as db:
  db.execute('UPDATE telemetry_expiry SET expires_at=?',(past,))
  db.execute('UPDATE runs SET finished_at=?',(past,))
 runs.maintenance();assert runs.detail(r.id) is None
 with runs.db() as db:assert db.execute('SELECT count(*) FROM telemetry_expiry').fetchone()[0]==1
 monkeypatch.setenv('LANGFUSE_ENABLED','true');monkeypatch.setattr(observability,'config',lambda:('http://example.invalid','public','secret'))
 import httpx
 class FakeHTTP:
  status=503
  def __init__(self,**kw):pass
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def request(self,method,url,**kw):
   assert method=='DELETE' and kw['json']=={'traceIds':[r.id]}
   return SimpleNamespace(status_code=self.status)
 monkeypatch.setattr(httpx,'Client',FakeHTTP)
 assert observability.cleanup_once()==0
 FakeHTTP.status=202;assert observability.cleanup_once()==1
 with runs.db() as db:assert db.execute('SELECT count(*) FROM telemetry_expiry').fetchone()[0]==0


def test_langfuse_public_url_does_not_expose_credentials(monkeypatch):
 monkeypatch.setenv('LANGFUSE_PUBLIC_URL','http://user:SECRET@localhost:3000')
 assert observability.public_url() is None
 monkeypatch.setenv('LANGFUSE_PUBLIC_URL','http://127.0.0.1:3000')
 assert observability.public_url('abc').endswith('/project/marine-travel/traces/abc')


def test_local_setup_preserves_existing_secrets_and_explicit_disable(monkeypatch,tmp_path,capsys):
 from scripts import setup_observability as setup
 monkeypatch.setattr(setup,'ROOT',tmp_path);monkeypatch.setattr(setup,'DATA',tmp_path/'data')
 env=tmp_path/'.env';env.write_text('OPS_TOKEN=KEEP_OPERATOR\nSYNC_TOKEN=KEEP_SYNC\nLANGFUSE_ENABLED=false\nLF_USER_PASSWORD=KEEP_LOCAL_PASSWORD\n')
 setup.main();first=env.read_text();setup.main()
 assert env.read_text()==first
 assert 'OPS_TOKEN=KEEP_OPERATOR' in first and 'LANGFUSE_ENABLED=false' in first
 login=json.loads((tmp_path/'data/langfuse-local-login.json').read_text())
 assert login['password']=='KEEP_LOCAL_PASSWORD'
 assert 'KEEP_' not in capsys.readouterr().out
