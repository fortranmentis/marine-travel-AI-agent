# v0.5 — PDF export, attraction selection and live ferry observations

> For dated ferry and public transport API endpoints, see the [v0.6 contract](TRANSPORT_API.md). The browser ferry adapter below remains today-only.

**v0.5.1 update:** [Conditional island tourism drafts](ISLAND_DRAFTS.md) now
enable the five former forecast-only UI selections. Full round-trip access is
still unverified; the today-only adapter contract below is unchanged.

English first; Korean behavior notes follow each contract. Existing trip, revision,
stream and replacement contracts remain in [v0.2](API-v02.md), [v0.3](API-v03.md)
and [v0.4](API-v04.md).

## Setup

Install `requirements.txt`, then `python -m playwright install chromium` for the
public-screen adapters. Existing transit browser-path configuration also applies
to ferries. No new ferry API key is required by this adapter; `KOMSA_API_KEY` is
not used by it. A network-accessible official page and compatible Chromium are
required. Browser failure leaves an explicit unavailable result.

PDF rendering uses ReportLab and embeds a local Korean TrueType font. Windows
detects `C:/Windows/Fonts/malgun.ttf`. On Debian/Ubuntu install `fonts-nanum`, or
set `PDF_FONT_PATH` to an available licensed Korean TTF. A missing font returns
503 with setup guidance. Font files, generated PDFs and local browser binaries
are not committed. Run a single Uvicorn worker as before.

실제 배편 조회는 별도 키 없이 공식 공개 화면을 읽습니다. PDF 한글 폰트는
서버에 설치된 파일을 사용하며 Linux에서는 별도 설치·설정이 필요합니다.

## GET `/api/plans/{plan_id}/pdf?revision=N`

- `revision` is required, integer >= 1. The server copies the stored plan only if
  the current revision matches. It does not regenerate the trip or call providers.
- Success: `application/pdf`, attachment filename including region/date/revision,
  `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.
- Includes party, day windows, sea-travel grade, weather during those windows,
  visits, addresses, food details, adjacent transfer summaries, caveats and source
  timestamps. Missing forecasts/routes stay unknown; ground transfers are not
  invented across a scheduled ferry leg. Dynamic strings are XML-escaped.
- Photos and interactive maps stay in the web view. Each subsequent itinerary
  day starts on a new page; long days may span pages. Korean text is embedded.
- 409: stale revision. 410: missing/expired plan. 422: invalid revision. 503:
  unavailable font or busy/failed PDF rendering. Rendering is serialized with a
  short lock wait. Existing plan limit: 128 entries / 2 hours in one process.
- The web button exports the currently displayed revision. A concurrent edit can
  trigger 409; the application shows the error instead of saving another revision.

화면의 **일정 PDF 저장** 버튼으로 현재 버전을 내려받습니다. 만료·서버 재시작으로
일정이 없으면 다시 생성해야 합니다. 지도·사진은 PDF에 포함하지 않습니다.

## GET `/api/ferries/live?office=인천&date=YYYY-MM-DD`

Source: [KOMSA official public operation screen](https://www.komsa.or.kr/prog/pssgCurState/kor/sub03_0202/list.do).
Playwright operates its management-office selector and search control, then reads
the rendered table. It does not use hidden JSON endpoints or bypass a login.

`office` defaults to 인천. Allowed values: 전체, 부산, 인천, 완도, 목포, 제주, 여수,
전북, 보령, 통영, 경북, 강원, 고흥. `전체` is a selector, not a thirteenth office.
The source's management jurisdictions do not equal tourism/forecast regions.
`date` defaults to today in Korea. Invalid office/date returns 422; a valid date
other than today returns `date_unsupported` with no sailings.

Available response example (abbreviated schema; not a current sailing):

```json
{
  "status": "available",
  "office": "인천",
  "date": "2026-10-16",
  "as_of": "2026-10-16T10:57:00+09:00",
  "observed_at": "2026-10-16T10:58:00+09:00",
  "count": 1,
  "rows": [{
    "departure": "11:00", "vessel": "source vessel", "route": "source route",
    "origin": "source port", "direction": "source direction",
    "licensed_route": "source licensed route", "operation": "정상",
    "operation_status": "reported_normal", "departure_status": "출항전",
    "arrival": null, "destination": null, "remaining_seats": null, "fare": null
  }],
  "arrival_verified": false,
  "reservation_verified": false,
  "usable_for_planning": false,
  "cached": false
}
```

The complete response also preserves route type, reason, source URL and notes.
`정상`, `증회`, `증선` map to `reported_normal`; `비운`, `결항`, `통제`, `휴항`
map to `not_operating`; other operation labels remain `unknown`. The source's
departure status `완료` is not an independently verified arrival timestamp.

The source timestamp must be today and no more than 30 minutes old. An invalid
timestamp/table or browser failure yields `unavailable`; an old source timestamp
yields `stale`. Both omit rows. Malformed rows are skipped and counted. No usable
rows after malformed input is an unavailable result. Header changes fail closed.

Success cache: 5 minutes; failure cache: 1 minute; 16 entries maximum in memory.
The source freshness is checked again on cache reads. One browser lookup runs
at a time, with a 35-second subprocess deadline and process-tree cleanup on
timeout. HTTP responses use `no-store`. The UI queries only on demand, shows 40
rows at a time with “more”, and filters the returned licensed-route value exactly.

The sixth typed agent tool, `get_ferry_operations`, accepts the same office and
optional date. To bound model input it returns at most 12 rows, with the complete
count and an explicit truncation note. It is not a complete route search result.

한국어: 오늘의 출항편·선박·운항상태를 실제 조회합니다. 정상=예약 완료,
출항 완료=도착 확인으로 해석하지 않습니다. 도착시각·미래 시간표·잔여석을
임의 계산하지 않으며, 기존 섬 편성의 왕복·접근 검증 조건을 우회하지 않습니다.
도서 예보 5개 권역과 검토용 섬 명세는 계속 별도입니다. 대규모 운영의 제공기관
이용조건·용량 검토와 안정적인 날짜별 시간표/도착 자료 연결은 후속 과제입니다.

## Automatic tourism selection

[`attractions.py`](../marine_agent/attractions.py) is shared by regional search,
AI candidate lookup, initial planning, alternatives and reviewed-island candidate
selection. Eligible source types remain 12/14/28. Category exclusions cover
convention centers, performance venues, culture centers, libraries, large
bookstores, cinemas, language schools and schools. Explicit title rules also
remove generic culture/public halls, welfare/administrative centers and ordinary
sports facilities. Exact rules are inspectable in the module.

Museums, galleries, memorials, exhibitions and heritage/nature attractions are
retained. This policy can exclude a facility that has a worthwhile specific
program; program-level discovery is not implemented. Explicit fixed visits are
preserved. Existing stored itineraries are not retroactively rewritten.

Snapshot profile: [10,102 records; 5,176 tourism-type rows; 81 excluded; 5,095
remaining before region/access screening](v05-profile.json). This profiles the
existing October 16 catalog, not a fresh collection. It does not establish
operating hours, indoor status, child suitability or accessibility.

한국어: 문화회관 등 목적이 불분명한 일반 시설을 자동 관광 후보에서 제외합니다.
박물관·미술관 등은 유지하며 사용자가 고정한 방문은 임의로 삭제하지 않습니다.
