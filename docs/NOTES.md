# Operational notes · 운영 참고

[English README](../README.md) · [한국어 README](../README.ko.md) · [Data foundation](DATA.md) · [Validation](../VALIDATION.md)

## Runtime and persistence · 실행과 보관

| Component | Current behavior / 현재 동작 |
| --- | --- |
| Catalog | `data/catalog.json`; refresh with `python -m marine_agent.sync`. / 명령으로 수동 갱신. |
| Failed refresh | Incomplete marine collection preserves the previous catalog and records `data/sync_failure.json`. / 해양 수집이 불완전하면 기존 카탈로그 유지. |
| Freshness | Plans reject catalogs older than 24 hours. Marine slots additionally require a catalog collected on the current Korean calendar date. / 24시간 초과 자료는 일정 생성 거부, 해양 편성은 한국시간 당일 수집 자료 필요. |
| Plan registry | One process, 128 plans, two hours from creation; restart loses plans. / 단일 프로세스 최대 128개·생성 후 2시간 보관. |
| Chat concurrency | One generation; additional chat requests receive HTTP 429. / AI 생성 동시 한 건. |
| Replacement | Preserves time and other visits, checks adjacent routes, increments revision; previous AI explanation becomes outdated. / 기존 시간 유지·인접 경로 검증·리비전 증가·이전 AI 설명에 변경 전 표시. |
| Undo | One replacement checkpoint; lock changes clear it. / 직전 교체 한 건, 고정 변경 시 초기화. |
| Stream recovery | Closing the dialog does not cancel work; page reload has no reconnect/job-resume endpoint. / 팝업 닫기는 작업 취소가 아니며 새로고침 후 재연결 API는 없음. |

Use one Uvicorn worker and loopback binding for this unauthenticated prototype. Multi-worker deployment requires shared plan storage. Public APIs, remote Ollama, maps and routing still require network access.

인증 없는 프로토타입이므로 루프백·단일 워커로 실행합니다. 다중 워커는 공유 일정 저장소가 필요합니다. 공공 API·외부 Ollama·지도·도로 경로 호출에는 네트워크가 필요합니다.

## Enrichment and credits · 사진과 경로

- Successful road routes are cached for 24 hours; route failures for 60 seconds. Uncached requests are serialized with at least one second between starts. / 정상 경로 24시간·실패 60초 캐시, 미캐시 요청 시작 간격 최소 1초.
- Photo metadata is cached for seven days; transient failures are retried after five minutes. Only approved source hosts and explicit Type1/Type3 metadata are displayed. Missing matches show placeholders. / 사진 메타데이터 7일 캐시, 일시 실패 5분 후 재시도. 허용 호스트·명시된 공공누리 1·3유형 확인 후 표시.
- Route failure never becomes fabricated straight-line road geometry. Driving estimates exclude current traffic; ferry routes are rejected. / 경로 실패를 직선 도로로 대체하지 않으며 실시간 교통·배편은 미지원.
- Source links, image-license links and OpenStreetMap attribution accompany displayed content. Vendored Leaflet retains its own license. / 출처·이용조건·지도 저작자 표기를 유지합니다.

## Troubleshooting · 문제 해결

| Symptom / 증상 | Action / 조치 |
| --- | --- |
| Missing catalog / 카탈로그 없음 | Configure credentials and run the collector before planning. / 인증 문서 설정 후 수집 실행. |
| Stale or missing forecast / 오래된 예보·예보 없음 | Refresh and check source forecast dates; missing records do not mean favorable conditions. / 갱신 후 원천 예보 날짜 확인. |
| AI unavailable / AI 연결 실패 | Check the Ollama server and model. With a usable trip and catalog, use the rule-based draft. / 서버·모델 확인, 입력·자료가 있으면 규칙 기반 초안 사용. |
| HTTP 409 / 수정 충돌 | Use the latest revision; unlock the visit before replacement if necessary. / 최신 리비전 사용·고정 방문 해제. |
| HTTP 410 / 일정 만료 | Generate a new itinerary after expiry, eviction or restart. / 만료·퇴출·재시작 시 재생성. |
| HTTP 422 on replacement / 교체 거부 | Choose another offered candidate; check eligibility, routes and travel gaps. / 제안된 다른 후보 선택·교체 조건·경로·이동 여유 확인. |
| No photo or route / 사진·경로 없음 | Check source availability and accepted metadata; missing evidence intentionally produces placeholders. / 원천 제공 여부·허용 메타데이터 확인. |

## GitHub repository metadata · 저장소 소개 설정

Suggested values for the GitHub sidebar follow. This documentation refresh does not change remote repository settings.

GitHub 우측 About에 사용할 수 있는 문구입니다. 이번 문서 작업에서는 원격 저장소 설정을 변경하지 않았습니다.

**Description (English):**

```text
Forecast-aware coastal travel agent for Incheon: bounded Ollama tools, Korean public-data pipelines, inspectable itineraries and revisioned trip editing.
```

**한국어 소개:**

```text
제한된 Ollama 도구 호출과 관광·해양·기상 공공데이터 파이프라인으로 인천 가족 여행의 검토용 일정과 방문 단위 수정을 제공하는 AI 에이전트.
```

**Suggested topics:** `ai-agent`, `ollama`, `tool-calling`, `fastapi`, `python`, `travel-planner`, `marine-forecast`, `public-data`, `incheon`, `leaflet`.

## Documentation map · 문서 안내

| Document | Read it for / 용도 |
| --- | --- |
| [README.md](../README.md) / [README.ko.md](../README.ko.md) | Project overview and setup, English first / 프로젝트 소개·실행. |
| [DATA.md](DATA.md) / [data-profile.json](data-profile.json) | Data grain, dated counts, quality controls and aggregate evidence / 데이터 단위·건수·품질 범위. |
| [VALIDATION.md](../VALIDATION.md) | Re-run tests separated from earlier live observations / 재실행 검사와 과거 실제 실행 근거 구분. |
| [API-v02.md](API-v02.md) | Stream events, replacement payloads and revision errors / 스트림·교체·오류 계약. |
| [ROADMAP.md](ROADMAP.md) | Implemented features and pending feasibility work / 구현·후속 검증 과제. |

README badges are local SVG labels for the inspected version and stack. The overview strip records 37 Python and 4 Node.js tests passed on October 15, 2026; it is a dated result. These assets do not report remote CI, coverage, production readiness or license status. Hero route/card illustrations are schematic; the JPG gallery contains actual saved development screens.

README 배지는 로컬 SVG로 작성한 버전·기술 표시입니다. 핵심 수치 스트립의 테스트 41개는 2026년 10월 15일의 Python 37개·Node.js 4개 통과 기록이며 원격 CI·커버리지·운영 준비·라이선스 상태를 나타내지 않습니다. 배너의 경로·일정 카드는 개념 그림이고 JPG 갤러리는 기존 실제 개발 화면입니다.
