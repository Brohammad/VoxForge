# Competitive Benchmark — Voice AI Platforms

**Date:** 2026-07-10 · **VoxForge version:** RC-1

## Comparison matrix

| Capability | VoxForge | Vapi | Retell | LiveKit Agents | OpenWebUI | LangGraph | Pipecat | Voiceflow | ElevenLabs ConvAI |
|------------|----------|------|--------|----------------|-----------|-----------|---------|-----------|-------------------|
| **Self-hosted** | ✅ Full | ❌ SaaS | ❌ SaaS | ✅ | ✅ | ✅ Lib | ✅ Lib | ❌ SaaS | ❌ SaaS |
| **Voice pipeline** | ✅ Built-in | ✅ | ✅ | ⚙️ Build | ⚙️ Plugin | ⚙️ Build | ⚙️ Build | ✅ | ✅ |
| **WebSocket** | ✅ | ✅ | ✅ | ✅ | ⚙️ | ⚙️ | ✅ | ✅ | ✅ |
| **WebRTC/LiveKit** | ✅ | ✅ | ✅ | ✅ Native | ❌ | ❌ | ✅ | ⚙️ | ⚙️ |
| **Knowledge RAG** | ✅ | ⚙️ | ⚙️ | ❌ | ✅ | ⚙️ | ❌ | ✅ | ⚙️ |
| **Human handoff** | ✅ | ⚙️ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **Session replay** | ✅ | ⚙️ | ⚙️ | ❌ | ❌ | ❌ | ❌ | ⚙️ | ❌ |
| **Per-turn evaluation** | ✅ | ⚙️ | ⚙️ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **MCP tools** | ✅ | ❌ | ❌ | ❌ | ✅ | ⚙️ | ❌ | ❌ | ❌ |
| **Operator dashboard** | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ | ⚙️ |
| **SAML SSO** | ✅ | ✅ Ent | ✅ Ent | ❌ | ⚙️ | ❌ | ❌ | ✅ | ❌ |
| **Docker deploy** | ✅ | ❌ | ❌ | ⚙️ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Open source** | ✅ MIT | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |

Legend: ✅ native · ⚙️ partial/BYO · ❌ not available

## Latency (indicative)

| Platform | Typical E2E | Notes |
|----------|---------------|-------|
| VoxForge (mock) | ~36ms | CI/demo path, no network |
| VoxForge (real) | 800ms–2s | Depends on providers |
| Vapi / Retell | 500ms–1.5s | Managed, optimized |
| LiveKit Agents | Variable | BYO stack |
| ElevenLabs | Low TTS | STT/LLM separate |

## Architecture comparison

| Platform | Model |
|----------|-------|
| **VoxForge** | Modular monolith, Clean Architecture |
| **Vapi / Retell** | Managed multi-tenant SaaS |
| **LiveKit Agents** | Framework + media server |
| **LangGraph** | Agent orchestration library |
| **Pipecat** | Real-time pipeline framework |
| **OpenWebUI** | LLM chat UI + plugins |

## Strengths (VoxForge)

1. **Full stack in one repo** — auth, voice, knowledge, handoff, dashboard, deploy
2. **Self-hosted with TLS automation** — data sovereignty
3. **Evaluation + replay first-class** — operator trust
4. **MCP tool router** — extensibility without code forks
5. **423 tests collected** — engineering credibility with explicit pass/skip accounting

## Weaknesses (VoxForge)

1. No managed SaaS — operator must run infrastructure
2. Single-node compose default — not multi-region
3. Zendesk ticketing is implemented but awaits live sandbox proof; Freshdesk is not implemented
4. Voice UX polish behind Vapi/Retell managed UIs
5. No visual flow builder (Voiceflow-style)

## Differentiators

- **Replay + evaluation** as core product, not add-on
- **One pipeline** for WS, onboarding API, and LiveKit
- **Production deploy script** with Certbot, not just docker-compose dev
- **Open source** with enterprise features (SAML, RBAC, API keys)

## Missing capabilities (roadmap)

- Visual agent builder
- Multi-tenant hosted offering
- Native telephony (SIP/PSTN) — use LiveKit SIP
- Live Zendesk sandbox proof; Freshdesk adapter is not implemented
- httpOnly dashboard sessions — **shipped** (JWT paste remains under Advanced)

## Pricing positioning

| Platform | Model |
|----------|-------|
| VoxForge | Free OSS + infra + API costs |
| Vapi / Retell | Per-minute SaaS |
| ElevenLabs | Per-character + platform |
| LiveKit | Infrastructure + build cost |

**Pilot pitch:** "Vapi-class capabilities, self-hosted control, no per-minute platform tax."
