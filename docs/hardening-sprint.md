# VoxForge Hardening Sprint

> **Note:** Historical document from pre-RC-1 hardening. Current status: [release/RC-1-REPORT.md](release/RC-1-REPORT.md) and [release/known-limitations.md](release/known-limitations.md).

Production blockers from the staff engineering review. No architectural redesign — fixes only.

**Goal:** Move from *Needs additional engineering before release* → *Ready for enterprise pilot*.

---

## P0 — Must fix before enterprise pilot

| Group | Item | Status |
|-------|------|--------|
| 1 | Knowledge worker: fix `configure_logging` import; commit failed jobs instead of rollback | Done |
| 2 | File upload: sanitize filenames; enforce max upload size | Done |
| 3 | Pipeline factory: wire handoff orchestrator/policy (WebSocket + LiveKit parity) | Done |
| 4 | Replay links: wire `ReplayLinkService.verify()` into replay API; enforce TTL | Done |
| 5 | Tool permissions: enforce `required_scopes` at invocation | Done |
| 6 | Auth: block `AUTH_REQUIRED=false` in production; validate API key scopes at creation | Done |

---

## P1 — Required for confident enterprise pilot

| Item | Why |
|------|-----|
| Postgres/Redis session create/end compensating behavior | Prevents orphan sessions under partial failures | **Done** — [session-consistency.md](../architecture/session-consistency.md) |
| Integrity & concurrency hardening (handoff, outcomes, KB, tickets) | Idempotent concurrent escalations and writes | **Done** — [integrity-concurrency.md](../architecture/integrity-concurrency.md) |
| Rate limiting: fail-closed on Redis errors; extend to expensive endpoints | DoS/cost abuse protection | **Done** — [rate-limiting.md](../architecture/rate-limiting.md) |
| Metrics protection & observability hardening | Production diagnosability without SSH | **Done** — [observability.md](../architecture/observability.md), [metrics.md](../architecture/metrics.md) |
| Protect `/api/v1/metrics` in application layer | Defense in depth beyond NGINX | **Done** (part of observability hardening) |
| Validate `CreateSessionRequest.config` schema | Prevents arbitrary JSON injection into session state | **Done** |
| Validate `HANDOFF_REPLAY_SIGNING_SECRET` in production | Separate replay integrity from JWT secret | **Done** (required, strong, distinct from JWT) |
| Reject stub Zendesk/Freshdesk providers in production | Avoid late opaque failures mid-pilot | **Done** |
| **Failure recovery runbook** | Document actual behavior under Redis/Postgres/LiveKit/API failures — see [failure-recovery.md](../architecture/failure-recovery.md) |

---

## P2 — Post-pilot hardening

| Item | Why |
|------|-----|
| Coverage gate in CI (`fail_under`) | Regression protection |
| Minimal concurrency test (N parallel sessions) | Validates async correctness |
| **Failure recovery runbook** | `docs/architecture/failure-recovery.md` — operational scenarios (done) |
| Un-skip or delete stale KB integration tests | Test hygiene |
| Wire `FastAPIInstrumentor` for OTel | Trace completeness — deferred; manual spans on critical paths instead |
| Implement or remove dead `provider_errors` metric | Observability accuracy — **Done** (wired in voice pipeline) |

---

## Implementation order

1. P0 Group 1 → review
2. P0 Group 2 → review
3. P0 Group 3 → review
4. P0 Group 4 → review
5. P0 Group 5 → review
6. P0 Group 6 → review
7. P1 items (sequential)
8. P2 items (backlog)
