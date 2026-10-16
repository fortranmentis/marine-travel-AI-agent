"""Explicit island tourism scopes. Ferry observations do not verify access."""
import datetime as dt
from . import providers

# Exact TourAPI IDs inspected in the coastal catalog. These are application
# pilot scopes, not official KHOA forecast polygons or port-coordinate matches.
PROFILES = {
    '인천북서': dict(title='백령도', office='인천', access='ferry',
        ids=('1932853','561002','560981','560996','2932000','2932002'),
        routes=('인천-백령',), ports=('인천','백령')),
    '인천남서': dict(title='덕적도', office='인천', access='ferry',
        ids=('780350','2782235'), routes=('인천-덕적',), ports=('인천','덕적')),
    '신안북동': dict(title='증도', office='목포', access='bridge',
        ids=('619141','2723780','1279369','778219','2723802'),
        food_ids=('135091',), routes=(), ports=()),
    '신안남서': dict(title='흑산도', office='목포', access='ferry',
        ids=('126301',), routes=('목포-홍도','목포-흑산'), ports=('목포','흑산')),
    '여수도서': dict(title='거문도', office='여수', access='ferry',
        ids=('2723663','129151','988129'), routes=('여수-거문',), ports=('여수','거문')),
}


def get(region):
    return PROFILES.get(region)


def access_info(region, date, *, lookup=True):
    """Keep ferry evidence outside timed slots; missing arrival stays unknown."""
    profile=get(region)
    if not profile: return None
    result=dict(island=profile['title'],mode=profile['access'],office=profile['office'],
        status='unconfirmed' if profile['access']=='ferry' else 'bridge_route',
        travel_date=date,roundtrip_verified=False,arrival_verified=False,
        mainland_access_verified=False,booking_verified=False,
        mainland_port=profile['ports'][0] if profile['ports'] else None,
        island_port=profile['ports'][1] if profile['ports'] else None,
        source_url='https://www.komsa.or.kr/prog/pssgCurState/kor/sub03_0202/list.do',
        rows=[],operation_status='not_requested',
        note='교량 연결 관광 범위입니다. 지도는 관광지 사이 경로이며 숙소·실제 출발지 접근은 별도 확인합니다.')
    if profile['access']=='bridge': return result
    result['note']='왕복 배편 미확정 · 섬 내 관광 초안입니다. 일별 시작·마침은 섬에 머무를 계획 시간이며 입출도 시간은 포함하지 않습니다. 출발항 접근·도착시각·예약·차량 선적은 미확인입니다.'
    if date!=dt.datetime.now(providers.KST).date().isoformat():
        result['operation_status']='date_unsupported'
        result['operation_note']='미래 여행일 배편은 현재 당일 운항정보로 확인할 수 없습니다.'
        return result
    if not lookup: return result
    from .browser_ferries import live
    try: observation=live(profile['office'],date)
    except Exception: observation=dict(status='unavailable',rows=[],reason='공식 배편 정보를 확인하지 못했습니다.')
    result.update(operation_status=observation['status'],as_of=observation.get('as_of'),
                  observed_at=observation.get('observed_at'),operation_note=observation.get('reason') or observation.get('note'))
    if observation['status']=='available':
        # Exact licensed-route allowlist only. Circular/multi-stop routes do not
        # become an inferred outbound/return pair or island departure time.
        result['rows']=[r for r in observation['rows'] if r['licensed_route'] in profile['routes']]
        result['matching_count']=len(result['rows'])
        result['operation_note']='관련 면허항로의 당일 관측입니다. 경유항 도착·출발시각과 승선 가능 여부를 보장하지 않습니다.'
    return result
