# Validation record — 2026-10-15 (Asia/Seoul)

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
