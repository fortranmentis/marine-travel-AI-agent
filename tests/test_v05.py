import copy
import datetime as dt
from io import BytesIO
import json
import time

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from marine_agent import attractions,planner,plans,providers,browser_ferries as ferry,pdf_export,agent
from marine_agent.app import app
from test_core import snapshot


@pytest.mark.parametrize('row',[
    dict(title='시민문화회관',contenttypeid='14'),dict(title='문화예술회관',contenttypeid='14'),
    dict(title='동네 주민센터',contenttypeid='12'),dict(title='종합운동장',contenttypeid='28'),
    dict(title='일반 공연장',contenttypeid='14',cat3='A02060600'),dict(title='도서관',contenttypeid='14',cat3='A02060900'),
    dict(title='컨벤션센터',contenttypeid='14',cat3='A02060400')])
def test_generic_facility_excluded(row):
    assert not attractions.eligible(row) and attractions.exclusion_reason(row)


@pytest.mark.parametrize('title,code',[('박물관','A02060100'),('기념관','A02060200'),('미술관','A02060500'),('전시관','A02060300'),('해변',None)])
def test_real_visitor_candidates_remain(title,code):
    assert attractions.eligible(dict(title=title,cat3=code,contenttypeid='14'))


def test_filter_applies_to_search_plan_and_replacement(snapshot,monkeypatch):
    data,date=snapshot
    data['places'][0].update(title='문화예술회관',cat3='A02060600')
    assert '0' not in {p['id'] for p in planner.tourism_candidates('영종·용유')}
    store=plans.PlanStore();result=store.register(planner.build_plan(dict(start_date=date,activity='none',days=1)))
    assert not any(i.get('id')=='0' for d in result['days'] for i in d['items'])
    day=result['days'][0];slot=next(i for i in day['items'] if i['kind']=='tourism')
    with pytest.raises(plans.PlanError):store.replace(result['plan_id'],1,slot['slot_id'],'0')
    assert store.get(result['plan_id'],1)==result


NOW=dt.datetime(2026,10,16,11,0,tzinfo=providers.KST)


def raw():
    return dict(headers=ferry.HEADERS.copy(),as_of='2026년 10월 16일 10:55',rows=[
        ['1100','세종7호','장봉-삼목(직항)','역방향','삼목','편도항로','정상','','출항전','장봉-삼목'],
        ['1430','검사선','인천-덕적(직항)','정방향','인천','편도항로','비운','선박검사','출항전','인천-덕적']])


def test_actual_ferry_fields_do_not_imply_arrivals_or_inventory():
    result=ferry.normalize(raw(),'인천',now=NOW)
    assert result['status']=='available' and result['count']==2
    assert result['rows'][0]['departure']=='11:00' and result['rows'][0]['origin']=='삼목'
    assert result['rows'][0]['operation_status']=='reported_normal'
    assert result['rows'][1]['operation_status']=='not_operating'
    assert all(r['arrival'] is None and r['remaining_seats'] is None for r in result['rows'])
    assert not result['usable_for_planning'] and not result['reservation_verified']


@pytest.mark.parametrize('as_of',['2026년 10월 15일 10:55','2026년 10월 16일 10:29','2026년 10월 16일 12:00','bad'])
def test_stale_future_and_invalid_source_times_fail_closed(as_of):
    value=raw();value['as_of']=as_of
    result=ferry.normalize(value,'인천',now=NOW)
    assert result['status'] in ('stale','unavailable') and result['rows']==[]


def test_ferry_date_and_header_mismatch_are_explicit():
    assert ferry.normalize(raw(),'인천','2026-10-17',now=NOW)['status']=='date_unsupported'
    value=raw();value['headers']=value['headers'][::-1]
    assert ferry.normalize(value,'인천',now=NOW)['status']=='unavailable'
    value=raw();value['rows'].append(['bad'])
    assert ferry.normalize(value,'인천',now=NOW)['skipped_rows']==1


def test_live_ferry_cache_isolated_and_errors_sanitized(monkeypatch):
    from marine_agent import browser_jobs
    ferry._cache.clear();calls=[]
    def run(*a,**kw):
        calls.append(a); value=raw();value['as_of']=dt.datetime.now(providers.KST).strftime('%Y년 %m월 %d일 %H:%M');return dict(value,status='ok')
    monkeypatch.setattr(browser_jobs,'run',run)
    first=ferry.live('인천');assert first['status']=='available'
    first['rows'].clear();second=ferry.live('인천')
    assert second['rows'] and second['cached'] and len(calls)==1
    ferry._cache.clear();monkeypatch.setattr(browser_jobs,'run',lambda *a:(_ for _ in ()).throw(RuntimeError('secret')))
    assert 'secret' not in json.dumps(ferry.live('인천'))
    ferry._cache.clear()


def test_ferry_api_validation_and_sixth_typed_tool(monkeypatch):
    monkeypatch.setattr(ferry,'live',lambda office,date:dict(status='available',rows=[],office=office))
    client=TestClient(app)
    response=client.get('/api/ferries/live?office=인천')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert client.get('/api/ferries/live?office=unknown').status_code==422
    assert client.get('/api/ferries/live?date=bad').status_code==422
    assert 'get_ferry_operations' in agent.TOOLS
    assert agent.FerryOperations(date='2026-10-16').model_dump(mode='json')['office']=='인천'


def pdf_plan():
    return dict(plan_id='example',revision=2,generated_at='2026-10-16T11:00:00+09:00',collected_at='2026-10-16',
        trip=dict(region='Incheon',start_date='2026-10-16',days=1,party_type='solo',adults=1,child_count=0,transport='car'),
        days=[dict(date='2026-10-16',day_start='09:00',day_end='18:00',items=[
            dict(slot_id='a',kind='tourism',title='Beach & <Park>',start='10:00',end='11:30'),
            dict(slot_id='b',kind='meal',title='Restaurant',start='12:00',end='12:45')])],
        routes={'2026-10-16':dict(legs=[dict(from_slot='a',to_slot='b',status='available',mode='car',duration_s=180,distance_m=1000)])})


def test_pdf_snapshot_contains_visits_and_embedded_revision(monkeypatch):
    monkeypatch.setattr(pdf_export,'font_name',lambda:'Helvetica')
    plan=pdf_plan();original=copy.deepcopy(plan);content=pdf_export.create_pdf(plan)
    assert content.startswith(b'%PDF-') and plan==original
    pages=PdfReader(BytesIO(content)).pages;text='\n'.join(p.extract_text() for p in pages)
    assert 'Beach & <Park>' in text and 'Restaurant' in text and 'example' in text
    assert len(pages)>=1


def test_pdf_weather_window_and_missing_values():
    value=dict(forecasts={'0900':dict(TMP='0',POP='0',WSD='0'),'2300':dict(TMP='-20',POP='100',WSD='20')})
    text=pdf_export.weather_text(value,'09:00','18:00')
    assert '0~0' in text and '100%' not in text
    assert '미확인' in pdf_export.weather_text({})
    assert '미확인' in pdf_export.route_text(dict(status='unavailable'))


def test_pdf_rejects_missing_font(monkeypatch):
    pdf_export.font_name.cache_clear()
    monkeypatch.setattr(pdf_export.Path,'is_file',lambda *a:False)
    with pytest.raises(pdf_export.PdfUnavailable):pdf_export.font_name()


def test_pdf_route_revision_expiry_and_snapshot(monkeypatch):
    store=plans.PlanStore();plan=pdf_plan();store.entries['example']=dict(plan=plan,expires=time.monotonic()+20)
    monkeypatch.setattr(plans,'store',store)
    seen=[];monkeypatch.setattr(pdf_export,'create_pdf',lambda p:(seen.append(p) or b'%PDF-synthetic'))
    client=TestClient(app);response=client.get('/api/plans/example/pdf?revision=2')
    assert response.status_code==200 and response.headers['content-type']=='application/pdf'
    assert 'attachment' in response.headers['content-disposition'] and response.headers['cache-control']=='no-store'
    assert seen[0]==plan and client.get('/api/plans/example/pdf?revision=1').status_code==409
    assert client.get('/api/plans/example/pdf').status_code==422
    store.entries['example']['expires']=0
    assert client.get('/api/plans/example/pdf?revision=2').status_code==410
