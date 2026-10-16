# Ferry planning proposal / 배편 제공 제안

Historical planning proposal. **v0.5 now implements today-only KOMSA public-screen
operations**; see [the implemented contract](API-v05.md). Reviewed date-specific
round trips and arrivals remain required for automatic island itineraries. The
proposal below describes that later scheduling scope, not current capabilities.

## Suggested first release

Start with one or two reviewed island routes and passenger-only day returns.
Match actual islands, terminal coordinates and TourAPI IDs explicitly: a KHOA
forecast region is not an island or a ferry route. Keep mainland terminal access,
ferry crossings and island walking as separate itinerary legs.

Use official operator timetables or the user's already selected sailings to obtain
both directions, exact date, vessel, ports, departure and published arrival time.
Treat user input as user-provided rather than independently verified. If a source
only supplies departures, leave arrival unknown until another authoritative source
is checked. Do not invent arrival by adding a typical voyage duration.

## Data and status

- **Scheduled sailings:** date-specific outbound and return timetables.
- **Operation status:** timestamped normal/cancelled/delayed/unknown observations,
  separately from timetable publication. Today's normal status is not a guarantee
  for a future travel date.
- **Booking:** operator or reservation-site link; stock, fare and booking status
  remain unknown unless explicitly obtained from the relevant source. Vessel
  passenger capacity is not remaining ticket inventory.
- **Access:** chosen origin to mainland terminal, boarding cutoff/check-in,
  crossing, disembarkation, island transport, return check-in and return crossing.
  Confirm route-specific check-in deadlines rather than treating the current
  40-minute prototype allowance as a universal operator requirement.
- **Vehicle:** default parking at the mainland terminal and walking on the island;
  vehicle shipping needs separate vessel, vehicle and reservation data.

## API-free prototype and later connection

For an API-free first version, maintain a small reviewed route catalog and use
Playwright to read public official timetable/status screens for the selected route
and date, after confirming collection/reuse conditions. Keep source URL, observed
time and exact vessel/port identity. A missing field, source-layout change or access
restriction must result in unknown status, not a fabricated departure or normal state.
No private endpoints, CAPTCHA bypass or automated ticket purchases are proposed.

Later, an approved KOMSA schedule adapter can replace the screen reader behind
the same interface. The existing `ferries.py` prepares this integration. API source
coverage and actual response fields must still be checked, particularly arrivals.

Official sources inspected on 2026-10-16:

- [KOMSA operation lookup](https://www.komsa.or.kr/prog/pssgCurState/kor/sub03_0202/list.do).
- [KOMSA schedule API description](https://www.data.go.kr/data/15142302/openapi.do):
  describes date, vessel, departure, port, route and control information. It does
  not establish ticket availability or a complete reviewed round trip.

## 한국어 화면 흐름

`실제 섬 선택 → 출발항 선택 → 가는 배·오는 배 선택 → 항구 접근·승선 여유 확인 → 섬 일정 생성`

화면에는 왕복 배편 카드와 함께 **시간표 확인 / 당일 운항 상태 / 예약 확인**을
각각 표시합니다. 다음 날 운항 예보도 확정 운항과 구분합니다. 예약은 원문으로
연결하고, 왕복 중 한 방향이나 도착시각이 없으면 확정된 섬 일정으로 표시하지 않습니다.
바다여행지수는 참고 전망으로 제공하며 결항 여부를 대신 판정하지 않습니다.

먼저 인천의 소수 항로를 검토해 적용하고 이후 전국으로 늘리는 것을 제안합니다.
현재 변경에는 실제 배편 수집·예약·섬 활성화가 포함되지 않습니다.
