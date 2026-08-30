# Frequently Asked Questions

Quick answers. Full docs: [README.md](README.md)

---

## Getting started

### Do I need API keys to try VoxForge locally?

No. Copy `.env.example` — mock STT/LLM/TTS/embedding providers work without paid keys. Open http://localhost:8000/demo and click **Run one-click sample call**.

### How long does local setup take?

About 15 minutes. See [ONBOARDING.md](ONBOARDING.md).

### What's the difference between local and production config?

| File | Use |
|------|-----|
| `.env` | Local development |
| `.env.production` | VPS deployment (never commit) |

See [CONFIGURATION.md](CONFIGURATION.md).

---

## Deployment

### How do I deploy to production?

```bash
./scripts/setup-production-env.sh your-domain.example.com
./deploy.sh init
```

Full guide: [deployment/guide.md](deployment/guide.md)

### Is there a live reference deployment?

Yes — https://voxforge.brohammad.tech ([record](deployment/public-deployment-record.md))

### What VPS size do I need?

Minimum **2 GB RAM** for core stack. Use **4 GB+** if enabling knowledge worker + monitoring.

### How do backups work?

`./deploy.sh backup` — see [operations/backup-restore.md](operations/backup-restore.md)

---

## Voice & providers

### Can I use real voice providers?

Yes. Set `STT_PROVIDER`, `LLM_PROVIDER`, `TTS_PROVIDER` and API keys. Production validation requires real providers when `DEMO_ENABLED=false`.

### Is LiveKit required?

No. WebSocket voice works without LiveKit. LiveKit adds browser WebRTC — set `LIVEKIT_URL` and deploy the `livekit` worker profile.

### Why does `/demo` return 404?

Set `DEMO_ENABLED=true` in `.env` and restart.

---

## Knowledge base

### How are uploads processed?

- **Local (`KNOWLEDGE_WORKER_ENABLED=false`):** inline ingestion
- **Production:** `KNOWLEDGE_WORKER_ENABLED=true` with blobs on `/data/knowledge` (Docker volume). `deploy.sh` starts the worker. Uploads stay queued if the worker is down.

### Why does search return no results with mock embeddings?

Mock provider uses a permissive similarity threshold automatically. Ensure documents show status `ready`.

---

## Testing & CI

### How do I run tests?

```bash
make test              # 417 collected (407 passed, 10 skipped; excludes browser)
make test-browser      # 9 Playwright UI journeys
```

See [testing/README.md](testing/README.md).

### What is the coverage gate?

70% minimum in CI. Report: [testing/coverage-report.md](testing/coverage-report.md)

---

## Security

### Where are dashboard tokens stored?

Login sets **HttpOnly cookies** (`voxforge_access`) with CSRF protection for mutating requests. Pasting a JWT into the dashboard connect bar still uses Bearer + `localStorage` as a debugging override. See [release/known-limitations.md](release/known-limitations.md).

### How do I report a vulnerability?

[SECURITY.md](../SECURITY.md) — private advisory, not a public issue.

---

## Contributing & pilots

### How do I become a design partner?

[pilot/onboarding-guide.md](pilot/onboarding-guide.md)

### How is VoxForge different from Vapi or Retell?

Self-hosted, open source, evaluation/replay built-in, no per-minute platform fee. [benchmarks/competitive-analysis.md](benchmarks/competitive-analysis.md)

---

## Known limitations

[release/known-limitations.md](release/known-limitations.md) · [ROADMAP.md](ROADMAP.md)
