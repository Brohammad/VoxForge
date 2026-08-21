# Design Partner Pilot Onboarding Guide

Welcome to the VoxForge design partner program. This guide takes you from kickoff to first production voice session in one week.

## Week 0 — Kickoff

| Day | Activity | Owner |
|-----|----------|-------|
| 0 | Sign pilot agreement (informal OK) | Both |
| 0 | Share success metrics (see [success-metrics.md](success-metrics.md)) | Partner |
| 1 | Provision staging or use `voxforge.brohammad.tech` | VoxForge |
| 1 | Create org + admin account | VoxForge |

## Week 1 — Deploy & configure

### Option A: Shared demo environment

1. Visit https://voxforge.brohammad.tech/dashboard
2. Register your team accounts
3. Upload 3–5 knowledge documents
4. Run demo call + review replay

### Option B: Dedicated VPS

```bash
git clone https://github.com/Brohammad/VoxForge.git
./scripts/setup-production-env.sh your-company.voxforge.app
# Add provider API keys
./deploy.sh init
```

Follow [deployment checklist](../deployment/verification-checklist.md).

## Week 1 — Configure voice stack

| Setting | Recommendation |
|---------|----------------|
| `STT_PROVIDER` | `deepgram` |
| `LLM_PROVIDER` | `openai` |
| `TTS_PROVIDER` | `cartesia` |
| `KNOWLEDGE_WORKER_ENABLED` | `true` on 4GB+ VPS |
| `DEMO_ENABLED` | `false` in production pilot |

## Week 2 — Validate journeys

- [ ] Voice onboarding call completes
- [ ] Knowledge search returns grounded answers
- [ ] Handoff creates queue item + replay link
- [ ] Dashboard shows latency + evaluation metrics
- [ ] Operator can replay session

## Support channels

| Channel | Use for |
|---------|---------|
| GitHub Issues | Bugs, feature requests |
| GitHub Discussions | Questions, architecture |
| Security advisories | Vulnerabilities |

## Pilot completion

Complete [feedback questionnaire](feedback-questionnaire.md) and [pilot completion report](pilot-completion-report.md) template.
