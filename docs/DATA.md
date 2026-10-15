# Data foundation · 데이터 기반

[English README](../README.md) · [한국어 README](../README.ko.md) · [Validation](../VALIDATION.md) · [Aggregate profile](data-profile.json)

This document describes the inspected implementation and the local catalog collected at **2026-10-15T16:42:01.930293+09:00**. Counts below were recomputed from the existing file during the documentation refresh. No new provider requests were made. The ignored source catalog is not bundled with a fresh clone.

이 문서는 현재 코드와 **2026년 10월 15일 16:42:01 KST** 수집본을 대상으로 합니다. 건수는 이번 작업에서 기존 로컬 파일을 다시 집계했으며 원천 API를 재호출하지 않았습니다. 원본 카탈로그는 Git 제외 대상이므로 새 복제본에 포함되지 않습니다.

## Entities and grain · 데이터 단위

| Entity | Grain and identity | Interpretation / 해석 |
| --- | --- | --- |
| Tourism | TourAPI Incheon entry; string `contentid`. | Mixed tourism categories, including entries not used in planning. / 여행 편성에 쓰지 않는 유형도 포함. |
| Marine index | Feed-specific forecast record, with site/date and potentially additional dimensions. | A site can contribute multiple records; national row counts are not venue counts. / 전국 행 수를 고유 체험장 수로 해석할 수 없음. |
| KMA weather | Grid + issue time + forecast date/hour + category; condensed into hour/category dictionaries. | Representative forecast point, not observations at every visited venue. / 방문지별 실측 날씨가 아님. |
| Photo | Tourism-ID-associated metadata and accepted license code. | No inferred match from a similar name or nearby venue. / 유사 이름·인근 장소의 사진을 추정 연결하지 않음. |
| Route | Ordered coordinate pair and OSRM provider; GeoJSON geometry, meters and seconds. | Road-network estimate without current traffic or verified parking access. / 실시간 교통·주차장 접근 미검증. |

## Inspected catalog · 확인한 카탈로그

| Tourism measure | Result |
| --- | ---: |
| Incheon area code / 인천 지역 코드 | `2` |
| Collected entries / 수집 레코드 | 513 |
| Distinct nonempty content IDs / 고유 비어 있지 않은 ID | 513 |
| Duplicate IDs / 중복 ID | 0 |
| Basic coordinate-range pass / 기본 좌표 범위 통과 | 511 |
| Missing, invalid or out-of-range coordinates / 미통과 좌표 | 2 |
| Entries in planning content types `12`, `14`, `28`, before regional filtering / 권역 필터 전 편성 유형 | 185 |

The coordinate screen parses finite numeric latitude/longitude and applies `33 < latitude < 39` and `124 < longitude < 132`. It does not verify a point's true position, its administrative area or road access. A numeric coordinate within that rectangle is not a validated geocode.

좌표 검사는 유한한 숫자로 변환 가능한지와 위도·경도 범위만 확인합니다. 실제 위치·행정구역·도로 접근을 검증하지 않습니다. 좌표 범위를 통과했다는 사실만으로 정확한 지오코딩으로 판단할 수 없습니다.

### Marine feed inventory · 해양 피드

| Feed key | Activity / 활동 | Forecast rows / 예보 행 |
| --- | --- | ---: |
| `beach` | Swimming / 해수욕 | 500 |
| `seasplit` | Sea splitting / 바다갈라짐 | 59 |
| `fishing` | Rock fishing / 갯바위낚시 | 1,750 |
| `sickness` | Seasickness / 뱃멀미 | 382 |
| `scuba` | Scuba / 스킨스쿠버 | 180 |
| `mudflat` | Mudflat experience / 갯벌체험 | 126 |
| `surfing` | Surfing / 서핑 | 540 |
| `seatrip` | Sea travel / 바다여행 | 290 |
| **Total / 합계** | **National forecast records / 전국 예보 레코드** | **3,827** |

All eight inspected feeds have requested date `20261015` and forecast dates spanning **October 15–21, 2026**. This is the observed file coverage, not a guarantee of future service horizons or availability. Only mudflat experiences are automatically scheduled.

확인한 8종의 요청 날짜는 `20261015`, 예보 날짜 범위는 **2026년 10월 15~21일**입니다. 이 수집본의 관찰 범위이며 향후 서비스 제공 기간이나 가용성을 보장하지 않습니다. 자동 편성은 갯벌체험만 지원합니다.

### Candidate filtering · 후보 필터

`tourism_candidates` uses content types `12`, `14`, `28`, parseable coordinates and region bounding boxes. Running that function with `limit=200` over this catalog returns:

| Region / 권역 | Candidates / 후보 |
| --- | ---: |
| Yeongjong–Yongyu / 영종·용유 | 29 |
| Ganghwa / 강화 | 57 |
| Songdo–urban Incheon / 송도·도심 | 60 |

Counts describe the implemented filters; they are not audited family-friendly attractions. Region boxes are heuristics, not administrative boundary polygons. Initial visit selection additionally applies exclusions, used IDs and a 12 km straight-line proximity rule when a previous point is available.

건수는 코드상 후보 필터의 결과이며 검증된 가족 관광지 수가 아닙니다. 권역은 행정구역 폴리곤 대신 좌표 사각형을 사용합니다. 초기 방문 선택에는 제외·기사용 ID와 이전 지점이 있을 때의 직선거리 12km 조건이 추가됩니다.

## Collection contract · 수집 검증

1. Fetch each page until the reported total is reached. Reject changed totals, repeated full rows, early exhaustion, excess records and pagination-limit failures.
2. Check tourism IDs separately for uniqueness; preserve IDs as strings in candidate output.
3. Require successful completion of all eight marine feeds before publishing a new catalog. Incomplete marine refresh writes a sanitized failure record and retains the previous catalog.
4. Write JSON to a temporary file and replace the catalog after successful collection. This is local-file replacement, not a transactional database or a concurrent multi-writer guarantee.

1. 보고 총건수까지 수집하며 총건수 변동·동일 행 반복·조기 종료·초과·페이지 한도 실패를 거부합니다.
2. 관광지 ID 고유성을 별도로 확인하며 후보 출력의 ID는 문자열로 유지합니다.
3. 해양 8종 수집이 완료된 뒤 새 카탈로그를 반영합니다. 해양 수집 실패 시 기존 카탈로그를 보존하고 정제된 실패 기록을 남깁니다.
4. 임시 JSON 파일을 작성한 뒤 교체합니다. 데이터베이스 트랜잭션이나 여러 수집 프로세스의 동시 쓰기를 보장하는 구조는 아닙니다.

## Freshness and spatial semantics · 최신성과 공간 해석

- **Collection time vs. forecast time:** `collected_at`, `requested_date`, forecast dates and KMA `issue_at` have different meanings. They should not be substituted for one another.
- **Freshness gates:** planning rejects a catalog older than 24 hours. Marine slots additionally require a catalog collected on the current Korean calendar date; a previous-evening catalog can therefore be too old for marine use before it is 24 hours old.
- **Regional selection:** marine sites are filtered by their own coordinates. A favorable forecast is not transferred to a nearby tourism venue. Operator-to-forecast-site associations remain unverified.
- **Unknown conditions:** unavailable marine forecasts do not enable marine slots. Missing weather remains unknown but does not block every index-based provisional candidate. The UI retains warning/operating-condition checks.

- **시각 구분:** 수집 시각·요청 날짜·예보 날짜·기상청 발표 시각은 각각 다른 의미입니다.
- **최신성:** 일정 생성은 24시간을 초과한 카탈로그를 거부하고, 해양 편성은 한국시간 당일 수집을 추가 요구합니다. 전날 저녁 자료는 24시간 전이라도 해양 편성에는 사용할 수 없습니다.
- **공간 연결:** 해양 지점은 해당 좌표로 필터링하며 좋은 지수를 인근 관광지에 옮겨 적용하지 않습니다. 운영 체험장과 예보 지점의 공식 대응은 미검증입니다.
- **미확인 상태:** 해양예보 누락은 편성 근거가 되지 않습니다. 기상 누락은 미확인으로 유지하지만 모든 지수 기반 후보를 차단하지는 않습니다.

## What these checks do not establish · 품질 검사의 경계

Record completeness relative to a reported API total does not prove semantic accuracy, source freshness, operator availability, age suitability, warning coverage, route feasibility or model grounding. Photos and map sources also retain their own terms. Use the [validation record](../VALIDATION.md) alongside this profile.

API 보고 총건수와 일치한다는 사실은 의미 정확성·원천 갱신·운영 여부·연령 적합성·특보 확인·경로 실현 가능성·AI 설명의 근거 일치를 증명하지 않습니다. 사진·지도 이용조건도 별도 적용됩니다. [검증 기록](../VALIDATION.md)과 함께 확인해야 합니다.
