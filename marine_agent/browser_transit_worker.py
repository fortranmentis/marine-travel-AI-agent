"""Isolated Chromium worker: reads rendered route cards, never network responses."""
import datetime as dt
import json
from pathlib import Path
import re
import sys

from .browser_transit import failure, point, route_url

# Stable semantic classes observed on the public route UI; no hashed CSS names.
CARDS = '.list_pubtrans_directions_summary > li'
EXTRACT = r'''cards => cards.map(card => {
  const text = (root, s) => root.querySelector(s)?.textContent?.trim() || '';
  return {
    duration: text(card, '.wrap_time_taken'),
    fare: text(card, '.pubtrans_fare'),
    time_label: text(card, '.pubtrans_base_info .base_info:not(.wrap_time_taken):not(.pubtrans_fare)'),
    timeline: Array.from(card.querySelectorAll('ol._pubtrans_directions_timeline_total_bar > li')).map(e => e.textContent.trim()),
    steps: Array.from(card.querySelectorAll('.list_pubtrans_directions_step > li')).map(e => ({
      station: text(e, '.citystep_station'),
      label: text(e, '.summary_icon_label'),
      lines: Array.from(e.querySelectorAll('.alt_bus_arrival_number')).map(n => n.textContent.trim()),
      line: text(e, '.wrap_remaining_bus .summary_icon_label')
    })),
    later: /다음날|익일|나중에 출발|운행 시간 주의/.test(card.textContent),
    unsupported: /여객선|페리|항공|고속버스|시외버스|KTX|SRT|무궁화|새마을/.test(text(card, 'ol._pubtrans_directions_timeline_total_bar'))
  };
})'''


def minutes(text):
    text = str(text).strip()
    if not re.fullmatch(r'(?:\d+\s*시간\s*)?(?:\d+\s*분)?', text) or not text:
        raise ValueError('unknown duration')
    hours = re.search(r'(\d+)\s*시간', text)
    mins = re.search(r'(\d+)\s*분', text)
    value = (int(hours[1]) * 60 if hours else 0) + (int(mins[1]) if mins else 0)
    if not 0 <= value <= 1440:
        raise ValueError('invalid duration')
    return value


def normalize(cards, url, observed_at=None):
    for card in cards:
        if card.get('later') or card.get('unsupported'):
            continue
        try:
            duration = minutes(card['duration'])
            if duration <= 0:
                continue
            sections = []
            rides = []
            for text in card['timeline']:
                mode = 'walk' if '도보' in text else 'bus' if '버스' in text else 'subway' if any(s in text for s in ('지하철', '전철', '호선', '수도권', '경전철', '공항철도', '경의중앙', '수인분당', '신분당', '동해선', '우이신설', '신림선', '서해선', 'GTX', '김포골드')) else None
                if mode is None:
                    raise ValueError('unsupported section')
                match = re.search(r'(?:\d+\s*시간\s*)?\d+\s*분\s*$', text)
                if not match:
                    raise ValueError('missing section duration')
                sections.append(dict(mode=mode, minutes=minutes(match[0]), lines=[], start=None, end=None))
                if mode != 'walk':
                    rides.append(sections[-1])
            if not rides:
                continue
            # Rounded section totals can differ by a few minutes, not by hours.
            if abs(sum(s['minutes'] for s in sections) - duration) > max(5, len(sections)):
                continue
            steps = card.get('steps', [])
            if len(steps) != len(rides) + 1 or any(not s.get('station') for s in steps):
                continue
            for n, section in enumerate(rides):
                step = steps[n]
                section.update(start=step['station'], end=steps[n + 1]['station'],
                               lines=list(dict.fromkeys(step.get('lines') or ([step['line']] if step.get('line') else [step.get('label', '')]))))
            fare = card.get('fare', '').replace(',', '')
            return dict(status='available', mode='transit', duration_s=duration * 60,
                distance_m=None, geometry=None, source='네이버 지도 · Playwright 화면 조회', source_url=url,
                sections=sections, fare=int(fare[:-1]) if re.fullmatch(r'\d+원', fare) else None,
                walking_minutes=sum(s['minutes'] for s in sections if s['mode'] == 'walk'),
                transfers=max(0, len(rides) - 1), observed_at=observed_at or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
                lookup_time_label=card.get('time_label'), schedule_verified=False,
                traffic='lookup_time_only', departure_time_applied=False,
                note='조회 시점 지도 화면의 참고 경로입니다. 여행일 출발시각·배차·막차는 미확인입니다. 요금은 화면 기준이며 인원별 합계가 아닙니다.')
        except (KeyError, TypeError, ValueError):
            continue
    return failure('지원하는 버스·지하철 경로를 화면에서 확인하지 못했습니다. 지도에서 확인해 주세요.', url)


def lookup(a, b, screenshot=None):
    from playwright.sync_api import sync_playwright
    a, b = point(a), point(b)
    url = route_url(a, b)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, timeout=10000)
            try:
                context = browser.new_context(locale='ko-KR', timezone_id='Asia/Seoul',
                    viewport=dict(width=1280, height=900), accept_downloads=False)
                page = context.new_page()
                page.set_default_timeout(15000)
                page.goto(url, wait_until='domcontentloaded', timeout=20000)
                # A fresh page contains only this request; wait for complete visible cards.
                page.locator(CARDS).first.wait_for(state='visible', timeout=18000)
                if page.get_by_role('combobox', name='출발지 입력', exact=True).input_value() != a['title'] or page.get_by_role('combobox', name='도착지 입력', exact=True).input_value() != b['title']:
                    return failure('지도 출발·도착지 일치를 확인하지 못했습니다.', url)
                result = normalize(page.locator(CARDS).evaluate_all(EXTRACT), url)
                if screenshot:
                    page.screenshot(path=str(screenshot), full_page=False)
                return result
            finally:
                browser.close()
    except Exception:
        return failure('지도 화면을 읽지 못했습니다. 연결·화면 변경·접근 제한 여부를 확인해 주세요.', url)


def main():
    if '--check' in sys.argv:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                ready = Path(p.chromium.executable_path).exists()
        except Exception:
            ready = False
        print(json.dumps(dict(ready=ready)))
        return
    try:
        request = json.loads(sys.stdin.read(12000))
        result = lookup(request['a'], request['b'])
    except Exception:
        result = failure('브라우저 조회 입력 또는 실행을 확인하지 못했습니다.')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
