# Weather-aware planning rules / 날씨·동행·이동 기반 배치 규칙

## Contract

Qwen chooses tools and explains results; `rules.py` and `planner.py` enforce the same policy for AI and rule-only requests. This is a provisional scheduling policy, not a safety assessment. Existing trips are not monitored or automatically rewritten when a new forecast is published. Generate again to use fresh forecasts. Transport is never changed without the traveler choosing it.

The executable [20 input/output cases](planning-scenarios.json) test candidate eligibility. Each case specifies its visit time, hourly forecast fields, reviewed venue facts, traveler input and exact expected allow/reject codes. A further 13 integration cases in [the test suite](../tests/test_planning_rules.py) cover actual placement, shortage, reservations, routes, food, replacement and ferries. Dates use **T = tomorrow in Asia/Seoul**, so tests remain rerunnable.

### Concrete end-to-end scenarios

All place names/IDs below are synthetic fixtures, not real opening or safety claims.

| Scenario | Input | Expected result |
|---|---|---|
| Morning outdoors, rainy afternoon | T, 09–18, walking, 2 visits; PTY=0 before 13:00 and 1 afterwards; place 0 reviewed outdoor, places 1–3 indoor; 1-minute/100m routes | First outdoor visit before noon, second verified indoor after 13:00; walking retained; rain explanation |
| No verified indoor supply | T, 09–18, 5 visits; rain all day; no reviewed indoor facts | 0 automatic tourist visits; meal placeholder retained; explicit 5→0 shortage and indoor-evidence warning; no invented venues |
| Locked rainy/closed booking | T, place 0 fixed at 14–15; reviewed closed on T and outdoors during rain | Same ID/time retained; `locked_conflict` with weather/closure reasons; ask traveler to resolve booking |
| No route / insufficient travel time | T, 5 visits, walk or car; all inter-place routes unavailable or 999999 seconds | At most one unanchored visit; subsequent visits omitted with route/time explanation |
| Rainy walking burden | T, walking, 5 visits, indoor supply; every inter-place route 900m | At most one visit because wet-leg limit is 500m; propose choosing transit; never silently use car |
| Young children, short day | T, 10–15, children 3 and 8, 6 requested visits | 60-minute visits, 30-minute rest blocks, fewer than 6 visits; lunch/bounds retained; no child-suitability claim |
| Group | T, 10 adults | 15-minute route/assembly allowance; group booking/capacity warning |
| Expired or partial weather | Forecast issued two days ago, or only 10:00 PTY available | Unknown/incomplete weather warning; no inferred sunshine or rain from the stale data |
| Hour boundary | Rain hourly interval 10–11; visit 10:30–11 vs 11–11:30 | First overlaps rain; second does not overlap that interval |
| Invalid venue evidence | Auth query URL, invalid time 12:99, or review from 2000 | Facts ignored; venue stays unknown, never verified indoor |
| Closed restaurant / optional cafe | Only candidate restaurant 99 is reviewed closed on T | Keep lunch placeholder; no closed restaurant/cafe inserted; no overlap |
| Replace with unknown venue during rain | Existing registered plan, candidate 3 unreviewed, rain in target slot | Reject with 422; same revision/items/routes/media preserved |
| Ferry return cancelled/unknown | Reviewed test island, outbound 10–11, return 16–17 but cancelled/unknown | No verified round-trip plan; existing `IslandUnavailable` error. Conditional island drafts remain explicitly unconfirmed |

### Priorities and thresholds

1. Honor known closure/hours/age/capacity constraints for automatic visits.
2. Preserve locked bookings, exposing conflicts rather than claiming they are feasible.
3. Apply weather and walking policies to the visit and adjacent access window.
4. Preserve meals, rests and each day's bounds; reduce visit count if necessary.
5. Rank remaining candidates by weather preference, marine outlook and proximity.

- Known rain/snow: PTY > 0 in an overlapping hourly interval → require **reviewed indoor** tourist/food candidates. Mixed/unknown are not indoor. The hour preceding a half-hour visit is checked, not just hour labels that fall inside it.
- POP ≥ 60%, without PTY precipitation → prefer indoor, retain outdoor fallback and explain uncertainty.
- WSD ≥ 8m/s → require indoor candidates in the affected window.
- Incomplete PTY coverage or issue age over 12 hours → mark uncertainty; do not replace missing fields with sunshine/zero. Valid precipitation in a partially covered period still applies.
- Walking: max 1500m per leg / 5000m between scheduled stops per day; relaxed pace or a child ≤5: 800m / 2500m. Wet/windy leg: max 500m. Missing routed distance is not zero. Distances exclude an unknown hotel/start point and walking within attractions.
- Relaxed pace / child ≤5: 60-minute visits, 30-minute rests, 15-minute travel allowance. Normal: 90-minute visits and 15-minute rests. Active: 90-minute visits without added rest blocks. Group: at least 15-minute rest/assembly and route allowance. These are editable product assumptions, **not official safety thresholds or medical advice**.
- Known dated opening windows must contain the full visit. Unknown hours retain a check label. A reviewed age/capacity limit can exclude; absent limits do not establish suitability/availability.
- Marine outlook remains separate from land weather. A good sea grade cannot override rain. Existing swimming/experience and reviewed ferry restrictions remain in force.
- Candidate search is bounded: up to 200 regional candidates, best 12 candidates per placement, up to 8 nearby food candidates. This is a heuristic draft, not a globally optimized itinerary.

## Source-reviewed venue facts

TourAPI content type 14 is **not** proof of an indoor venue. No production venues are certified by this patch. Without reviewed facts, rainy slots may have no tourist visits. Grow coverage by reviewing actual venue/operator sources, using exact TourAPI IDs.

Store reviewed facts in ignored `data/reviewed_venues.json` (mounted into the app by existing Compose). Format:

```json
[
  {
    "id": "123456",
    "environment": "indoor",
    "source_url": "https://example.org/official-venue-information",
    "checked_at": "2026-11-02T15:00:00+09:00",
    "valid_until": "2026-11-09",
    "hours": {"2026-11-03": [["09:00", "12:00"], ["13:00", "17:00"]]},
    "closed_dates": ["2026-11-04"],
    "min_age": 6,
    "max_party": 10
  }
]
```

This example is fictional; do not copy it into production as evidence. Omit unverified age/capacity/hours. `hours[date]=[]` means confirmed closed for that date; an absent date means unknown. Reviews must use HTTPS URLs without credentials/query strings, a timezone-aware review time within 30 days, and validity covering the travel date. Malformed or duplicate files are ignored; stale entries do not certify venues. The URL is a citation only and is never executed by the rule engine.

Each day exposes `rule_summary` (version, decisions, profile, product thresholds and reviewed count); each automatic tourist visit exposes `rule_evidence`. The traveler sees applied reasons, source-linked venue type and remaining checks. Existing NDJSON/SSE event format and 7-day summary-only telemetry remain unchanged; raw venue data, coordinates and conversations are not added to telemetry.

## 한국어 운영 안내

AI 요청과 규칙 기반 요청은 동일한 Python 규칙을 사용합니다. 위 표와 JSON은 **합성 입력·기대 결과**이며 실제 관광지 검증 자료가 아닙니다.

- 비·눈·강풍 시간대에는 확인된 실내 후보를 배치합니다. 실내 정보가 없으면 야외를 실내로 바꾸어 표기하지 않고 방문 수를 줄입니다.
- 오전 야외·오후 실내 배치는 운영시간·고정 예약·경로가 허용할 때 적용합니다. 기존 일정을 날씨 변화에 따라 자동 감시·수정하는 기능은 포함하지 않습니다.
- `data/reviewed_venues.json`에 정확한 관광지 ID와 출처·확인일·유효일을 등록해야 실내·운영·연령·수용인원 규칙이 실제 장소에 적용됩니다. 현재 패치 자체가 전국 장소의 실내 여부를 검증한 것은 아닙니다.
- 여행 속도는 ‘여유롭게 / 보통 / 알차게’로 선택합니다. 개인·커플이라는 이유만으로 빠른 일정을 가정하지 않습니다. 영유아·단체에는 추가 여유를 반영합니다.
- 도보 누적 거리는 일정의 장소 사이 경로만 계산합니다. 숙소 접근·관광지 내부 이동은 포함하지 않습니다. 대중교통 변경은 제안이며 사용자 선택을 바꾸지 않습니다.
- 고정 예약은 그대로 남기고 날씨·운영·이동 충돌을 경고합니다. 실제 결항·통제 데이터가 연결되지 않은 섬 내 초안은 왕복 확정 일정으로 바뀌지 않습니다.
- PDF와 화면에는 날짜별 적용 이유·미확인 정보가 함께 남습니다. 수치 기준은 서비스 배치 정책이며 공식 안전 판단 기준이 아닙니다.

Run: `python -m pytest tests/test_planning_rules.py -q`.
