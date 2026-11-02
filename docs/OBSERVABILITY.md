# v0.8 — Live execution graphs and local Langfuse

**v0.9:** form-based journeys now use local LangGraph nodes with persisted choice/resume state. The new two-hour recovery stores contain structured trip/plan data and are separate from the seven-day summary-only telemetry described here. They are not sent to Langfuse. [Service flow, retention and recovery](LANGGRAPH.md).

## What runs where

- **Cytoscape.js 3.34.4:** the travel progress popup, completed request graph and authenticated `/ops` live graph. Color/status changes come from real execution events, not simulated percentages or model reasoning.
- **NDJSON:** the requesting traveler receives the existing stream with step IDs and timings.
- **Authenticated SSE:** `/api/ops/events` sends safe snapshots and run/step/finish updates to operators. Bearer tokens stay in request headers and browser memory, never query strings or local storage.
- **SQLite:** seven-day canonical execution summaries, including repeats and errors.
- **Langfuse 4.72.0 OSS / Python SDK 4.18.0:** optional asynchronous OpenTelemetry export with the **same run ID as trace ID**. It is not the event transport for the live graph.
- **n8n:** still owns collection scheduling. AI itinerary execution is visualized in the app and traced in Langfuse, not moved into n8n.

Solid graph edges mean parent/child membership; dashed edges mean start order. They are not invented data dependencies. Repeated tool invocations receive separate IDs. Selecting a node shows status, measured duration, count and safe error code. `null`/`—` means unmeasured. Langfuse may render an immediately created summary event as 0 seconds; its metadata still preserves an unmeasured duration.

Zoom, fit, pan and a keyboard-accessible step list are available. The list opens by default on small screens; mobile graphs initially show a readable region rather than shrinking all nodes to tiny text. The graph is capped at 299 steps plus the run root. It does not allow editing or executing arbitrary nodes.

## Local setup

Configure external public-API credential paths and Ollama as before. Generate independent local observability secrets, then start the stack:

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_observability
docker compose up -d --build
```

The helper fills missing/empty values only; it does not rotate existing secrets. Set `LANGFUSE_ENABLED=true` in `.env` to enable export. An explicit `false` is respected. Native Python execution supports the same optional adapter; stop the container backend first when sharing `data/`.

| Surface | URL | Authentication |
| --- | --- | --- |
| Travel service | http://127.0.0.1:8001 | Existing local service |
| Operator live graph | http://127.0.0.1:8001/ops | `.env` → `OPS_TOKEN` |
| Langfuse | http://127.0.0.1:3000 | Ignored `data/langfuse-local-login.json` |
| n8n | http://127.0.0.1:5678 | Existing n8n local account |

Langfuse headless initialization creates organization `marine-local`, project `marine-travel` and a local operator account. Initialization keys and passwords remain in ignored `.env`; the convenience login file is local only. Provider credential documents are never mounted into Langfuse. Existing operator/n8n credentials are preserved.

Compose includes the additional `compose.langfuse.yaml`: web, worker, PostgreSQL, ClickHouse, Redis and MinIO. Only the Langfuse web port is published, bound to loopback. Database, cache, worker and object-storage ports are internal. Named volumes preserve Langfuse state across restarts. Do not remove volumes unless intentionally discarding the project. This local stack uses HTTP; external hosting and authentication architecture are outside this release.

## Operator workflow

1. Connect to `/ops` with the operator token.
2. Leave **새 여행 요청 따라가기** enabled and start **AI로 여행 그리기** in the travel page. The operator graph follows new AI/rules executions.
3. Select a run to stop following and inspect it. Choosing an execution-history row also displays its graph.
4. Use **이 실행의 Langfuse 추적 열기** for new traced runs. Older pre-integration runs still have local graphs but link to the Langfuse project rather than a nonexistent trace.
5. In Langfuse, Tree/Timeline/Graph show model/tool hierarchy and timings. Generation observations include Ollama-provided token counts. Token costs are not configured; no price/free-service claim is made.

A graph updates immediately from local events. Langfuse export/ingestion is asynchronous, so a trace may appear a few seconds later; open spans may not be queryable until they end. The operator label “연결 설정됨” means configured, not a successful upload acknowledgement. Fixed adapter/retention error codes appear alongside it when observed.

## Data and failure contracts

Only allowlisted run kinds, stage/tool/provider names, IDs, states, timestamps, durations, counts, fixed error codes, configured model name and nonnegative input/output token counters are exported. **No prompts, model reasoning, generated answer, tool arguments, provider response, credential URL, precise itinerary coordinates or photos** are sent to Langfuse. Seeing undefined/empty Input and Output in its UI is intentional.

The SDK has a dedicated tracer provider and no automatic HTTP/framework/model instrumentation. The adapter is fail-soft; initialization/span failures cannot stop itinerary generation. Export is best-effort, without a historical backfill queue. SQLite remains the local source of truth even when Langfuse is unavailable. `LANGFUSE_ENABLED=false` disables export, not local graphs or execution records.

SSE allows 16 simultaneous operator clients and retains a 1,024-event in-process ring. It begins with up to 16 active executions plus 20 recent terminal summaries, reading at most 300 steps per run from a consistent database snapshot; overflow is explicitly marked. Active requests cannot be displaced by newer completed work. a ring gap sends a fresh snapshot. Reconnection uses a new snapshot, not an exactly-once replay promise. Event reduction is idempotent by step ID; terminal steps and executions cannot regress from late start events. The frontend aborts on logout, page hide or hidden tab and reconnects with capped backoff when visible. API keys are never embedded in URLs. Reloading requires operator authentication again.

### Seven-day trace cleanup

Langfuse's built-in self-hosted retention is an Enterprise feature. This OSS deployment **does not claim or enable that feature**. Instead, the app remembers only its own successfully started trace IDs in a separate SQLite expiry queue. Every five minutes while the app is running, it requests official batch deletion of up to 100 expired IDs. A failed request leaves IDs queued for retry; local history pruning does not remove this queue. Operator status reports `langfuse_retention_pending` on failure.

Deletion is asynchronous inside Langfuse; acceptance is not proof of immediate physical deletion. If the PC, app or Langfuse is off, cleanup resumes after startup. This integration does not export media or create datasets. Backups, server logs and datasets manually created by an operator have separate retention policies. Disabling export also pauses this app's Langfuse cleanup; re-enable it to process pending IDs.

## Validation

Offline checks cover repeated calls, graph bounds and idempotence, Korean SSE chunks/heartbeats/auth errors, bounded feed gaps/client limits, secret omission, parent trace IDs, token-counter allowlists, unavailable Langfuse and retryable expiry cleanup. These are not live-provider evidence.

The [live check](../reports/v08-observability-check.json) used a real Qwen request: 17 step updates reached an authenticated operator SSE connection; 11 Langfuse observations, including two generations, shared the execution ID. The Observations v2 query explicitly requested `core,basic,usage,metadata,io`; all input/output fields were empty and both generations had usage counters. This is a smoke check, not a model-quality or pricing benchmark. Trace deletion timing after seven actual days has not been measured; cleanup requests and retry logic are covered by offline tests.

Sources: [Cytoscape.js](https://js.cytoscape.org/), [Langfuse local deployment](https://langfuse.com/self-hosting/deployment/docker-compose), [headless initialization](https://langfuse.com/self-hosting/administration/headless-initialization), [SDK](https://langfuse.com/docs/observability/sdk/overview), [deletion](https://langfuse.com/docs/administration/data-deletion), [retention limits](https://langfuse.com/docs/administration/data-retention).

## 한국어 요약

- 여행 생성 팝업과 결과에 실제 실행 그래프를 표시합니다. `/ops`는 다른 여행 요청도 인증된 SSE로 실시간 수신합니다.
- 노드 색은 실제 상태이며, 실선은 소속 관계·점선은 시작 순서입니다. 내부 사고 과정이나 가짜 진행률은 표시하지 않습니다.
- 로컬 Langfuse는 별도 로그인 파일을 사용합니다. 운영 화면의 같은 실행에서 추적을 열 수 있으며, 모델·도구 시간과 토큰 수를 확인합니다.
- 입력·출력 원문이 비어 있는 것은 의도된 설정입니다. Langfuse 장애 시에도 일정 생성과 로컬 기록·그래프는 계속 동작합니다.
- SQLite 요약은 7일 보관합니다. 앱이 만든 Langfuse 추적은 별도 만료 큐를 통해 7일 후 삭제를 요청하며, 실제 삭제는 비동기입니다. 유료 자체 보관기간 기능을 사용하는 구성은 아닙니다.


## v0.8.1 reliability

- Server SSE uses an async generator with an idempotent connection lease. Both normal cancellation and the response cleanup path return the slot; a second release cannot consume another client's slot.
- Snapshots prioritize up to 16 active executions plus 20 completed executions, with a 300-step-per-run cap and explicit truncation flags. The frontend keeps at most 40 runs, prioritizing the selected run and active work. Manual history selections survive reconnects; follow mode picks active AI work first.
- Visibility changes, logout and new login invalidate the previous connection generation. Stale responses cannot publish events, clear a newer connection or schedule another retry. A hidden tab aborts its connection. Temporary failures use 1–15 second backoff; 401/403 stop reconnecting and require a new token, including non-JSON error responses.
- The operator page clears selected execution, detail data and graphs on authentication loss. Generation checks prevent an old request's authentication failure from logging out a newer session.
- Replay cannot turn terminal nodes back into running nodes. Completed provider/tool spans are ended once; boolean values are rejected as token counters while a valid zero remains zero.
- `/api/ops/status` includes safe live connection counts. This is local process state, not a distributed client count. The prototype remains single-worker.
