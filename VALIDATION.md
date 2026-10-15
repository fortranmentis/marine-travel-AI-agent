# Validation record — 2026-10-15 (Asia/Seoul)

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
