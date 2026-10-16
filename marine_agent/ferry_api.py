"""Exact pilot port joins and date-specific ferry reference timetables."""
import datetime as dt
import re
from . import transport_api as api

# IDs and names read from TAGO GetPortList, not guessed from a place title.
PORTS={
 '인천북서':(('SEA10100','인천','인천'),('SEA10030','백령도','백령')),
 '인천남서':(('SEA10100','인천','인천'),('SEA10110','덕적도_진리','덕적')),
 '신안남서':(('SEA31010','목포','목포'),('SEA32390','대흑산도','흑산')),
 '여수도서':(('SEA96140','여수','여수'),('SEA31310','거문도','거문')),
}
ALIASES={'코리아피스호':'코리아피스','코리아프린세스호':'코리아프린세스',
         '코리아익스프레스':'코리아익스프레스카훼리'}


def timestamp(value):
    value=str(value)
    if not re.fullmatch(r'\d{12}',value):raise ValueError('Invalid sailing timestamp')
    return dt.datetime.strptime(value,'%Y%m%d%H%M').replace(tzinfo=api.KST)


def normalize(result,origin,destination,date):
    rows=[];rejected=0;seen=set()
    shared={}
    for raw in result['rows']:
        identity=(str(raw.get('depPlaceNm') or ''),str(raw.get('vihicleNm') or '').strip(),str(raw.get('depPlandTime')),str(raw.get('arrPlandTime')))
        shared.setdefault(identity,set()).add(str(raw.get('arrPlaceNm') or ''))
    for raw in result['rows']:
        if raw.get('depPlaceNm')!=origin or raw.get('arrPlaceNm')!=destination:continue
        try:
            start,end=timestamp(raw['depPlandTime']),timestamp(raw['arrPlandTime'])
            if start.date().isoformat()!=date or not start<end<=start+dt.timedelta(hours=24):raise ValueError()
            if not isinstance(raw.get('vihicleNm'),str):raise ValueError()
            vessel=raw['vihicleNm'].strip();key=(start,end,vessel)
            if not vessel or key in seen:raise ValueError()
            seen.add(key)
            fare=raw.get('charge')
            rows.append(dict(origin=origin,destination=destination,departure=start.isoformat(),arrival=end.isoformat(),
                vessel=vessel,fare_krw=fare if isinstance(fare,(int,float)) and fare>=0 else None,
                arrival_verified=False,operation_status='not_checked',timetable_source=result['source_url'],
                quality_flags=['shared_arrival_across_destinations'] if len(shared[(origin,vessel,str(raw['depPlandTime']),str(raw['arrPlandTime']))])>1 else []))
        except (KeyError,ValueError,TypeError):rejected+=1
    return rows,rejected


def komsa(date,vessel):
    return api.pages('komsa','get-oprt-schd-info-v2',dict(rlvtYmd=date.replace('-',''),psnshpNm=vessel),
                     ttl=300 if date==dt.datetime.now(api.KST).date().isoformat() else 1800,limit=500)


def reconcile(row,records,date,origin,destination):
    expected=dt.datetime.fromisoformat(row['departure'])
    vessel=ALIASES.get(row['vessel'],row['vessel'])
    matches=[]
    for r in records['rows']:
        time=str(r.get('sail_tm') or '').zfill(4)
        if (str(r.get('rlvt_ymd'))==date.replace('-','') and r.get('psnshp_nm')==vessel
            and r.get('oport_nm')==origin and r.get('dest_nm')==destination and time==expected.strftime('%H%M')):
            matches.append(r)
    if len(matches)!=1:return dict(row,operation_status='unmatched',operation_source=records['source_url'])
    matched=matches[0];state=str(matched.get('nvg_se_nm') or '')
    reason=matched.get('cntrl_rsn_nm') or matched.get('nnavi_rsn_nm') or matched.get('cnls_etc_rsn')
    # Departure/arrival time not supplied by KOMSA is never inferred from its
    # direction/status. Even a matching departure does not validate TAGO arrival.
    return dict(row,operation_status='not_operating' if state in ('비운','비운항','결항','통제','운항통제','휴항') or reason else
                'reported_normal' if state in ('정상','증회','증선') else 'unknown',
                operation_label=state,departure_status=matched.get('nvg_stts_nm'),
                reason=reason,
                operation_source=records['source_url'],departure_matched=True)


def timetables(region,date):
    if region not in PORTS:raise ValueError('배편 시범 권역을 선택하세요.')
    dt.date.fromisoformat(date)
    a,b=PORTS[region]
    ports=api.pages('ship','GetPortList',ttl=86400,limit=2000)
    valid={(str(p.get('nodeId')),p.get('nodeNm')) for p in ports['rows']}
    if (a[0],a[1]) not in valid or (b[0],b[1]) not in valid:
        return dict(status='unavailable',region=region,date=date,rows=[],pairs=[],pair_count=0,rejected_rows=0,
            observed_at=dt.datetime.now(api.KST).isoformat(),roundtrip_verified=False,usable_for_planning=False,
            reason='공식 항구 ID·명칭을 확인하지 못했습니다.',port_source_status=ports['status'])
    legs=[];statuses=[];rejected=0
    for origin,destination in ((a,b),(b,a)):
        response=api.pages('ship','GetShipOpratInfoList',dict(depNodeId=origin[0],depPlandTime=date.replace('-','')),ttl=300,limit=1000)
        statuses.append(response['status']);rows,bad=normalize(response,origin[1],destination[1],date);rejected+=bad
        legs.extend((row,origin[2],destination[2]) for row in rows)
    # At most three vessels per request, preserving quota for the small KOMSA
    # development account. Unchecked additional rows stay explicit references.
    checks={}
    for row,origin,destination in legs:
        vessel=ALIASES.get(row['vessel'],row['vessel'])
        if vessel not in checks and len(checks)<3:checks[vessel]=komsa(date,vessel)
    rows=[]
    for row,origin,destination in legs:
        evidence=checks.get(ALIASES.get(row['vessel'],row['vessel']))
        rows.append(reconcile(row,evidence,date,origin,destination) if evidence else row)
    outbound=[r for r in rows if r['origin']==a[1] and r['operation_status']=='reported_normal' and not r['quality_flags']]
    returning=[r for r in rows if r['origin']==b[1] and r['operation_status']=='reported_normal' and not r['quality_flags']]
    pairs=[]
    for out in outbound:
        for back in returning:
            available=(dt.datetime.fromisoformat(back['departure'])-dt.datetime.fromisoformat(out['arrival'])).total_seconds()/60-40-15
            if available>=120 and dt.datetime.fromisoformat(back['arrival']).date().isoformat()==date:
                pairs.append(dict(outbound=out,returning=back,island_minutes=int(available),roundtrip_verified=False,
                    usable_for_planning=False))
    pairs.sort(key=lambda r:-r['island_minutes'])
    return dict(status='available' if rows else 'no_data' if all(s in ('available','no_data') for s in statuses) else 'unavailable',
        region=region,date=date,rows=rows,pairs=pairs[:8],pair_count=len(pairs),rejected_rows=rejected,
        observed_at=dt.datetime.now(api.KST).isoformat(),roundtrip_verified=False,usable_for_planning=False,
        note='TAGO 출도착 예정시간과 KOMSA 출항 대조 결과입니다. 도착시각·경유항 시간의 독립 검증, 예약·잔여석·항구 접근은 미확인입니다. 참고 조합을 확정 일정에 자동 적용하지 않습니다.')
