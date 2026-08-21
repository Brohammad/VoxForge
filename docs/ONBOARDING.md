# 15-Minute Developer Onboarding

Get from `git clone` to first voice session in under 15 minutes.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Docker + Compose v2

## Steps

| Minute | Action | Command |
|--------|--------|---------|
| 0–2 | Clone | `git clone https://github.com/Brohammad/VoxForge.git && cd VoxForge` |
| 2–3 | Env | `cp .env.example .env` |
| 3–5 | Dependencies | `uv sync` or `pip install -e ".[dev,livekit]"` |
| 5–7 | Database | `docker compose up -d postgres redis && alembic upgrade head` |
| 7–8 | Start API | `uvicorn voxforge.main:app --reload --app-dir src` |
| 8–10 | First API call | Open http://localhost:8000/api/v1/docs → `GET /health` |
| 10–12 | Dashboard | http://localhost:8000/dashboard → register account |
| 12–15 | Voice demo | http://localhost:8000/demo → **Run one-click sample call** |

## Verify tests

```bash
make test              # 346+ tests (~16s)
make test-browser      # 8 Playwright journeys (~6s)
ruff check src tests
```

## Local production smoke

```bash
./scripts/validate-prod-smoke.sh
```

## Deploy to VPS

```bash
./scripts/setup-production-env.sh your-domain.example
./deploy.sh init
```

See [deployment guide](deployment/guide.md) for full production path. Full docs index: [README.md](README.md).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `connection refused` on 5432 | `docker compose up -d postgres redis` |
| Landing 404 in Docker | Ensure `public/` is mounted (see `docker-compose.yml`) |
| Browser tests fail | Run `./scripts/run_browser_tests.sh` (installs Chromium) |
