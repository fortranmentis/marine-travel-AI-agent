"""Optional local Langfuse adapter. Never captures prompts, responses or arguments."""
from functools import lru_cache
import os
import threading
from urllib.parse import urlsplit

_health={'configured':False,'last_error_code':None}
def enabled():return os.environ.get('LANGFUSE_ENABLED','false').lower()=='true'
def config():
 return (os.environ.get('LANGFUSE_BASE_URL','http://127.0.0.1:3000'),os.environ.get('LANGFUSE_PUBLIC_KEY',''),os.environ.get('LANGFUSE_SECRET_KEY',''))
def status():return dict(_health,enabled=enabled(),configured=enabled() and all(config()))
def public_url(run_id=None):
 base=os.environ.get('LANGFUSE_PUBLIC_URL','http://127.0.0.1:3000').rstrip('/')
 p=urlsplit(base)
 if p.scheme not in ('http','https') or not p.netloc or p.username or p.password or p.query or p.fragment:return None
 return base+'/project/marine-travel/traces/'+run_id if run_id else base
@lru_cache(maxsize=2)
def client(base,public,secret):
 from langfuse import Langfuse
 from opentelemetry.sdk.trace import TracerProvider
 # Dedicated provider: unrelated instrumentations cannot leak through this adapter.
 return Langfuse(base_url=base,public_key=public,secret_key=secret,timeout=2,flush_at=20,flush_interval=1,environment='local',release='v0.8.2',tracer_provider=TracerProvider())
def get_client():
 if not enabled() or not all(config()):return None
 try:return client(*config())
 except Exception:_health['last_error_code']='langfuse_initialization_failed';return None
class Trace:
 def __init__(self,run_id,kind):
  self.run_id=run_id;self.client=get_client();self.root=None;self.spans={};self.ended_spans=set();self.finished=False
  if self.client:
   from . import runs
   def remember():
    import datetime as dt
    with runs.db() as c:c.execute('INSERT OR IGNORE INTO telemetry_expiry VALUES(?,?)',(run_id,(runs.now()+dt.timedelta(days=7)).isoformat()))
   try:
    self.root=self.client.start_observation(name='marine.'+kind,as_type='agent' if kind=='ai_plan' else 'span',trace_context={'trace_id':run_id},metadata={'run_id':run_id,'kind':kind})
    runs.safe(remember)
   except Exception:_health['last_error_code']='langfuse_span_failed'
 def step(self,row,event):
  if not self.root:return
  try:
   identity=row['id']
   if identity in self.ended_spans:return
   span=self.spans.get(identity)
   if span is None:
    parent=self.spans.get(row.get('parent_id')) or self.root
    typ='generation' if row.get('provider')=='Ollama' else 'tool' if row.get('tool') else 'span'
    span=self.client.start_observation(name=row.get('tool') or row.get('provider') or row['stage'],as_type=typ,trace_context={'trace_id':self.run_id,'parent_span_id':parent.id},metadata={'run_id':self.run_id,'step_id':identity,'stage':row['stage']})
    self.spans[identity]=span
   meta={k:row[k] for k in ('stage','state','count','duration_s','error_code') if row.get(k) is not None}
   args=dict(metadata=meta,level='ERROR' if row['state']=='failed' else 'WARNING' if row['state']=='warning' else 'DEFAULT')
   if row.get('provider')=='Ollama':
    usage=event.get('usage') or {};usage={k:v for k,v in usage.items() if k in ('input','output') and type(v) is int and v>=0}
    if usage:args['usage_details']=usage
    model=os.environ.get('OLLAMA_MODEL','qwen3.8:27b-mtp-q8_0')
    args['model']=model[:100]
   span.update(**args)
   if row['state']!='started':
    span.end();self.ended_spans.add(identity)
  except Exception:_health['last_error_code']='langfuse_span_failed'
 def finish(self,state):
  if not self.root or self.finished:return
  self.finished=True
  try:self.root.update(metadata={'state':state},level='ERROR' if state=='failed' else 'WARNING' if state=='warning' else 'DEFAULT');self.root.end()
  except Exception:_health['last_error_code']='langfuse_span_failed'
def flush():
 c=get_client()
 if c:
  try:c.flush()
  except Exception:_health['last_error_code']='langfuse_export_failed'


_retention_thread=None
_retention_stop=threading.Event()
def cleanup_once():
 if not enabled() or not all(config()):return 0
 from . import runs
 import httpx
 def expired():
  with runs.db() as c:return [r[0] for r in c.execute('SELECT trace_id FROM telemetry_expiry WHERE expires_at<? LIMIT 100',(runs.stamp(),))]
 ids=runs.safe(expired,[])
 if not ids:return 0
 base,public,secret=config()
 try:
  with httpx.Client(timeout=3,trust_env=False,auth=(public,secret)) as c:
   response=c.request('DELETE',base.rstrip('/')+'/api/public/traces',json={'traceIds':ids})
   if response.status_code not in (200,202,204):raise RuntimeError()
  def remove():
   with runs.db() as c:c.executemany('DELETE FROM telemetry_expiry WHERE trace_id=?',[(i,) for i in ids])
  runs.safe(remove)
  if _health.get('last_error_code')=='langfuse_retention_pending':_health['last_error_code']=None
  return len(ids)
 except Exception:_health['last_error_code']='langfuse_retention_pending';return 0

def start_retention():
 global _retention_thread
 if _retention_thread and _retention_thread.is_alive():return
 if not enabled():return
 _retention_stop.clear()
 def work():
  while not _retention_stop.is_set():
   cleanup_once();_retention_stop.wait(300)
 _retention_thread=threading.Thread(target=work,daemon=True);_retention_thread.start()

def stop_retention():_retention_stop.set()
