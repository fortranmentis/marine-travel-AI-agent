# Browser transit lookup / 브라우저 대중교통 조회

> v0.6 adds an optional [official TAGO evidence panel](TRANSPORT_API.md) for stops, current arrivals and reference schedules. General route planning below continues through Playwright; TAGO is not an end-to-end route engine.

The default transit provider is **Playwright + Naver Map's rendered public UI**.
No transit API key, hidden endpoint call, network-response interception, login,
personal browser profile, or CAPTCHA bypass is used. This is a prototype adapter;
provider collection/reuse permission and production capacity have not been established.

## Setup

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\run.ps1
```

`TRANSIT_PROVIDER=playwright` is the default. `disabled` turns it off.
The legacy ODsay adapter requires explicit `TRANSIT_PROVIDER=odsay`; it is never
used as a fallback for browser failures. `PLAYWRIGHT_BROWSERS_PATH` can override
the browser install location. This development checkout also detects browsers
installed under `.tmp/playwright`; those binaries are ignored by Git.
`/api/config` reports installation readiness, not live source availability.

## Contract

`POST /api/transit/route`:

```json
{
  "origin": {"lat": 37.47636, "lon": 126.61694, "title": "인천역"},
  "destination": {"lat": 37.4739, "lon": 126.6008, "title": "월미공원"},
  "departure_at": "2026-10-18T12:00:00+09:00"
}
```

Coordinates are required, finite, and constrained to the Korea bounding range.
Coordinates select exact points, with titles used as display labels; no fuzzy
place-name match is performed. Source coordinate accuracy is still unverified.
Optional departure timestamps must include a timezone.

- Available results include `duration_s`, `sections` with walking/bus/subway modes,
  line labels and boarding/alighting stops, walking minutes, transfers, displayed
  fare when numeric, `observed_at`, `source_url`, and cache status.
- This version reads the **lookup-time** route. `requested_departure_at` records
  the itinerary's requested departure separately; `departure_time_applied=false`
  and `schedule_verified=false` always remain explicit. The source UI's arrival
  label is not an arrival prediction for the future itinerary.
- Missing fare/distance/geometry remain `null`. No invented line is drawn on OSM.
  Next-day/later-departure cards and unsupported ferry/flight/intercity modes are
  rejected. The first supported route in source display order is selected;
  it is not guaranteed to be fastest or appropriate for every traveller.
- For itinerary legs within 600 m straight-line distance, transit + walking
  deliberately selects the existing FOSSGIS walking graph before any browser
  lookup, with the actual walking route/time and source shown. Failure is not
  replaced with a car route. Longer legs use the browser transit adapter.
- `fits_schedule` compares only the displayed reference duration with the gap.
  It does not establish travel-date timetable feasibility.
- Failure preserves the draft and offers a source-map link. Replacement still
  fails closed when adjacent routes are missing or do not fit the time gap.

## Resource limits and operation

One browser worker runs at a time; competing lookups wait at most two seconds.
Each itinerary/chat/replacement request has a shared budget of six uncached
browser lookups and 90 seconds of browser budget. Candidate screening and meal
checks share this budget, so complex trips can have explicit missing legs.
Each worker has at most 30 seconds; a timeout terminates its process tree.
Normal workers close Chromium before returning. There is no persistent browser profile.
Cache: process memory only, at most 256 directional coordinate/title pairs,
five minutes for success and one minute for failure. Future requested times are
attached after cloning the lookup-time cache entry, never treated as applied.
No page HTML, authentication state or source network payload is persisted.

Rendered-page changes, blocking, missing routes and unsupported layouts return
`unavailable`; raw browser errors are not shown. Future work includes source
permission review, requested-time UI support and broader reliability evaluation.
Transit does not enable ferry island planning; reviewed round-trip data is still required.

## 한국어 사용 안내

이동수단에서 **대중교통 + 도보 (지도 참고 경로)**를 선택하면 서버의
Playwright가 네이버 지도 화면을 읽습니다. 별도 대중교통 API 키는 필요하지 않습니다.
버스·지하철 노선과 승하차 지점, 도보 합계, 환승, 화면 요금, 조회 시각과
원본 지도 링크를 일정 지도 아래에 표시합니다. 지도에 없는 이동 선형은 그리지 않습니다.

**여행일 출발시각을 적용한 시간표 조회는 아직 지원하지 않습니다.**
조회 시점의 참고 이동시간으로 간격을 비교하며 배차·막차·좌석·접근성은 미확인입니다.
요금은 화면에 표시된 값으로 가족·단체 전체 합계가 아닙니다.
브라우저 한도나 화면 변경으로 조회하지 못한 구간은 원본 지도에서 확인해야 합니다.
자동 수집·캐시·서비스 재표시의 운영상 허용 범위는 별도 확인이 필요합니다.

Official references: [Playwright locators](https://playwright.dev/python/docs/locators),
[auto-waiting](https://playwright.dev/python/docs/actionability),
[Naver terms](https://policy.naver.com/rules/service.html).
