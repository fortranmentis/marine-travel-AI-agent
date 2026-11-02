"""Local, capability-protected LangGraph sessions (2h TTL, 128 sessions)."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import queue
import re
import secrets
import sqlite3
import threading
import time
from uuid import uuid4, uuid5, NAMESPACE_URL

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from . import planner, plans, progress, runs, journey_graph
from .config import DATA
from .browser_transit import budgeted

TTL=7200
CAPACITY=128
router=APIRouter()

def path():return Path(os.environ.get('JOURNEYS_DB_PATH',str(DATA/'journeys.sqlite3')))

@contextmanager
def database():
    p=path();p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(p,timeout=10);c.row_factory=sqlite3.Row
    try:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS journeys(id TEXT PRIMARY KEY,token_hash TEXT,expires REAL,revision INTEGER,status TEXT,input TEXT,result TEXT,run_id TEXT)')
        with c:yield c
    finally:c.close()

def maintenance(recover=False):
    with database() as c:
        if recover:c.execute("UPDATE journeys SET status='interrupted' WHERE status='running'")
        expired=[r[0] for r in c.execute("SELECT id FROM journeys WHERE expires<=? AND status!='running'",(time.time(),))]
        excess=[r[0] for r in c.execute("SELECT id FROM (SELECT id,status FROM journeys ORDER BY expires DESC LIMIT -1 OFFSET ?) WHERE status!='running'",(CAPACITY,))]
        for identity in set(expired+excess):
            for table in ('checkpoints','writes'):
                if c.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():
                    c.execute(f'DELETE FROM {table} WHERE thread_id=?',(identity,))
            c.execute('DELETE FROM journeys WHERE id=?',(identity,))
    with plans.store.database() as c:c.execute('DELETE FROM plans WHERE expires<=?',(time.time(),))

@contextmanager
def graph_session(identity):
    with SqliteSaver.from_conn_string(str(path())) as saver:
        yield journey_graph.graph(saver),{'configurable':{'thread_id':identity},'recursion_limit':30}

def load(identity,token):
    if not re.fullmatch('[0-9a-f]{32}',identity):raise HTTPException(404,'여행 진행을 찾을 수 없습니다.')
    maintenance()
    with database() as c:r=c.execute('SELECT * FROM journeys WHERE id=?',(identity,)).fetchone()
    if not r or r['expires']<=time.time():raise HTTPException(410,'여행 진행 보관 시간이 지났습니다. 새로 생성해 주세요.')
    if not token or not hmac.compare_digest(r['token_hash'],hashlib.sha256(token.encode()).hexdigest()):
        raise HTTPException(401,'이 여행 진행의 접근 정보가 필요합니다.')
    return dict(r)

def view(row):
    result=json.loads(row['result']) if row['result'] else None
    plan_missing=False
    if result and result.get('plan'):
        try:result['plan']=plans.store.latest(result['plan']['plan_id'])
        except plans.PlanError:result['plan']=None;plan_missing=True
    meta=dict(id=row['id'],revision=row['revision'],status='expired' if plan_missing else row['status'],expires_at=row['expires'])
    if plan_missing:result.update(decision=None,answer='보관 기간 또는 최대 보관 수를 초과해 일정이 만료됐습니다. 새로 생성해 주세요.')
    if result:result['journey']=meta
    return dict(journey=meta,result=result)

class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    trip:planner.Trip
    use_ai:bool=True

class Resume(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    choice:Literal['keep','fewer','transit','retry']

@router.get('/api/journeys/{identity}')
def get(identity:str,x_journey_token:str|None=Header(default=None)):
    return JSONResponse(view(load(identity,x_journey_token)),headers={'Cache-Control':'no-store'})

@budgeted
def execute(identity,send,run_id,choice=None):
    with database() as c:row=dict(c.execute('SELECT * FROM journeys WHERE id=?',(identity,)).fetchone())
    with runs.execution('ai_plan' if json.loads(row['input'])['use_ai'] else 'rules_plan',run_id=run_id) as execution, progress.reporting(send):
        progress.emit('input','저장된 여행 조건을 확인했어요.',state='completed')
        with graph_session(identity) as (g,config):
            snapshot=g.get_state(config)
            if not snapshot.values:
                initial=json.loads(row['input']);initial['attempts']=0
                output=g.invoke(initial,config)
            else:
                output=g.invoke(None if choice=='retry' else Command(resume=choice),config)
        pending=bool(output.get('__interrupt__'))
        if pending:progress.emit('schedule','사용자의 선택을 기다리고 있어요.',event='tool',tool='journey_decision',state='warning')
        draft=output['plan']
        # Replay cannot create a second plan for the same graph attempt.
        plan_key=uuid5(NAMESPACE_URL,f'marine-journey:{identity}:{output["attempts"]}').hex
        plan=plans.store.register(draft,plan_id=plan_key)
        status='pending' if pending else 'completed'
        meta=dict(id=identity,revision=row['revision'],status=status,expires_at=row['expires'])
        result=dict(status='waiting' if pending else 'ok',plan=plan,journey=meta,
            decision=output['__interrupt__'][0].value if pending else None,
            answer=output.get('answer','검토용 초안입니다.'),trace=output.get('trace',[]),attempts=output['attempts'])
        if output['attempts']>=3:
            result['answer']='최대 2회 재검토를 마쳤습니다. 남은 제약은 일정 카드에 표시했습니다.'
        progress.emit('result','선택을 기다립니다.' if pending else '결과를 준비했어요.',state='completed')
        result['execution']=execution.finish('warning' if pending or output.get('model_status') in ('degraded','limited') else 'success')
        with database() as c:c.execute('UPDATE journeys SET status=?,result=? WHERE id=?',(status,json.dumps(result,ensure_ascii=False),identity))
        return result

def stream(identity,run_id,lock,choice=None,token=None):
    events=queue.SimpleQueue();started=time.monotonic()
    def send(event):events.put(dict(event,elapsed_seconds=round(time.monotonic()-started,1)))
    # Ticket is sent only to this browser, never through progress/trace capture.
    if token:send(dict(type='journey',id=identity,token=token))
    def work():
        try:send(dict(type='result',result=execute(identity,send,run_id,choice)))
        except Exception:
            with database() as c:c.execute("UPDATE journeys SET status='failed' WHERE id=?",(identity,))
            send(dict(type='error',message='진행을 완료하지 못했습니다. 저장된 진행을 불러와 다시 시도하거나 새 일정을 생성해 주세요.'))
        finally:lock.release();events.put(None)
    try:threading.Thread(target=work,daemon=True).start()
    except BaseException:lock.release();raise
    def lines():
        while True:
            try:event=events.get(timeout=10)
            except queue.Empty:event=dict(type='heartbeat')
            if event is None:return
            yield json.dumps(event,ensure_ascii=False)+'\n'
    return StreamingResponse(lines(),media_type='application/x-ndjson',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

def acquire():
    from .app import generation_lock
    if not generation_lock.acquire(blocking=False):raise HTTPException(429,'다른 일정을 처리 중입니다. 잠시 후 다시 시도하세요.')
    return generation_lock

@router.post('/api/journeys/stream')
def start(request:Start):
    lock=acquire()
    try:
        maintenance();identity=uuid4().hex;token=secrets.token_urlsafe(32)
        kind='ai_plan' if request.use_ai else 'rules_plan';run_id=runs.create(kind)
        with database() as c:
            c.execute('INSERT INTO journeys VALUES(?,?,?,?,?,?,?,?)',(identity,hashlib.sha256(token.encode()).hexdigest(),time.time()+TTL,1,'running',
                json.dumps(dict(trip=request.trip.model_dump(mode='json'),use_ai=request.use_ai),ensure_ascii=False),None,run_id))
        maintenance()
    except BaseException:lock.release();raise
    return stream(identity,run_id,lock,token=token)

@router.post('/api/journeys/{identity}/resume/stream')
def resume(identity:str,request:Resume,x_journey_token:str|None=Header(default=None)):
    row=load(identity,x_journey_token)
    if row['revision']!=request.revision:raise HTTPException(409,'이미 변경된 진행입니다. 저장된 진행을 다시 불러오세요.')
    if row['status']=='running':raise HTTPException(409,'이미 처리 중입니다.')
    if row['status']=='completed':raise HTTPException(409,'완료된 진행입니다. 새 일정을 생성하세요.')
    if row['status']=='pending':
        result=json.loads(row['result'])
        if request.choice not in result['decision']['options']:raise HTTPException(422,'현재 선택할 수 없는 항목입니다.')
        try:
            if plans.store.latest(result['plan']['plan_id'])['revision']!=result['plan']['revision']:
                raise HTTPException(409,'대기 중 일정이 수정됐습니다. 최신 조건으로 새 일정을 생성하세요.')
        except plans.PlanError:raise HTTPException(410,'일정이 만료됐습니다. 새로 생성하세요.') from None
    elif request.choice!='retry':raise HTTPException(422,'중단된 진행은 다시 시도해 주세요.')
    lock=acquire()
    try:
        run_id=runs.create('ai_plan' if json.loads(row['input'])['use_ai'] else 'rules_plan',parent=row['run_id'],attempt=request.revision+1)
        with database() as c:
            changed=c.execute("UPDATE journeys SET status='running',revision=revision+1,run_id=? WHERE id=? AND revision=? AND status!='running'",(run_id,identity,request.revision)).rowcount
            if not changed:raise HTTPException(409,'이미 변경된 진행입니다.')
    except BaseException:lock.release();raise
    return stream(identity,run_id,lock,choice=request.choice)
