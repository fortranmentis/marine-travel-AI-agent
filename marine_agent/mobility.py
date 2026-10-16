"""Mode-specific routes. A car graph is never used as a walking graph."""
import hashlib
import math
import os
import threading

import httpx

_transit_lock = threading.Lock()


def transit_provider():
    return os.environ.get('TRANSIT_PROVIDER', 'playwright').strip().lower()


def transit_route(a, b, departure_at=None):
    if transit_provider() == 'playwright':
        from . import browser_transit
        return browser_transit.route(a, b, departure_at)
    if transit_provider() != 'odsay':
        return dict(status='not_configured', mode='transit', reason='대중교통 조회가 비활성화되어 있습니다.')
    return _odsay_route(a, b)


def _odsay_route(a, b):
    from . import enrichment
    key_value = os.environ.get('ODSAY_API_KEY')
    if not key_value:
        return dict(status='not_configured', reason='대중교통 API 키가 아직 연결되지 않았습니다.', mode='transit')
    cache_key = 'transit:' + hashlib.sha256(str((a['lat'], a['lon'], b['lat'], b['lon'])).encode()).hexdigest()
    with _transit_lock:
        hit = enrichment.cached(cache_key)
        if hit:
            return hit
        try:
            with httpx.Client(timeout=15, trust_env=False) as client:
                response = client.get('https://api.odsay.com/v1/api/searchPubTransPathT', params=dict(
                    apiKey=key_value, SX=a['lon'], SY=a['lat'], EX=b['lon'], EY=b['lat'], SearchPathType=0))
                response.raise_for_status()
                result = response.json().get('result', {})
            paths = [p for p in result.get('path', []) if p.get('pathType') in (1, 2, 3)
                     and math.isfinite(float(p.get('info', {}).get('totalTime', -1)))
                     and float(p.get('info', {}).get('totalTime', -1)) > 0]
            if not paths:
                raise ValueError('no urban route')
            route = min(paths, key=lambda p: float(p['info']['totalTime']))
            info = route['info']
            sections = []
            for s in route.get('subPath', []):
                sections.append(dict(mode={1: 'subway', 2: 'bus', 3: 'walk'}.get(s.get('trafficType'), 'unknown'),
                    minutes=s.get('sectionTime'), start=s.get('startName'), end=s.get('endName'),
                    lines=[l.get('busNo') or l.get('name') for l in s.get('lane', [])]))
            return enrichment.remember(cache_key, dict(status='available', mode='transit',
                duration_s=float(info['totalTime']) * 60, distance_m=float(info.get('totalDistance') or 0),
                source='ODsay', sections=sections, geometry=None, fare=info.get('payment'),
                schedule_verified=False, traffic='not_included',
                note='일반 경로 예상 시간입니다. 여행일 출발시각·막차·배차 및 도보 선형은 미확인입니다.'), 3600)
        except Exception:
            return enrichment.remember(cache_key, dict(status='unavailable', mode='transit', reason='대중교통 경로 미확보'), 60)


def route_between(a, b, mode='car', departure_at=None):
    from . import enrichment
    if mode == 'car':
        return enrichment.road_route(a, b)
    if mode == 'walk':
        return enrichment.road_route(a, b, mode='walk')
    # Transit + walking: deliberately choose a short walking leg before lookup.
    # A failed browser route never causes this branch or a car fallback.
    from .planner import distance
    if distance((a['lat'], a['lon']), (b['lat'], b['lon'])) <= 0.6:
        result = dict(enrichment.road_route(a, b, mode='walk'))
        result.update(mode='walk', requested_departure_at=departure_at,
                      departure_time_applied=False, schedule_verified=False,
                      note='가까운 구간은 도보 경로로 계산했습니다. 대중교통 시간표 조회 결과가 아닙니다.')
        return result
    return transit_route(a, b, departure_at)


def capabilities():
    provider = transit_provider()
    if provider == 'playwright':
        from .browser_transit import readiness
        state = readiness()
    else:
        state = dict(ready=provider == 'odsay' and bool(os.environ.get('ODSAY_API_KEY')), reason='대중교통 조회 미연결')
    return dict(car=True, walk=True, transit=state['ready'], transit_provider=provider,
                transit_reason=state['reason'], transit_schedule_verified=False)
