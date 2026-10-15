"""Read-only public-data clients. Never expose authenticated request URLs."""
import datetime as dt
import json
import math
import os
from pathlib import Path
import time
from functools import lru_cache

from scripts.check_data_connections import get, load_credentials, marine_schema, summarize
from .config import DATA, CATALOG

KST = dt.timezone(dt.timedelta(hours=9))
MARINE = {'beach': (15142484, 'fcstBeachv2'), 'seasplit': (15142485, 'fcstSeaSplitv2'),
          'fishing': (15142486, 'fcstFishingv2'), 'sickness': (15142487, 'fcstSicknessv2'),
          'scuba': (15142488, 'fcstSkinScubav2'), 'mudflat': (15142489, 'fcstMudflatv2'),
          'surfing': (15142490, 'fcstSurfingv2'), 'seatrip': (15142491, 'fcstSeaTripv2')}


def credentials():
    path = os.environ.get('MARINE_CREDENTIALS_FILE')
    if not path:
        raise RuntimeError('MARINE_CREDENTIALS_FILE is not configured')
    return load_credentials(path)


def service(suffix):
    for entry in credentials():
        if entry['endpoint'].endswith('/' + suffix) or (suffix == 'fcstSeaTripv2' and entry['endpoint'].endswith('/fcstSeaTripv')):
            return entry
    raise RuntimeError('Required API credential is missing')


def fetch_pages(url, params, *, limit=20000, success_codes=()):
    rows, seen, expected = [], set(), None
    for page in range(1, 201):
        summary, batch = summarize(get(url, dict(params, pageNo=page)))
        if summary['status'] not in ('ok', 'no_data') and summary.get('result_code') not in success_codes:
            raise RuntimeError('Public API did not return a success code')
        total = int(summary.get('total_count') or 0)
        if expected is None:
            expected = total
        if total != expected:
            raise RuntimeError('Public API total changed during collection; retry')
        if not batch:
            if len(rows) != expected:
                raise RuntimeError('Incomplete pagination')
            return rows
        for row in batch:
            identity = json.dumps(row, sort_keys=True, ensure_ascii=False)
            if identity in seen:
                raise RuntimeError('Repeated row during pagination')
            seen.add(identity)
            rows.append(row)
        if len(rows) == expected:
            return rows
        if len(rows) > expected or len(rows) > limit:
            raise RuntimeError('Unexpected record count')
        time.sleep(.05)
    raise RuntimeError('Pagination limit exceeded')


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def sync_catalog(scope='incheon', all_marine=False):
    from . import regions
    if scope not in ('incheon','coastal'):
        raise ValueError('Unknown collection scope')
    entry = service('KorService2')
    params = dict(serviceKey=entry['key'], MobileOS='ETC', MobileApp='MarineTravelAgent', _type='json', numOfRows=100)
    codes = fetch_pages(entry['endpoint'] + '/areaCode2', params)
    area = next(row['code'] for row in codes if row['name'] == '인천')
    selected = [str(area)] if scope == 'incheon' else list(regions.AREA_NAMES)
    known = {str(row['code']) for row in codes}
    if not set(selected) <= known:
        raise RuntimeError('Tourism area metadata incomplete')
    rows, administrative = [], {}
    for code in selected:
        administrative[code] = fetch_pages(entry['endpoint'] + '/areaCode2', dict(params, areaCode=code)) if scope == 'coastal' else []
        rows.extend(fetch_pages(entry['endpoint'] + '/areaBasedList2', dict(params, areaCode=code, arrange='A')))
    ids = [str(row['contentid']) for row in rows]
    if len(set(ids)) != len(ids):
        raise RuntimeError('Duplicate tourism content IDs')
    marine, errors = {}, {}
    if scope == 'coastal' and CATALOG.exists():
        previous = catalog()
        marine = {k: dict(v, collected_at=v.get('collected_at',previous['collected_at'])) for k,v in previous.get('marine',{}).items()}
    today = dt.datetime.now(KST).strftime('%Y%m%d')
    for activity, (page, suffix) in MARINE.items():
        if scope == 'coastal' and not all_marine and activity != 'seatrip':
            continue
        try:
            schema, source = marine_schema(page)
            operation = next(iter(schema['paths']))
            entry = service(suffix)
            query = dict(serviceKey=entry['key'], type='json', reqDate=today, numOfRows=300)
            if activity == 'fishing':
                query['gubun'] = '갯바위'
            marine[activity] = dict(rows=fetch_pages('https://' + schema['host'] + operation, query),
                                     source=source, requested_date=today, collected_at=dt.datetime.now(KST).isoformat())
        except Exception as error:
            errors[activity] = type(error).__name__
    if errors:
        # Do not replace a complete existing snapshot with a partial marine refresh.
        atomic_json(DATA / 'sync_failure.json', dict(checked_at=dt.datetime.now(KST).isoformat(), errors=errors))
        raise RuntimeError('Marine collection incomplete; previous catalog preserved (see data/sync_failure.json)')
    result = dict(collected_at=dt.datetime.now(KST).isoformat(), tourism_source='https://www.data.go.kr/data/15101578/openapi.do',
                  scope=scope, area_code=area, area_codes=selected, administrative=administrative, places=rows, marine=marine)
    atomic_json(CATALOG, result)
    return dict(places=len(rows), marine={k: len(v['rows']) for k, v in marine.items()}, collected_at=result['collected_at'])


def catalog():
    if not CATALOG.exists():
        raise RuntimeError('Catalog is missing. Run python -m marine_agent.sync first.')
    stamp=CATALOG.stat()
    return _read_catalog(str(CATALOG),stamp.st_mtime_ns,stamp.st_size)


@lru_cache(maxsize=2)
def _read_catalog(path, mtime, size):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def place_detail(content_id):
    # IDs are looked up locally before being sent to an external service.
    row = next((p for p in catalog()['places'] if str(p['contentid']) == str(content_id)), None)
    if row is None:
        raise ValueError('Unknown place ID')
    entry = service('KorService2')
    query = dict(serviceKey=entry['key'], MobileOS='ETC', MobileApp='MarineTravelAgent', _type='json', contentId=str(content_id), numOfRows=10)
    details = {}
    for operation, extra in [('detailCommon2', {}), ('detailIntro2', {'contentTypeId': row['contenttypeid']})]:
        status, rows = summarize(get(entry['endpoint'] + '/' + operation, dict(query, **extra)))
        if status['status'] not in ('ok', 'no_data'):
            raise RuntimeError('Tourism details unavailable')
        details[operation] = rows
    return dict(content_id=str(content_id), title=row['title'], details=details,
                checked_at=dt.datetime.now(KST).isoformat(), source='TourAPI')


def weather_grid(lat, lon):
    """KMA Lambert conformal grid conversion; WGS84 degrees to grid cells."""
    rad = math.pi / 180
    rearth, grid = 6371.00877, 5.0
    slat1, slat2, olon, olat = 30 * rad, 60 * rad, 126 * rad, 38 * rad
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(math.tan(math.pi / 4 + slat2 / 2) / math.tan(math.pi / 4 + slat1 / 2))
    sf = math.tan(math.pi / 4 + slat1 / 2) ** sn * math.cos(slat1) / sn
    ro = rearth / grid * sf / math.tan(math.pi / 4 + olat / 2) ** sn
    ra = rearth / grid * sf / math.tan(math.pi / 4 + lat * rad / 2) ** sn
    theta = (lon * rad - olon + math.pi) % (2 * math.pi) - math.pi
    return math.floor(ra * math.sin(theta * sn) + 43 + .5), math.floor(ro - ra * math.cos(theta * sn) + 136 + .5)


def weather_for_place(content_id, date):
    dt.date.fromisoformat(date)
    row = next((p for p in catalog()['places'] if str(p['contentid']) == str(content_id)), None)
    if not row or not row.get('mapy') or not row.get('mapx'):
        raise ValueError('Place coordinates unavailable')
    lat, lon = float(row['mapy']), float(row['mapx'])
    if not (33 < lat < 39 and 124 < lon < 132):
        raise ValueError('Coordinates outside supported grid')
    nx, ny = weather_grid(lat, lon)
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(hours=1)  # conservative publication allowance
    candidates = [dt.datetime.combine((now - dt.timedelta(days=d)).date(), dt.time(h), KST)
                  for d in (0, 1) for h in (2, 5, 8, 11, 14, 17, 20, 23)]
    issue = max(c for c in candidates if c <= cutoff)
    entry = service('VilageFcstInfoService_2.0')
    rows = fetch_pages(entry['endpoint'] + '/getVilageFcst', dict(serviceKey=entry['key'], dataType='JSON', numOfRows=1000,
        base_date=issue.strftime('%Y%m%d'), base_time=issue.strftime('%H%M'), nx=nx, ny=ny))
    matching = [r for r in rows if r['fcstDate'] == date.replace('-', '')]
    # Condense by forecast time while retaining all forecast elements for the date.
    by_time = {}
    for r in matching:
        by_time.setdefault(r['fcstTime'], {})[r['category']] = r['fcstValue']
    return dict(status='available' if matching else 'no_forecast', date=date, grid=dict(nx=nx, ny=ny),
                issue_at=issue.isoformat(), checked_at=now.isoformat(), forecasts=by_time,
                source='KMA short-term forecast', warnings_checked=False,
                reference_place=dict(id=str(content_id), title=row['title'], lat=lat, lon=lon))
