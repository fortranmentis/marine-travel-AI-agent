"""Deterministic travel policy. Thresholds are product preferences, not safety limits."""
import datetime as dt
import json
import math
import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .config import DATA
from . import providers

VERSION = '1.0'
RAIN_PROBABILITY = 60
WIND_MS = 8


class VenueReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^\d{1,20}$')
    environment: Literal['indoor', 'outdoor', 'mixed', 'unknown'] = 'unknown'
    source_url: str
    checked_at: dt.datetime
    valid_until: dt.date
    # Explicit date overrides; absent dates mean unknown, not closed.
    hours: dict[dt.date, list[tuple[str, str]]] = Field(default_factory=dict)
    closed_dates: list[dt.date] = Field(default_factory=list)
    min_age: int | None = Field(default=None, ge=0, le=100)
    max_party: int | None = Field(default=None, ge=1, le=10000)


def reviewed_venues():
    """Local, source-reviewed facts only. Never consume model-generated classifications."""
    path = DATA / 'reviewed_venues.json'
    try:
        rows = [VenueReview.model_validate(v) for v in json.loads(path.read_text(encoding='utf-8'))]
        if len({r.id for r in rows}) != len(rows):
            return {}
        now = dt.datetime.now(providers.KST)
        result = {}
        from .planner import minutes
        for row in rows:
            url = urlsplit(row.source_url)
            if (url.scheme != 'https' or not url.hostname or url.username or url.password or url.query
                    or row.checked_at.utcoffset() is None or not dt.timedelta(0) <= now-row.checked_at <= dt.timedelta(days=30)
                    or row.valid_until < now.date()):
                continue
            if any(not (re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',a) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',b) and minutes(a)<minutes(b))
                   for periods in row.hours.values() for a,b in periods):
                continue
            result[row.id] = row.model_dump(mode='json')
        return result
    except (OSError, ValueError, TypeError):
        return {}


def number(value):
    if isinstance(value,bool): return None
    try:
        v = float(value)
        return v if math.isfinite(v) and v >= 0 else None
    except (TypeError, ValueError):
        return None


def weather_window(weather, start, end):
    """Hourly intervals overlap visits AND access buffers; missing values stay unknown."""
    from .planner import minutes
    usable = weather.get('status') == 'available'
    issue = weather.get('issue_at')
    if issue:
        try:
            issued = dt.datetime.fromisoformat(issue)
            usable &= issued.utcoffset() is not None and dt.timedelta(0) <= dt.datetime.now(providers.KST)-issued <= dt.timedelta(hours=12)
        except (TypeError, ValueError):
            usable = False
    rows, covered = [], set()
    if usable:
        for hour, row in (weather.get('forecasts') or {}).items():
            try:
                h = minutes(hour[:2]+':'+hour[2:])
            except (ValueError, TypeError):
                continue
            if max(start, h) < min(end, h+60):
                rows.append(row)
                if number(row.get('PTY')) is not None:
                    covered.update(range(max(start,h), min(end,h+60)))
    rain = any(number(r.get('PTY')) not in (None, 0) for r in rows)
    possible = any((number(r.get('POP')) or 0) >= RAIN_PROBABILITY for r in rows)
    wind = any((number(r.get('WSD')) or 0) >= WIND_MS for r in rows)
    return dict(rain=rain, possible_rain=possible, wind=wind, complete=len(covered)==end-start and end>start,
                status='available' if rows else 'unknown')


def evidence(place, reviews, date):
    value = reviews.get(str(place.get('id')), {})
    return value if value.get('valid_until', '') >= date else {}


def profile(trip):
    young = bool(trip.child_ages) and min(trip.child_ages) <= 5
    relaxed = trip.pace == 'relaxed' or young
    return dict(young_children=young, visit_minutes=60 if relaxed else 90,
                rest_minutes=30 if relaxed else 15 if trip.party_type == 'group' or trip.pace=='normal' else 0,
                route_buffer_minutes=15 if relaxed or trip.party_type == 'group' else 0,
                walk_leg_m=800 if relaxed else 1500,
                walk_day_m=2500 if relaxed else 5000)


def walk_fits(items, trip, weather, mode):
    if mode != 'walk': return True
    from .mobility import route_between
    from .planner import minutes
    stops = sorted([i for i in items if i.get('lat') is not None and i.get('lon') is not None],key=lambda i:i['start'])
    total = 0
    p = profile(trip)
    for a,b in zip(stops,stops[1:]):
        route = route_between(a,b,'walk')
        km = number(route.get('distance_m'))
        if route.get('status')!='available' or km is None: return False
        wet = weather_window(weather,minutes(a['end']),minutes(b['start']))
        leg_limit = min(p['walk_leg_m'],500) if wet['rain'] or wet['wind'] else p['walk_leg_m']
        total += km
        if km > leg_limit: return False
    return total <= p['walk_day_m']


def assess(place, trip, date, start, end, weather, reviews, mode=None):
    from .planner import minutes
    start = minutes(start) if isinstance(start,str) else start
    end = minutes(end) if isinstance(end,str) else end
    fact = evidence(place, reviews, date)
    environment = fact.get('environment', 'unknown')
    mode = mode or trip.transport
    # Include a short access window before/after a visit; it is not a forecast for each route point.
    wx = weather_window(weather, max(minutes(trip.hours(dt.date.fromisoformat(date))[0]),start-30),
                        min(minutes(trip.hours(dt.date.fromisoformat(date))[1]),end+30))
    reasons = []
    if date in fact.get('closed_dates',[]): reasons.append('venue_closed')
    hours = fact.get('hours',{})
    if date in hours and not any(minutes(a)<=start and end<=minutes(b) for a,b in hours[date]):
        reasons.append('outside_hours')
    if trip.child_ages and fact.get('min_age') is not None and min(trip.child_ages)<fact['min_age']:
        reasons.append('age_restriction')
    if fact.get('max_party') is not None and trip.adults+trip.child_count>fact['max_party']:
        reasons.append('party_capacity')
    if wx['rain'] and environment != 'indoor': reasons.append('rain_indoor_required')
    if wx['wind'] and environment != 'indoor': reasons.append('wind_indoor_required')
    rank = (0 if environment=='indoor' else 1) if wx['possible_rain'] else (1 if environment=='indoor' else 0)
    return dict(allowed=not reasons, codes=reasons, environment=environment, weather=wx, rank=rank,
                source_url=fact.get('source_url'), checked_at=fact.get('checked_at'))


MESSAGES = {
    'rain_indoor_required':'강수 예보 시간대에는 실내로 확인된 관광지만 배치했습니다. 후보가 부족하면 방문 수를 줄입니다.',
    'wind_indoor_required':'강풍 예보 시간대에는 노출된 야외·실내 미확인 관광지의 배치를 제한했습니다.',
    'venue_closed':'확인된 휴무일과 겹치는 후보를 제외했습니다.',
    'outside_hours':'확인된 운영시간 안에 방문을 마칠 수 없는 후보를 제외했습니다.',
    'age_restriction':'확인된 최소 이용 연령에 맞지 않는 후보를 제외했습니다.',
    'party_capacity':'확인된 수용인원보다 여행 인원이 많아 해당 후보를 제외했습니다.',
    'walk_budget':'도보 구간 또는 하루 누적 이동량 기준을 초과하는 방문을 줄였습니다. 필요하면 대중교통 전환을 선택하세요.',
    'route_unavailable':'방문 사이 경로를 확보하지 못한 후보를 배치하지 않았습니다.',
    'route_time':'이동·휴식 여유 시간을 확보할 수 없는 후보를 제외했습니다.',
}


def explain(day, trip, reviews, rejected):
    from .planner import minutes
    weather = weather_window(day['weather'],minutes(day['day_start']),minutes(day['day_end']))
    decisions = [dict(code=code,message=MESSAGES[code]) for code in sorted(rejected) if code in MESSAGES]
    if weather['rain']: decisions.append(dict(code='rain',message='강수 예보와 실내 여부를 방문·접근 시간대별로 비교했습니다.'))
    if weather['possible_rain'] and not weather['rain']:
        decisions.append(dict(code='rain_possible',message='강수확률이 높아 실내 후보를 우선했습니다. 비가 확정된 것으로 처리하지 않았습니다.'))
    if not weather['complete']:
        decisions.append(dict(code='weather_incomplete',message='여행 시간대 예보가 없거나 일부 누락됐습니다. 맑음으로 가정하지 않았으며 조건부 초안입니다.'))
    for item in day['items']:
        if item['kind'] != 'locked': continue
        check = assess(item,trip,day['date'],item['start'],item['end'],day['weather'],reviews,day['transport'])
        if check['codes']:
            decisions.append(dict(code='locked_conflict',message=f"고정 일정 ‘{item['title']}’은 유지했습니다. 날씨·운영·이용 조건 충돌을 확인하고 예약 변경 여부를 결정하세요.",reasons=check['codes']))
    p = profile(trip)
    if p['young_children']:
        decisions.append(dict(code='child_rest',message='영유아 동반을 반영해 방문 시간을 줄이고 이동·휴식 여유를 확보했습니다. 유모차 접근과 이용 조건은 별도 확인하세요.'))
    if trip.party_type=='group':
        decisions.append(dict(code='group_buffer',message='단체 집결 여유를 반영했습니다. 식당 좌석·체험 수용인원·예약은 별도 확인하세요.'))
    if trip.child_ages:
        decisions.append(dict(code='child_checks',message='자녀 나이와 인원을 반영했습니다. 연령 제한 자료가 없는 장소는 이용 가능으로 확정하지 않습니다.'))
    locked = sorted([i for i in day['items'] if i['kind']=='locked' and i.get('lat') is not None and i.get('lon') is not None],key=lambda i:i['start'])
    if len(locked)>1:
        from .mobility import route_between
        for a,b in zip(locked,locked[1:]):
            route = route_between(a,b,day['transport'])
            if route.get('status')!='available' or route['duration_s']>(minutes(b['start'])-minutes(a['end']))*60:
                decisions.append(dict(code='locked_route_conflict',message='고정 일정 사이의 이동 경로·시간을 확보하지 못했습니다. 예약을 유지했으므로 시간을 직접 조정해 주세요.'))
                break
    day['rule_summary'] = dict(version=VERSION,decisions=decisions,profile=p,
                              reviewed_places=len(reviews),
                              thresholds=dict(rain_probability=RAIN_PROBABILITY,wind_ms=WIND_MS),
                              note='서비스 편의상 적용한 배치 기준이며 공식 안전 기준이 아닙니다. 대표 지점 예보를 사용합니다.')
    day['warnings'].extend(d['message'] for d in decisions)
