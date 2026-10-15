# v0.2 interfaces

Existing `/api/chat`, `/api/plan` and `/api/places` remain available. Generated plans
now contain `plan_id`, monotonic `revision`, `can_undo`, `media` keyed by tourism ID,
`routes` keyed by date, and per-item `slot_id`. Route geometry is GeoJSON, distances
are meters and durations are seconds. Unknown routes have no fabricated geometry.

## Task progress

`POST /api/chat/stream` accepts the same JSON body as `/api/chat`. Its content type
is `application/x-ndjson`. Each line is an independent UTF-8 JSON object:

```json
{"type":"stage","stage":"input","state":"completed","message":"여행 조건을 확인했어요.","elapsed_seconds":0.0}
```

Stages: `input`, `data`, `schedule`, `enrich`, `result`. Event types: `stage`,
`activity`, `tool`, `fallback`, `heartbeat`, `result`, `error`. Activity/tool events
are public work descriptions, never hidden reasoning or raw function arguments.
The terminal result event contains the ordinary chat result in `result`; a terminal
error contains a sanitized `message`. A clarification can return no plan.

The worker continues if the popup is closed or its connection drops. The browser
continues reading while the popup is hidden. This version has no reconnect/job-resume
endpoint; a page reload can lose the response. One LLM generation runs at a time;
concurrent chat requests return 429 before streaming.

## Replace, undo and locks

`POST /api/plans/{plan_id}/replace`:

```json
{"revision":1,"slot_id":"slot-token","candidate_id":"1619630"}
```

Only a tourism visit can be replaced. The candidate must be an offered, unused,
non-excluded local tourism ID. The slot ID, date, start/end times and other visits
are preserved. Both neighboring routes must be available and fit the free time
excluding meal, preparation and changing blocks. The plan revision increases.
No LLM call is made. The returned `explanation_outdated` flag marks past AI prose.

`POST /api/plans/{plan_id}/undo` takes `{"revision":2}` and restores the previous
replacement's itinerary, routes and images at a new revision. One undo is retained.

`POST /api/plans/{plan_id}/lock` takes:

```json
{"revision":1,"slot_id":"slot-token","locked":true}
```

Lock/unlock preserves tourism ID, coordinates, image association and the original
visit kind. Changing locks clears the previous replacement's undo checkpoint.

Errors: 404 for unknown slot, 409 for stale revisions or locked/ineligible slot,
410 for expired/evicted plans or a restarted server, 422 for unavailable candidates,
missing routes or insufficient travel gaps. Failures preserve the stored plan.
The registry holds at most 128 plans for two hours from creation in one process.
Run a single Uvicorn worker; multiple workers need a shared registry before deployment.

## Optional media and maps

`GET /api/config` returns public tile URL and attribution information. No source API
keys are returned. Route calls use server-side `OSRM_BASE_URL`, a project User-Agent,
one uncached request per second, and a 24-hour success cache. Short-lived failures
are cached for 60 seconds. Ferry routes are unsupported; no direct-line road fallback
is drawn. No turn-by-turn or traffic-aware navigation is claimed.

Photos use the local representative image or the same content ID's `detailImage2`.
Only approved source hosts and explicit Type1/Type3 metadata are displayed. Other
cases show a placeholder. Photo metadata is cached seven days; transient failures
are retried after five minutes. Browser images retain proportions and source links.
