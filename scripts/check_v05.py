"""Explicit live v0.5 smoke check against the local development server."""
import argparse
import datetime as dt
from io import BytesIO
import json
from pathlib import Path

import httpx
from pypdf import PdfReader


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ai',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    with httpx.Client(base_url='http://127.0.0.1:8001',timeout=240,trust_env=False) as client:
        config=client.get('/api/config').json();assert config['version']=='0.5.0'
        response=client.get('/api/ferries/live',params=dict(office='인천',date=config['today']))
        response.raise_for_status();ferries=response.json();assert ferries['status']=='available' and ferries['rows']
        assert all(row['arrival'] is None for row in ferries['rows'])
        print('Live ferry:',ferries['count'],ferries['as_of'],flush=True)
        response=client.post('/api/plan',json=dict(region='제주북동',start_date=config['today'],days=1,activity='none',
            transport='car',visits_per_day=2,party_type='couple',adults=2,child_count=0,child_ages=[],cafes=False))
        response.raise_for_status();plan=response.json()
        assert not any('문화회관' in i['title'] or '문화예술회관' in i['title'] for d in plan['days'] for i in d['items'])
        response=client.get(f"/api/plans/{plan['plan_id']}/pdf",params=dict(revision=plan['revision']))
        response.raise_for_status();assert response.content.startswith(b'%PDF-')
        pdf=PdfReader(BytesIO(response.content));text='\n'.join(p.extract_text() for p in pdf.pages)
        assert plan['days'][0]['items'][0]['title'] in text
        output=root/'output'/'pdf'/'travel-itinerary.pdf';output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(response.content)
        (root/'.tmp'/'v05-live-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        report=dict(version=config['version'],ferry_count=ferries['count'],ferry_as_of=ferries['as_of'],
                    pdf_pages=len(pdf.pages),pdf_bytes=len(response.content),visits=plan['days'][0]['actual_visits'])
        print('PDF:',len(pdf.pages),'pages;',len(response.content),'bytes',flush=True)
        if args.ai:
            response=client.post('/api/chat',json=dict(message='오늘 인천의 실제 여객선 운항정보를 조회하고, 확인된 정보와 미확인 정보를 구분해 알려주세요.'))
            response.raise_for_status();result=response.json();report['ai_trace']=result['trace'];report['ai_status']=result['status']
            assert any(t['tool']=='get_ferry_operations' and t['status']=='ok' for t in result['trace'])
            print('AI ferry trace:',result['trace'],flush=True)
        (root/'.tmp'/'v05-live-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Saved PDF:',output)


if __name__=='__main__': main()
