# VoxForge Project Metrics

> Single source of truth for repository engineering metrics.  
> Last updated: 2026-07-10  
> Regenerate: `python scripts/generate_project_metrics.py`

## Summary

| Metric | Value |
|--------|------:|
| Application modules | 19 |
| REST endpoints | 72 |
| WebSocket endpoints | 1 |
| Tests collected | 352 |
| Line coverage (`src/voxforge`) | 76.9% |
| ADRs | 7 |
| Architecture documents | 25 |
| Benchmark documents | 2 |

## Application modules (19)

- `agent_config`
- `agent_orchestrator`
- `alerts`
- `auth`
- `conversation`
- `dashboard`
- `evaluation`
- `handoff`
- `knowledge`
- `livekit_gateway`
- `mcp_tool_router`
- `memory`
- `onboarding`
- `outcomes`
- `replay`
- `session_manager`
- `stt`
- `tts`
- `voice_gateway`

## API surface

| Transport | Count | Entry points |
|-----------|------:|--------------|
| REST | 72 | `/api/v1/*` routers |
| WebSocket | 1 | `/api/v1/ws/voice` |

## Tests

Run: `PYTHONPATH=. pytest -v`

| Category | Location |
|----------|----------|
| Unit | `tests/unit/` |
| Integration | `tests/integration/` |

## Architecture decision records (7)

- [ADR-001-programmatic-voice-pipeline-runner.md](adr/ADR-001-programmatic-voice-pipeline-runner.md)
- [ADR-002-onboarding-session-lifecycle.md](adr/ADR-002-onboarding-session-lifecycle.md)
- [ADR-003-mcp-runtime-discovery.md](adr/ADR-003-mcp-runtime-discovery.md)
- [ADR-004-livekit-transport-adapter.md](adr/ADR-004-livekit-transport-adapter.md)
- [ADR-005-enterprise-knowledge-base.md](adr/ADR-005-enterprise-knowledge-base.md)
- [ADR-008-retrieval-pipeline.md](adr/ADR-008-retrieval-pipeline.md)
- [ADR-006-human-handoff.md](adr/ADR-006-human-handoff.md)

## Architecture documents (25)

- [agent-config-versioning.md](architecture/agent-config-versioning.md)
- [agent-orchestrator.md](architecture/agent-orchestrator.md)
- [alerts.md](architecture/alerts.md)
- [authentication.md](architecture/authentication.md)
- [ci-hardening.md](architecture/ci-hardening.md)
- [customer-support-tools.md](architecture/customer-support-tools.md)
- [dashboard.md](architecture/dashboard.md)
- [evaluation-engine.md](architecture/evaluation-engine.md)
- [failure-recovery.md](architecture/failure-recovery.md)
- [human-handoff.md](architecture/human-handoff.md)
- [integrity-concurrency.md](architecture/integrity-concurrency.md)
- [knowledge-base.md](architecture/knowledge-base.md)
- [livekit-integration.md](architecture/livekit-integration.md)
- [livekit-webrtc.md](architecture/livekit-webrtc.md)
- [mcp-runtime-discovery.md](architecture/mcp-runtime-discovery.md)
- [mcp-tool-router.md](architecture/mcp-tool-router.md)
- [memory.md](architecture/memory.md)
- [metrics.md](architecture/metrics.md)
- [observability.md](architecture/observability.md)
- [onboarding-voice-pipeline.md](architecture/onboarding-voice-pipeline.md)
- [outcomes.md](architecture/outcomes.md)
- [rate-limiting.md](architecture/rate-limiting.md)
- [replay.md](architecture/replay.md)
- [session-consistency.md](architecture/session-consistency.md)
- [voice-pipeline.md](architecture/voice-pipeline.md)

## Benchmarks (2)

- [knowledge-base.md](benchmarks/knowledge-base.md)
- [onboarding.md](benchmarks/onboarding.md)

## Supported providers

| Capability | Providers |
|------------|-----------|
| STT | `deepgram`, `mock` |
| LLM | `openai`, `mock` |
| TTS | `cartesia`, `mock` |
| Embeddings | `openai` (`text-embedding-3-small`) |
| WebRTC transport | LiveKit |
| Voice transport | WebSocket, LiveKit WebRTC |

## Supported MCP servers

MCP servers are **runtime-discovered** from `MCP_SERVERS_CONFIG` (stdio transport). Static
tool metadata is used as a degraded fallback when discovery fails. Inspect live status via:

- `GET /api/v1/tools/mcp/health`
- `GET /api/v1/tools/mcp/servers`

No servers are hardcoded in the repository; operators declare servers in environment config.

## Phase status

| Phase | Status |
|-------|--------|
| Phase 0 — Stabilization | Complete |
| Phase 1 — Onboarding voice pipeline | Complete |
| Phase 2 — CI hardening | Complete |
| Phase 3 — MCP runtime discovery | Complete |
| Phase 4 — LiveKit transport adapter | Complete |
| Phase 5 — Public deployment | Complete |
| Production hardening & load testing | Planned |
