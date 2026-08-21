# Failure Recovery

Operational failure modes for VoxForge: what breaks, what recovers automatically, and what requires intervention.

This document reflects **current behavior** in the codebase. Session consistency improvements from P1 are documented in [session-consistency.md](./session-consistency.md).

**Related:** [operations.md](../deployment/operations.md), [livekit-integration.md](./livekit-integration.md), [hardening-sprint.md](../hardening-sprint.md)

---

## Quick reference

| Component | Detection | Survives brief outage? | Auto-recovers? |
|-----------|-----------|------------------------|----------------|
| Redis | `/api/v1/ready` → `redis: error` | No (ephemeral session state) | **Partial (P1)** — reconcile on resume; create compensates; end is DB-first |
| PostgreSQL | `/api/v1/ready` → `database: error` | No (durable data) | Partial — `pool_pre_ping` on reconnect; no request retry |
| LiveKit worker | Worker logs, `livekit_room_lifecycle_total` | 30s grace window | Client redispatch + DB history reload |
| API process | `/api/v1/health` | N/A | Process restart; clients reconnect |
| External providers | Pipeline errors, tool status | Per-call | Next turn / next request |

---

## Health endpoints

| Endpoint | Purpose | Redis down | Postgres down |
|----------|---------|------------|---------------|
| `GET /api/v1/health` | Liveness | `200 ok` | `200 ok` |
| `GET /api/v1/ready` | Readiness | `200` with `status: degraded` | `200` with `status: degraded` |

**Note:** `/ready` returns HTTP 200 when optional deps are degraded (so LBs that only check status codes keep routing). Critical failures (Postgres/Redis) always return **503**. Set `READY_FAIL_ON_DEGRADED=true` to treat soft failures as 503 as well. Prefer inspecting the JSON `status` field for alerting; see [uptime.md](../deployment/uptime.md).

---

## Scenario matrix

### Redis unavailable

| | |
|---|---|
| **Detection** | `GET /api/v1/ready` → `redis: error: …`; Redis connection errors in logs (`SessionNotFoundError`, `ConnectionError`) |
| **User impact** | **New sessions:** Redis failure during create marks session **FAILED** in Postgres (compensated). **Resume/activate:** reconciles Redis from Postgres when keys missing. **End:** completes in Postgres; Redis delete is best-effort. **Rate limiting:** fail-closed categories return 503; others fail open (see [rate-limiting.md](./rate-limiting.md)). |
| **Recovery** | When Redis returns, new sessions work. Resume/activate rebuild ephemeral state from DB. Stale Redis keys expire via TTL. |
| **Retry behavior** | No Redis client retry/backoff. Each operation fails immediately unless reconciliation succeeds. |
| **Observability** | `/ready` degraded; `session_ephemeral_reconciled`, `session_redis_*` logs; `voxforge_session_consistency_total` |
| **Manual intervention** | Restart Redis; verify `/ready`. Clients retry after `status=failed` create. See [session-consistency.md](./session-consistency.md). |

**What breaks → what recovers (summary):**

```
Redis dies
  → ephemeral state (phase, interrupt, sequence, heartbeats) unavailable
  → rate limits disabled (fail-open)
  → /ready degraded; /health still ok
Redis returns
  → new sessions work immediately
  → resume/activate reconciles ephemeral state from Postgres (P1)
  → end_session always completes in Postgres; Redis cleanup best-effort
```

---

### PostgreSQL unavailable

| | |
|---|---|
| **Detection** | `GET /api/v1/ready` → `database: error: …`; SQLAlchemy errors in API logs |
| **User impact** | **All durable operations fail:** auth, orgs, sessions CRUD, messages, knowledge, handoffs, replay (JWT path), evaluations, dashboard. **Voice pipeline:** turn persistence (`commit` per turn) fails — user may hear a response but artifacts are not saved. **WebSocket disconnect cleanup:** `end_session` in `finally` block errors are **swallowed** (`except Exception: pass`). |
| **Recovery** | When Postgres returns, `pool_pre_ping=True` helps drop stale connections. **No automatic retry** on failed requests. Clients must retry HTTP calls. |
| **Retry behavior** | None at application layer. SQLAlchemy pool may reconnect on next checkout. |
| **Observability** | `/ready` degraded; unhandled 500s on REST; `livekit_session_end_failed` if shutdown during outage |
| **Manual intervention** | Restore Postgres; run `alembic upgrade head` if needed; verify `/ready`; inspect sessions stuck `active` after outage. |

**Graceful degradation:** None for data-backed features. Mock STT/LLM/TTS can still run locally, but session/message persistence requires Postgres.

**Crash?** API process does **not** exit on Postgres failure mid-request. Individual requests return 500; process stays alive.

---

### LiveKit unavailable / worker restart

| | |
|---|---|
| **Detection** | Token API 503 if `LIVEKIT_*` unset; worker logs `livekit_worker_error`, `livekit_invalid_room`; metrics `voxforge_livekit_room_lifecycle_total` |
| **User impact** | **LiveKit Cloud down:** clients cannot connect; WebSocket transport unaffected. **Worker crash:** single room job fails. **Participant disconnect:** 30s grace (`livekit_reconnect_grace_seconds`), then worker ends session in DB and clears Redis. |
| **Recovery** | **In-job reconnect:** `participant_connected` → `handle_reconnect` → `resume_session` (Redis sequence bump, heartbeat refresh). **Worker restart:** LiveKit redispatches agent; worker loads session + **message history from Postgres**; in-process orchestrator memory is rebuilt via `load_history`. **Client reconnect:** new token + same `session_id` room naming pattern. |
| **Retry behavior** | Agent dispatch failures do **not** block token issuance (logged only). Audio queue full → frame dropped with warning. |
| **Observability** | `livekit_reconnection_attempts_total`, `livekit_participant_events_total`, `livekit_streaming_latency_seconds` |
| **Manual intervention** | Restart `livekit-worker`; verify `LIVEKIT_*` env; check session not ended if user still in grace window. |

**Sessions resume or terminate?**

| Event | Outcome |
|-------|---------|
| Participant disconnect | Grace timer starts (30s default) |
| Reconnect within grace | Session **resumes** (`resume_session`); pipeline continues |
| Grace expires | Worker **terminates** session (`end_session`, reason `worker_exit`) |
| Worker restart (new job) | Session **resumes** from DB if not ended; history reloaded |

**State preserved:** Messages, metrics, evaluations, handoffs in **Postgres**. Ephemeral phase/interrupt in **Redis** (subject to TTL). In-process LLM conversation buffer is **rebuilt from DB** on prepare.

---

### OpenAI timeout / LLM provider failure

| | |
|---|---|
| **Detection** | `pipeline_listening_error`, `ProviderError` in logs; evaluation/hallucination judge failures |
| **User impact** | Turn fails or returns error callback; user may hear silence or error message depending on transport callbacks. Multi-agent graph may produce fallback text or empty response. |
| **Recovery** | **Next turn** attempts a fresh LLM call. No circuit breaker. |
| **Retry behavior** | No automatic retry on LLM calls. |
| **Observability** | Pipeline error logs; evaluation `overall_status=failed` when judge runs |
| **Manual intervention** | Check API key, quotas, provider status; switch to `LLM_PROVIDER=mock` only in non-prod. |

---

### Embedding provider unavailable

| | |
|---|---|
| **Detection** | `knowledge_ingest_failed` logs; memory/KB search errors |
| **User impact** | **Knowledge ingest:** job marked `failed` (P0: worker commits failure state). **Memory retrieval:** turn proceeds without semantic context. **KB search:** API error or empty results depending on path. |
| **Recovery** | Reindex/re-upload after provider restored. Failed jobs remain `failed` until manual reindex. |
| **Retry behavior** | Worker does not retry failed jobs automatically (job stays `failed`). |
| **Observability** | `knowledge_ingest_jobs_total{status="failed"}`, `knowledge_ingest_failed` |
| **Manual intervention** | `POST /knowledge/documents/{id}/reindex` after provider recovery. |

---

### Knowledge worker crash

| | |
|---|---|
| **Detection** | Process exit; no `knowledge_worker_started` log; ingest jobs stuck `queued`/`running` |
| **User impact** | With `KNOWLEDGE_WORKER_ENABLED=true`, uploads stay `queued` until worker runs. With worker disabled, API processes ingest inline in request (blocking). |
| **Recovery** | Restart worker (`make knowledge-worker`). Worker polls `claim_next` with `FOR UPDATE SKIP LOCKED`. Stale `running` jobs may need manual DB fix if worker died mid-job (no lease timeout yet). |
| **Retry behavior** | Failed jobs (P0): committed as `failed`, not retried. Queued jobs picked up on restart. |
| **Observability** | `knowledge_worker_job_failed`, `knowledge_ingest_jobs_total` |
| **Manual intervention** | Restart worker container; reindex failed documents; reset stuck `running` rows if needed. |

---

### Ticket provider failure (handoff)

| | |
|---|---|
| **Detection** | Exception during `HandoffOrchestrator.initiate_handoff`; handoff span errors |
| **User impact** | Handoff transaction may **roll back entirely** (ticket creation is inside the same DB transaction scope as orchestration). User does not get escalation package. Auto-policy may retry on next turn if trigger still applies. |
| **Recovery** | Idempotent handoff: `get_by_session` returns existing record on retry; concurrent races handled via `uq_handoff_records_session` + `IntegrityError` recovery (see [integrity-concurrency.md](./integrity-concurrency.md)). |
| **Retry behavior** | Agent explicit `handoff_to_human` tool can be invoked again. Auto-policy re-evaluates each turn. |
| **Observability** | `handoff_initiated_total`, `handoff.orchestrate` trace |
| **Manual intervention** | Fix ticketing credentials; use `TICKETING_PROVIDER=mock` in dev. |

---

### MCP server offline

| | |
|---|---|
| **Detection** | `mcp_discovery_timeout`, `mcp_discovery_error`; `GET /api/v1/tools/mcp/health` shows `offline`/`degraded` |
| **User impact** | MCP tools unavailable at invoke time (`MCP server offline` error). Builtin and support tools unaffected. Startup **not blocked** — discovery is per-server timeout isolated. |
| **Recovery** | Restart MCP server; call discovery refresh or restart API/worker to rediscover. Static tool metadata used as degraded fallback per ADR-003. |
| **Retry behavior** | No invoke retry. Next tool call attempts again. |
| **Observability** | `mcp_registry_health`, `mcp_discovery_*` logs, `tool_calls_total{status="error"}` |
| **Manual intervention** | Fix MCP stdio process/config; verify `MCP_SERVERS_CONFIG`. |

---

### Tool timeout

| | |
|---|---|
| **Detection** | `tool_calls_total{status="timeout"}`; tool result `status=timeout` |
| **User impact** | Agent receives timeout error in tool message; may retry tool or escalate via handoff policy if `escalate_on_tool_failure=true`. |
| **Recovery** | Next tool invocation in same or subsequent turn. |
| **Retry behavior** | Single attempt per invocation (`tool_timeout_seconds`, default 30s). No exponential backoff. |
| **Observability** | `tool_latency_seconds`, `tool_calls_total` |
| **Manual intervention** | Increase timeout; fix slow MCP/backend; disable problematic tool. |

---

### Voice disconnect (WebSocket)

| | |
|---|---|
| **Detection** | `ws_disconnected` log; `ws_connections` gauge drops |
| **User impact** | Connection closed; listening task cancelled. Session ended with reason `disconnect` if cleanup succeeds. |
| **Recovery** | Client sends `start` with `session_id` + `last_sequence` to **resume** if Redis state exists and DB session not `completed`. History reloaded from Postgres. |
| **Retry behavior** | Client-driven reconnect only. |
| **Observability** | `ws_disconnected`, `active_sessions`, `voxforge_ws_connections` |
| **Manual intervention** | None if within TTL; otherwise start new session. |

**Cleanup caveat:** disconnect `end_session` errors are swallowed — session may remain `active` in Postgres if DB/Redis fails during cleanup.

---

### API restart

| | |
|---|---|
| **Detection** | Process exit; load balancer health flip; `/health` fails during downtime |
| **User impact** | All in-flight HTTP and WebSocket connections dropped. |
| **Recovery** | See below. |
| **Retry behavior** | Client retry on HTTP. WebSocket client reconnect. |
| **Observability** | Container restart count; missing heartbeat on `/ready` |
| **Manual intervention** | `docker compose restart app`; verify migrations applied. |

**Replay links still valid?** **Yes**, if:

- `replay_token` query param provided
- HMAC verifies (`ReplayLinkService.verify`)
- Token matches stored `handoff_records.replay_token`
- Age &lt; `handoff_replay_token_ttl_seconds` (default 7 days)
- Session data still in Postgres

JWT-based replay (`sessions:read`) works after restart — stateless auth.

**Session recovery works?**

| Transport | Recovery |
|-----------|----------|
| WebSocket | Resume with `session_id` if Redis TTL not expired and session not ended in DB |
| LiveKit | New worker job loads DB history; client may need new token |
| Programmatic | N/A (short-lived onboarding runs) |

**Lost on restart:** in-process orchestrator `_history` / `_traces` (rebuilt from DB messages on next `start`/`prepare`). MCP registry rediscovered at startup.

---

### Container restart (full stack)

| | |
|---|---|
| **Detection** | All `/ready` checks fail during rollout |
| **User impact** | Complete service interruption for duration of restart |
| **Recovery** | Postgres data persists on volume. Redis data **lost** unless Redis persistence (AOF/RDB) configured — default Compose Redis is ephemeral. |
| **Retry behavior** | N/A |
| **Observability** | Deployment logs; `/ready` recovery timeline |
| **Manual intervention** | Follow [operations.md](../deployment/operations.md) restore procedure if Postgres volume corrupt. |

**After full restart:**

- **Replay links:** valid (Postgres + signed token)
- **Active sessions:** **not** resumable if Redis flushed — client must start new session
- **Queued knowledge jobs:** survive in Postgres; worker resumes polling
- **Handoffs:** survive in Postgres; pending handoffs still visible in API

---

## The four verification questions

### 1. Can I kill Redis?

**What breaks:**

- Ephemeral session state (phase, sequence, interrupt, heartbeats)
- WebSocket resume (unless keys still cached elsewhere)
- Rate limiting on auth/demo paths (fails **open**)
- `/ready` reports degraded

**What does NOT break immediately:**

- API liveness (`/health`)
- Postgres-backed replay (JWT or signed token)
- Read-only REST that does not touch session state (rare)

**What recovers automatically:**

- New sessions after Redis returns
- Rate limiting when Redis returns
- `/ready` returns ok when `PING` succeeds

**What does NOT recover automatically:**

- Orphan Postgres sessions created during outage
- Expired/missing Redis keys — client must start fresh
- In-flight turn state

---

### 2. Can I kill Postgres?

**What happens:**

- `/ready` degraded; durable APIs return 500
- Voice turns may partially execute but **fail to persist**
- Auth, knowledge, handoffs, replay (DB path) unavailable

**Retry?** No application-level retry. Pool reconnects on next connection.

**Graceful degradation?** No — platform is Postgres-dependent for multi-tenant operation.

**Crash?** API process stays up; per-request failures.

---

### 3. Can I restart LiveKit?

**Sessions resume?** Yes, within **30s grace** after participant disconnect, or on worker redispatch with same `session_id` (history from Postgres).

**Sessions terminate?** Yes, if grace expires without reconnect — `end_session(reason=worker_exit)`.

**State preserved?** Messages and metrics in Postgres; ephemeral state in Redis (TTL-bound); agent memory buffer reloaded from DB.

---

### 4. Can I restart the API?

**Replay links still valid?** Yes — HMAC + Postgres, 7-day TTL (independent of API uptime).

**Session recovery works?** WebSocket resume works if Redis state exists and DB session not completed. Otherwise client starts new session. Message history survives in Postgres.

---

## Known gaps (P1 targets)

| Gap | Scenario | Status |
|-----|----------|--------|
| Non-atomic Postgres+Redis session create/end | Redis or API restart | **P1 done** — see [session-consistency.md](./session-consistency.md) |
| Handoff/outcome/KB concurrent duplicate writes | Parallel escalations / turns | **P1 done** — see [integrity-concurrency.md](./integrity-concurrency.md) |
| `/ready` returns HTTP 200 when degraded | All | Stricter readiness semantics (ops doc update) |
| Rate limit fail-open | Redis unavailable | **P1 done** — per-category fail-closed; see [rate-limiting.md](./rate-limiting.md) |
| No request retry on transient DB errors | Postgres blip | Consider bounded retry (P1 discussion) |
| Stuck `running` ingest jobs | Worker crash | Lease timeout / dead-letter (P2) |
| `is_stale` never enforced in voice paths | Silent session | Wire or remove (P2) |
| Disconnect cleanup swallows errors | DB outage | Log + reconcile (P1) |

---

## Recommended failure drills

Run before enterprise pilot:

1. **Redis kill** — `docker stop redis`; verify `/ready`; start voice session; restore Redis; verify new session works.
2. **Postgres kill** — verify `/ready` degraded; confirm no silent data loss on running voice turn.
3. **API restart** — mid-session WebSocket; verify resume with `session_id` within TTL.
4. **LiveKit worker restart** — verify redispatch and message history continuity.
5. **Replay token** — access `/api/v1/sessions/{id}/replay?replay_token=…` after API restart without JWT.

Document results in your ops runbook alongside [production-checklist.md](../deployment/production-checklist.md).
