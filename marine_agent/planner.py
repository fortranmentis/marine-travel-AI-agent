import datetime as dt
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import providers, progress

REGIONS = ['영종·용유', '강화', '송도·도심']


class Lock(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date: dt.date
    start: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    end: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    title: str = Field(min_length=1, max_length=100)
    id: str | None = Field(default=None, max_length=20)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    original_kind: Literal['tourism', 'marine'] | None = None


class Trip(BaseModel):
    model_config = ConfigDict(extra='forbid')
    region: Literal['영종·용유', '강화', '송도·도심'] = '영종·용유'
    start_date: dt.date
    days: int = Field(default=2, ge=1, le=3)
    adults: int = Field(default=2, ge=1, le=10)
    child_ages: list[int] = Field(default_factory=list, max_length=8)
    activity: Literal['mudflat', 'beach', 'none'] = 'mudflat'
    transport: Literal['car'] = 'car'
    day_start: str = Field(default='09:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    day_end: str = Field(default='18:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    excluded_ids: list[str] = Field(default_factory=list, max_length=100)
    locked: list[Lock] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def validate_trip(self):
        if self.start_date < dt.datetime.now(providers.KST).date():
            raise ValueError('여행 시작일은 오늘 이후여야 합니다.')
        if any(age < 0 or age > 17 for age in self.child_ages):
            raise ValueError('자녀 나이는 0~17세로 입력하세요.')
        if minutes(self.day_end) - minutes(self.day_start) < 240:
            raise ValueError('하루에 최소 4시간의 여행 시간을 지정하세요.')
        for lock in self.locked:
            if not self.start_date <= lock.date < self.start_date + dt.timedelta(days=self.days):
                raise ValueError('고정 일정 날짜가 여행 기간 밖입니다.')
            if not minutes(self.day_start) <= minutes(lock.start) < minutes(lock.end) <= minutes(self.day_end):
                raise ValueError('고정 일정이 하루 여행 시간 밖이거나 역전되어 있습니다.')
        for i, lock in enumerate(self.locked):
            if any(other.date == lock.date and overlaps(minutes(lock.start), minutes(lock.end), minutes(other.start), minutes(other.end))
                   for other in self.locked[i + 1:]):
                raise ValueError('고정 일정 시간이 겹칩니다.')
        return self


def minutes(value):
    h, m = str(value).split(':')[:2]
    return int(h) * 60 + int(m)


def hhmm(value):
    return f'{value // 60:02d}:{value % 60:02d}'


def overlaps(a, b, c, d):
    return a < d and c < b


def in_region(lat, lon, region):
    if region == '영종·용유':
        return 37.38 <= lat <= 37.57 and 126.34 <= lon <= 126.62
    if region == '강화':
        return 37.58 <= lat <= 37.86 and 126.25 <= lon <= 126.55
    return 37.35 <= lat <= 37.57 and 126.60 <= lon <= 126.83


def coords(row, marine=False):
    try:
        lat, lon = float(row['lat' if marine else 'mapy']), float(row['lot' if marine else 'mapx'])
        return lat, lon
    except (KeyError, ValueError, TypeError):
        return None


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    v = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(v)))


def tourism_candidates(region, keyword='', limit=30):
    c = providers.catalog()
    rows = [p for p in c['places'] if coords(p) and in_region(*coords(p), region)
            and str(p.get('contenttypeid')) in ('12', '14', '28') and keyword.casefold() in p['title'].casefold()]
    return [dict(id=str(p['contentid']), title=p['title'], address=p.get('addr1'),
                 lat=coords(p)[0], lon=coords(p)[1], content_type=str(p['contenttypeid']),
                 family_suitability='unverified', operating_hours='unverified', source='TourAPI') for p in rows[:limit]]


def marine_conditions(region, activity, date):
    dt.date.fromisoformat(date)
    c = providers.catalog()
    data = c['marine'].get(activity, {})
    rows = [r for r in data.get('rows', []) if coords(r, True) and in_region(*coords(r, True), region)
            and str(r.get('predcYmd', '')).replace('-', '') == date.replace('-', '')]
    stale = dt.datetime.fromisoformat(c['collected_at']).date() != dt.datetime.now(providers.KST).date()
    return dict(status='stale' if stale else ('available' if rows else 'no_forecast'), rows=rows,
                collected_at=c['collected_at'], source=data.get('source'),
                spatial_match='regional bounding box; no point-to-point forecast transfer',
                warning='지수는 현장 운영·통제 여부나 어린이 이용 가능 여부를 보장하지 않습니다.')


def eligible_marine(row):
    return row.get('totalIndex') in ('매우좋음', '좋음') and row.get('opnStat') != '폐장'


def validate_schedule(days):
    for day in days:
        slots = sorted(day['items'], key=lambda r: r['start'])
        for slot in slots:
            if minutes(slot['start']) >= minutes(slot['end']):
                raise ValueError('Invalid schedule interval')
        for a, b in zip(slots, slots[1:]):
            if minutes(a['end']) > minutes(b['start']):
                raise ValueError('Schedule overlap')
    return True


def build_plan(trip):
    if isinstance(trip, dict):
        trip = Trip.model_validate(trip)
    progress.emit('data', '인천 관광 후보와 해양예보를 확인하고 있어요.')
    c = providers.catalog()
    candidates = [p for p in tourism_candidates(trip.region, limit=200) if p['id'] not in trip.excluded_ids]
    if not candidates:
        raise ValueError('해당 권역에 사용할 관광 후보가 없습니다. 먼저 데이터를 수집하세요.')
    locked_titles = {lock.title for lock in trip.locked}
    used = {p['id'] for p in candidates if p['title'] in locked_titles}
    days, marine_used = [], False
    source_age = dt.datetime.now(providers.KST) - dt.datetime.fromisoformat(c['collected_at'])
    if source_age > dt.timedelta(days=1):
        raise ValueError('데이터가 24시간 이상 지났습니다. 데이터 수집을 다시 실행하세요.')
    prepared = {}
    for offset in range(trip.days):
        date = trip.start_date + dt.timedelta(days=offset)
        progress.emit('data', f'{date.month}월 {date.day}일 날씨와 해양 활동 시간을 조회하고 있어요.', event='activity')
        conditions = marine_conditions(trip.region, trip.activity, date.isoformat()) if trip.activity != 'none' else dict(status='not_requested', rows=[])
        weather = dict(status='unavailable', warnings_checked=False)
        try:
            weather = providers.weather_for_place(candidates[0]['id'], date.isoformat())
        except Exception:
            pass
        prepared[offset] = (conditions, weather)
    progress.emit('data', '예보·관광 자료 조회를 마쳤어요.', state='completed')
    progress.emit('schedule', '갯벌체험 가능 시간과 점심·고정 일정을 비교하고 있어요.')
    for offset in range(trip.days):
        date = trip.start_date + dt.timedelta(days=offset)
        items = [dict(kind='locked', title=l.title, start=l.start, end=l.end, source='사용자 고정 일정',
                      id=l.id, lat=l.lat, lon=l.lon, original_kind=l.original_kind)
                 for l in trip.locked if l.date == date]
        for item in items:
            match = next((p for p in candidates if (item.get('id') and p['id'] == item['id']) or p['title'] == item['title']), None)
            if match:
                item.update(id=match['id'], lat=match['lat'], lon=match['lon'], original_kind='tourism')
        conditions, weather = prepared[offset]
        if not marine_used and conditions['status'] == 'available':
            for row in conditions['rows']:
                if not eligible_marine(row):
                    continue
                if trip.activity == 'beach':
                    # No swimming slot without site-level operating and age checks.
                    continue
                try:
                    begin = max(minutes(row['mdftExprnBgngTm']) + 30, minutes(trip.day_start) + 30)
                    latest_end = min(minutes(row['mdftExprnEndTm']) - 30, minutes(trip.day_end) - 30)
                except (KeyError, ValueError):
                    continue
                # Preserve lunch and one-hour buffers around fixed reservations.
                blocked = [(minutes(i['start']) - 60, minutes(i['end']) + 60) for i in items] + [(720, 780)]
                starts = [s for s in range(begin, latest_end - 59, 10)
                          if not any(overlaps(s - 30, s + 90, a, b) for a, b in blocked)]
                if not starts:
                    continue
                begin, end = starts[0], starts[0] + 60
                forecasts = weather.get('forecasts', {})
                adverse = any(begin <= minutes(t[:2] + ':' + t[2:]) < end and
                              (str(v.get('PTY', '0')) != '0' or float(v.get('WSD', 0)) >= 8)
                              for t, v in forecasts.items())
                if adverse:
                    continue
                lat, lon = coords(row, True)
                items.extend([
                    dict(kind='buffer', title='체험 준비·현장 확인', start=hhmm(begin - 30), end=hhmm(begin)),
                    dict(kind='marine', title=row['mdftExpcnVlgNm'] + ' 갯벌체험 후보', start=hhmm(begin), end=hhmm(end),
                         lat=lat, lon=lon, forecast=row, source=conditions['source'],
                         reason='좋음 이상 지수와 예보상 체험 시간 범위 안에 배치',
                         checks=['현장 통제·특보', '체험장 운영·예약', '자녀 이용 연령', '입장·퇴장 시간']),
                    dict(kind='buffer', title='환복·휴식', start=hhmm(end), end=hhmm(end + 30))])
                marine_used = True
                break
        # Explicit lunch; skip when a user reservation already occupies the interval.
        if minutes(trip.day_start) <= 720 and minutes(trip.day_end) >= 780 and not any(overlaps(720, 780, minutes(i['start']), minutes(i['end'])) for i in items):
            items.append(dict(kind='break', title='점심·휴식 (장소 미정)', start='12:00', end='13:00'))
        last_point = next(((i['lat'], i['lon']) for i in items if i.get('lat') is not None and i.get('lon') is not None), None)
        count = 0
        tourism_budget = max(0, 2 - sum(i['kind'] in ('locked', 'marine') for i in items))
        for start in range(max(600, minutes(trip.day_start) + 60), minutes(trip.day_end) - 89, 30):
            if count >= tourism_budget:
                break
            end = start + 90
            if any(overlaps(start - 60, end + 60, minutes(i['start']), minutes(i['end'])) for i in items if i['kind'] != 'break'):
                continue
            if any(overlaps(start, end, minutes(i['start']), minutes(i['end'])) for i in items):
                continue
            available = [p for p in candidates if p['id'] not in used and (last_point is None or distance(last_point, (p['lat'], p['lon'])) <= 12)]
            if not available:
                continue
            available.sort(key=lambda p: (distance(last_point, (p['lat'], p['lon'])) if last_point else 0, p['title']))
            place = available[0]
            used.add(place['id'])
            last_point = (place['lat'], place['lon'])
            items.append(dict(place, kind='tourism', start=hhmm(start), end=hhmm(end), source=c['tourism_source'],
                              reason='같은 권역의 관광 후보; 방문 시간은 가정값', checks=['운영시간·휴무', '가족 적합성', '실제 경로·이동시간']))
            count += 1
            if count >= tourism_budget:
                break
        alternatives = [p for p in candidates if p['id'] not in used][:6]
        days.append(dict(date=date.isoformat(), items=sorted(items, key=lambda i: i['start']), marine=conditions,
                         weather=weather, alternatives=alternatives,
                         alternative_note='같은 권역의 대체 후보입니다. 실내 여부·운영시간·가족 적합성은 개별 확인 필요'))
    for day in days:
        day['alternatives'] = [p for p in candidates if p['id'] not in used][:6]
    validate_schedule(days)
    progress.emit('schedule', '시간 겹침과 고정 일정을 확인했어요.', state='completed')
    return dict(status='provisional', trip=trip.model_dump(mode='json'), days=days,
                generated_at=dt.datetime.now(providers.KST).isoformat(), collected_at=c['collected_at'],
                marine_scheduled=marine_used,
                notices=['검토용 초안입니다. 특보·현장 통제·체험장 운영·자녀 연령 조건은 미확인입니다.',
                         '차량 여행만 지원합니다. 배편이 필요한 섬은 초기 권역에서 제외합니다.',
                         '초기 방문 배치는 직선거리와 이동·휴식 가정을 사용합니다. 지도에 표시된 도로 경로·시간과 여유 시간 경고를 확인하세요.',
                         '예보 없음·나쁨·폐장·보통 지수는 체험 추천 근거로 사용하지 않습니다.',
                         '해수욕은 개장·연령·현장 조건 검증 전까지 자동 배치하지 않습니다.'])
