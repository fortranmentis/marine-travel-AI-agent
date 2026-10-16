"""TAGO reference transit and live observations, separated from route feasibility."""
import datetime as dt
import math
import re
from . import transport_api as api


def identifier(value):
    value=str(value)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value):raise ValueError('Invalid transport identifier')
    return value


def point(lat,lon):
    lat,lon=float(lat),float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon) or not 33<=lat<=39 or not 124<=lon<=132:
        raise ValueError('국내 좌표를 입력하세요.')
    return lat,lon


def nearby(lat,lon):
    from .planner import distance
    lat,lon=point(lat,lon)
    result=api.pages('stops','getCrdntPrxmtSttnList',dict(gpsLati=lat,gpsLong=lon),ttl=86400,limit=500)
    rows=[];rejected=0
    for row in result['rows']:
        try:
            p=point(row['gpslati'],row['gpslong']);km=distance((lat,lon),p)
            if km>.6:raise ValueError()
            rows.append(dict(city_code=identifier(row['citycode']),id=identifier(row['nodeid']),
                title=str(row['nodenm'])[:150],stop_number=str(row['nodeno'])[:20] if row.get('nodeno') is not None else None,
                lat=p[0],lon=p[1],distance_m=round(km*1000)))
        except (KeyError,ValueError,TypeError):rejected+=1
    rows.sort(key=lambda r:r['distance_m'])
    return dict(result,rows=rows[:12],returned_count=len(rows[:12]),rejected_rows=rejected,
        truncated=len(rows)>12,
        note='반경 약 500m 정류소 조회입니다. 직선거리이며 실제 도보 접근·횡단 가능 여부는 별도 확인하세요.')


def stop(city,node):
    city,node=identifier(city),identifier(node)
    result=api.pages('bus_arrivals','getSttnAcctoArvlPrearngeInfoList',dict(cityCode=city,nodeId=node),ttl=20,limit=300)
    rows=[]
    for row in result['rows']:
        try:
            seconds=int(row['arrtime'])
            if seconds<0 or str(row.get('nodeid'))!=node:continue
            rows.append(dict(route_id=identifier(row['routeid']),route_name=str(row['routeno'])[:100],
                seconds=seconds,remaining_stops=row.get('arrprevstationcnt'),vehicle_type=row.get('vehicletp')))
        except (KeyError,ValueError,TypeError):continue
    return dict(result,rows=rows,city_code=city,node_id=node,
        note='조회 시점의 도착예정정보입니다. 미래 여행일 시간표가 아니며 운행·저상차 탑승을 보장하지 않습니다.')


def route(city,route_id):
    params=dict(cityCode=identifier(city),routeId=identifier(route_id))
    info=api.request('bus_routes','getRouteInfoIem',params,ttl=86400)
    stops=api.pages('bus_routes','getRouteAcctoThrghSttnList',params,ttl=86400,limit=1000)
    positions=api.pages('bus_positions','getRouteAcctoBusLcList',params,ttl=20,limit=500)
    # Vehicle registrations are unnecessary for the travel UI; retain only public
    # position/stop fields, and validate before plotting or displaying them.
    live=[]
    for row in positions['rows']:
        try:
            lat,lon=point(row['gpslati'],row['gpslong'])
            live.append(dict(lat=lat,lon=lon,stop=str(row.get('nodenm') or '')[:150],order=row.get('nodeord')))
        except (KeyError,TypeError,ValueError):continue
    return dict(status=info['status'],route_id=route_id,info=info,stops=stops,
        positions=dict(positions,rows=live),schedule_verified=False,
        note='첫차·막차는 노선 기점 기준 참고 정보입니다. 정류소별 정확한 출발시각·여행일 운행은 미확인입니다. 정류소 순서는 실제 도로 선형이 아닙니다.')


def stations(keyword):
    result=api.pages('subway','GetKwrdFndSubwaySttnList',dict(subwayStationName=keyword),ttl=86400,limit=1000)
    rows=[]
    for r in result['rows']:
        try:
            if not r.get('subwayStationName'):continue
            rows.append(dict(id=identifier(r['subwayStationId']),title=str(r['subwayStationName'])[:100],line=str(r.get('subwayRouteName') or '')[:100]))
        except (KeyError,ValueError,TypeError):continue
    return dict(result,rows=rows[:30],returned_count=min(len(rows),30),truncated=len(rows)>30)


def subway(station_id,date,direction='U'):
    identifier(station_id)
    day=dt.date.fromisoformat(date);day_type='02' if day.weekday()==5 else '03' if day.weekday()==6 else '01'
    if direction not in ('U','D'):raise ValueError('Invalid direction')
    params=dict(subwayStationId=station_id,dailyTypeCode=day_type,upDownTypeCode=direction)
    times=api.pages('subway','GetSubwaySttnAcctoSchdulList',params,ttl=86400,limit=1500)
    rows=[]
    for row in times['rows']:
        if row.get('depTime') is None or row.get('depTime')=='':continue
        value=str(row['depTime']).zfill(6)
        if not re.fullmatch(r'(?:[01]\d|2[0-9])[0-5]\d[0-5]\d',value):continue
        rows.append(dict(departure=value[:2]+':'+value[2:4],destination=str(row.get('endSubwayStationNm') or '')[:100],
                         service_day_offset=int(value[:2])//24))
    exits=api.pages('subway','GetSubwaySttnExitAcctoBusRouteList',dict(subwayStationId=station_id),ttl=86400,limit=500)
    return dict(status=times['status'],station_id=station_id,date=date,direction=direction,day_type=day_type,
        times=dict(times,rows=sorted(rows,key=lambda r:r['departure'])),exits=exits,schedule_verified=False,
        note='선택 날짜의 요일 유형에 따른 참고 시간표입니다. 공휴일·임시 운행 변경은 미확인입니다. 24시 이상은 영업일 기준 익일 시각입니다.')
