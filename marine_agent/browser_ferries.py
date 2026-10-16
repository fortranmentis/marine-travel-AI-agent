"""Actual KOMSA public-screen observations; never fabricated arrival times."""
from collections import OrderedDict
import copy
import datetime as dt
import re
import threading
import time

from . import providers

SOURCE='https://www.komsa.or.kr/prog/pssgCurState/kor/sub03_0202/list.do'
OFFICES={'전체':'','부산':'C','인천':'D','완도':'E','목포':'F','제주':'G','여수':'H','전북':'J','보령':'K','통영':'L','경북':'M','강원':'N','고흥':'Q'}
HEADERS=['출항시각','여객선명','운항항로명','운항방향','출항지','항로구분','운항구분','사유','출항여부','면허항로']
_cache=OrderedDict()
_lock=threading.Lock()


def unavailable(reason,status='unavailable',**extra):
    return dict(status=status,reason=reason,source_url=SOURCE,rows=[],arrival_verified=False,
                reservation_verified=False,usable_for_planning=False,**extra)


def normalize(raw,office,requested_date=None,now=None):
    now=now or dt.datetime.now(providers.KST)
    match=re.fullmatch(r'\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(\d{1,2}):(\d{2})\s*',str(raw.get('as_of','')))
    if not match or raw.get('headers') != HEADERS:
        return unavailable('공식 화면의 기준시각·표 구조를 확인하지 못했습니다.')
    try: as_of=dt.datetime(*map(int,match.groups()),tzinfo=providers.KST)
    except ValueError: return unavailable('공식 화면의 기준시각이 올바르지 않습니다.')
    if as_of.date()!=now.date() or not dt.timedelta(0)<=now-as_of<=dt.timedelta(minutes=30):
        return unavailable('공식 화면의 운항정보가 오래되었거나 기준시각이 맞지 않습니다.',status='stale',as_of=as_of.isoformat())
    requested_date=requested_date or now.date().isoformat()
    if requested_date!=as_of.date().isoformat():
        return unavailable('이 공식 화면은 오늘 운항정보만 제공합니다. 여행일 시간표로 사용할 수 없습니다.',status='date_unsupported',
                           date=as_of.date().isoformat(),requested_date=requested_date,as_of=as_of.isoformat())
    rows=[]; skipped=0
    for cells in raw.get('rows',[]):
        if len(cells)!=10: skipped+=1;continue
        cells=[str(c).strip()[:250] for c in cells]
        if not re.fullmatch(r'(?:[01]\d|2[0-3])[0-5]\d',cells[0]) or not cells[1] or not cells[2]:
            skipped+=1;continue
        state='reported_normal' if cells[6] in ('정상','증회','증선') else 'not_operating' if cells[6] in ('비운','결항','통제','휴항') else 'unknown'
        rows.append(dict(departure=cells[0][:2]+':'+cells[0][2:],vessel=cells[1],route=cells[2],
                         direction=cells[3],origin=cells[4],route_type=cells[5],operation=cells[6],
                         reason=cells[7],departure_status=cells[8],licensed_route=cells[9],
                         operation_status=state,arrival=None,destination=None,remaining_seats=None,fare=None))
    if not rows and skipped:
        return unavailable('공식 화면에서 유효한 출항편을 읽지 못했습니다.')
    return dict(status='available',office=office,date=as_of.date().isoformat(),requested_date=requested_date,
                as_of=as_of.isoformat(),observed_at=now.isoformat(),source='한국해양교통안전공단 KOMSA',source_url=SOURCE,
                rows=rows,count=len(rows),skipped_rows=skipped,arrival_verified=False,reservation_verified=False,
                usable_for_planning=False,
                note='조회 시점의 당일 운항정보입니다. 정상 표시는 예약·잔여석·향후 운항 보장이 아닙니다. 도착시각이 없어 섬 일정에 자동 확정하지 않습니다.')


def live(office='인천',date=None):
    from .browser_jobs import run
    if office not in OFFICES: raise ValueError('지원하는 운항관리 지역을 선택하세요.')
    date=date or dt.datetime.now(providers.KST).date().isoformat()
    dt.date.fromisoformat(date)
    if date!=dt.datetime.now(providers.KST).date().isoformat():
        return unavailable('공식 화면은 오늘 운항정보만 제공합니다. 오늘 날짜로 조회하세요.',status='date_unsupported',requested_date=date)
    if not _lock.acquire(timeout=2): return unavailable('다른 배편 조회가 진행 중입니다. 잠시 후 다시 시도하세요.')
    try:
        now=time.monotonic();key=(office,date)
        for old in [k for k,v in _cache.items() if v[0]<=now]: del _cache[old]
        if key in _cache:
            value=_cache[key][1]
            if value['status']!='available' or dt.datetime.now(providers.KST)-dt.datetime.fromisoformat(value['as_of'])<=dt.timedelta(minutes=30):
                return dict(copy.deepcopy(value),cached=True)
            del _cache[key]
        try:
            raw=run('marine_agent.browser_ferry_worker',dict(office=office))
            result=normalize(raw,office,date) if raw.get('status')=='ok' else unavailable('공식 운항 화면을 읽지 못했습니다. 원문에서 확인하세요.')
        except Exception: result=unavailable('배편 조회 시간 초과 또는 브라우저 연결 실패입니다. 원문에서 확인하세요.')
        _cache[key]=(time.monotonic()+(300 if result['status']=='available' else 60),copy.deepcopy(result))
        while len(_cache)>16: _cache.popitem(last=False)
        return dict(result,cached=False)
    finally: _lock.release()


def tool_live(office='인천',date=None):
    result=live(office,date)
    return dict(result,rows=result['rows'][:12],truncated=len(result['rows'])>12,
                tool_note='대표 12편만 도구에 전달합니다. 전체는 배편 조회 화면에서 확인하세요. 도착시각·예약은 미확인입니다.')
