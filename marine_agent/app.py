from typing import Literal
import threading
import json
import queue
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, CATALOG
from . import agent, planner, providers, progress, plans

app = FastAPI(title='Marine Travel AI Agent', version='0.2.0')
app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')
generation_lock = threading.Lock()


class Message(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[Message] = Field(default_factory=list, max_length=8)
    trip: planner.Trip | None = None
    locked: list[planner.Lock] = Field(default_factory=list, max_length=12)
    excluded_ids: list[str] = Field(default_factory=list, max_length=100)


class Replacement(BaseModel):
    revision: int = Field(ge=1)
    slot_id: str = Field(min_length=1, max_length=64)
    candidate_id: str = Field(pattern=r'^\d{1,20}$')


class Revision(BaseModel):
    revision: int = Field(ge=1)


class LockUpdate(Revision):
    slot_id: str = Field(min_length=1, max_length=64)
    locked: bool


@app.get('/')
def index():
    return FileResponse(ROOT / 'web' / 'index.html')


@app.get('/api/health')
def health():
    result = dict(status='ok', catalog_ready=CATALOG.exists())
    if CATALOG.exists():
        c = providers.catalog()
        result.update(collected_at=c['collected_at'], places=len(c['places']),
                      marine_counts={k: len(v['rows']) for k, v in c['marine'].items()})
    return result


@app.get('/api/config')
def public_config():
    import os
    return dict(tile_url=os.environ.get('OSM_TILE_URL', 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'),
                tile_attribution='© OpenStreetMap contributors', routing='OSRM', version='0.2.0')


@app.get('/api/places')
def places(region: Literal['영종·용유', '강화', '송도·도심'] = '영종·용유', keyword: str = ''):
    try:
        return planner.tourism_candidates(region, keyword)
    except RuntimeError:
        raise HTTPException(503, '먼저 데이터를 수집하세요.') from None


@app.post('/api/plan')
def plan(trip: planner.Trip):
    try:
        return plans.store.register(planner.build_plan(trip))
    except (ValueError, RuntimeError):
        raise HTTPException(503, '일정 생성에 필요한 최신 데이터·후보를 확인하세요.') from None


@app.post('/api/chat')
def chat(request: ChatRequest):
    if not CATALOG.exists():
        raise HTTPException(503, 'python -m marine_agent.sync를 먼저 실행하세요.')
    if not generation_lock.acquire(blocking=False):
        raise HTTPException(429, '다른 일정을 생성 중입니다. 잠시 후 다시 시도하세요.')
    try:
        result = agent.chat(request.message, [m.model_dump() for m in request.history], request.trip,
                            request.locked, request.excluded_ids)
        if result.get('plan'):
            result['plan'] = plans.store.register(result['plan'])
        return result
    except Exception:
        return JSONResponse(status_code=503, content=dict(detail='일정 생성에 실패했습니다. 데이터와 날짜를 확인하세요.'))
    finally:
        generation_lock.release()


@app.post('/api/chat/stream')
def chat_stream(request: ChatRequest):
    if not CATALOG.exists():
        raise HTTPException(503, '먼저 데이터를 수집해 주세요.')
    if not generation_lock.acquire(blocking=False):
        raise HTTPException(429, '다른 일정을 생성 중입니다. 잠시 후 다시 시도하세요.')
    events = queue.SimpleQueue()
    started = time.monotonic()

    def send(event):
        events.put(dict(event, elapsed_seconds=round(time.monotonic() - started, 1)))

    def work():
        try:
            with progress.reporting(send):
                progress.emit('input', '여행 조건을 확인했어요.', state='completed')
                progress.emit('data', '여행에 필요한 자료와 도구를 선택하고 있어요.')
                result = agent.chat(request.message, [m.model_dump() for m in request.history], request.trip,
                                    request.locked, request.excluded_ids)
                if result.get('plan'):
                    result['plan'] = plans.store.register(result['plan'])
                else:
                    progress.emit('enrich', '일정 생성 전에 필요한 추가 질문을 준비했어요.', state='skipped')
                progress.emit('result', '결과를 화면에 준비했어요.', state='completed')
                send(dict(type='result', result=result))
        except Exception:
            send(dict(type='error', message='자료 또는 연결을 확인하지 못했습니다. 다시 시도하거나 데이터 초안을 선택해 주세요.'))
        finally:
            generation_lock.release()
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def lines():
        while True:
            try:
                event = events.get(timeout=10)
            except queue.Empty:
                event = dict(type='heartbeat', elapsed_seconds=round(time.monotonic() - started, 1))
            if event is None:
                return
            yield json.dumps(event, ensure_ascii=False) + '\n'

    return StreamingResponse(lines(), media_type='application/x-ndjson',
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@app.post('/api/plans/{plan_id}/replace')
def replace(plan_id: str, request: Replacement):
    try:
        return plans.store.replace(plan_id, request.revision, request.slot_id, request.candidate_id)
    except plans.PlanError as error:
        raise HTTPException(error.status, error.message) from None


@app.post('/api/plans/{plan_id}/undo')
def undo(plan_id: str, request: Revision):
    try:
        return plans.store.undo(plan_id, request.revision)
    except plans.PlanError as error:
        raise HTTPException(error.status, error.message) from None


@app.post('/api/plans/{plan_id}/lock')
def lock_slot(plan_id: str, request: LockUpdate):
    try:
        return plans.store.set_lock(plan_id, request.revision, request.slot_id, request.locked)
    except plans.PlanError as error:
        raise HTTPException(error.status, error.message) from None
