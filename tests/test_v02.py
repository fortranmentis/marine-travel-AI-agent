import copy
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from marine_agent import enrichment, plans, planner, providers, agent, progress
from marine_agent.app import app


def route_value(seconds=60):
    return dict(status='available', duration_s=seconds, distance_m=500,
                geometry={'type':'LineString','coordinates':[[126.41,37.43],[126.42,37.44]]})


@pytest.fixture
def draft(monkeypatch):
    date = (dt.datetime.now(providers.KST).date() + dt.timedelta(days=1)).isoformat()
    candidates = [dict(id=str(i),title=f'장소{i}',lat=37.43,lon=126.42,content_type='12',source='TourAPI') for i in range(1,5)]
    monkeypatch.setattr(planner, 'tourism_candidates', lambda *a, **kw: copy.deepcopy(candidates))
    monkeypatch.setattr(enrichment,'road_route',lambda *a:route_value())
    monkeypatch.setattr(enrichment,'photo_for',lambda id:dict(status='available',url=f'https://tong.visitkorea.or.kr/{id}.jpg'))
    trip=planner.Trip(start_date=date,activity='none').model_dump(mode='json')
    slots=[dict(candidates[0],kind='tourism',start='10:00',end='11:30'),
           dict(kind='break',title='점심',start='12:00',end='13:00'),
           dict(candidates[1],kind='tourism',start='14:00',end='15:30')]
    return dict(status='provisional',trip=trip,days=[dict(date=date,items=slots,alternatives=candidates[2:],weather={},marine={})],notices=[])


def test_replace_only_one_visit_and_undo(draft):
    store=plans.PlanStore();original=store.register(draft);slot=original['days'][0]['items'][0]
    replaced=store.replace(original['plan_id'],1,slot['slot_id'],'3')
    assert replaced['days'][0]['items'][0]['id']=='3'
    assert replaced['days'][0]['items'][0]['start']==slot['start']
    assert replaced['days'][0]['items'][1:]==original['days'][0]['items'][1:]
    assert replaced['can_undo'] and replaced['explanation_outdated']
    restored=store.undo(replaced['plan_id'],2)
    assert restored['days']==original['days']
    assert restored['media']==original['media']
    assert restored['routes']==original['routes']
    assert restored['revision']==3 and not restored['can_undo']


@pytest.mark.parametrize('route',[dict(status='unavailable',reason='경로 미확보'),dict(status='unsupported_ferry',reason='배편'),route_value(999999)])
def test_invalid_route_leaves_plan_intact(draft,monkeypatch,route):
    store=plans.PlanStore();original=store.register(draft)
    monkeypatch.setattr(enrichment,'road_route',lambda *a:copy.deepcopy(route))
    with pytest.raises(plans.PlanError) as error:
        store.replace(original['plan_id'],1,original['days'][0]['items'][0]['slot_id'],'3')
    assert error.value.status==422
    assert store.get(original['plan_id'],1)==original


def test_lock_preserves_photo_coordinates_and_blocks_replace(draft):
    store=plans.PlanStore();original=store.register(draft);slot=original['days'][0]['items'][0]
    locked=store.set_lock(original['plan_id'],1,slot['slot_id'],True)
    assert locked['trip']['locked'][0]['id']=='1'
    assert locked['days'][0]['items'][0]['lat']==slot['lat']
    assert locked['media']==original['media']
    with pytest.raises(plans.PlanError) as error:store.replace(original['plan_id'],2,slot['slot_id'],'3')
    assert error.value.status==409
    unlocked=store.set_lock(original['plan_id'],2,slot['slot_id'],False)
    assert unlocked['trip']['locked']==[]
    assert store.replace(original['plan_id'],3,slot['slot_id'],'3')['revision']==4


def test_old_revision_and_expiration(draft,monkeypatch):
    now=[100.0];monkeypatch.setattr(plans.time,'monotonic',lambda:now[0])
    store=plans.PlanStore(capacity=1,ttl=10);a=store.register(draft)
    b=store.register(draft)
    with pytest.raises(plans.PlanError) as error:store.get(a['plan_id'],1)
    assert error.value.status==410
    with pytest.raises(plans.PlanError) as error:store.get(b['plan_id'],99)
    assert error.value.status==409
    now[0]=111
    with pytest.raises(plans.PlanError) as error:store.get(b['plan_id'],1)
    assert error.value.status==410


def test_invalid_candidate_and_non_tourism(draft):
    store=plans.PlanStore();p=store.register(draft)
    for slot,id in [(p['days'][0]['items'][0]['slot_id'],'999'),(p['days'][0]['items'][1]['slot_id'],'3')]:
        with pytest.raises(plans.PlanError):store.replace(p['plan_id'],1,slot,id)


def test_free_time_excludes_lunch(draft):
    store=plans.PlanStore();p=store.register(draft)
    assert p['routes'][p['days'][0]['date']]['legs'][0]['available_minutes']==90


def test_stream_contains_steps_and_final_result(draft,monkeypatch):
    monkeypatch.setattr('marine_agent.app.CATALOG',type('Exists',(),{'exists':lambda self:True})())
    def fake_chat(*a):
        progress.emit('data','예보 조회 중',state='completed')
        progress.emit('schedule','시간 확인 중',state='completed')
        return dict(status='ok',answer='검토용 초안',plan=draft,trace=[])
    monkeypatch.setattr(agent,'chat',fake_chat)
    with TestClient(app).stream('POST','/api/chat/stream',json={'message':'일정'}) as response:
        events=[json.loads(line) for line in response.iter_lines() if line]
    assert response.status_code==200
    assert events[0]['stage']=='input'
    assert events[-1]['type']=='result'
    assert events[-1]['result']['plan']['revision']==1
    assert any(e.get('stage')=='enrich' and e.get('state')=='completed' for e in events)
    assert 'thinking' not in json.dumps(events)


def test_stream_error_releases_generation_lock(monkeypatch):
    monkeypatch.setattr('marine_agent.app.CATALOG',type('Exists',(),{'exists':lambda self:True})())
    def fail(*a):raise RuntimeError('do-not-leak-secret')
    monkeypatch.setattr(agent,'chat',fail)
    client=TestClient(app)
    for _ in range(2):
        response=client.post('/api/chat/stream',json={'message':'일정'})
        assert response.status_code==200
        assert 'do-not-leak-secret' not in response.text
        assert json.loads(response.text.splitlines()[-1])['type']=='error'


def test_http_replacement_conflict(draft,monkeypatch):
    store=plans.PlanStore();monkeypatch.setattr(plans,'store',store);p=store.register(draft)
    response=TestClient(app).post(f"/api/plans/{p['plan_id']}/replace",json={'revision':99,'slot_id':p['days'][0]['items'][0]['slot_id'],'candidate_id':'3'})
    assert response.status_code==409


def test_photo_fallback_uses_exact_id_and_license(monkeypatch,tmp_path):
    monkeypatch.setattr(enrichment,'_cache',{})
    monkeypatch.setattr(enrichment,'DATA',tmp_path)
    monkeypatch.setattr(providers,'catalog',lambda:dict(places=[dict(contentid='1',title='이 장소')]))
    monkeypatch.setattr(providers,'service',lambda *a:dict(endpoint='https://example.com',key='not-returned'))
    queried=[]
    def get(url,params):
        queried.append(params['contentId'])
        return json.dumps(dict(response=dict(header=dict(resultCode='00'),body=dict(totalCount=2,items=dict(item=[
            dict(contentid='2',originimgurl='https://tong.visitkorea.or.kr/wrong.jpg',cpyrhtDivCd='Type3'),
            dict(contentid='1',originimgurl='https://tong.visitkorea.or.kr/right.jpg',cpyrhtDivCd='Type3')])))))
    monkeypatch.setattr(providers,'get',get)
    photo=enrichment.photo_for('1')
    assert queried==['1'] and photo['url'].endswith('right.jpg')
    assert photo['license']=='Type3' and 'not-returned' not in json.dumps(photo)
    enrichment.photo_for('1')
    assert queried==['1']


def test_untrusted_image_host_is_rejected():
    assert enrichment.image_url('https://evil.example/image.jpg') is None
    assert enrichment.image_url('http://tong.visitkorea.or.kr/a.jpg').startswith('https://')


def test_route_rate_limit_cache_and_ferry(monkeypatch,tmp_path):
    monkeypatch.setattr(enrichment,'_cache',{});monkeypatch.setattr(enrichment,'DATA',tmp_path)
    monkeypatch.setattr(enrichment,'_last_route',0)
    now=[10.0];waits=[];requests=[]
    monkeypatch.setattr(enrichment.time,'monotonic',lambda:now[0])
    def wait(seconds):waits.append(seconds);now[0]+=seconds
    monkeypatch.setattr(enrichment.time,'sleep',wait)
    class Response:
        def raise_for_status(self):pass
        def json(self):return dict(code='Ok',routes=[dict(duration=20,distance=50,geometry=dict(type='LineString',coordinates=[[1,2],[2,3]]),legs=[dict(steps=[dict(mode='ferry')])])])
    class Client:
        def __init__(self,*a,**k):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get(self,*a,**k):requests.append(a);return Response()
    monkeypatch.setattr(enrichment.httpx,'Client',Client)
    a,b,c=dict(lat=37.4,lon=126.4),dict(lat=37.41,lon=126.41),dict(lat=37.42,lon=126.42)
    assert enrichment.road_route(a,b)['status']=='unsupported_ferry'
    enrichment.road_route(a,b)
    enrichment.road_route(a,c)
    assert len(requests)==2 and waits==[1.0]
