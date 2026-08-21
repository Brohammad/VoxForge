# VoxForge — Resume & Portfolio Copy-Paste Kit

Use any section below as-is or mix for LinkedIn, resume, portfolio site, GitHub, and interviews.

**Live demo:** https://voxforge.brohammad.tech  
**Repo:** https://github.com/Brohammad/VoxForge  
**Release:** v1.0.0-rc.1

---

## Headlines (pick one)

- **Voice AI Infrastructure Platform** — self-hosted, production-grade, open source
- **Built & shipped a full-stack voice agent platform** — from WebSocket to operator dashboard
- **Open-source alternative to managed voice SaaS** — deployable in 15 minutes, live in production

---

## One-liner (resume header / GitHub bio)

Open-source voice AI infrastructure platform with unified pipeline, RAG, evaluation, replay, and one-command HTTPS deployment — live at voxforge.brohammad.tech.

---

## LinkedIn / portfolio summary (short — ~80 words)

VoxForge is a production-grade, open-source voice AI platform I designed and shipped end-to-end. It unifies WebSocket, REST onboarding, and LiveKit WebRTC through a single voice pipeline, with LangGraph orchestration, pgvector knowledge retrieval, MCP tools, per-turn evaluation, and human handoff. The system is live in production with HTTPS, 354+ automated tests, Playwright UI coverage, and Docker-based deployment. Built for teams who want Vapi-class capabilities without vendor lock-in or per-minute platform fees.

---

## Portfolio project description (medium — ~150 words)

### VoxForge — Voice AI Infrastructure Platform

**Role:** Founder / Principal Engineer (solo)  
**Stack:** Python 3.12, FastAPI, LangGraph, PostgreSQL/pgvector, Redis, Docker, NGINX, OpenTelemetry  
**Live:** https://voxforge.brohammad.tech

VoxForge is an open-source platform for building and operating enterprise voice agents. Most “voice AI” projects stop at an LLM wrapper; VoxForge ships the full stack: transport layer, agent orchestration, knowledge base with RAG, MCP tool routing, per-turn evaluation, session replay, human escalation, SAML SSO, and an operator dashboard.

I architected it as a modular monolith with Clean Architecture boundaries — one codebase, one deploy, clear module separation. A single `VoicePipelineService` handles all entry points so WebSocket, programmatic onboarding, and LiveKit WebRTC share identical business logic.

Production deployment is automated (`./deploy.sh init` on Ubuntu 24.04 with Let's Encrypt). CI enforces linting, dependency audit, secret scanning, 70% coverage gate, and browser tests for critical user journeys.

**Impact:** Recruiters and pilot customers can try a live demo without cloning. Engineering evaluators can inspect ADRs, runbooks, and 354+ tests.

---

## Portfolio project description (long — for dedicated case study page)

### Problem

Teams building voice agents face a false choice: managed SaaS (fast, expensive, opaque) or DIY frameworks (flexible, incomplete, no ops story). Neither gives you evaluation, replay, handoff, and self-hosted deployment in one place.

### Solution

VoxForge — a batteries-included voice AI platform you deploy on your own infrastructure.

### What I built

| Area | Deliverable |
|------|-------------|
| Voice core | WebSocket gateway, `VoicePipelineService`, multi-provider STT/LLM/TTS |
| Agents | LangGraph pipeline: planner, safety, executor, critic |
| Knowledge | Document ingestion, chunking, pgvector search, citation grounding |
| Tools | MCP runtime discovery + builtin tools |
| Operations | Dashboard (sessions, latency, alerts, policy presets) |
| Trust | Per-turn evaluation, signed replay links, handoff queue |
| Auth | JWT, RBAC, API keys, SAML SSO |
| WebRTC | LiveKit token API + worker integration |
| Deploy | Docker Compose prod stack, NGINX, Certbot, health/readiness, backups |
| Quality | 354+ tests, Playwright browser suite, pip-audit, gitleaks |

### Technical decisions

- **Modular monolith** over microservices — faster pilots, simpler ops, module boundaries in code
- **pgvector** over dedicated vector DB — fewer moving parts for self-hosted deployments
- **Mock providers** for local/CI — zero API keys for demos and tests
- **Evaluation on every turn** — operator trust and regression detection

### Results

- Live production deployment with HTTPS and smoke-tested endpoints
- v1.0.0-rc.1 released on GitHub
- 81% test coverage, green CI
- Public demo completes voice pipeline in ~100ms (mock providers)

### Links

- Demo: https://voxforge.brohammad.tech/demo
- Docs: https://github.com/Brohammad/VoxForge/tree/main/docs
- Architecture: https://github.com/Brohammad/VoxForge/blob/main/docs/portfolio/architecture-diagrams.md

---

## Resume bullets

### Staff / Principal (impact-first)

- **Architected and launched VoxForge**, an open-source voice AI infrastructure platform deployed in production at voxforge.brohammad.tech, enabling self-hosted enterprise voice agents without SaaS lock-in.

- **Unified three transport layers** (WebSocket, REST onboarding, LiveKit WebRTC) into a single voice pipeline, reducing duplicated logic and enabling one test suite to cover all entry points.

- **Shipped operator-grade tooling** — per-turn evaluation, session replay, human handoff queue, and analytics dashboard — closing the gap between voice demos and production operability.

- **Automated production deployment** (Docker, NGINX, Let's Encrypt) with health/readiness probes, backup/restore, and env validation; fresh VPS to HTTPS in one command.

- **Established engineering quality bar** with 354+ automated tests, Playwright UI coverage, 81% code coverage, dependency audit, and secret scanning in CI.

### Senior (technical depth)

- Built **FastAPI + LangGraph** voice agent platform with swappable STT/LLM/TTS providers, pgvector RAG, and MCP tool discovery.

- Implemented **JWT/RBAC, API keys, and SAML SSO** with rate limiting, CSP/HSTS security headers, and production metrics auth.

- Designed **knowledge ingestion pipeline** — upload, chunk, embed, search — with citation grounding in agent responses.

- Added **failure-mode and integration test suites** for provider outages, WebSocket lifecycle, and handoff/replay flows.

- Published **ADRs, runbooks, incident response docs**, and competitive analysis vs Vapi, Retell, and LiveKit Agents.

### Condensed (3 bullets for tight resume)

- Built **VoxForge**, open-source voice AI platform (Python/FastAPI, LangGraph, pgvector) — live in prod with HTTPS, 354+ tests, operator dashboard.

- Designed **unified voice pipeline** for WebSocket, REST, and LiveKit; RAG, MCP tools, evaluation, replay, and human handoff included.

- Delivered **one-command deploy** (Docker/NGINX/Certbot), CI hardening, and full ops documentation for pilot customers.

---

## Skills to list on resume / LinkedIn

**Languages:** Python  
**Backend:** FastAPI, Uvicorn, SQLAlchemy, Alembic, asyncpg  
**AI / Voice:** LangGraph, LangChain, STT/LLM/TTS provider integration, RAG, pgvector  
**Data:** PostgreSQL, Redis, vector search  
**Infra:** Docker, Docker Compose, NGINX, Let's Encrypt, Ubuntu VPS  
**Observability:** OpenTelemetry, Prometheus, structured logging  
**Testing:** pytest, Playwright, coverage gates, failure-mode testing  
**Security:** JWT, RBAC, SAML SSO, CSP/HSTS, rate limiting, secret scanning  
**Practices:** Clean Architecture, ADRs, CI/CD, technical writing, open-source governance  

---

## GitHub repository description (160 chars)

Open-source voice AI infrastructure — unified pipeline, RAG, evaluation, replay, handoff. Live demo: voxforge.brohammad.tech

---

## GitHub About / topics

**Website:** https://voxforge.brohammad.tech  
**Topics:** voice-ai, fastapi, langgraph, livekit, docker, python, open-source, rag, mcp, postgres

---

## Portfolio website — hero copy

**Title:** VoxForge  
**Subtitle:** Voice AI infrastructure you can deploy, operate, and trust.  
**CTA:** [Live Demo](https://voxforge.brohammad.tech/demo) · [GitHub](https://github.com/Brohammad/VoxForge) · [API Docs](https://voxforge.brohammad.tech/api/v1/docs)

**Tags:** Open Source · Python · FastAPI · LangGraph · Docker · Production

---

## STAR stories (interview-ready)

### Story 1 — Unified voice pipeline

- **S:** Three transports (WebSocket, LiveKit, REST onboarding) threatened duplicated business logic.
- **T:** One orchestration path for all voice entry points.
- **A:** Built `VoicePipelineService` with transport adapters; centralized STT → agent → TTS → evaluation.
- **R:** Single test suite covers all transports; public demo runs production code path.

### Story 2 — Production in one command

- **S:** Stack spanned Postgres, Redis, app, NGINX, Certbot, optional workers — hard to reproduce.
- **T:** Any engineer should deploy HTTPS from a fresh VPS without manual edits.
- **A:** `deploy.sh init` with env validation, TLS bootstrap, health-gated compose ordering.
- **R:** Live at voxforge.brohammad.tech; documented verification checklist and runbooks.

### Story 3 — Quality as launch blocker

- **S:** RC-1 launch required confidence from recruiters and pilot customers, not just features.
- **T:** Prove reliability before tagging v1.0.0-rc.1.
- **A:** 354+ tests, Playwright browser suite, smoke scripts, gitleaks/pip-audit in CI, public deployment.
- **R:** Green CI, live demo, GitHub release — portfolio-ready artifact.

---

## Elevator pitch (30 seconds)

> "I built VoxForge — an open-source voice AI platform that's live in production. It's not a chatbot demo; it's the full stack: voice pipeline, knowledge retrieval, tool execution, evaluation, replay, and an operator dashboard. You can deploy it to your own VPS with HTTPS in one command, or try the demo in your browser right now. It's what I'd want if I were evaluating voice infrastructure for a startup — without paying per-minute SaaS fees."

---

## Numbers to cite (verified)

| Metric | Value |
|--------|-------|
| Automated tests | 354+ |
| Code coverage | 81% |
| Browser test journeys | 8 |
| Demo E2E latency (mock) | ~100ms |
| Time to local demo | ~15 min |
| Deploy path | `git clone` → `./deploy.sh init` |
| Production URL | voxforge.brohammad.tech |
| License | MIT |

---

## Cover letter paragraph

In my personal project VoxForge, I set out to prove I can ship production systems—not prototypes. I designed and deployed an open-source voice AI platform with a unified pipeline across WebSocket and WebRTC, knowledge retrieval with pgvector, per-turn evaluation, and operator tooling including replay and human handoff. The system is live at voxforge.brohammad.tech with automated HTTPS deployment, 354+ tests, and CI gates for coverage, dependency audit, and secret scanning. It demonstrates the same skills I bring to product engineering: clear architecture, operational maturity, and user trust through observability and documentation.

---

## “Tell me about a project you’re proud of”

VoxForge is the project I'm most proud of because it reflects how I think about real engineering—not feature lists, but operability. I noticed most voice AI repos are either SaaS you can't inspect or frameworks that stop at the LLM call. I built the middle ground: a self-hosted platform with auth, voice transport, RAG, tools, evaluation, replay, handoff, dashboard, and deployment automation. The hardest part was keeping one voice pipeline across WebSocket, REST, and LiveKit without copy-paste logic. I solved that with a transport-agnostic service layer and invested heavily in tests—unit through browser—so I could ship RC-1 with confidence. It's live, open source, and documented enough that a pilot customer or hiring manager can evaluate it in minutes.
