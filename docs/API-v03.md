# v0.3 — Travel preferences and transport readiness

The existing endpoints remain compatible. `POST /api/plan`, `/api/chat` and
`/api/chat/stream` accept these additional Trip fields:

| Field | Default / behavior |
| --- | --- |
| `party_type` | `family`; also `solo`, `couple`, `group`. UI offers starting headcounts; users can edit them. |
| `adults` | 2; 1–50. Group capacity at venues is unverified. |
| `child_count` | Inferred from `child_ages` for legacy requests; explicit count must match ages (0–8 children, ages 0–17). |
| `transport` | `car`, `walk`, `transit` (bus/subway + walking). |
| `visits_per_day` | 2; 1–6. Counts tourism and marine visits, including those fixed by the user; excludes food, rest, ferries and transport. Feasible count may be lower. |
| `cuisines` | Empty means all; `korean`, `chinese`, `japanese`, `western`, `other`. |
| `cafes` | `true`; attempt one cafe between located visits when time and routes permit. |
| `daily_times` | `[{"date":"2026-10-16","start":"10:00","end":"17:00"}]`. Dates must be unique and within the trip. Omitted dates use legacy `day_start` / `day_end`. End must follow start; no overnight time interval. |
| `island_id` | `null`. Reviewed passenger-ferry **one-day round trips** only. Mainland travel to the departure port is outside this draft. |

Days retain `day_start`, `day_end`, `transport`, requested/actual visit counts,
warnings, `food_recommendations`, and `travel_index`. The plan also includes an
overall `travel_index`. Index grades are the worst official grade across required
half-days/days; missing or stale coverage yields no overall grade. The named
`인천내륙` reference outlook is displayed for the three mainland regions; it is
not a venue forecast or an official composite land-tourism score. No point forecast
is transferred to an unreviewed island. Warning bulletins and ferry operations are separate.

Food uses TourAPI content type 39 and the verified `categoryCode2` mappings:
`A05020100` Korean, `A05020200` Western, `A05020300` Japanese, `A05020400`
Chinese, `A05020700` other, `A05020900` cafes/traditional tea. Clubs are excluded.
Source category errors are possible: cards label the source classification and
show `detailIntro2` menu/hours when available. Opening calendars, dietary suitability
and capacity are **not** automatically verified. Lunch and dinner are reserved
when a full meal window fits. Failure leaves an unlocated break or candidate list;
food/cafes never consume the selected attraction count. Nearby distances in candidate
lists are straight-line distances; scheduled food uses route-time checks.

## Walking and public transport

- `OSRM_FOOT_BASE_URL=https://routing.openstreetmap.de/routed-foot` uses a distinct
  foot graph; the service's `/route/v1/driving/` URL suffix does not choose the graph.
- `ODSAY_API_KEY` enables the server-only ODsay adapter. Its urban bus/subway path
  results provide section times, lines and fares. Only car/walking geometry is
  drawn; transit lines are listed as instructions, never fabricated as a straight line.
- Transit results are **general route estimates**, not verified future departure,
  first/last-service or live timetable results. No key means explicit
  `not_configured`; the planner cannot establish inter-visit transit feasibility.
- Existing car behavior remains a heuristic draft with post-generation route-gap
  checks. Walking/transit visit insertion and replacement check neighboring routes;
  missing routes never fall back to the car graph.
- Public routing remains serialized at at most one uncached request per second;
  successful car/foot routes cache for 24h, transit results for 1h. API keys stay
  on the server. Production traffic needs an appropriately provisioned provider.

References: [FOSSGIS policy](https://routing.openstreetmap.de/about.html),
[ODsay API](https://lab.odsay.com/guide/releaseReference).

## Ferries: connection preparation, not live availability

The user has no additional transit/ferry keys yet. No live ferry island is enabled
by default. `GET /api/config` returns mobility readiness and only fresh reviewed
islands. The UI never offers an island with missing/expired review data.

1. Obtain approval for [KOMSA schedule data](https://www.data.go.kr/data/15142302/openapi.do)
   and the needed [route data](https://www.data.go.kr/data/15142301/openapi.do)/arrival-time
   service. Configure `KOMSA_API_KEY` in the server environment or ignored `.env`.
2. `python -m marine_agent.ferries --date YYYY-MM-DD --vessel "EXACT VESSEL NAME"`
   collects raw schedules to ignored `data/ferry_schedule_raw.json`. Both filters
   are required by the inspected official schema. This does **not** activate trips.
3. Review the exact outbound/return ports, TourAPI place IDs, real arrival times,
   operating status and official source links. A raw schedule alone does not prove
   arrival time or that a return trip is available. Do not infer unknown status as operating.
4. Store an array matching [the reviewed island schema](reviewed-island.schema.json)
   in ignored `data/reviewed_islands.json`. Each entry requires an aware `reviewed_at`,
   exact island `place_ids`, mainland/island ports, and dated crossings with direction,
   vessel, departure, arrival, status (`scheduled`, `cancelled`, `unknown`), source URL.
   Review must be within the last 24h. Example schedules from tests are **not live data**.
5. A one-day trip requires both scheduled directions inside the requested daily
   bounds, check-in buffers (default 40min, minimum 30), and at least two hours
   between arrival and return check-in. Island walking must fit around those times.
   Cancellation, missing return or expired review blocks generation. Ferry times
   and port buffers cannot be replaced by instant attraction replacement.

Vehicle shipping, overnight island stays, live cancellations, ticket inventory,
reservations, mainland-to-port access and verified island food remain future work.
The adapter and reviewed-data scheduler are covered by offline tests; live KOMSA
and ODsay connections have not been verified without approved keys.

## 한국어 요약

개인·커플·가족·단체, 자녀 수·개별 나이, 도보, 음식 종류와 주변 식당·카페,
하루 방문 수, 일별 시작·마침, 바다여행지수 기반 전망을 추가했습니다.
날씨는 좌우 버튼·마우스 드래그·터치·방향키로 탐색합니다.
음식 종류는 원천 분류이며 실제 메뉴와 다를 수 있습니다.
대중교통은 ODsay 키가 필요하고, 여객선은 별도 승인과 항로·도착시각 검증이
필요합니다. 현재는 연결 준비 단계로 운영 가능한 섬을 제공하지 않습니다.
검증 자료를 넣은 당일 여객 왕복만 시험할 수 있으며 섬 숙박·차량 선적·예약은 미지원입니다.
