from typing import Literal
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, CATALOG
from . import agent, planner, providers

app = FastAPI(title='Marine Travel AI Agent', version='0.1.0')
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


@app.get('/api/places')
def places(region: Literal['영종·용유', '강화', '송도·도심'] = '영종·용유', keyword: str = ''):
    try:
        return planner.tourism_candidates(region, keyword)
    except RuntimeError:
        raise HTTPException(503, '먼저 데이터를 수집하세요.') from None


@app.post('/api/plan')
def plan(trip: planner.Trip):
    try:
        return planner.build_plan(trip)
    except (ValueError, RuntimeError):
        raise HTTPException(503, '일정 생성에 필요한 최신 데이터·후보를 확인하세요.') from None


@app.post('/api/chat')
def chat(request: ChatRequest):
    if not CATALOG.exists():
        raise HTTPException(503, 'python -m marine_agent.sync를 먼저 실행하세요.')
    if not generation_lock.acquire(blocking=False):
        raise HTTPException(429, '다른 일정을 생성 중입니다. 잠시 후 다시 시도하세요.')
    try:
        return agent.chat(request.message, [m.model_dump() for m in request.history], request.trip,
                          request.locked, request.excluded_ids)
    except Exception:
        return JSONResponse(status_code=503, content=dict(detail='일정 생성에 실패했습니다. 데이터와 날짜를 확인하세요.'))
    finally:
        generation_lock.release()
