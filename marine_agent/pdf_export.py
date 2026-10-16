"""Network-free PDF export of an existing, revision-checked plan snapshot."""
from functools import lru_cache
from io import BytesIO
import math
import os
from pathlib import Path
import threading
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak

_font_lock = threading.Lock()
_export_lock = threading.Lock()
MODES = {'car':'자차', 'walk':'도보', 'transit':'대중교통', 'bus':'버스', 'subway':'지하철', 'ferry':'여객선'}


class PdfUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def font_name():
    candidates = [os.environ.get('PDF_FONT_PATH',''), 'C:/Windows/Fonts/malgun.ttf',
                  '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
                  '/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf']
    path = next((Path(p) for p in candidates if p and Path(p).is_file()), None)
    if path is None:
        raise PdfUnavailable('한국어 PDF 폰트가 없습니다. PDF_FONT_PATH에 한글 TTF 폰트를 설정하세요.')
    with _font_lock:
        if 'MarineKorean' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('MarineKorean', str(path)))
    return 'MarineKorean'


def text(value):
    return escape(str(value or '')).replace('\n','<br/>')


def route_text(leg):
    duration = leg.get('duration_s')
    if leg.get('status') != 'available' or not isinstance(duration,(int,float)) or not math.isfinite(duration):
        return '이동 경로·시간 미확인: ' + str(leg.get('reason') or '웹 일정에서 확인하세요.')
    sections = leg.get('sections') or []
    mode = ' + '.join(dict.fromkeys(MODES.get(s.get('mode'),'이동') for s in sections)) if sections else MODES.get(leg.get('mode'),'이동')
    summary = f'{mode} 약 {math.ceil(duration/60)}분'
    distance = leg.get('distance_m')
    if isinstance(distance,(int,float)) and math.isfinite(distance):
        summary += f' · {distance/1000:.1f}km'
    details = [' '.join(filter(None,[MODES.get(s.get('mode'),'이동'), '/'.join(filter(None,s.get('lines') or [])),
                f"{s['minutes']}분" if s.get('minutes') is not None else '',
                f"{s['start']} → {s['end']}" if s.get('start') and s.get('end') else ''])) for s in sections]
    if details: summary += '\n' + ' → '.join(details)
    if leg.get('fits_schedule') is False: summary += '\n이동 여유 시간 부족'
    if leg.get('note'): summary += '\n' + leg['note']
    if leg.get('source'): summary += '\n출처: ' + leg['source']
    return summary


def weather_text(weather,start='00:00',end='23:59'):
    hourly = [row for hour,row in (weather.get('forecasts') or {}).items() if start.replace(':','')<=hour<=end.replace(':','')]
    def values(key):
        result=[]
        for row in hourly:
            try:
                value=float(row[key])
                if math.isfinite(value) and value > -900: result.append(value)
            except (KeyError,TypeError,ValueError): pass
        return result
    temperatures, rain, wind = values('TMP'),values('POP'),values('WSD')
    parts=[f'기온 {min(temperatures):g}~{max(temperatures):g}°C' if temperatures else '기온 미확인',
           f'최대 강수확률 {max(rain):g}%' if rain else '강수확률 미확인',
           f'최대 풍속 {max(wind):g}m/s' if wind else '풍속 미확인']
    return ' · '.join(parts) + f'\n{start}~{end} 대표 지점 예보 · 특보·현장 통제 미확인' + ('\n발표: '+weather['issue_at'] if weather.get('issue_at') else '')


def transfer_legs(day,route):
    stops=[(n,i) for n,i in enumerate(day['items']) if i['kind'] in ('tourism','marine','locked','meal','cafe','port')]
    result={}
    for (n,a),(m,b) in zip(stops,stops[1:]):
        if any(i['kind']=='ferry' for i in day['items'][n+1:m]): continue
        leg=next((r for r in route.get('legs',[]) if r['from_slot']==a.get('slot_id') and r['to_slot']==b.get('slot_id')),None)
        result[b.get('slot_id')]=leg or dict(from_slot=a.get('slot_id'),to_slot=b.get('slot_id'),status='unavailable',reason='이동 경로를 확인하지 못했습니다.')
    return result


def create_pdf(plan):
    if not _export_lock.acquire(timeout=2):
        raise PdfUnavailable('다른 PDF를 생성 중입니다. 잠시 후 다시 시도하세요.')
    try: return _create_pdf(plan)
    finally: _export_lock.release()


def _create_pdf(plan):
    font = font_name()
    output = BytesIO()
    teal, muted = colors.HexColor('#126c70'), colors.HexColor('#5c706c')
    body = ParagraphStyle('MarineBody',fontName=font,fontSize=9.5,leading=15,wordWrap='CJK',spaceAfter=5)
    title = ParagraphStyle('MarineTitle',parent=body,fontSize=23,leading=32,textColor=teal,spaceAfter=14)
    heading = ParagraphStyle('MarineHeading',parent=body,fontSize=15,leading=22,textColor=teal,spaceAfter=10)
    small = ParagraphStyle('MarineSmall',parent=body,fontSize=8,leading=12,textColor=muted,spaceAfter=3)
    def p(value,style=body): return Paragraph(text(value),style)
    trip = plan['trip']
    story=[p('바다결 여행 일정',title),p(f"{trip['region']} · {trip['start_date']}부터 {trip['days']}일",heading),
           p(f"동행 {dict(family='가족',solo='개인',couple='커플',group='단체').get(trip.get('party_type'),'여행객')} · 성인 {trip.get('adults',0)}명 · 자녀 {trip.get('child_count',len(trip.get('child_ages',[])))}명 · 이동 {MODES.get(trip.get('transport'),'이동수단 미확인')}"),
           p('전체 바다여행 전망: '+str((plan.get('travel_index') or {}).get('grade') or '자료 미확인')),
           p('검토용 초안입니다. 운영시간·예약·연령 조건·현장 통제는 별도 확인이 필요합니다. 대중교통은 조회 시점 참고 경로입니다.',small),Spacer(1,12)]
    for index,day in enumerate(plan['days']):
        if index: story.append(PageBreak())
        story.extend([p(f"{index+1}일차 · {day['date']} · {day.get('day_start','')}~{day.get('day_end','')}",heading),
                      p('바다여행지수: '+str((day.get('travel_index') or {}).get('grade') or '미확인')),
                      p(weather_text(day.get('weather') or {},day.get('day_start','00:00'),day.get('day_end','23:59')),small),Spacer(1,8)])
        for warning in day.get('warnings') or []: story.append(p('확인: '+warning,small))
        legs=transfer_legs(day,plan.get('routes',{}).get(day['date'],{}))
        by_slot={i.get('slot_id'):i for i in day['items']}
        for item in day['items']:
            leg=legs.get(item.get('slot_id'))
            if leg:
                origin=by_slot.get(leg['from_slot'],{})
                flow=p(f"{origin.get('title','이전 장소')} → {item['title']}\n{route_text(leg)}",small)
                table=Table([[flow]],colWidths=[475]);table.setStyle(TableStyle([
                    ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#edf4f0')),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#c6d9d1')),
                    ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
                    ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
                story.extend([table,Spacer(1,8)])
            header=p(f"{item['start']} - {item['end']}  {item['title']}",ParagraphStyle('Visit',parent=body,fontSize=12,leading=18,textColor=teal))
            story.append(KeepTogether([header,p(item.get('address') or item.get('reason') or '',small)]))
            food=item.get('food_details') or {}
            for label,key in [('대표 메뉴','menu'),('안내 영업시간','hours'),('안내 휴무','rest_days')]:
                if food.get(key): story.append(p(label+': '+food[key],small))
            if item.get('vessel'): story.append(p('여객선: '+item['vessel'],small))
            if item.get('checks'): story.append(p('확인 필요: '+' · '.join(item['checks']),small))
            story.append(Spacer(1,9))
    notes = ParagraphStyle('MarineNotes',parent=small,fontSize=7.5,leading=10.5,spaceAfter=2)
    story.extend([Spacer(1,8),p('이용 전 확인',heading)])
    for notice in plan.get('notices') or []: story.append(p(notice,notes))
    story.append(p('사진과 인터랙티브 지도는 웹 일정에서 확인하세요. 이동시간은 실시간 교통·미래 배차를 보장하지 않습니다.',notes))
    story.append(p(f"계획 {plan.get('plan_id','')} · 버전 {plan.get('revision','')} · 생성 {plan.get('generated_at','')}\n자료 수집: {plan.get('collected_at','미확인')}",notes))
    def footer(canvas,document):
        canvas.saveState();canvas.setFont(font,8);canvas.setFillColor(muted)
        canvas.drawString(40,25,'바다결 · Marine Travel AI Agent v0.5')
        canvas.drawRightString(A4[0]-40,25,str(document.page));canvas.restoreState()
    doc=SimpleDocTemplate(output,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=38,bottomMargin=42,
                          title=f"바다결 {trip['region']} 여행 일정",author='Marine Travel AI Agent')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
