# v0.4 — Nationwide sea-travel outlooks

## Coverage and meaning

The service now follows the **29 named sea-travel forecast regions** returned by
[KHOA's sea-travel index API](https://www.data.go.kr/data/15142491/openapi.do).
It is not a forecast for every municipality or every visited venue. There is no
nearest-point substitution for a city without a named supported forecast.

**24 regions** currently support land-tourism drafts: 인천내륙, 강릉, 속초, 삼척,
태안북부, 태안남부, 보령, 군산, 부안, 영광, 해남, 여수내륙, 통영, 거제,
고성 (경남), 부산북동, 부산남서, 울산, 포항, 영덕, 제주북동, 제주북서,
제주남동, 제주남서. The existing 영종·용유 / 강화 / 송도·도심 presets remain compatible.

**Forecast only:** 인천북서, 인천남서, 신안북동, 신안남서, 여수도서. Their
outlooks can be compared, but generating an unreviewed ferry itinerary is rejected.
Reviewed passenger day trips retain the v0.3 opt-in mechanism; no real ferry island
is activated by this expansion.

The UI compares the worst valid grade over **09:00–18:00** and separately displays
morning/afternoon source grades. When KHOA supplies `predcNoonSeCd=일`, the
source daily grade is used and explicitly labelled as having no morning/afternoon
breakdown. An itinerary uses its own daily hours when half-day data is available.
A missing required half-day without valid daily data, or a stale feed, yields no
combined grade. No numeric score is invented.
Poor/very-poor outlooks prioritize cultural-facility candidates; this is a planning
preference, not a finding that a venue is indoors, open or suitable for current land weather.

## API changes

- `GET /api/regions?date=YYYY-MM-DD`: returns the selected date, source collection
  time, actually returned forecast-date range and 29 region records. Each includes
  ID/title, province, exact `forecast_area`, tourism administrative filters,
  `planning_enabled`, reason, search `gateway`, and grade/evidence/coverage status.
  Missing tourism data or gateway metadata disables draft generation in the UI.
- `Trip.region`, place search and model tools accept the named regions in addition
  to existing presets. Names remain allowlisted; unknown names are rejected.
- `Trip.activity=seatrip` creates a land-tourism draft using that region's sea outlook.
  It becomes the default for new national regions when the field is omitted.
  Legacy API requests retain their previous default. Explicit mudflat/swimming
  requests outside the original presets are rejected in this rollout.
- `/api/health` adds `scope` and `forecast_regions`. Existing endpoints and plan
  revisions, replacement, undo, photos, weather and transport settings remain supported.
- Days expose `search_reference`: an exact TourAPI place used for nearby candidate
  discovery and road-access screening. It is **not** lodging or the user's actual origin.
  Its location supplies the representative KMA forecast for new regions.

## Matching and routing

Tourism matching uses source `areacode` + `sigungucode`, joined to `areaCode2`
metadata, rather than extending Incheon's rectangles to the rest of the country.
Exact forecast-name associations and inspected TourAPI gateway IDs live in
[`regions.py`](../marine_agent/regions.py). Taean north/south uses a 36.75° latitude
search split; Jeju east/west uses 126.5° longitude and its source municipality.
These are **application search boundaries, not official forecast polygons**.

New regions screen candidates against a road route from the named gateway, then
check actual mode-specific adjacent routes and time gaps. A ferry/unknown road
connection is not accepted as mainland access. Connected bridge islands can be
included; parking, ticket inventory and accessibility are not verified. Search
references do not add a fictional timed origin-to-first-visit leg. Typical boat
activity names are excluded from national tourism candidates; no marine experience
is automatically added by `seatrip` mode. These filters are not comprehensive
operator or venue verification.

## Collection and freshness

```powershell
# Default: 10 coastal provincial catalogs + required sea-travel forecast.
.\.venv\Scripts\python.exe -m marine_agent.sync --scope coastal

# Refresh all eight marine feeds while retaining nationwide tourism coverage.
.\.venv\Scripts\python.exe -m marine_agent.sync --scope coastal --all-marine
```

The default CLI scope is `coastal`. `--scope incheon` is an explicit legacy mode
that replaces tourism coverage with Incheon and refreshes all eight feeds.
Existing approved TourAPI / KHOA / KMA credentials are reused. No new key is needed
for that rollout. Transit now defaults to the [Playwright UI adapter](BROWSER_TRANSIT.md)
without a transit API key; KOMSA/reviewed ferry access remains separate.

Ten complete provincial catalogs and administrative metadata are fetched before
atomic publication. Count drift, missing pages, duplicate IDs or sea-travel failure
preserve the previous catalog. Other marine feeds can be retained with their own
original collection times; a new tourism/sea-travel refresh never makes them fresh.
The catalog is read-cached by file metadata to avoid repeatedly parsing the national
snapshot for each candidate/photo. Collected raw data remains Git-ignored.

Observed collection at **2026-10-16 00:16 KST**: 10,102 tourism records across
인천 513, 부산 565, 울산 225, 강원 1,998, 충남 1,136, 경북 1,370, 경남 1,346,
전북 1,056, 전남 1,146, 제주 747. These are whole-province catalog counts, **not**
10,102 approved coastal itinerary stops. The source returned 29 sea-travel regions
and dates spanning October 16–21. October 16–17 have 58 records/day
(29 regions × morning/afternoon); October 18–21 have 29 records/day with `일` resolution.

## 한국어 요약

전국 29개 바다여행 예보 권역을 비교하고 그중 24개 육상 관광 권역에서 초안을
생성합니다. 10개 시도 관광정보를 수집하되 실제 후보는 지정 행정구역·탐색 범위로
좁힙니다. 도서 5개 권역은 배편 검증 전까지 예보만 제공합니다. 지수는 선택한
해상 권역의 전망이며 육상 날씨·안전·운항 여부를 보증하지 않습니다. 지수가 나쁜
날은 문화시설 후보를 우선하고, 예보 결측은 좋음으로 바꾸지 않습니다.
