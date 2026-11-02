"""Single-server durable job summaries; bounded catch-up and one catalog writer."""
import datetime as dt
import threading
from . import providers, runs
_lock=threading.Lock()
KINDS=('seatrip_sync','tourism_sync')
def snapshot_status(at=None):
 at=at or runs.now();c=providers.catalog() if providers.CATALOG.exists() else {}
 result={}
 for kind in KINDS:
  if kind=='seatrip_sync':
   stamp=c.get('marine',{}).get('seatrip',{}).get('collected_at');due_at=at.replace(hour=0,minute=15,second=0,microsecond=0)
   fresh=bool(stamp and dt.datetime.fromisoformat(stamp).astimezone(runs.KST).date()==at.date())
   next_at=due_at+dt.timedelta(days=1) if fresh else due_at
  else:
   stamp=c.get('tourism_collected_at',c.get('collected_at'));monday=(at-dt.timedelta(days=at.weekday())).replace(hour=0,minute=25,second=0,microsecond=0)
   fresh=bool(c.get('places') and stamp and dt.datetime.fromisoformat(stamp)>=monday);due_at=monday;next_at=monday+dt.timedelta(days=7) if fresh else monday
  if not stamp or kind=='tourism_sync' and not c.get('places'):due_at=at;next_at=at
  attempts=[r for r in runs.listing(kind=kind,limit=500) if r['scheduled'] and dt.datetime.fromisoformat(r['started_at']).astimezone(runs.KST).date()==at.date()]
  active=next((r for r in runs.listing(limit=100) if r['kind'] in KINDS and r['status'] in ('queued','running')),None)
  recent=attempts[0] if attempts else None
  cooldown=bool(recent and (at-dt.datetime.fromisoformat(recent['started_at'])).total_seconds()<1800)
  due=not fresh and at>=due_at and len(attempts)<3 and not cooldown and not active
  age=(at-dt.datetime.fromisoformat(stamp)).total_seconds()/86400 if stamp else None
  if cooldown:next_at=max(next_at,dt.datetime.fromisoformat(recent['started_at'])+dt.timedelta(minutes=30))
  if not fresh and len(attempts)>=3:next_at=(at+dt.timedelta(days=1)).replace(hour=0,minute=5,second=0,microsecond=0)
  recent_runs=runs.listing(kind=kind,limit=100)
  last_success=next((r['finished_at'] for r in recent_runs if r['status'] in ('success','warning')),stamp)
  last_failure=next((r['finished_at'] for r in recent_runs if r['status'] in ('failed','interrupted')),None)
  result[kind]=dict(last_success_at=last_success,last_failure_at=last_failure,collected_at=stamp,fresh=fresh,due=due,attempts_today=len(attempts),next_due_at=next_at.isoformat(),warning=bool(age is not None and age>=7) if kind=='tourism_sync' else not fresh,blocked=bool(age is None or age>=8) if kind=='tourism_sync' else not fresh,last_run=next(iter(runs.listing(kind=kind,limit=1)),None))
 return result

def submit(kind,scheduled=False,parent=None):
 if kind not in KINDS:raise ValueError('Unsupported job')
 with _lock:
  # Recording is mandatory for jobs, but optional for traveler requests.
  def probe():
   with runs.db():return True
  if not runs.safe(probe,False):raise RuntimeError('Job storage unavailable')
  active=next((r for r in runs.listing(limit=100) if r['kind'] in KINDS and r['status'] in ('queued','running')),None)
  if active:return dict(job_id=active['id'],status=active['status'],deduplicated=True,kind=active['kind'])
  if scheduled and not snapshot_status()[kind]['due']:return dict(job_id=None,status='skipped',kind=kind)
  if parent:
   old=runs.detail(parent)
   if not old or old['kind']!=kind or old['status'] not in ('failed','interrupted'):raise ValueError('Only failed collection jobs can be retried')
  attempt=(runs.detail(parent)['attempt']+1) if parent else 1
  if scheduled:
   recent=next((r for r in runs.listing(kind=kind,limit=100) if r['scheduled'] and r['status'] in ('failed','interrupted')),None)
   if recent:parent=recent['id'];attempt=recent['attempt']+1
  job_id=runs.create(kind,parent=parent,scheduled=scheduled,attempt=attempt)
  if not runs.detail(job_id):raise RuntimeError('Job storage unavailable')
  threading.Thread(target=work,args=(kind,job_id),daemon=True).start()
  return dict(job_id=job_id,status='queued',kind=kind,deduplicated=False)

def work(kind,job_id):
 try:
  with runs.execution(kind,job_id) as execution:
   providers.sync_component(kind);execution.finish('success')
 except Exception:pass # execution records sanitized failure; no raw source exceptions.
 finally:runs.maintenance()
