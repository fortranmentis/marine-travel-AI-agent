"""Explicit live smoke check; run only with a local development server."""
import argparse
import datetime as dt
import json
from pathlib import Path
import time

import httpx


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ai',action='store_true',help='Also send a real model request')
    args=parser.parse_args()
    report={}
    with httpx.Client(base_url='http://127.0.0.1:8001',timeout=240,trust_env=False) as client:
        report['config']=client.get('/api/config').json()['mobility']
        response=client.post('/api/transit/route',json=dict(
            origin=dict(lat=37.47636,lon=126.61694,title='인천역'),
            destination=dict(lat=37.4739,lon=126.6008,title='월미공원'),
            departure_at='2026-10-18T12:00:00+09:00'))
        response.raise_for_status(); report['route']=response.json()
        assert report['route']['status']=='available', 'Public transit route unavailable'
        assert not report['route']['departure_time_applied'] and not report['route']['schedule_verified']
        print('Route:',report['route']['status'],flush=True)
        trip=dict(region='송도·도심',start_date=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat(),
            days=1,activity='none',transport='transit',visits_per_day=2,cafes=False,child_ages=[])
        response=client.post('/api/plan',json=trip)
        response.raise_for_status(); report['plan']=response.json()
        assert report['plan']['trip']['transport']=='transit'
        print('Rule plan:',report['plan']['status'],flush=True)
        if args.ai:
            events=[]; started=time.monotonic()
            with client.stream('POST','/api/chat/stream',json=dict(message='선택한 조건 그대로 대중교통 여행 일정을 만들어 주세요.',trip=trip)) as stream:
                stream.raise_for_status()
                for line in stream.iter_lines():
                    if not line: continue
                    event=json.loads(line); events.append(dict(event,received_seconds=round(time.monotonic()-started,2)))
                    if event['type']=='error': raise RuntimeError(event['message'])
            report['stream']=events
            final=events[-1]['result']
            assert final['status']=='ok' and final.get('plan'), 'AI did not return a plan'
            assert events[0]['received_seconds']<events[-1]['received_seconds']
            print('AI:',events[-1]['type'],'first',events[0]['received_seconds'],'seconds',flush=True)
    output=Path(__file__).resolve().parents[1]/'.tmp'/'browser-transit-live.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved:',output)


if __name__=='__main__': main()
