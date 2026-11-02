# v0.7 — Workflows and execution summaries / 워크플로우·실행 기록

> v0.8 adds [live Cytoscape graphs and local Langfuse](OBSERVABILITY.md). Run `python -m scripts.setup_observability` before Compose to configure its additional services and independent secrets.

## Local deployment

Keep `.env` and both public API credential documents outside Git. Set independent random `OPS_TOKEN` and `SYNC_TOKEN` values (at least 32 random bytes recommended). Keep the existing Windows credential file paths in `.env`; Compose mounts these files read-only and supplies Linux paths inside the application. No provider key/document is mounted into n8n. The Ollama URL remains the configured LAN endpoint.

```powershell
docker compose build app
docker compose up -d
.\.venv\Scripts\python.exe -m scripts.setup_n8n
```

Stop a native server using port 8001 before starting Compose. **Do not run native and container backends against the same data directory at the same time:** SQLite WAL and catalog locks are not cross-OS coordination mechanisms. Windows `run.ps1` remains supported after stopping the Compose app. Back up `data/` and the `n8n_data` Docker volume before changing deployment modes.

The app binds to `127.0.0.1:8001`; n8n binds to `127.0.0.1:5678`. Container-to-container calls use `http://app:8001`. This is a local prototype: HTTP and non-secure n8n cookies are deliberately confined to loopback. A remote deployment needs TLS and a separate access-control review. Docker restart policy does not start Docker Desktop itself; the PC and engine must be running.

The image installs Playwright Chromium and Nanum Gothic for PDF export. App code runs as a non-root user. Existing `data/` is a persistent bind mount; n8n uses a named volume. Do not run `docker compose down -v` unless intentionally removing n8n state.

## n8n setup and schedule

The bootstrap script targets only localhost. On a **new instance**, it provisions a local operator account and saves its randomly generated login only to ignored `data/n8n-local-login.json`. It creates the scoped Header Auth credential `Marine Sync API` and imports the workflow **unpublished**. Existing owner accounts are not reset; an unrelated existing instance requires manual credential setup/import through that owner's account.

Open [n8n](http://127.0.0.1:5678), sign in with the local login file, and open **바다결 · 자료 갱신 파이프라인**. Its `수동 확인` branch forces a sea-travel refresh. The scheduled branch checks due status before sending jobs; a fresh snapshot causes no provider calls. Tourist refresh can be triggered in `/ops`.

After a successful manual execution, publish the workflow in the editor. CLI alternative, using the workflow ID printed by setup:

```powershell
docker compose exec -T -e N8N_RUNNERS_BROKER_PORT=5681 n8n n8n execute --id=<workflow-id>
docker compose exec -T n8n n8n publish:workflow --id=<workflow-id>
docker compose restart n8n
```

CLI execution can print execution details; redirect it to an ignored local log rather than publishing raw output. n8n 2.45.7's optional Python runner warning does not affect this JavaScript/HTTP-only workflow. There is no Python Code node.

- Timezone: `Asia/Seoul` for workflow and instance.
- Every five minutes: check policy; no external provider calls if not due.
- Sea travel: daily after 00:15 KST, same-Korean-day collected metadata required.
- Tourism: Monday after 00:25 KST; missed periods are caught up when the PC returns.
- Scheduled failure retries: at least 30 minutes apart, maximum three attempts per job type per Korean day. Manual retries are separate and link to the original failed/interrupted run.
- One catalog job runs at a time. A duplicate returns the active job ID, including its actual kind. An initially empty installation may require two checks to populate both components.
- Five-minute polling is not a promise of exact execution time. n8n does not operate while the PC/engine is off.

[Official n8n Schedule Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/) · [CLI documentation](https://docs.n8n.io/hosting/cli-commands/) · [Execution retention](https://docs.n8n.io/hosting/scaling/execution-data/)

## Collection and freshness contracts

`python -m marine_agent.sync --component seatrip` and `--component tourism` use the same component collectors, execution summaries and file lock as HTTP jobs. Existing `--scope coastal` / `--all-marine` collection remains supported.

Tourism and individual marine feed timestamps are independent. Updating a forecast never resets the age of tourism or another marine feed. Tourism older than seven days is warned; older than eight days blocks new planning. Legacy snapshots without the separate tourism timestamp retain their previous 24-hour planning guard until the first component migration. Missing tourism records are never treated as a fresh tourism catalog.

Collections validate page totals, duplicate records, mandatory identifiers/fields, selected province metadata, current forecast date and coverage of the named forecast regions. Only a complete candidate replaces the catalog atomically. Empty or failed forecasts preserve previous data. Forecast freshness is not an independent verification of weather, operating hours, tourist suitability or ferry operations. Exact tourism gateway IDs can disappear from fresh upstream data; affected regions stay unavailable rather than choosing a different reference by guesswork.

## Operations UI and API

Open [/ops](http://127.0.0.1:8001/ops), enter the `OPS_TOKEN` from your local `.env`, and connect. The browser keeps it only in memory; refresh requires reconnecting. Public diagrams remain visible without authentication; all records and job controls require authentication. The page polls every three seconds only while visible. It shows freshness, last success/failure, policy's next due time, filters, step durations/counts and retry relationships.

| API | Authentication / behavior |
| --- | --- |
| `GET /internal/sync-status` | `Authorization: Bearer <SYNC_TOKEN>`; policy and last-run summaries |
| `POST /internal/jobs` | Sync token; `{kind, scheduled, parent_run_id?}`; 202 with job ID, deduplicated active job or skipped policy result |
| `GET /internal/jobs/{id}` | Sync token; collection jobs only |
| `GET /api/ops/status` | Operator token; collection policy and recording health |
| `GET /api/ops/runs` | Operator token; optional `kind`, `status`, `since` (Korean date), `limit` 1–500 |
| `GET /api/ops/runs/{id}` | Operator token; allowlisted run/step summary |
| `POST /api/ops/jobs` | Operator token; manual collection; failed/interrupted collection retries only |

Only `seatrip_sync` and `tourism_sync` are accepted as job kinds. Arbitrary commands, paths, URLs and extra fields are rejected. A missing token disables the corresponding protected API (503); an incorrect token returns 401. Responses use `Cache-Control: no-store`. API provider credentials never appear in these interfaces.

Existing plan/chat endpoints retain their response contracts and add an `execution` summary. NDJSON keeps existing event fields and adds `run_id`, `step_id`, `parent_step_id`, timestamp and measured duration when available. A duration of `null` means it was not measured, not zero. Heartbeats are not execution steps. Closing the progress popup or disconnecting does not cancel server work; reconnecting to that stream is not implemented in v1. Operators can still inspect its stored summary.

## Storage and failures

SQLite stores allowlisted names, statuses, IDs, timestamps, measured durations, counts, attempt numbers, parent relationships and fixed error codes. It stores **no prompts, model thoughts, model responses, provider payloads, credential URLs or precise trip coordinates**. Since v0.9, traveler results use a separate two-hour bounded SQLite plan registry and LangGraph recovery store. These richer local stores are not execution history or exported telemetry. See [LangGraph storage/recovery](LANGGRAPH.md).

Terminal summaries expire after seven days. Cleanup runs when creating executions, viewing ops status and completing jobs. Startup marks unfinished executions interrupted, without replaying them. AI requests can finish if summary storage fails; `/ops` exposes recording health. Collection jobs require a working summary store before acceptance. Jobs already started during a recording outage may still complete collection; operators must verify freshness and recording health.

A rejected tool, model fallback or unavailable photos/routes produces warning evidence without pretending full success. Error details are fixed codes, not raw exceptions. AI requests cannot be replayed from the history because their inputs are not retained.

n8n also prunes terminal executions after 168 hours, capped at 10,000. Its payloads contain only job IDs, status and sanitized summaries. No external notifications are configured.

## 한국어 운영 요약

1. `.env`의 독립된 `OPS_TOKEN`·`SYNC_TOKEN`을 설정하고 Docker를 시작합니다.
2. Compose 실행 후 `python -m scripts.setup_n8n`으로 새 로컬 계정·갱신 인증·워크플로우를 준비합니다. 로그인 정보는 Git 제외 `data/n8n-local-login.json`에만 있습니다.
3. n8n 수동 실행 성공을 확인한 뒤 예약을 게시합니다. 예보는 매일, 관광정보는 주 1회 갱신하며 PC가 꺼진 동안에는 실행되지 않습니다.
4. `/ops`에 운영자 토큰을 입력하면 최근 7일의 상태·단계·실패·재시도를 조회하고 자료 갱신을 수동 요청할 수 있습니다.
5. Windows 서버와 Docker 서버를 같은 자료 폴더로 동시에 실행하지 마세요. 배포 전환 시 기존 서버를 먼저 중지합니다.
