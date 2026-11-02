"""Local operator API and narrowly scoped n8n control plane."""
from contextlib import asynccontextmanager
import datetime as dt
import hmac
import os
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi import Response
from pydantic import BaseModel, ConfigDict
from typing import Literal
from . import jobs, runs, progress
from .config import ROOT

@asynccontextmanager
async def lifespan(app):
 runs.maintenance(recover=True)
 from .observability import start_retention,stop_retention
 start_retention()
 yield
 stop_retention()
def no_store(response:Response):response.headers['Cache-Control']='no-store'
router=APIRouter(lifespan=lifespan,dependencies=[Depends(no_store)])
def check(name,authorization):
 expected=os.environ.get(name,'')
 if not expected:raise HTTPException(503,'운영 기능의 토큰이 설정되지 않았습니다.')
 if not authorization or not hmac.compare_digest(authorization,'Bearer '+expected):raise HTTPException(401,'운영 인증이 필요합니다.')
def admin(authorization: str|None=Header(default=None)):check('OPS_TOKEN',authorization)
def scheduler(authorization: str|None=Header(default=None)):check('SYNC_TOKEN',authorization)
class Job(BaseModel):
 model_config=ConfigDict(extra="forbid")
 kind:Literal['seatrip_sync','tourism_sync']
 scheduled:bool=False
 parent_run_id:str|None=None

def submit(request,internal=False):
 try:return jobs.submit(request.kind,scheduled=request.scheduled if internal else False,parent=request.parent_run_id)
 except ValueError:raise HTTPException(422,'재시도할 수 없는 작업입니다.') from None
 except RuntimeError:raise HTTPException(503,'작업 기록 저장소를 확인하세요.') from None
@router.get('/ops')
def ops():return FileResponse(ROOT/'web'/'ops.html',headers={'Cache-Control':'no-store'})
@router.get('/internal/sync-status',dependencies=[Depends(scheduler)])
def sync_status():return dict(jobs=jobs.snapshot_status(),recording=runs.health())
@router.post('/internal/jobs',dependencies=[Depends(scheduler)],status_code=202)
def internal_job(request:Job):return submit(request,True)
@router.get('/internal/jobs/{job_id}',dependencies=[Depends(scheduler)])
def internal_detail(job_id:str):
 value=runs.detail(job_id)
 if not value or value['kind'] not in jobs.KINDS:raise HTTPException(404,'작업을 찾을 수 없습니다.')
 return value
@router.get('/api/ops/status',dependencies=[Depends(admin)])
def status():
 runs.maintenance()
 from .observability import status as trace_status, public_url
 return dict(jobs=jobs.snapshot_status(),recording=runs.health(),retention_days=7,langfuse=dict(trace_status(),url=public_url()))
@router.get('/api/ops/runs',dependencies=[Depends(admin)])
def listing(kind:Literal['ai_plan','rules_plan','seatrip_sync','tourism_sync','full_sync']|None=None,status:Literal['queued','running','success','warning','failed','interrupted']|None=None,since:dt.date|None=None,limit:int=Query(100,ge=1,le=500)):
 return dict(runs=runs.listing(kind,status,dt.datetime.combine(since,dt.time(),runs.KST).isoformat() if since else None,limit))
@router.get('/api/ops/runs/{run_id}',dependencies=[Depends(admin)])
def detail(run_id:str):
 value=runs.detail(run_id)
 if not value:raise HTTPException(404,'실행 기록을 찾을 수 없습니다.')
 return value
@router.post('/api/ops/jobs',dependencies=[Depends(admin)],status_code=202)
def manual(request:Job):return submit(request)


@router.get('/api/ops/events',dependencies=[Depends(admin)])
def live_events():
 from .live import feed
 if not feed.acquire():raise HTTPException(429,'실시간 연결 수 제한에 도달했습니다.')
 def snapshot():
  recent=runs.listing(limit=20)
  return dict(runs=[runs.detail(r['id']) for r in recent if r],epoch=feed.epoch)
 def stream():
  try:
   cursor=feed.cursor()
   yield feed.encode('snapshot',snapshot(),cursor)
   while True:
    current,events,gap=feed.read(cursor,timeout=2)
    if gap:yield feed.encode('snapshot',snapshot(),current)
    else:
     for seq,value in events:yield feed.encode('update',value,seq)
    cursor=current
    yield ': heartbeat\n\n'
  finally:feed.release()
 return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
