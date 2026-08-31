# Contributing to VoxForge

Thank you for helping improve VoxForge. This project targets production-grade voice AI infrastructure — contributions should increase reliability, clarity, or maintainability.

## Good first issues

Start here if this is your first contribution:

https://github.com/Brohammad/VoxForge/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22

Pick one issue, comment that you are taking it, then open a PR against `main`. Prefer docs, tests, copy, and provider adapters over large refactors.

## Development setup

```bash
git clone https://github.com/Brohammad/VoxForge.git
cd VoxForge
cp .env.example .env
docker compose up -d postgres redis
uv sync                    # or: pip install -e ".[dev,livekit]"
alembic upgrade head
uvicorn voxforge.main:app --reload --app-dir src
```

Open:

- API docs: http://localhost:8000/api/v1/docs
- Demo: http://localhost:8000/demo
- Dashboard: http://localhost:8000/dashboard

On `/demo`, the buttons are **Start talking**, **Run trust loop**, and **Run one-click sample call**.

## Running tests

```bash
# Full suite (excludes browser — use make test-browser for Playwright)
make test

# By layer
make test-unit
make test-integration
make test-feature
make test-failure
make test-e2e
make test-browser

# Lint
ruff check src tests

# Coverage gate (70% minimum)
make test-cov
```

CI runs the same layers against Postgres + Redis with mock providers (no API keys required).

Live provider tests (`tests/live/`) require API keys:

```bash
scripts/run_live_tests.sh
```

Manual production-like QA against a running server:

```bash
scripts/e2e_qa_manual.py
```

## Pull request guidelines

1. **One logical change per commit** when possible.
2. **Explain why** in the commit message, not just what changed.
3. **Run relevant tests** — at minimum `ruff check src tests` and `pytest` for affected areas.
4. **Do not reduce coverage** or break existing APIs without discussion.
5. **Update docs** when behavior, env vars, or deployment steps change.
6. **Keep line endings LF.** Do not rewrite unchanged files.

## Code style

- Python 3.12+, formatted with **ruff** (line length 100).
- Clean Architecture layering: `api/` → `modules/` → `core/`; infrastructure adapters in `infrastructure/`.
- Prefer extending existing factories and services over duplicating pipeline wiring.

## Architecture decisions

Significant design changes should include or update an ADR in `docs/adr/`.

## Security

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md).

## Questions

Search [existing issues](https://github.com/Brohammad/VoxForge/issues) first, then open a [Question](https://github.com/Brohammad/VoxForge/issues/new?template=question.md) issue. Do not file security reports as public issues.

Documentation index: [docs/README.md](docs/README.md)
