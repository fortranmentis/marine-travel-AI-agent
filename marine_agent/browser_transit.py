"""Bounded, UI-only transit lookup. No private endpoint calls or browser profiles."""
from collections import OrderedDict
from contextvars import ContextVar
from functools import wraps
import copy
import importlib.util
import json
import math
import os
import subprocess
import sys
import threading
import time
from urllib.parse import quote

from . import progress
from .config import ROOT

_budget = ContextVar('browser_transit_budget', default=None)
_gate = threading.Lock()
_cache = OrderedDict()


def budgeted(function):
    @wraps(function)
    def run(*args, **kwargs):
        if _budget.get() is not None:
            return function(*args, **kwargs)
        token = _budget.set(dict(remaining=6, deadline=None))
        try:
            return function(*args, **kwargs)
        finally:
            _budget.reset(token)
    return run


def browser_env():
    env = os.environ.copy()
    local = ROOT / '.tmp' / 'playwright'
    if 'PLAYWRIGHT_BROWSERS_PATH' not in env and local.exists():
        env['PLAYWRIGHT_BROWSERS_PATH'] = str(local)
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def readiness():
    if importlib.util.find_spec('playwright') is None:
        return dict(ready=False, reason='Playwright 설치가 필요합니다.')
    try:
        result = subprocess.run([sys.executable, '-m', 'marine_agent.browser_transit_worker', '--check'],
                                cwd=ROOT, env=browser_env(), capture_output=True, text=True,
                                encoding='utf-8', timeout=5, check=False)
        ready = result.returncode == 0 and json.loads(result.stdout).get('ready') is True
    except Exception:
        ready = False
    return dict(ready=ready, reason='' if ready else 'Playwright Chromium 설치가 필요합니다.')


def point(value):
    lat, lon = float(value['lat']), float(value['lon'])
    if not math.isfinite(lat) or not math.isfinite(lon) or not (32 <= lat <= 40 and 124 <= lon <= 132):
        raise ValueError('Korea coordinates required')
    return dict(lat=lat, lon=lon, title=str(value.get('title') or '관광지')[:100])


def route_url(a, b):
    def location(value):
        p = point(value)
        x = 6378137 * math.radians(p['lon'])
        y = 6378137 * math.log(math.tan(math.pi / 4 + math.radians(p['lat']) / 2))
        return f"{x:.3f},{y:.3f},{quote(p['title'], safe='')},,"
    return f'https://map.naver.com/p/directions/{location(a)}/{location(b)}/-/transit'


def failure(reason, url=None):
    return dict(status='unavailable', mode='transit', reason=reason,
                source='네이버 지도 · Playwright 화면 조회', source_url=url,
                schedule_verified=False, geometry=None)


def run_worker(a, b, timeout):
    worker = subprocess.Popen([sys.executable, '-m', 'marine_agent.browser_transit_worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT,
        env=browser_env(), text=True, encoding='utf-8', start_new_session=os.name != 'nt')
    try:
        stdout, _ = worker.communicate(json.dumps(dict(a=a, b=b), ensure_ascii=False), timeout=timeout)
        if worker.returncode:
            raise RuntimeError('browser worker failed')
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        # Stop only this worker's process tree, including its Chromium children.
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(worker.pid), '/T', '/F'], capture_output=True, timeout=5)
        else:
            import signal
            os.killpg(worker.pid, signal.SIGKILL)
        worker.kill()
        worker.communicate(timeout=5)
        raise


def route(a, b, departure_at=None):
    try:
        a, b = point(a), point(b)
        url = route_url(a, b)
    except (KeyError, TypeError, ValueError, OverflowError):
        return failure('유효한 국내 출발·도착 좌표가 필요합니다.')
    # Only lookup-time estimates are cached. Requested future times are never applied.
    key = (a['lat'], a['lon'], a['title'], b['lat'], b['lon'], b['title'])
    if not _gate.acquire(timeout=2):
        return failure('다른 대중교통 경로 조회가 진행 중입니다. 지도에서 확인해 주세요.', url)
    try:
        now = time.monotonic()
        for expired in [k for k, (expires, _) in _cache.items() if expires <= now]:
            del _cache[expired]
        hit = _cache.get(key)
        if hit:
            result = copy.deepcopy(hit[1])
            result['cached'] = True
        else:
            budget = _budget.get()
            if budget and budget['deadline'] is None:
                budget['deadline'] = now + 90
            left = budget['deadline'] - now if budget else 30
            if budget and (budget['remaining'] <= 0 or left < 5):
                return failure('이번 일정의 브라우저 조회 한도에 도달했습니다. 지도에서 확인해 주세요.', url)
            if budget:
                budget['remaining'] -= 1
            progress.emit('enrich', f"{a['title']} → {b['title']} 대중교통을 지도 화면에서 확인하고 있어요.", event='status')
            try:
                result = run_worker(a, b, min(30, left))
            except Exception:
                result = failure('지도 조회 시간 초과 또는 브라우저 연결 실패 · 지도에서 확인해 주세요.', url)
            result['cached'] = False
            _cache[key] = (time.monotonic() + (300 if result['status'] == 'available' else 60), copy.deepcopy(result))
            while len(_cache) > 256:
                _cache.popitem(last=False)
        result['requested_departure_at'] = departure_at
        result['departure_time_applied'] = False
        return result
    finally:
        _gate.release()
