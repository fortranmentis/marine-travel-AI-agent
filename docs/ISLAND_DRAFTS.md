# v0.5.1 — Island tourism drafts / 도서 관광 초안

All 29 named forecast regions can now request a tourism draft when their pilot
catalog scope is loaded: 25 ground/bridge scopes and four conditional ferry-island
scopes. This changes the previous forecast-only UI gate. It does **not** turn a
today-only operation observation into a verified complete round trip.

| Forecast selection | Explicit pilot tourism scope | Access treatment |
| --- | --- | --- |
| 인천북서 | 백령도 | Conditional on-island draft; Incheon operation observations |
| 인천남서 | 덕적도 | Conditional on-island draft; Incheon operation observations |
| 신안북동 | 증도 | Bridge-connected tourism scope; no ferry invented |
| 신안남서 | 흑산도 | Conditional on-island draft; Mokpo operation observations |
| 여수도서 | 거문도 | Conditional on-island draft; Yeosu operation observations |

These are inspectable application pilot mappings, **not official forecast
polygons**, exhaustive island coverage or a guarantee that every attraction on
the island is loaded. Exact TourAPI IDs are in
[`island_drafts.py`](../marine_agent/island_drafts.py). The bridge classification
for Jeungdo is supported by [Sinan County's bridge description](https://eng.shinan.go.kr/home/www/openinfo/participation_07/participation_07_01/show/1026);
mainland-to-island route availability is still not verified by the plan.

## What the generated plan means

- Ferry-island plans return `status=conditional_island`. The persistent card and
  each day label the result as **왕복 배편 미확정 · 섬 내 관광 초안**.
- Daily start/end are the user's **planned time on the island**. Selected car,
  walking or reference transit applies only to island visits. The map connects
  tourism visits, not mainland access or a ferry crossing.
- The trip can span one to three days. Arrival/departure-day feasibility, lodging,
  car shipping, rentals, reservations and last-return availability are unknown.
  Multi-day caveats are repeated. Fewer visits appear when the inspected source
  candidates or route gaps cannot support the request; visits are not duplicated
  across days merely to fill a quota.
- The existing expiring reviewed-`island_id` scheduler remains separate and still
  requires dated departure/arrival pairs. Combining that mode with a pilot-scope
  selection is rejected. No reviewed manifest was invented or enabled.
- Fixed visits, alternatives and foods are confined to the pilot IDs. Coordinates
  or a nearby name do not automatically associate another island's record.
  Unmapped food venues leave an unlocated meal/rest block with an explicit note.
- Future-dated requests create tourism drafts without querying/reusing today's
  ferry data. A source failure also leaves the tourism draft usable and explicitly
  unconfirmed, rather than fabricating a crossing or failing all tourism.
- Korean PDF export includes the island title and access caveat. Replacement,
  lock/unlock and undo retain access metadata and never confirm a sailing.

## Ferry evidence in the plan

`island_access` is independent of timed `days[].items`:

```json
{
  "island": "덕적도",
  "mode": "ferry",
  "status": "unconfirmed",
  "travel_date": "2026-10-16",
  "roundtrip_verified": false,
  "arrival_verified": false,
  "mainland_access_verified": false,
  "booking_verified": false,
  "operation_status": "available",
  "matching_count": 8,
  "rows": []
}
```

This abbreviated example omits the matching observed rows. They are selected by
an **exact licensed-route allowlist**, retain source departure/operation labels,
and include both cancelled/non-operating and normal observations. They are not
paired by direction into booked outbound/return trips. Historical departures
remain observations, not suggested catchable sailings. Multi-stop arrival or
island departure times are not inferred.

The card shows up to six rows, the complete match count, the source timestamp and
an action to open today's complete management-office table. This table is the
same [v0.5 today-only adapter](API-v05.md), including its freshness, date and cache
checks. Source aliases outside the explicit list are not guessed, so an available
official table may still have zero mapped observations.

## Validation and remaining work

Run offline checks with `python -m pytest -q` and `node --test tests/web.test.mjs`.
Explicit live probe: `python scripts/check_island_drafts.py --ai` against the local
server. Local reports and plans remain ignored under `.tmp/`.

The October 16 single live observation generated visits for all five scopes;
the available source supported 2/2/2/1/1 visits respectively. Related official
departure counts were 4/8/not requested/9/4 at 11:30 KST. These are source/date/
request observations, not a service-level or feasibility guarantee. A real Qwen
request recovered from one rejected tool argument set and returned an `ok`
`build_itinerary` result with the conditional access status intact.

Next: dependable date-specific port-to-port arrivals/departures, exact terminal
coordinates, mainland access and island-port transfer validation, explicit
outbound/return selection, inventory/booking links and more island/venue records.
PATIS can display port details for some sailings, but the exploratory screen check
did not establish reliable complete data for all pilot routes; it is not used to
claim verified round trips in this release.

한국어: 권역을 선택하면 해당 시범 섬의 관광 초안을 만들 수 있습니다. 오늘 관련
배편을 보여주되 입출도 시간·항구 접근이 확정된 여행으로 표시하지 않습니다.
시간·지도·이동수단은 섬 내 관광 기준이며, 배편을 확정한 후 섬 체류시간을 바꿔
다시 생성해야 합니다. 현재 단계는 왕복 여객선 자동 확정 서비스가 아닙니다.
