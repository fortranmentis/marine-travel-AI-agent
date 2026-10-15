"""TourAPI food categories and source-labelled regional sea-travel outlooks."""
import datetime as dt

from . import providers, regions

CUISINES = {'A05020100': ('korean', '한식'), 'A05020200': ('western', '양식'),
            'A05020300': ('japanese', '일식'), 'A05020400': ('chinese', '중식'),
            'A05020700': ('other', '기타')}
INDEX_ORDER = ['매우좋음', '좋음', '보통', '나쁨', '매우나쁨']


def food_candidates(region, cuisines=(), cafe=False, near=None, radius_km=3):
    from .planner import coords, distance
    result = []
    catalog=providers.catalog()
    for row in catalog['places']:
        point = coords(row)
        code = str(row.get('cat3', ''))
        category = CUISINES.get(code)
        if str(row.get('contenttypeid')) != '39' or not point or not regions.matches(row,region,catalog):
            continue
        if cafe and code != 'A05020900' or not cafe and (category is None or cuisines and category[0] not in cuisines):
            continue
        km = distance(near, point) if near else None
        if km is not None and km > radius_km:
            continue
        result.append(dict(id=str(row['contentid']), title=row['title'], lat=point[0], lon=point[1],
            address=row.get('addr1'), content_type='39', cuisine='cafe' if cafe else category[0],
            cuisine_label='카페·전통찻집' if cafe else category[1], distance_km=round(km, 2) if km is not None else None,
            source='한국관광공사 TourAPI', operating_hours='unverified'))
    return sorted(result, key=lambda p: (p['distance_km'] or 0, p['title']))


def sea_outlook(region, date, start, end):
    """Keep official ordinal grades; do not fabricate an official 0–100 score."""
    area = regions.SPECS.get(region,{}).get('forecast_area')
    c = providers.catalog()
    feed = c.get('marine', {}).get('seatrip', {})
    feed_collected=feed.get('collected_at',c['collected_at'])
    stale = dt.datetime.fromisoformat(feed_collected).date() != dt.datetime.now(providers.KST).date()
    rows = [r for r in feed.get('rows', []) if r.get('sareaDtlNm') == area
            and str(r.get('predcYmd', '')).replace('-', '') == date.replace('-', '')]
    # KHOA half-day codes: preserve raw evidence and require both halves when crossing noon.
    periods = ({'오전'} if end <= '12:00' else {'오후'} if start >= '12:00' else {'오전', '오후'})
    selected = [r for r in rows if str(r.get('predcNoonSeCd')) in periods]
    grades = [str(r.get('totalIndex', '')).replace(' ', '') for r in selected]
    complete = periods <= {r.get('predcNoonSeCd') for r in selected} and all(g in INDEX_ORDER for g in grades)
    resolution='half_day'
    daily=[r for r in rows if r.get('predcNoonSeCd')=='일']
    daily_grades=[str(r.get('totalIndex','')).replace(' ','') for r in daily]
    if not complete and daily and all(g in INDEX_ORDER for g in daily_grades):
        selected,grades,complete,resolution=daily,daily_grades,True,'daily'
    return dict(status='stale' if stale else 'available' if complete else 'no_forecast',
        grade=max(grades, key=INDEX_ORDER.index) if complete and not stale else None,
        area=area, source=feed.get('source'), collected_at=feed_collected, rows=selected,
        temporal_resolution=resolution,
        label='바다여행지수 기반 여행 전망', aggregation='공식 일 단위 등급 · 오전·오후 구분 없음' if resolution=='daily' else '해당 여행 시간대의 가장 낮은 공식 등급',
        note='권역 단위 해상 전망입니다. 육상 관광 적합성·여객선 운항·현장 통제 여부와 다릅니다.')


def overall_outlook(days):
    indexes = [d['travel_index'] for d in days]
    available = [i for i in indexes if i['status'] == 'available' and i.get('grade') in INDEX_ORDER]
    complete = len(available) == len(indexes) and bool(indexes)
    return dict(status='available' if complete else 'incomplete',
        grade=max((i['grade'] for i in available), key=INDEX_ORDER.index) if complete else None,
        covered_days=len(available), total_days=len(indexes),
        label='전체 여행 전망 · 바다여행지수 기반',
        note='여행일별 권역 등급 중 가장 낮은 등급입니다. 모든 날짜의 자료가 있어야 전체 등급을 표시합니다. 공식 종합 관광점수가 아닙니다.')


def add_food(day, trip):
    """Place one nearby meal per meal window, and at most one optional cafe break."""
    from .planner import minutes, hhmm, overlaps, distance
    from .mobility import route_between
    items = day['items']
    used = {i.get('id') for i in items} | set(trip.excluded_ids)
    warnings = day.setdefault('warnings', [])

    def offer(start, end, cafe=False):
        anchored = [i for i in items if i.get('lat') is not None and i.get('lon') is not None]
        if not anchored:
            return False
        before = [i for i in anchored if minutes(i['end']) <= start]
        after = [i for i in anchored if minutes(i['start']) >= end]
        a = max(before, key=lambda i: i['end']) if before else None
        b = min(after, key=lambda i: i['start']) if after else None
        anchor = a or b
        if anchor is None:
            return False
        candidates = food_candidates(trip.region, trip.cuisines, cafe,
            (anchor['lat'], anchor['lon']), 1 if trip.transport == 'walk' else 3)
        day.setdefault('food_recommendations', []).append(dict(kind='cafe' if cafe else 'meal',
            start=hhmm(start), end=hhmm(end), candidates=[p for p in candidates if p['id'] not in used][:4]))
        for candidate in [p for p in candidates if p['id'] not in used][:2]:
            duration = 30 if cafe else 45
            begin, finish = start, end
            before_seconds = after_seconds = 0
            if a:
                route = route_between(a, candidate, trip.transport)
                if route['status'] != 'available':
                    continue
                begin = max(begin, minutes(a['end']) + int((route['duration_s'] + 59) // 60))
                before_seconds = route['duration_s']
            if b:
                route = route_between(candidate, b, trip.transport)
                if route['status'] != 'available':
                    continue
                finish = min(finish, minutes(b['start']) - int((route['duration_s'] + 59) // 60))
                after_seconds = route['duration_s']
            if finish - begin < duration:
                continue
            if any(overlaps(begin, begin + duration, minutes(i['start']), minutes(i['end'])) for i in items):
                continue
            def free_between(lo, hi):
                return hi - lo - sum(max(0, min(hi, minutes(i['end'])) - max(lo, minutes(i['start'])))
                                     for i in items if i is not a and i is not b)
            if a and free_between(minutes(a['end']), begin) * 60 < before_seconds:
                continue
            if b and free_between(begin + duration, minutes(b['start'])) * 60 < after_seconds:
                continue
            items.append(dict(candidate, kind='cafe' if cafe else 'meal', start=hhmm(begin), end=hhmm(begin + duration),
                reason='주변 카페에서 쉬어가기' if cafe else '식사 시간대의 주변 식당 후보 · TourAPI 음식 분류 기준',
                checks=['원천 분류와 실제 메뉴의 일치', '영업시간·휴무', '예약·단체 좌석' if trip.party_type == 'group' else '좌석·식이 제한']))
            used.add(candidate['id'])
            return True
        return False

    # Replace the old unlocated lunch placeholder, preserving the reserved hour.
    for placeholder in [i for i in items if i['kind'] == 'break']:
        items.remove(placeholder)
        if not offer(minutes(placeholder['start']), minutes(placeholder['end'])):
            items.append(placeholder)
            warnings.append(placeholder['title'].split('·')[0]+': 조건과 이동시간에 맞는 식당을 확보하지 못했습니다. 주변 후보의 영업 여부를 확인하세요.')
    lower, upper = map(minutes, (day['day_start'], day['day_end']))
    if upper >= 18 * 60 + 45 and not any(i['kind'] in ('meal','break') and i['start'] >= '17:30' for i in items):
        for start in range(max(lower, 17 * 60 + 30), min(upper - 44, 19 * 60) + 1, 15):
            if not any(overlaps(start, start + 45, minutes(i['start']), minutes(i['end'])) for i in items):
                if offer(start, min(upper, start + 60)):
                    break
    if trip.cafes:
        anchors = sorted([i for i in items if i.get('lat') is not None], key=lambda i: i['start'])
        for a, b in zip(anchors, anchors[1:]):
            start, end = minutes(a['end']) + 15, minutes(b['start']) - 15
            if end - start >= 30 and not any(overlaps(start, end, minutes(i['start']), minutes(i['end'])) for i in items):
                if offer(start, min(end, start + 60), True):
                    break
    items.sort(key=lambda i: i['start'])
