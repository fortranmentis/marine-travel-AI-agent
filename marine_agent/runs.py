"""Seven-day, allowlisted execution summaries. No input, response or exception text."""
from contextlib import contextmanager
from contextvars import ContextVar
import datetime as dt
from functools import wraps
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4
from .config import DATA

KST=dt.timezone(dt.timedelta(hours=9))
KINDS={'ai_plan','rules_plan','seatrip_sync','tourism_sync','full_sync'}
STAGES={'input','data','schedule','enrich','result','collect','validate','save','fallback'}
TOOLS={'find_family_places','get_marine_conditions','get_place_details','get_weather','build_itinerary','get_ferry_operations','get_ferry_timetable','get_nearby_transport','unknown','journey_build','journey_validate','journey_decision','journey_finish'}
PROVIDERS={'TourAPI','KHOA','KMA','OSRM','photos','Ollama','transport'}
_current=ContextVar('execution_run',default=None)
_health={'available':True,'error_code':None}
def now():return dt.datetime.now(KST)
def stamp():return now().isoformat()
def _connect():
 path=Path(os.environ.get('RUNS_DB_PATH',str(DATA/'runs.sqlite3')));path.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(path,timeout=10);c.row_factory=sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA foreign_keys=ON')
 c.executescript("""CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,kind TEXT,status TEXT,started_at TEXT,finished_at TEXT,duration_s REAL,attempt INTEGER,parent_run_id TEXT,scheduled INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS steps(id TEXT PRIMARY KEY,run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,parent_id TEXT,stage TEXT,tool TEXT,provider TEXT,state TEXT,started_at TEXT,finished_at TEXT,duration_s REAL,count INTEGER,error_code TEXT);
 CREATE INDEX IF NOT EXISTS steps_run ON steps(run_id);
 CREATE TABLE IF NOT EXISTS telemetry_expiry(trace_id TEXT PRIMARY KEY,expires_at TEXT);""")
 return c
@contextmanager
def db():
 c=_connect()
 try:
  with c:yield c
 finally:c.close()

def safe(action,default=None):
 try:
  value=action();_health.update(available=True,error_code=None);return value
 except Exception:
  _health.update(available=False,error_code='recording_unavailable');return default
def maintenance(recover=False):
 def work():
  with db() as c:
   if recover:
    c.execute("UPDATE runs SET status='interrupted',finished_at=? WHERE status IN ('running','queued')",(stamp(),))
    c.execute("UPDATE steps SET state='interrupted',finished_at=? WHERE state='started'",(stamp(),))
   c.execute("DELETE FROM runs WHERE finished_at IS NOT NULL AND finished_at<?",((now()-dt.timedelta(days=7)).isoformat(),))
 safe(work)
def health():return dict(_health)
def create(kind,*,parent=None,scheduled=False,attempt=1,status='queued'):
 if kind not in KINDS:raise ValueError('Unsupported run kind')
 maintenance()
 run_id=uuid4().hex
 def work():
  with db() as c:c.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',(run_id,kind,status,stamp(),None,None,attempt,parent,int(scheduled)))
 safe(work);return run_id
class Execution:
 def __init__(self,kind,run_id=None):
  self.id=run_id or create(kind,status='running');self.started=time.monotonic();self.open={};self.tools={};self.steps=[];self.warning=False
  def work():
   with db() as c:c.execute("UPDATE runs SET status='running',started_at=? WHERE id=?",(stamp(),self.id))
  safe(work)
  from .observability import Trace
  self.trace=Trace(self.id,kind)
  self.kind=kind;self.finished=False
  from .live import feed
  feed.publish(dict(type='run',run=dict(id=self.id,kind=kind,status='running',started_at=stamp(),langfuse_trace_id=self.id if self.trace.root else None,steps=[])))
 def event(self,event):
  e=dict(event);stage=e.get('stage');typ=e.get('type');state=e.get('state','started');key=None;tool=None;provider=None
  if typ=='fallback':stage='fallback';state='completed';self.warning=True
  if typ=='tool':
   tool=e.get('tool') if e.get('tool') in TOOLS else 'unknown';key=('tool',tool)
   if state=='started':self.tools[tool]=uuid4().hex
   step_id=self.tools.get(tool,uuid4().hex)
  elif typ=='provider':
   provider=e.get('provider') if e.get('provider') in PROVIDERS else 'transport';key=('provider',provider);step_id=self.open.get(key,uuid4().hex)
  elif typ in ('stage','fallback') and stage in STAGES:key=('stage',stage);step_id=self.open.get(key,uuid4().hex)
  else:return dict(e,run_id=self.id,at=stamp())
  if state not in ('started','completed','failed','skipped','warning'):state='warning'
  if state in ('failed','warning'):self.warning=True
  parent=self.open.get(('stage',stage)) if typ in ('tool','provider') else None
  existing=next((s for s in self.steps if s['id']==step_id),None)
  timed=existing is not None
  if existing is None:
   existing=dict(id=step_id,run_id=self.id,parent_id=parent,stage=stage if stage in STAGES else 'data',tool=tool,provider=provider,state=state,started_at=stamp(),finished_at=None,duration_s=None,count=None,error_code=None)
   self.steps.append(existing);existing['_clock']=time.monotonic()
  existing['state']=state
  if isinstance(e.get('count'),int):existing['count']=max(0,e['count'])
  if state in ('failed','warning'):existing['error_code']='source_or_step_unavailable'
  if state!='started':
   existing.update(finished_at=stamp(),duration_s=round(time.monotonic()-existing['_clock'],3) if timed else None);self.open.pop(key,None)
  else:self.open[key]=step_id
  def work():
   row={k:v for k,v in existing.items() if not k.startswith('_')}
   with db() as c:c.execute('INSERT OR REPLACE INTO steps VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
  safe(work)
  row={k:v for k,v in existing.items() if not k.startswith('_')}
  self.trace.step(row,e)
  from .live import feed
  feed.publish(dict(type='step',run_id=self.id,step=row))
  return dict(e,run_id=self.id,step_id=step_id,parent_step_id=parent,at=stamp(),duration_seconds=existing['duration_s'])
 def finish(self,status):
  for s in list(self.steps):
   if s['state']=='started':
    if s['tool']:self.event(dict(type='tool',stage=s['stage'],tool=s['tool'],state='failed' if status=='failed' else 'skipped'))
    elif s['provider']:self.event(dict(type='provider',stage=s['stage'],provider=s['provider'],state='failed' if status=='failed' else 'skipped'))
    else:self.event(dict(type='stage',stage=s['stage'],state='failed' if status=='failed' else 'skipped'))
  state='warning' if status=='success' and self.warning else status
  def work():
   with db() as c:c.execute('UPDATE runs SET status=?,finished_at=?,duration_s=? WHERE id=?',(state,stamp(),round(time.monotonic()-self.started,3),self.id))
  safe(work)
  self.trace.finish(state)
  from .live import feed
  if not self.finished:feed.publish(dict(type='finished',run=dict(id=self.id,kind=self.kind,status=state,langfuse_trace_id=self.id if self.trace.root else None,finished_at=stamp(),duration_s=round(time.monotonic()-self.started,3),steps=[{k:v for k,v in s.items() if not k.startswith('_')} for s in self.steps])))
  self.finished=True
  return dict(run_id=self.id,kind=self.kind,status=state,duration_s=round(time.monotonic()-self.started,3),steps=[{k:v for k,v in s.items() if not k.startswith('_')} for s in self.steps])
@contextmanager
def execution(kind,run_id=None):
 value=Execution(kind,run_id);token=_current.set(value)
 try:yield value
 except BaseException:value.finish('failed');raise
 finally:_current.reset(token)
def current():return _current.get()
def capture(event):return current().event(event) if current() else event
def tracked(kind):
 def decorate(fn):
  @wraps(fn)
  def wrapped(*a,**kw):
   with execution(kind) as run:
    from . import progress
    progress.emit('input','요청 조건 확인',state='completed')
    result=fn(*a,**kw)
    progress.emit('result','요청 처리 완료',state='completed')
    if hasattr(result,'status_code') and result.status_code>=400:state='failed'
    else:state='warning' if isinstance(result,dict) and result.get('status') in ('degraded','limited') else 'success'
    summary=run.finish(state)
    if isinstance(result,dict):result['execution']=summary
    return result
  return wrapped
 return decorate
def listing(kind=None,status=None,since=None,limit=100):
 def work():
  sql='SELECT * FROM runs WHERE 1=1';args=[]
  for col,val in [('kind',kind),('status',status)]:
   if val:sql+=' AND '+col+'=?';args.append(val)
  if since:sql+=' AND started_at>=?';args.append(since)
  sql+=' ORDER BY started_at DESC LIMIT ?';args.append(limit)
  with db() as c:return [dict(r) for r in c.execute(sql,args)]
 return safe(work,[])
def detail(run_id):
 def work():
  with db() as c:
   r=c.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
   if not r:return None
   return dict(dict(r),langfuse_trace_id=run_id if c.execute('SELECT 1 FROM telemetry_expiry WHERE trace_id=?',(run_id,)).fetchone() else None,steps=[dict(s) for s in c.execute('SELECT * FROM steps WHERE run_id=? ORDER BY started_at,rowid',(run_id,))])
 return safe(work)


def live_snapshot(recent_limit=20,active_limit=16,step_limit=300):
 """One consistent read; active work cannot be displaced by newer completed runs."""
 def work():
  with db() as c:
   c.execute('BEGIN')
   active=c.execute("SELECT * FROM runs WHERE status IN ('queued','running') ORDER BY started_at DESC,id LIMIT ?",(active_limit+1,)).fetchall()
   recent=c.execute("SELECT * FROM runs WHERE status NOT IN ('queued','running') ORDER BY started_at DESC,id LIMIT ?",(recent_limit,)).fetchall()
   values=[]
   for row in [*active[:active_limit],*recent]:
    run=dict(row)
    steps=c.execute('SELECT * FROM steps WHERE run_id=? ORDER BY started_at,rowid LIMIT ?',(run['id'],step_limit+1)).fetchall()
    run.update(steps=[dict(s) for s in steps[:step_limit]],steps_truncated=len(steps)>step_limit,
               langfuse_trace_id=run['id'] if c.execute('SELECT 1 FROM telemetry_expiry WHERE trace_id=?',(run['id'],)).fetchone() else None)
    values.append(run)
   return dict(runs=values,active_truncated=len(active)>active_limit,active_limit=active_limit,recent_limit=recent_limit)
 return safe(work,dict(runs=[],active_truncated=False,active_limit=active_limit,recent_limit=recent_limit))
