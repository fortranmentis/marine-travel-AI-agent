"""Mode-specific routes. A car graph is never used as a walking graph."""
import hashlib
import math
import os
import threading

import httpx

_transit_lock = threading.Lock()


def transit_route(a, b):
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


def route_between(a, b, mode='car'):
    from . import enrichment
    if mode == 'car':
        return enrichment.road_route(a, b)
    if mode == 'walk':
        return enrichment.road_route(a, b, mode='walk')
    return transit_route(a, b)


def capabilities():
    return dict(car=True, walk=True, transit=bool(os.environ.get('ODSAY_API_KEY')))
