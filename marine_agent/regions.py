"""Explicit forecast-name / tourism-administration joins, not official forecast polygons."""
from pydantic import Field
from typing import Annotated

LEGACY = ('영종·용유', '강화', '송도·도심')
AREA_NAMES = {'2':'인천','6':'부산','7':'울산','32':'강원','34':'충남',
              '35':'경북','36':'경남','37':'전북','38':'전남','39':'제주'}


def spec(name, code, cities=(), *, plan=True, sector=None):
    return dict(id=name, title=name, forecast_area=name, area_code=code, province=AREA_NAMES[code],
                municipalities=list(cities), planning_enabled=plan, sector=sector,
                reason='' if plan else '도서 예보 권역 · 왕복 배편·접근 경로 검증 후 일정 지원',
                spatial_note='TourAPI 행정구역 기반 자체 관광 탐색 범위입니다. 공식 예보 영역의 경계가 아닙니다.')


SPECS = {s['id']:s for s in [
    spec('인천내륙','2',('중구','연수구','제물포구')),
    spec('인천북서','2',plan=False),spec('인천남서','2',plan=False),
    spec('강릉','32',('강릉시',)),spec('속초','32',('속초시',)),spec('삼척','32',('삼척시',)),
    spec('태안북부','34',('태안군',),sector='taean-north'),spec('태안남부','34',('태안군',),sector='taean-south'),
    spec('보령','34',('보령시',)),spec('군산','37',('군산시',)),spec('부안','37',('부안군',)),
    spec('영광','38',('영광군',)),spec('해남','38',('해남군',)),
    spec('신안북동','38',plan=False),spec('신안남서','38',plan=False),
    spec('여수내륙','38',('여수시',)),spec('여수도서','38',plan=False),
    spec('통영','36',('통영시',)),spec('거제','36',('거제시',)),spec('고성','36',('고성군',)),
    spec('부산북동','6',('기장군','해운대구')),spec('부산남서','6',('영도구','서구','사하구')),
    spec('울산','7',('동구','북구','울주군')),
    spec('포항','35',('포항시',)),spec('영덕','35',('영덕군',)),
    spec('제주북동','39',('제주시',),sector='jeju-east'),spec('제주북서','39',('제주시',),sector='jeju-west'),
    spec('제주남동','39',('서귀포시',),sector='jeju-east'),spec('제주남서','39',('서귀포시',),sector='jeju-west'),
]}
for name in LEGACY:
    SPECS[name] = dict(spec(name,'2'), forecast_area='인천내륙', legacy=True)

RegionName = Annotated[str, Field(min_length=1,max_length=40,json_schema_extra={'enum':list(SPECS)})]

# Exact TourAPI records inspected in the national catalog. These are search
# reference points, not lodging, actual trip origins, or official forecast sites.
GATEWAYS = {'인천내륙':'2601714','강릉':'2773046','속초':'125779','삼척':'127872',
    '태안북부':'125842','태안남부':'2638444','보령':'129637','군산':'2605528',
    '부안':'128980','영광':'126289','해남':'130907','여수내륙':'2037308',
    '통영':'753306','거제':'127938','고성':'2652453','부산북동':'128810',
    '부산남서':'126122','울산':'128022','포항':'130083','영덕':'2732161',
    '제주북동':'126451','제주북서':'127870','제주남동':'130474','제주남서':'126449'}


def get(name):
    if name not in SPECS:
        raise ValueError('지원하는 바다여행 권역을 선택하세요.')
    return SPECS[name]


def matches(row, name, catalog):
    from .planner import coords, in_region
    definition=get(name)
    point=coords(row)
    if not point:
        return False
    if name in LEGACY:
        return str(row.get('areacode','2')) == '2' and in_region(*point,name)
    if str(row.get('areacode')) != definition['area_code'] or not definition['planning_enabled']:
        return False
    codes=catalog.get('administrative',{}).get(definition['area_code'],[])
    allowed={str(r['code']) for r in codes if r['name'] in definition['municipalities']}
    if str(row.get('sigungucode')) not in allowed:
        return False
    sector=definition.get('sector')
    return (sector is None or sector=='taean-north' and point[0]>=36.75
            or sector=='taean-south' and point[0]<36.75
            or sector=='jeju-east' and point[1]>=126.5
            or sector=='jeju-west' and point[1]<126.5)


def gateway(name, catalog=None):
    from . import providers
    from .planner import coords
    c=catalog or providers.catalog()
    row=next((p for p in c['places'] if str(p['contentid'])==GATEWAYS.get(name)),None)
    if not row or not matches(row,name,c):
        return None
    point=coords(row)
    return dict(id=str(row['contentid']),title=row['title'],lat=point[0],lon=point[1])


def overview(date, start='09:00', end='18:00'):
    from . import providers, travel
    c=providers.catalog()
    result=[]
    available={str(p.get('areacode')) for p in c['places']}
    for name,s in SPECS.items():
        if name in LEGACY:
            continue
        row=dict(s)
        row['tourism_loaded']=s['area_code'] in available
        row['planning_enabled']=s['planning_enabled'] and row['tourism_loaded']
        row['gateway']=gateway(name,c) if s['planning_enabled'] else None
        row['planning_enabled']=row['planning_enabled'] and row['gateway'] is not None
        if not row['tourism_loaded']:
            row['reason']='전국 관광정보 수집이 필요합니다.'
        elif s['planning_enabled'] and row['gateway'] is None:
            row['reason']='관광 탐색 기준점 확인이 필요합니다.'
        row['outlook']=travel.sea_outlook(name,date,start,end)
        result.append(row)
    feed=c.get('marine',{}).get('seatrip',{})
    dates=sorted({str(r.get('predcYmd','')).replace('-','') for r in feed.get('rows',[])})
    return dict(date=date, regions=result, collected_at=feed.get('collected_at',c['collected_at']),
                forecast_dates=[f'{d[:4]}-{d[4:6]}-{d[6:]}' for d in dates if len(d)==8],
                source=feed.get('source'),note='지수는 해상 권역 전망이며 육상 관광·배편 운항·현장 통제 여부와 다릅니다.')
