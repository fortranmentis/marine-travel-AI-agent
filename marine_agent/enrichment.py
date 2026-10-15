"""Optional imagery and read-only road routing; failures never invent geometry."""
import hashlib
import json
import os
import threading
import time
from urllib.parse import urlsplit

import httpx

from . import providers, progress
from .config import DATA
from .planner import minutes

_cache_lock = threading.RLock()
_route_lock = threading.Lock()
_last_route = 0.0
_cache = None


def cached(key):
    global _cache
    with _cache_lock:
        if _cache is None:
            try:
                _cache = json.loads((DATA / 'enrichment.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                _cache = {}
        entry = _cache.get(key)
        return entry['value'] if entry and entry['expires'] > time.time() else None


def remember(key, value, seconds):
    with _cache_lock:
        cached(key)
        _cache[key] = dict(expires=time.time() + seconds, value=value)
        now = time.time()
        for expired in [k for k, v in _cache.items() if v['expires'] <= now]:
            del _cache[expired]
        try:
            providers.atomic_json(DATA / 'enrichment.json', _cache)
        except OSError:
            pass  # Optional disk cache failure must not invalidate an itinerary.
    return value


def image_url(value):
    parsed = urlsplit(str(value or ''))
    if parsed.scheme not in ('https', 'http') or parsed.hostname != 'tong.visitkorea.or.kr':
        return None
    return parsed._replace(scheme='https').geturl()


def photo_for(content_id):
    key = 'photo:' + str(content_id)
    hit = cached(key)
    if hit is not None:
        return hit
    missing = dict(status='unavailable', reason='사진 정보 없음')
    try:
        row = next((p for p in providers.catalog()['places'] if str(p['contentid']) == str(content_id)), None)
        if row is None:
            return missing
        url, license_code = image_url(row.get('firstimage') or row.get('firstimage2')), row.get('cpyrhtDivCd')
        title = row['title']
        if not url or license_code not in ('Type1', 'Type3'):
            entry = providers.service('KorService2')
            summary, rows = providers.summarize(providers.get(entry['endpoint'] + '/detailImage2', dict(
                serviceKey=entry['key'], MobileOS='ETC', MobileApp='MarineTravelAgent', _type='json',
                contentId=str(content_id), imageYN='Y', numOfRows=10, pageNo=1)))
            if summary['status'] != 'ok':
                return remember(key, missing, 300)
            valid = next((r for r in rows if str(r.get('contentid')) == str(content_id)
                          and image_url(r.get('originimgurl')) and r.get('cpyrhtDivCd') in ('Type1', 'Type3')), None)
            if valid is None:
                return remember(key, missing, 7 * 86400)
            url, license_code = image_url(valid['originimgurl']), valid['cpyrhtDivCd']
            title = valid.get('imgname') or title
        return remember(key, dict(status='available', url=url, title=title, content_id=str(content_id),
            source='한국관광공사 TourAPI', source_url='https://api.visitkorea.or.kr/', license=license_code,
            license_url=f'https://www.kogl.or.kr/info/licenseType{license_code[-1]}.do'), 7 * 86400)
    except Exception:
        return remember(key, missing, 300)


def road_route(a, b):
    global _last_route
    base = os.environ.get('OSRM_BASE_URL', 'https://router.project-osrm.org').rstrip('/')
    coordinates = f"{a['lon']:.6f},{a['lat']:.6f};{b['lon']:.6f},{b['lat']:.6f}"
    key = 'route:' + hashlib.sha256((base + coordinates).encode()).hexdigest()
    with _route_lock:
        hit = cached(key)
        if hit is not None:
            return hit
        pause = 1.0 - (time.monotonic() - _last_route)
        if pause > 0:
            time.sleep(pause)
        _last_route = time.monotonic()
        failure = dict(status='unavailable', reason='경로 미확보')
        try:
            with httpx.Client(timeout=15, trust_env=False, headers={
                'User-Agent': 'MarineTravelAIAgent/0.2 (+https://github.com/fortranmentis/marine-travel-AI-agent)'}) as client:
                response = client.get(base + '/route/v1/driving/' + coordinates,
                    params=dict(overview='full', geometries='geojson', steps='true'))
                response.raise_for_status()
                obj = response.json()
            if obj.get('code') != 'Ok' or not obj.get('routes'):
                return remember(key, failure, 60)
            route = obj['routes'][0]
            modes = {s.get('mode') for leg in route.get('legs', []) for s in leg.get('steps', [])}
            if 'ferry' in modes:
                return remember(key, dict(status='unsupported_ferry', reason='배편이 포함된 경로는 지원하지 않아요.'), 86400)
            if not route.get('geometry', {}).get('coordinates') or route['duration'] < 0 or route['distance'] < 0:
                return remember(key, failure, 60)
            return remember(key, dict(status='available', geometry=route['geometry'], distance_m=route['distance'],
                duration_s=route['duration'], source='OSRM / OpenStreetMap', traffic='not_included',
                snapped_waypoints=[dict(location=p.get('location'), distance_m=p.get('distance')) for p in obj.get('waypoints', [])]), 86400)
        except Exception:
            return remember(key, failure, 60)


def day_route(day):
    stops = [i for i in day['items'] if i.get('lat') is not None and i.get('lon') is not None
             and i['kind'] in ('tourism', 'marine', 'locked')]
    legs = []
    for a, b in zip(stops, stops[1:]):
        route = dict(road_route(a, b))
        available = minutes(b['start']) - minutes(a['end'])
        # Preparation, lunch and changing blocks cannot be spent driving.
        for item in day['items']:
            if item is not a and item is not b:
                available -= max(0, min(minutes(b['start']), minutes(item['end'])) - max(minutes(a['end']), minutes(item['start'])))
        route.update(from_slot=a['slot_id'], to_slot=b['slot_id'], available_minutes=max(0, available))
        route['fits_schedule'] = route['duration_s'] <= max(0, available) * 60 if route['status'] == 'available' else None
        legs.append(route)
    return dict(waypoints=[dict(slot_id=i['slot_id'], title=i['title'], lat=i['lat'], lon=i['lon'], number=n + 1) for n, i in enumerate(stops)],
                legs=legs, source='© OpenStreetMap contributors · OSRM',
                total_distance_m=sum(r.get('distance_m', 0) for r in legs),
                total_duration_s=sum(r.get('duration_s', 0) for r in legs),
                complete=all(r['status'] == 'available' for r in legs))


def enrich(plan):
    progress.emit('enrich', '관광지 사진과 날짜별 도로 경로를 준비하고 있어요.')
    media, routes = {}, {}
    for day in plan['days']:
        for item in [*day['items'], *day['alternatives']]:
            if item.get('id') and item['id'] not in media:
                media[item['id']] = photo_for(item['id'])
        routes[day['date']] = day_route(day)
    plan['media'], plan['routes'] = media, routes
    progress.emit('enrich', '사진과 경로 조회를 마쳤어요. 확보하지 못한 자료는 따로 표시해요.', state='completed')
    return plan
