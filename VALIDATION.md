# Validation record — 2026-10-15 (Asia/Seoul)

## v0.2 release checks

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

## Live source checks

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

## Local LLM and application

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

## Automated checks

Offline pytest scenarios cover forecast windows, lunch adjustment, time bounds,
unfavorable/missing/closed forecasts, adverse rain, stale snapshots, reservation and
exclusion preservation, incomplete/repeated pagination, atomic refresh failure,
KMA reference grid conversion, HTTP validation, rejected tools, and model fallback.

The local release check passed **22 tests**. One dependency deprecation warning
recommends a future TestClient HTTP backend change; it did not fail the checks.

JavaScript syntax and Python compilation were checked. GitHub Actions is configured;
a local passing test run does not by itself establish remote CI success.

## Material limitations

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
