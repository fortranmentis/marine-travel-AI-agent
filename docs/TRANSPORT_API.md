# v0.6 — Official transport APIs / 공식 교통 API 연동

Seven user-supplied API services are connected through a server-side allowlist.
The existing Playwright route provider remains the source of general urban
transit route candidates; TAGO now adds inspectable nearby stops, live arrivals,
route details, vehicle positions and subway reference schedules. The new APIs
do not constitute an end-to-end optimal multimodal route engine.

## Configuration and credential handling

Set `TRANSPORT_CREDENTIALS_FILE` in the ignored `.env` to an external UTF-8 text
file. Each blank-line-separated block contains a service name, `End Point :`
and `인증키 :`. The original `엔드포인트 :` / `키 :` labels also work. Only the
seven exact HTTPS public API bases in
[`transport_api.py`](../marine_agent/transport_api.py) are accepted. Keys remain
in the external file/server memory and are never sent to the frontend or model.
Do not commit the credential document. No extra Python dependency is required.

The checked-in [live evidence](../reports/transport-connections.json) contains only
operation names, statuses, counts, public source URLs and typed model tool traces.
Provider errors are sanitized; authenticated URLs and raw exception messages are
not returned. `.env.example` contains a placeholder path only.

## Connected services

| Service | Integrated use | Official contract |
| --- | --- | --- |
| KOMSA operation schedules | Exact date/vessel departures, origin/destination, operating classification and control reasons | [15142302](https://www.data.go.kr/data/15142302/openapi.do) |
| TAGO domestic ships | Port ID inventory and date-specific planned departure/arrival references | [15098523](https://www.data.go.kr/data/15098523/openapi.do) |
| TAGO subway | Station search, weekday-type/direction timetables, exit bus links | [15098554](https://www.data.go.kr/data/15098554/openapi.do) |
| TAGO bus stops | Coordinate-based nearby stop lookup | [15098534](https://www.data.go.kr/data/15098534/openapi.do) |
| TAGO bus routes | Route details, first/last source times, intervals and ordered stops | [15098529](https://www.data.go.kr/data/15098529/openapi.do) |
| TAGO bus positions | Current vehicle stop/coordinate observations; registrations omitted | [15098533](https://www.data.go.kr/data/15098533/openapi.do) |
| TAGO bus arrivals | Current arrival estimates per stop | [15098530](https://www.data.go.kr/data/15098530/openapi.do) |

## User flows

- **주변 교통(API)** on tourism/meal/cafe cards, or the origin-stop action on an
  inline transfer card: nearby stops → current arrivals → route/vehicle positions.
- **교통 API · 정류소·지하철 조회** above the results: independent public-coordinate
  stop lookup and subway station search. Select a station after setting date and
  direction. No device geolocation or personal location is requested.
- **여행일 배편 시간표 · KOMSA + TAGO API**: select one of the four ferry pilot
  scopes and a date. Rows show planned times, exact departure reconciliation and
  data-quality flags. Reference round-trip combinations are expandable.
- When ship and KOMSA credentials are configured, island draft generation adds
  `island_access.timetable` from the date-specific API adapter. It no longer relies
  only on the today-only browser table. API errors stay explicit; the older browser
  panel remains a separate user-selected view, not a silent fallback.
- Qwen has two additional typed tools: `get_ferry_timetable` and
  `get_nearby_transport`, for eight tools total. Model results are bounded to eight
  ferry rows/two pairs or the nearby-stop limit, with unverified-access notes.

## HTTP interfaces

| GET endpoint | Parameters / behavior |
| --- | --- |
| `/api/transport/nearby` | Finite Korean `lat`, `lon`; source nearby search, nearest 12 accepted stops, straight distances |
| `/api/transport/stops/{node_id}` | Numeric `city`; current arrival estimates, including valid zero seconds |
| `/api/transport/routes/{route_id}` | Numeric `city`; route metadata, ordered stops and live positions |
| `/api/transport/subway` | Nonblank `keyword` up to 40 characters; up to 30 stations with exact IDs |
| `/api/transport/subway/{station_id}` | ISO `date`, `direction=U|D`; weekday/Saturday/Sunday reference timetable and exit buses |
| `/api/ferries/timetable` | ISO `date`, `region=인천북서|인천남서|신안남서|여수도서` |

All responses use `Cache-Control: no-store` at the HTTP boundary. Service statuses
distinguish `available`, `no_data`, `not_configured`, `unavailable` and `incomplete`.
`no_data` does not mean that no bus/train/ship operates. Invalid request parameters
return 422. `/api/config.transport_api` reports configured keys, not current
provider availability. Existing plan revisions and route modes are unchanged.

## Time and identity contracts

IDs remain strings. Port joins use inspected TAGO IDs and exact names, independently
of TourAPI attraction IDs. Vessel joins use an explicit alias table, exact date,
origin/destination and departure time; there is no generic fuzzy-name join.
An ambiguous/missing departure match never becomes verified operation.

Bus arrivals and positions are **lookup-time observations**. They do not change a
future itinerary's duration or `schedule_verified` flag. Stop distances are straight
distances; a stop across water or a barrier is not automatically walk-accessible.
Stop order is not road geometry, so no invented transit line is drawn on OSM.
First/last bus times are source route-origin references, not each stop's timetable.

Subway times use the selected date's weekday category (01/02/03). Holiday exceptions
and temporary schedules are unknown, so `schedule_verified=false`. Source 24–29h
times are retained as service-day next-day times; missing values are not midnight.
An actual Saturday query in this check returned no rows where the weekday query
returned 113: coverage is tested per selected condition, not inferred from metadata.

## Ferry quality gate and current boundary

The adapter reads both pilot-port directions for the **requested date**, validates
chronological timestamps and permits a return arrival on that same date for
reference pairing. Both departures must match reported-normal KOMSA records,
with no control/non-operation reason, before a reference pair is shown. Minimum
reference stay: two hours after 15 minutes of arrival preparation and 40 minutes
of return check-in. At most eight pairs are displayed. These are assumptions,
not operator check-in requirements or a booking.

Material issues found in actual source responses:

| Finding | Evidence / consequence | Handling |
| --- | --- | --- |
| Terminal identity/address inconsistency | TAGO's Incheon terminal row carried a Yeosu address | Terminal addresses/phones are not used for navigation or automatic coordinate joins |
| Shared arrival across distinct destinations | Several rows for one vessel/departure had identical arrivals for different intermediate ports; two rows in the tested Deokjeokdo request were flagged | Retain as warning-bearing reference rows; exclude from reference pair construction |
| No independent arrival validation | KOMSA schedule response contains departure/control fields but no arrival timestamp | Even matched departures keep `arrival_verified=false` and `roundtrip_verified=false` |
| Empty condition-specific transit data | One route had no current positions; the active line-2 probe had 26. Saturday subway query had no rows | Explicit empty state; do not infer that the service is suspended |

These are high-confidence response observations. The upstream cause of the
address/arrival inconsistencies is unconfirmed; the system does not claim to have
corrected source records. Even the four tested reference round trips remain
`usable_for_planning=false`. Reservation, seats, fare confirmation, mainland port
access and vehicle shipping are unverified. Island tourism hours are not shifted
automatically from these records. Source zero fares are not a booking quote.

## Caches and bounded collection

Shared in-process response cache: 256 entries, clone-on-read, explicit source
observation time. Provider failures: 60 seconds. Typical successes: nearby stops,
route metadata, stations and weekday subway tables 24h; live arrivals/positions
20 seconds; requested-date TAGO sailings 5 minutes; KOMSA today 5 minutes and
future date 30 minutes. There is no background polling.

Pagination enforces stable totals, no repeated rows and bounded record counts;
partial/changed data cannot masquerade as a complete port inventory or route.
HTTP calls have a 15-second timeout. A ferry lookup checks at most three distinct
vessels, preserving explicit unchecked states for additional vessels. The KOMSA
portal advertises a small development-account quota; the actual account's remaining
allowance is not known, and source limit errors remain unavailable responses.
Review production capacity before scaling.

## Validation

Offline: `python -m pytest -q` and `node --test tests/web.test.mjs`.
Tests always disable the user's transport credential file. Live verification is
explicit: `python -m scripts.check_transport_connections --ai` against the running
local app. The script writes the sanitized public report linked above.

Observed October 16: all seven authenticated services returned success. Incheon
Station tests returned 10 nearby stops, live arrival data, line-2 route details
with 132 ordered stops and 26 vehicle observations; station search returned 13
matches, the selected weekday table 113 entries and seven exit-bus rows. The
October 17 Deokjeokdo reference had eight departures, eight KOMSA departure matches,
two arrival-quality flags and four unverified reference pairs. Real Qwen called
both new tools successfully. These are individual observations, not nationwide
coverage, a performance benchmark or future-trip feasibility validation.

한국어: 7종 API는 실제 호출을 확인하고 화면에 연결했습니다. 주변 정류소·현재
버스 도착·노선·차량 위치·지하철 참고 시간표를 조회할 수 있습니다. 배편은 여행일
출항 대조와 예정시간을 보여주되 도착자료 문제·예약·항구 접근이 남아 있어 확정
왕복 일정으로 자동 적용하지 않습니다. 기존 Playwright 전체 경로 조회와는 별도입니다.
