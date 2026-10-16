# Validation record — updated 2026-10-16 (Asia/Seoul)

## v0.5 PDF, attraction filtering and actual ferry operations — 2026-10-16

- **102 Python + 11 Node tests passed** on the final source. Existing
  Starlette/httpx deprecation warning remains. Frontend syntax and
  `git diff --check` passed. Offline CI uses synthetic/mocked sources; the PDF
  unit fixture uses Helvetica for portability and is not Korean-font evidence.
- New regressions cover generic-facility exclusions and retained museum/gallery
  categories; initial plans and rejected replacements; ferry table/header/date/
  freshness failures, malformed rows, operation labels, unknown arrivals/seats,
  cache clone isolation, API validation and the sixth typed model tool; PDF
  contents, XML escaping, day-window weather, missing fonts, revision conflict,
  expiry and no-store headers; exact licensed-route filtering in the UI.
- Existing tourism catalog profile: 10,102 records, 5,176 tourism-type candidates,
  **81 exclusions / 5,095 retained before region/access checks**. Category names
  were checked against the actual TourAPI categoryCode2 response. This is a
  dated selection-policy audit, not a new collection or venue-quality check.
  [Aggregate only](docs/v05-profile.json); credentials/raw source data are excluded.
- Actual Playwright Chromium operated the KOMSA public office selector/search and
  read **77 Incheon departures**, source time **11:14 KST** on October 16. Earlier
  native Qwen request to the configured `qwen3.8:27b-mtp-q8_0` returned `ok` and
  `get_ferry_operations: ok` against the 10:57 source observation. This verifies
  one office/day and one native tool request, not all jurisdictions or reliability.
- Source departure time, vessel, route, direction, origin, operation classification
  and departure status were retained. Arrival, destination, seats and fare remain
  unknown. No reviewed island route was enabled and no reservation was made.
  The model receives at most 12 representative rows with an explicit truncation
  note; the web table can show all returned rows. [Contract](docs/API-v05.md).
- Actual rule-generated Jeju northeast plan exported through the revision-specific
  endpoint: **one A4 page, 61,828 bytes**, Korean text and embedded Korean TTF.
  Poppler-rendered final page was visually inspected: visits, weather, restaurant,
  adjacent car transfers, caveats and metadata fit without clipping. Browser PDF
  button also downloaded a Korean-named attachment. That earlier browser sample
  preceded the final spacing refinement; final layout was checked from the API PDF.
- Desktop 1280px and mobile 390px views were inspected. The ferry office selector,
  real rows and exact licensed-route filter worked (선수-주문: 12 rows). The PDF
  button returned to its enabled state after download. Mobile document width was
  375px within the 390px viewport, without horizontal page overflow.
  [Ferry panel](docs/v05-ferries.jpg), [PDF button](docs/v05-desktop.jpg),
  [mobile](docs/v05-mobile.jpg). Screenshots preserve their observation timestamps.
- Re-run live checks explicitly with `python scripts/check_v05.py --ai` against
  a running local server; outputs go to ignored `.tmp/` and `output/pdf/`.
  Source-page reuse/capacity, future ferry timetables, arrivals, round-trip access,
  inventory, bookings, operator/child conditions and warnings remain unverified.

## Inline travel cards — 2026-10-16

- **77 Python + 10 Node tests passed**; existing Starlette/httpx warning remains.
  Frontend regressions cover slot-ID pairing independent of route order, meal/cafe
  links, car/walk/mixed transit modes, missing coordinates/routes/distance, insufficient
  gaps, non-destination breaks and suppression of ground legs over scheduled ferries.
- Actual local Jeju northeast rule plan displayed Hamdeok Beach → travel card →
  Hunnam restaurant → travel card → Seoubong trail. Source car durations/distances
  were 1 minute/215m and 2 minutes/494m when rounded for display. These observations
  are not real-time traffic or driving feasibility guarantees.
- Desktop 1280px and mobile 390px layouts had no horizontal overflow
  (document widths 1265px / 375px). [Desktop](docs/inline-transfer-desktop.jpg) /
  [mobile](docs/inline-transfer-mobile.jpg) show the actual Jeju itinerary.
- Segment-map action highlighted exactly one route path. Photo captions were absent,
  while the plan-level photo-credit disclosure was present and initially closed.
- The ferry proposal describes a small reviewed-route pilot, separate timetable,
  observed operation status and booking data, and an optional public-screen adapter.
  No ferry data collection, reservation or island activation was added.

## Playwright transit checks — 2026-10-16

- **77 Python + 6 Node tests passed** with `--basetemp=.tmp/pytest-transit-walk`.
  Existing Starlette/httpx deprecation warning remains. No transit API calls are
  allowed in the new browser-provider regression fixtures.
- Offline coverage includes bus/subway transfers, missing distance/fare, later-day
  exclusion, unsupported modes/layouts, directional memory cache and clone isolation,
  future departure metadata, coordinate validation, request count/deadline limits,
  explicit failure, rejected replacement preserving revision, progress events and
  short-leg selection of a walking graph before browser lookup.
- Real Playwright Chromium read the public Naver Map UI for four public-coordinate
  pairs: Incheon Station–Wolmi Park, Busan Station–Haeundae Beach,
  Gangneung Station–Gyeongpo Beach, and Seoul Station–Jamsil Station.
  Three returned bus sections; the last returned subway lines 4 and 2 with one transfer.
  These are individual observations, not nationwide availability or timetable validation.
- The live `/api/transit/route` result preserved the requested October 18 departure,
  reported lookup-time data separately, and returned `departure_time_applied=false`,
  `schedule_verified=false`, no distance/geometry, and a source-map link.
- Final real Qwen `qwen3.8:27b-mtp-q8_0` NDJSON request returned `ok`,
  `build_itinerary: ok`, two tourism visits and one restaurant in Songdo/downtown.
  Both adjacent legs were short walking routes from FOSSGIS, explicitly labelled.
  Progress arrived before the final response (17.42s for this single observation).
- Desktop 1280px and mobile 390px views displayed the mixed-mode planner, actual
  walking map and reference-time caveats without horizontal overflow
  (document widths 1265px / 375px). See [desktop](docs/browser-transit-desktop.jpg)
  and [mobile](docs/browser-transit-mobile.jpg). Those screenshots show walking legs,
  not a claim that bus line geometry was obtained.
- Installed Playwright/Chromium locally. The live check is rerunnable with
  `python scripts/check_browser_transit.py --ai` against a running local server;
  its report stays under ignored `.tmp/`. Offline CI does not require Chromium.
- Travel-date timetable selection, source collection/reuse permission, accessibility,
  seats, ferry schedules and production capacity remain unverified. See
  [adapter contract and limitations](docs/BROWSER_TRANSIT.md).

## v0.4 national sea-travel checks — 2026-10-16

- **57 Python + 5 Node tests passed**; Python used
  `--basetemp=.tmp/pytest-national-final`. Existing Starlette/httpx deprecation warning remains.
  `git diff --check` and frontend syntax checks passed.
- New regressions cover source province/municipality joins (including the two 고성군
  names), unknown regions, marine activity scope, offshore planning gates, exact
  forecast-name selection, per-feed freshness, cultural preference under poor sea
  outlooks, missing/ferry road access, revision preservation on rejected replacement,
  region API readiness/date validation, daily `일` versus half-day source resolution,
  and atomic national collection with retained old-feed timestamps.
- Live collection: **10,102 records / 10,102 distinct IDs** from ten coastal provincial
  TourAPI catalogs, 10,073 coordinate-range passes; **29 sea-travel regions / 232 rows**.
  Snapshot: `2026-10-16T00:16:24.353847+09:00`. [Aggregate](docs/national-profile.json).
  October 16–17 provide morning/afternoon rows (58/day), October 18–21 daily rows
  (`predcNoonSeCd=일`, 29/day). Daily rows are used as daily outlooks with no fabricated
  morning/afternoon detail. Other marine feeds retain October 15 collection times.
- Live rule API: Gangneung and northeast Busan each returned HTTP 200, two tourism
  visits and one nearby meal, with both adjacent road legs available and within their
  time gaps (5.78s / 5.26s single observations). Missing cafe slots remain omitted.
- Real Qwen `qwen3.8:27b-mtp-q8_0` request for northeast Busan returned `ok` with
  `get_marine_conditions: ok`, `build_itinerary: ok`, region preserved and two visits.
  First stage: 0.07s; final: 33.4s. These are observations, not performance benchmarks.
- Live October 18 Gangneung daily outlook returned `나쁨` / `daily`. Its draft selected
  갈골한과체험전시관 and 강릉올림픽뮤지엄 (culture type 14) and a nearby meal, with the poor
  outlook notice. This does not validate operating hours, indoor status or land-weather suitability.
- Browser: 29 comparison cards, 24 draft-ready regions, province filters linked to
  form selection, Gangneung candidate-to-plan flow, half-day/daily labels, actual
  source dates, existing readable icons, and 1280px / 390px layouts checked.
  No horizontal page overflow at either viewport. [Desktop](docs/national-desktop.jpg),
  [mobile](docs/national-mobile.jpg), [Gangneung draft](docs/national-plan.jpg).
- Five offshore forecast regions remain forecast-only. Public transit and live ferry
  operations remain unverified without separate keys and reviewed schedules.
  Nationwide refers to supported named sea-travel regions, not every municipality.
  The service remains a local prototype; data is not included in Git.

## Readability update — 2026-10-15

- Sea-travel outlook cards now use inline SVG grade symbols, explicit grade text,
  a five-step legend and outlined current step. Unknown/stale grades have a
  separate neutral presentation. Mudflat activity cards share the grade badge.
- Computed browser fonts: body 16px, card body 15px, form labels 14px;
  prominent grade 23px on desktop / 22px on mobile. Supporting text was enlarged.
- Browser validation at 1280px and 390px: no horizontal page overflow, all five
  grades visible, current grade matched the actual returned outlook. Screenshot:
  [desktop](docs/readability-desktop.jpg), [mobile](docs/readability-mobile.jpg).
- Existing five Node tests passed; new frontend modules passed syntax checks;
  `git diff --check` passed. This presentation-only update does not revalidate
  provider availability or change forecast/scheduling rules.

## v0.3 implementation checks — current work

- Python **49 passed** (`--basetemp=.tmp/pytest-v03-final`); Node **5 passed**.
  One existing Starlette/httpx deprecation warning remains. Default sandbox temp
  permissions initially blocked three fixtures; an explicit workspace basetemp resolved this.
- Regression coverage includes daily time/lock bounds, child count/age consistency,
  major visit counts and shortages, exact TourAPI food categories and radius filters,
  unavailable meal routes, foot-graph isolation, missing transit keys, ODsay section
  parsing and redacted failures, ordinal sea-index missing coverage, dated ferry
  round trips/check-in/cancellations/expired reviews, and KOMSA filter/success parsing.
- Live TourAPI `categoryCode2` returned the food/cafe codes documented in
  [API-v03.md](docs/API-v03.md). Existing local catalog includes 284 content-type-39
  records. Source classification can disagree with actual menus; the UI explicitly
  labels it and displays available `detailIntro2` menu/hours without claiming calendar validation.
- A real foot route returned `available`, 433.8m / 347.1s from the separate FOSSGIS
  foot graph. A live couple/walk/Chinese-food request to `/api/chat/stream` using
  `qwen3.8:27b-mtp-q8_0` returned `ok` with `build_itinerary: ok`, 2 tourism visits,
  one cafe and one meal. First stage arrived after **0.11s**, final result after
  **33.31s** (single observation, not a performance benchmark). All 3 adjacent
  walking legs were available and fit their time gaps; total 1,291.1m / 1,032.9s.
- Browser checks covered solo defaults, group defaults, 2 child age fields,
  different daily time inputs, generated foot routes/markers, food/cafe photos and
  menu/hours, 24-hour weather arrows and horizontal scroll. At 1280px the hourly
  strip was 740px wide with 1,618px content; at 390px it was 308px wide. Page width
  did not exceed viewport width. [PC](docs/weather-v03.jpg), [mobile](docs/mobile-v03.jpg),
  [full interface](docs/interface-v03.jpg). A stale browser-module export during
  development was resolved by consistent versioned module/style URLs.
- ODsay and KOMSA keys are **not configured**. Adapter tests use synthetic responses;
  no live public-transport trip or ferry island has been verified or enabled.
  Ferry support is reviewed passenger day-trip scheduling and connection preparation,
  not overnight trips, car shipping, ticket availability or live cancellation monitoring.
- Food hours, cuisine accuracy, group capacity, warning bulletins, venue age suitability
  and mainland-to-port access remain unverified. Car scheduling still uses heuristic
  insertion with subsequent actual-route warnings. This is a local prototype.

Earlier sections below are historical v0.2 validation records.

## Documentation refresh checks — re-run in this work

On October 15, 2026 (Asia/Seoul), the current checkout passed:

- `.venv/Scripts/python.exe -m pytest -q --basetemp=.tmp/pytest-readme-refresh`: **37 passed**.
- `node --test tests/web.test.mjs`: **4 passed**.
- Pytest reported one `StarletteDeprecationWarning` about its TestClient HTTP backend.
- Documentation verification and local visual checks are described below. GitHub page
  rendering was not verified remotely.

### Local data profile — inspected in this refresh

The existing `data/catalog.json`, collected at `2026-10-15T16:42:01.930293+09:00`,
was inspected without refreshing the source APIs:

| Measure | Observed result |
| --- | ---: |
| Tourism records / distinct content IDs | 513 / 513 |
| Empty IDs / duplicate IDs | 0 / 0 |
| Basic coordinate-range pass / fail | 511 / 2 |
| Planning content types before regional filtering | 185 |
| Regional candidates: Yeongjong–Yongyu / Ganghwa / Songdo–urban | 29 / 57 / 60 |
| National marine forecast rows across eight feeds | 3,827 |

The coordinate screen checks finite numeric values and `33 < lat < 39`, `124 < lon < 132`;
it is not positional verification. Candidate counts use `tourism_candidates(limit=200)`.
Forecast rows are not unique site counts. Feed-level counts and forecast-date ranges
are documented in [DATA.md](docs/DATA.md) and the [aggregate profile](docs/data-profile.json).

이번 작업에서 기존 수집 파일의 ID·좌표 범위·유형·권역별 후보·해양 행 수를 재집계했습니다.
원천 API 재수집, 지오코딩 정확도, 가족 적합성을 확인한 결과는 아닙니다.

### Documentation and visual checks — performed in this refresh

- Seven Markdown documents passed checks for local link targets, anchors and balanced
  code fences. Seven SVG assets parsed without active content or external resources.
- The aggregate profile passed total/count arithmetic checks; `git diff --check` passed.
- The hero, overview strip and workflow SVGs were rasterized with Sharp and visually
  inspected. Both READMEs were rendered locally with Marked and headless Chrome using
  a GitHub-like stylesheet: no missing images or horizontal page overflow at 1280px.
- English top/feature views and Korean feature views were visually inspected. This is
  a local documentation preview, not verification of GitHub's sanitizer, Mermaid renderer,
  dark mode or mobile README behavior. Remote GitHub rendering and CI remain unchecked.

The test runs above use synthetic data and mocked dependencies. No live source
collection, Ollama inference, route request or live application browser session was
performed during this documentation refresh. The earlier live observations below
are inherited development records, not freshly verified service status.

이번 문서 작업에서는 Python 37개·프런트엔드 4개 오프라인 테스트, 로컬 카탈로그 프로파일,
문서 링크·SVG 검사, 1280px 로컬 README 렌더링을 확인했습니다. 아래 실제 API·모델·앱
브라우저 관찰은 기존 개발 기록이며 이번 작업에서 재검증하지 않았습니다.

## Historical limitations — v0.2

- Operators, age restrictions, hours, bookings, warning bulletins and on-site access are unverified.
- OSRM road routes and exact-ID TourAPI photos are implemented. Driving estimates exclude traffic;
  ferry routes and parking access remain unsupported or unverified.
- Initial scheduling uses straight-line candidate filtering and duration assumptions; subsequent
  enrichment may report travel-gap warnings. Replacement checks adjacent road-route feasibility.
- Marine slots require favorable, current marine forecasts. Missing weather remains unknown;
  it does not independently block every index-based provisional marine candidate.
- Weather is for a representative tourism point, not every visit. The 8 m/s wind cutoff and
  visit/buffer durations are prototype heuristics, not validated safety thresholds.
- Plans live in one process for two hours, capped at 128 entries. There is no authentication,
  shared multi-worker registry, stream reconnect endpoint or production/load evaluation.
- No comprehensive family-suitability, accessibility, device-matrix or Korean LLM evaluation
  establishes reliability. Model prose can diverge from the structured evidence.

## Existing v0.2 release checks — historical development record

- Python regression suite: **37 passed**. Frontend Node tests: **4 passed**.
- The live browser received task status before Qwen completed the itinerary. Closing
  the progress dialog did not interrupt generation; the completed draft still rendered.
- Live photos loaded for tourism visits, with Type3 source/license links. Marine
  venues without an explicit tourism ID displayed placeholders instead of guessed photos.
- OSRM returned a real driving route from Geojampo Beach to Mashian: 1,427.7 meters,
  160.9 seconds. This is one source response, not a traffic-aware accuracy benchmark.
- A browser replacement changed Geojampo Beach to Geojampo Pier without regenerating
  the trip. Undo restored the original visit, route and photo. Fixed visits preserve
  location and image metadata; locked slots reject replacement on the server.
- A 1280px desktop viewport used side-by-side visit photos. At a 390px mobile viewport,
  photos moved above content and document width equaled viewport content width (no
  horizontal page overflow). Browser map tiles, weather cards and photo loading were
  inspected. This is not a complete accessibility/device matrix audit.
- Optional media/route failures, ferry routes, time-gap violations, stale revisions,
  registry expiration/eviction, photo ID/license checks and stream parsing have
  synthetic regression coverage. Actual provider outages were not induced.
- Public route requests are throttled and cached. OSM attribution remains visible.
- Weather summaries describe trip hours at the labeled representative forecast point;
  warnings remain unchecked. Operating hours, age limits and local restrictions remain
  unverified. The initial heuristic schedule can still have route-time warnings;
  replacement rejects new adjacent route violations rather than moving other visits.
- The status stream contains task descriptions, not internal model reasoning. The
  model's final prose can still contain inaccurate wording or mixed-language fragments.
- Screen captures: `docs/progress-v02.jpg`, `docs/preview-v02.jpg`, `docs/mobile-v02.jpg`.
- Final browser checks confirmed that replacing a day-two visit selects day two on
  the map, and keyboard selection of a day-one card selects its day-one route.
  No browser console errors were reported in these checks.

The following sections retain the original v0.1 checks for historical context.

## Historical v0.1: live source checks

- TourAPI resolved Incheon area code `2`; full collection returned 513 distinct
  content IDs. These are mixed tourism entries, not 513 family-approved attractions.
- Marine collection reached reported totals: beach 500, sea splitting 59,
  rock fishing 1,750, seasickness 382, scuba 180, mudflat 126, surfing 540,
  sea travel 290. These are national forecast records, not Incheon site counts.
- Counts were checked across every page. The snapshot was published atomically.
- Marine forecast dates in the mudflat snapshot span October 15–21.
- Weather returned forecasts using a coordinate-derived KMA grid and an available
  issue time. This does not verify weather warnings or every visited location.
- Original connection-check results: `reports/data_connections.json`.
- The original sea-travel endpoint lacked the final `2`; the official schema's
  `fcstSeaTripv2` endpoint was used without changing the supplied credential file.

## Historical v0.1: local LLM and application

- Server reported Ollama `0.33.1`; the supplied Qwen model is installed.
- Synthetic tool selection and response round trip passed.
- Live Korean request for an October 16–17 Yeongjong family trip caused Qwen to call
  `build_itinerary` successfully. One direct run took approximately 31.9 seconds,
  including tool execution and final explanation. This is not a latency benchmark.
- The draft placed a Mashian mudflat candidate at 13:30–14:30, within the source
  forecast window 12:10–15:10, leaving lunch, preparation and changing blocks.
- Actual swimming records marked `폐장` are not scheduled.
- Rule-based HTTP planning and the Korean browser form were exercised locally.
- The browser's AI button completed a real Qwen tool call. A fixed tourism visit
  remained at its original time on regeneration, and an excluded place disappeared.
  No browser console errors were reported in that flow. Desktop layout was inspected;
  mobile layout and accessibility have not received a full manual audit.
- `.env`, local snapshots and live conversation reports are excluded from Git.
  Known supplied key values were checked against staged contents before publication.

## Historical v0.1: automated checks

Offline pytest scenarios cover forecast windows, lunch adjustment, time bounds,
unfavorable/missing/closed forecasts, adverse rain, stale snapshots, reservation and
exclusion preservation, incomplete/repeated pagination, atomic refresh failure,
KMA reference grid conversion, HTTP validation, rejected tools, and model fallback.

The local release check passed **22 tests**. One dependency deprecation warning
recommends a future TestClient HTTP backend change; it did not fail the checks.

JavaScript syntax and Python compilation were checked. GitHub Actions is configured;
a local passing test run does not by itself establish remote CI success.

## Historical v0.1: limitations at that version

This section preserves the earlier version's boundaries. Its statements about absent
road routes and unused photos were superseded by v0.2; see the current limitations above.

- No verified operator age restrictions, booking availability, hours or closures.
- No warning-bulletin integration, real driving routes, ferry routes or capacity tests.
- The regional boxes and straight-line distance filters are heuristics. No equivalent
  marine conditions are inferred between nearby tourism and forecast points.
- Unknown weather does not become a favorable forecast; a marine candidate can still
  appear as provisional based on its index, with explicit missing-check notices.
- The 8 m/s hourly wind cutoff and all durations/buffers are prototype planning
  heuristics, not officially validated safety thresholds.
- Travel comfort and age-specific suitability have not been evaluated with families.
- LLM prose is not formally grounded or safety-certified. An early live answer used
  a comfort assessment beyond verified evidence; the prompt now explicitly prohibits
  such assessments, but this does not guarantee compliance.
- No image publication, public deployment, booking or notification was performed.
- Photo API credentials were checked; photo content is not used in this version.
- No multi-user load, GPU scaling, comprehensive multi-turn evaluation or production
  availability test has been performed.
