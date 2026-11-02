# Operational notes · 운영 참고

[English README](../README.md) · [한국어 README](../README.ko.md) · [Data foundation](DATA.md) · [Validation](../VALIDATION.md)

## Runtime and persistence · 실행과 보관

| Component | Current behavior / 현재 동작 |
| --- | --- |
| Catalog | `data/catalog.json`; refresh with `python -m marine_agent.sync`. / 명령으로 수동 갱신. |
| Failed refresh | Incomplete marine collection preserves the previous catalog and records `data/sync_failure.json`. / 해양 수집이 불완전하면 기존 카탈로그 유지. |
| Freshness | Component timestamps remain independent: tourism older than 7 days warns, over 8 days blocks planning; legacy snapshots retain the 24-hour guard. Marine scheduling requires current-Korean-day collection. / 구성요소별 시각 유지. 관광 7일 초과 경고·8일 초과 차단, 기존 형식은 24시간 기준. 해양 편성은 한국시간 당일 수집 필요. |
| Plan registry | SQLite, 128 plans, two hours from registration; revisions and undo survive restart within retention limits. / SQLite에 등록 후 2시간·최대 128개, 보관 범위 안에서 재시작 후 리비전·되돌리기 복원. |
| Journey checkpoints | Local SQLite, 128 sessions, two hours from journey start; capacity can evict earlier. / 로컬 SQLite에 진행 시작 후 2시간·최대 128건, 용량에 따라 조기 퇴출 가능. |
| Chat concurrency | One generation; additional chat requests receive HTTP 429. / AI 생성 동시 한 건. |
| Replacement | Preserves time and other visits, checks adjacent routes, increments revision; previous AI explanation becomes outdated. / 기존 시간 유지·인접 경로 검증·리비전 증가·이전 AI 설명에 변경 전 표시. |
| Undo | One replacement checkpoint; lock changes clear it. / 직전 교체 한 건, 고정 변경 시 초기화. |
| Stream recovery | Closing the dialog does not cancel work. Form journeys recover in the same tab using a capability in sessionStorage. Running work becomes interrupted after restart and needs explicit retry; pending choices persist. Legacy chat is not resumable. / 팝업 종료는 취소가 아님. 폼 진행은 같은 탭에서 복구하며 재시작 전 실행 중 작업은 명시적 재시도 필요. 선택 대기는 유지, 기존 자유 대화는 재개 미지원. |

Use one Uvicorn worker and loopback binding. Journey capabilities and independent operator/sync tokens do not provide public account authentication. Never run native and Docker backends against the same live SQLite directory. Multi-worker deployment requires shared storage. Public APIs, remote Ollama, maps and routing still require network access.

루프백·단일 워커로 실행합니다. 진행별 접근 토큰과 운영·수집 토큰은 외부 공개용 계정 인증이 아닙니다. 네이티브와 Docker 백엔드가 같은 SQLite 디렉터리를 동시에 사용하지 않도록 합니다. 다중 워커는 공유 저장소가 필요합니다. 공공 API·외부 Ollama·지도·도로 경로 호출에는 네트워크가 필요합니다.

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
| HTTP 410 / 일정 만료 | Generate a new itinerary after expiry or eviction; restart alone does not erase persisted plans. / 만료·퇴출 시 재생성. 재시작만으로 저장 일정이 지워지지는 않음. |
| HTTP 422 on replacement / 교체 거부 | Choose another offered candidate; check eligibility, routes and travel gaps. / 제안된 다른 후보 선택·교체 조건·경로·이동 여유 확인. |
| No photo or route / 사진·경로 없음 | Check source availability and accepted metadata; missing evidence intentionally produces placeholders. / 원천 제공 여부·허용 메타데이터 확인. |

## GitHub repository metadata · 저장소 소개 설정

Suggested values for the GitHub sidebar follow. This documentation refresh does not change remote repository settings.

GitHub 우측 About에 사용할 수 있는 문구입니다. 이번 문서 작업에서는 원격 저장소 설정을 변경하지 않았습니다.

**Description (English):**

```text
Forecast-aware Korean coastal travel agent with bounded Ollama tools, resumable LangGraph journeys, public-data pipelines and inspectable trip editing.
```

**한국어 소개:**

```text
관광·해양·기상 공공데이터와 제한된 Ollama 도구, 재개 가능한 LangGraph로 전국 해안 여행 초안과 방문 단위 수정을 제공하는 AI 에이전트.
```

**Suggested topics:** `ai-agent`, `ollama`, `tool-calling`, `fastapi`, `python`, `travel-planner`, `marine-forecast`, `public-data`, `langgraph`, `n8n`, `langfuse`, `leaflet`.

## Documentation map · 문서 안내

| Document | Read it for / 용도 |
| --- | --- |
| [README.md](../README.md) / [README.ko.md](../README.ko.md) | Project overview and setup, English first / 프로젝트 소개·실행. |
| [DATA.md](DATA.md) / [data-profile.json](data-profile.json) | Data grain, dated counts, quality controls and aggregate evidence / 데이터 단위·건수·품질 범위. |
| [VALIDATION.md](../VALIDATION.md) | Re-run tests separated from earlier live observations / 재실행 검사와 과거 실제 실행 근거 구분. |
| [API-v02.md](API-v02.md) | Stream events, replacement payloads and revision errors / 스트림·교체·오류 계약. |
| [LANGGRAPH.md](LANGGRAPH.md) / [PLANNING_RULES.md](PLANNING_RULES.md) | Journey recovery, choices and weather/pace rules / 진행 복구·선택·날씨·여행 속도 규칙. |
| [WORKFLOWS.md](WORKFLOWS.md) / [OBSERVABILITY.md](OBSERVABILITY.md) | Collection schedules, operator authentication and execution graphs / 수집 일정·운영 인증·실행 그래프. |
| [ROADMAP.md](ROADMAP.md) | Implemented features and pending feasibility work / 구현·후속 검증 과제. |

README badges are local SVG labels for the inspected version and stack. The overview strip records 195 Python and 28 Node.js tests passed on November 2, 2026; it is a dated result. These assets do not report remote CI, coverage, production readiness or license status. Hero route/card illustrations are schematic; the gallery contains dated development screens, including explicitly labelled synthetic scenarios.

README 배지는 로컬 SVG로 작성한 버전·기술 표시입니다. 핵심 수치 스트립의 테스트 223개는 2026년 11월 2일의 Python 195개·Node.js 28개 통과 기록이며 원격 CI·커버리지·운영 준비·라이선스 상태를 나타내지 않습니다. 배너의 경로·일정 카드는 개념 그림이고 갤러리는 날짜별 개발 기록이며 명시적으로 표시한 합성 검증 화면도 포함합니다.
