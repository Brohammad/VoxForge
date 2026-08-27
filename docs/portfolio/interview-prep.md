# Interview Preparation — VoxForge

## STAR stories

### 1. Unified voice pipeline

- **Situation:** Multiple transports (WebSocket, LiveKit, onboarding API) risked divergent business logic.
- **Task:** Single orchestration path for all entry points.
- **Action:** Built `VoicePipelineService` with transport adapters; all paths call same STT→agent→TTS→evaluation flow.
- **Result:** One test suite covers all transports; demo runs same code as production.

### 2. Production deployment in one command

- **Situation:** Complex stack (Postgres, Redis, app, NGINX, Certbot, workers) hard to reproduce.
- **Task:** Fresh Ubuntu VPS → HTTPS in one script.
- **Action:** `deploy.sh init` with bootstrap TLS, health-gated startup, env validation in container.
- **Result:** Live at voxforge.brohammad.tech; verification checklist for operators.

### 3. Cookie auth broke dashboard sections

- **Situation:** HttpOnly cookie login worked, but Knowledge/SSO/Policies never loaded.
- **Task:** Fix auth gating without regressing JWT or register flows.
- **Action:** Replaced `if (!token)` with `isAuthenticated()`; fixed logout race with refresh generation; added Playwright hub-nav tests.
- **Result:** Full dashboard usable on cookie sessions; merged in OSS pilot hardening PR.

### 4. Policy presets not affecting live calls

- **Situation:** Operators could apply presets in UI, but voice sessions ignored active config.
- **Task:** Wire org active agent config into pipeline at session start.
- **Action:** `apply_active_agent_config()` in pipeline factory; eval thresholds from org config.
- **Result:** Preset changes affect live STT→agent→TTS path; integration tests cover runtime swap.

## System design talking points

1. **Why modular monolith over microservices?** — Pilot velocity, simpler deploy, clear module boundaries in code.
2. **Why pgvector over dedicated vector DB?** — Fewer moving parts for self-hosted pilots; upgrade path documented.
3. **Why evaluation on every turn?** — Operator trust, regression detection, replay diffing.
4. **How does handoff work?** — Queue + signed replay URLs + ticketing hooks.
5. **How do you handle provider failures?** — Failure-mode tests, mock fallback, structured `ProviderError`.

## Trade-offs to articulate

| Decision | Trade-off |
|----------|-----------|
| Single uvicorn worker | Simpler ops vs horizontal scale |
| JWT in localStorage | Cookie-first dashboard; JWT behind Advanced for API/dev |
| Mock providers default | Easy demo vs not "real voice" out of box |
| Self-hosted first | Control vs managed SaaS convenience |

## Common questions

**Q: How is this different from Vapi?**  
A: Self-hosted, open source, evaluation/replay first-class, no per-minute platform fee.

**Q: How do you test voice without a mic in CI?**  
A: Mock providers + WebSocket integration tests + manual checklist for real STT.

**Q: How would you scale to 10k concurrent sessions?**  
A: Horizontal app replicas, Redis session state, read replicas, LiveKit for media, provider rate limits.

**Q: Biggest technical mistake?**  
A: Early transport-specific logic duplication — fixed by centralizing in VoicePipelineService.

## Blog post ideas

1. "Building a unified voice pipeline for WebSocket and WebRTC"
2. "Why we evaluate every voice turn"
3. "Deploying voice AI to a $24 VPS with Docker and Let's Encrypt"
4. "Mock providers for zero-friction open source demos"
