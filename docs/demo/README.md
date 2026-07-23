# Demo Documentation

Materials for demonstrating VoxForge to recruiters, investors, and pilot customers.

## Live demo

| URL | Purpose |
|-----|---------|
| https://voxforge.brohammad.tech | Product landing page |
| https://voxforge.brohammad.tech/demo | One-click voice pipeline |
| https://voxforge.brohammad.tech/dashboard | Operator console |

## Scripts

| Document | Duration | Audience |
|----------|----------|----------|
| [demo-script-short.md](demo-script-short.md) | 60 seconds | Social, quick intro |
| [demo-script-long.md](demo-script-long.md) | 8 minutes | Technical walkthrough |
| [presenter-notes.md](presenter-notes.md) | — | Talking points and FAQs |

## Client demo (local, one command)

```bash
bash scripts/client_demo.sh
```

Starts Postgres/Redis, migrates, ensures the demo account, warms the pipeline, opens browser tabs, and prints an 8-minute cue card. Dashboard login: `demo@voxforge.io` / `VoxForgeDemo!`.

```bash
make client-demo          # same as above
OPEN_BROWSER=0 make client-demo   # prep only, no tabs
```

Teaching deep-dive (API walkthrough): `bash scripts/teach_me_voxforge.sh`

## Recording

| Document | Purpose |
|----------|---------|
| [recording-checklist.md](recording-checklist.md) | Pre-flight, assets, ffmpeg GIF |
| [../product/real-voice-proof.md](../product/real-voice-proof.md) | Automated + recorded real-provider proof |

## Assets

| Asset | Location |
|-------|----------|
| Demo GIF | `docs/assets/screenshots/demo.gif` |
| Screenshots | `docs/assets/screenshots/` |

## Local demo

```bash
uvicorn voxforge.main:app --reload --app-dir src
# Open http://localhost:8000/demo
```

Mock providers — no API keys required when `DEMO_ENABLED=true`.
