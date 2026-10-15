"""KOMSA connection preparation. Raw schedules are not verified round trips."""
import argparse
import datetime as dt
import os

from . import providers
from .config import DATA

SCHEDULE_URL = 'https://apis.data.go.kr/B554035/oprt-schd-info-v2/get-oprt-schd-info-v2'


def schedules(date, vessel):
    # The official schema requires both the date and vessel name. Do not scrape
    # arbitrary vessels, infer arrivals, or interpret a missing status as running.
    dt.date.fromisoformat(date)
    if not vessel.strip() or len(vessel) > 100:
        raise ValueError('정확한 여객선명을 입력하세요.')
    key = os.environ.get('KOMSA_API_KEY')
    if not key:
        raise ValueError('KOMSA_API_KEY를 서버 환경에 설정하세요. 운항 스케줄 API 이용 승인도 필요합니다.')
    rows = providers.fetch_pages(SCHEDULE_URL, dict(serviceKey=key, dataType='JSON',
        numOfRows=100, rlvtYmd=date.replace('-', ''), psnshpNm=vessel), success_codes=('200',))
    return dict(date=date, vessel=vessel, rows=rows, source='https://www.data.go.kr/data/15142302/openapi.do',
        collected_at=dt.datetime.now(providers.KST).isoformat(),
        warning='원시 운항 자료입니다. 도착시각·왕복 항로·통제 상태 검증 없이 일정에 자동 사용하지 않습니다.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True)
    parser.add_argument('--vessel', required=True)
    args = parser.parse_args()
    try:
        result = schedules(args.date, args.vessel)
        providers.atomic_json(DATA / 'ferry_schedule_raw.json', result)
        print(f"Collected {len(result['rows'])} raw schedules; review required. No itinerary enabled.")
    except Exception:
        # Authenticated URLs may be part of upstream exceptions: never print them.
        print('Schedule collection failed. Check KOMSA key, approval, vessel name and date. Existing data preserved.')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
