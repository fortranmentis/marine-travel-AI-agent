"""Explicit local live checks; never treats a ferry observation as a booking."""
import argparse
import json
from pathlib import Path
import httpx


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ai',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];report=[]
    with httpx.Client(base_url='http://127.0.0.1:8001',timeout=240,trust_env=False) as client:
        today=client.get('/api/config').json()['today']
        overview=client.get('/api/regions',params={'date':today}).json()
        for region in ('인천북서','인천남서','신안북동','신안남서','여수도서'):
            assert next(r for r in overview['regions'] if r['id']==region)['planning_enabled']
            response=client.post('/api/plan',json=dict(region=region,start_date=today,days=1,
                activity='seatrip',party_type='couple',child_count=0,child_ages=[],cafes=False,visits_per_day=2))
            response.raise_for_status();plan=response.json()
            assert plan['days'][0]['actual_visits']>0
            access=plan['island_access'];assert not access['roundtrip_verified']
            assert not any(i['kind']=='ferry' for d in plan['days'] for i in d['items'])
            record=dict(region=region,island=access['island'],status=plan['status'],visits=plan['days'][0]['actual_visits'],
                operation_status=access['operation_status'],matching_count=access.get('matching_count'),
                as_of=access.get('as_of'),route_statuses=[r['status'] for r in plan['routes'][today]['legs']])
            report.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
            (root/'.tmp'/f'island-{region}.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        if args.ai:
            response=client.post('/api/chat',json=dict(message=f'{today} 인천남서 덕적도에서 성인 2명이 하루 2곳을 관광하는 섬 내 일정 초안을 만들어줘. 배편 미확정 상태도 알려줘.',
                trip=dict(region='인천남서',start_date=today,days=1,activity='seatrip',adults=2,child_count=0,child_ages=[],cafes=False)))
            response.raise_for_status();value=response.json()
            assert value.get('plan') and value['plan']['status']=='conditional_island'
            report.append(dict(ai_status=value['status'],trace=value['trace']))
            print(json.dumps(report[-1],ensure_ascii=False),flush=True)
    (root/'.tmp'/'island-drafts-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
