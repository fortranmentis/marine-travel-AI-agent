"""Opt-in, reviewed passenger-ferry day trips. No synthetic departure/arrival times."""
import datetime as dt
import json
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import providers
from .config import DATA


class IslandUnavailable(ValueError):
    """Safe, user-facing validation error without upstream request data."""


class Point(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str
    lat: float = Field(ge=33, le=39)
    lon: float = Field(ge=124, le=132)


class Crossing(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date: dt.date
    direction: Literal['outbound', 'return']
    departure: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    arrival: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    vessel: str = Field(min_length=1)
    status: Literal['scheduled', 'cancelled', 'unknown']
    source_url: str

    @model_validator(mode='after')
    def valid(self):
        if self.departure >= self.arrival:
            raise ValueError('동일 날짜의 실제 출항·도착시각이 필요합니다.')
        if urlsplit(self.source_url).scheme != 'https':
            raise ValueError('출처 HTTPS URL이 필요합니다.')
        return self


class Island(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z0-9-]{1,60}$')
    title: str
    reviewed_at: dt.datetime
    mainland_port: Point
    island_port: Point
    place_ids: list[str] = Field(min_length=1)
    checkin_minutes: int = Field(default=40, ge=30, le=120)
    crossings: list[Crossing]

    @model_validator(mode='after')
    def dated(self):
        if self.reviewed_at.utcoffset() is None:
            raise ValueError('검증 시각에 시간대가 필요합니다.')
        return self


def reviewed():
    path = DATA / 'reviewed_islands.json'
    if not path.exists():
        return []
    try:
        values = [Island.model_validate(r) for r in json.loads(path.read_text(encoding='utf-8'))]
        if len({i.id for i in values}) != len(values):
            return []
        now = dt.datetime.now(providers.KST)
        return [i for i in values if dt.timedelta(0) <= now - i.reviewed_at <= dt.timedelta(hours=24)]
    except (ValueError, TypeError, OSError):
        return []


def resolve(island_id):
    match = next((i for i in reviewed() if i.id == island_id), None)
    if match is None:
        raise IslandUnavailable('해당 섬의 최신 검증 자료가 없습니다. 배편 연결·검증 후 이용하세요.')
    return match


def candidates(island, excluded):
    from .planner import coords
    return [dict(id=str(p['contentid']), title=p['title'], address=p.get('addr1'),
                 lat=coords(p)[0], lon=coords(p)[1], source='TourAPI', content_type=str(p['contenttypeid']))
            for p in providers.catalog()['places'] if str(p['contentid']) in island.place_ids
            and str(p['contentid']) not in excluded and coords(p) and str(p.get('contenttypeid')) in ('12','14','28')]


def day_crossings(island, date, start, end):
    from .planner import minutes, hhmm
    rows = [c for c in island.crossings if c.date.isoformat() == date and c.status == 'scheduled']
    pairs = [(a, b) for a in rows for b in rows if a.direction == 'outbound' and b.direction == 'return'
             and minutes(a.departure) - island.checkin_minutes >= minutes(start)
             and minutes(a.arrival) + 120 <= minutes(b.departure) - island.checkin_minutes
             and b.arrival <= end]
    if not pairs:
        raise IslandUnavailable('일별 시간 안의 왕복 여객선·섬 체류시간을 확보하지 못했습니다.')
    a, b = max(pairs, key=lambda pair: minutes(pair[1].departure) - minutes(pair[0].arrival))
    slots = []
    for c in (a, b):
        origin, destination = (island.mainland_port, island.island_port) if c.direction == 'outbound' else (island.island_port, island.mainland_port)
        slots.extend([
            dict(kind='buffer', title=origin.title+' 발권·승선 확인', start=hhmm(minutes(c.departure) - island.checkin_minutes), end=c.departure),
            dict(kind='ferry', title=origin.title+' → '+destination.title, start=c.departure, end=c.arrival,
                vessel=c.vessel, source=c.source_url,
                reason='검증한 여객선 시간표 · 당일 운항·예약·잔여석은 별도 확인',
                checks=['출항 통제·결항', '승선 예약·신분증', '여객 승선 전용·차량 선적 제외'])])
        if c.direction == 'outbound':
            slots.append(dict(kind='port', title=destination.title+' 하선·준비',
                lat=destination.lat, lon=destination.lon, start=c.arrival, end=hhmm(minutes(c.arrival) + 15)))
        else:
            slots[-2].update(kind='port', lat=origin.lat, lon=origin.lon)
    return dict(island_start=hhmm(minutes(a.arrival) + 15),
                island_end=hhmm(minutes(b.departure) - island.checkin_minutes), items=slots,
                port=island.island_port.model_dump())
