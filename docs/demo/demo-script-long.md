# Demo Script — 8-Minute Technical Walkthrough

**Audience:** Engineering managers, pilot customers, senior ICs  
**URL:** https://voxforge.brohammad.tech

## 0:00 — Hook (30s)

> "VoxForge is open-source voice AI infrastructure — not a chatbot wrapper. One pipeline powers WebSocket, programmatic onboarding, and LiveKit WebRTC, with evaluation and replay built in."

Show landing page hero.

## 0:30 — Live demo (90s)

1. Navigate to `/demo`
2. Click **Run demo call**
3. Point out: status `test_call_passed`, E2E latency (~36ms mock), session ID
4. Read transcript — billing support scenario

> "This is the same `VoicePipelineService` path used in production."

## 2:00 — Dashboard (2 min)

1. Open `/dashboard`, register or login
2. **Overview** — outcome trends, session counts
3. **Sessions** — find demo session
4. **Replay** — messages, tool calls, evaluations
5. **Latency** — STT/LLM/TTS breakdown

## 4:00 — Knowledge base (90s)

1. **Knowledge Base** section
2. Upload a PDF or TXT
3. Run search test
4. Explain RAG grounding in voice pipeline

## 5:30 — Handoff (60s)

1. **Handoffs** queue
2. Explain escalation + signed replay links
3. Explain the unit-tested Zendesk ticket flow with replay context; do not present it as
   live proof until sandbox verification is complete

## 6:30 — Architecture (90s)

Show landing architecture section or `docs/architecture/voice-pipeline.md`:

- Transport → Pipeline → Orchestrator → MCP
- Evaluation on every turn
- Docker Compose deployment

## 7:30 — Developer path (30s)

```bash
git clone → uv sync → docker compose up → demo in 15 min
```

Point to GitHub, the [verified CI run and canonical metrics](../project-metrics.md):
423 tests collected, with 404 non-browser tests passed and 10 skipped.

## 8:00 — Close

> "RC-1 is live. We're looking for design partners. Try the demo, star the repo, open an issue."

**CTA:** `/demo`, GitHub, pilot contact issue
