# Testing Documentation

VoxForge uses a **test pyramid**: unit → integration → feature → failure → browser, with a **70% coverage gate** in CI.

## Quick commands

```bash
make test              # 414 collected (404 passed, 10 skipped; excludes browser)
make test-browser      # 9 Playwright UI journeys
make test-unit
make test-integration
make test-feature
make test-failure
make test-e2e
make test-cov          # Coverage report (70% minimum)
ruff check src tests
```

## Test layers

| Layer | Directory | What it covers |
|-------|-----------|----------------|
| Unit | `tests/unit/` | Pure logic, parsers, middleware, deploy scripts |
| Integration | `tests/integration/` | DB, Redis, API routes, providers (mocked) |
| Feature | `tests/feature/` | Multi-step user scenarios (`@pytest.mark.feature`) |
| Failure | `tests/failure/` | Provider outages, timeouts (`@pytest.mark.failure`) |
| E2E | `tests/e2e/` | Smoke-level end-to-end (`@pytest.mark.e2e`) |
| Browser | `tests/browser/` | Playwright UI journeys (`@pytest.mark.browser`) |
| Live | `tests/live/` | Real provider keys (manual, not in CI) |

## Guides

| Document | Description |
|----------|-------------|
| [testing-strategy.md](testing-strategy.md) | Philosophy, gates, and conventions |
| [feature-tests.md](feature-tests.md) | Writing feature scenarios |
| [failure-testing.md](failure-testing.md) | Failure-mode test patterns |
| [e2e-tests.md](e2e-tests.md) | E2E smoke tests |
| [load-testing.md](load-testing.md) | Load and soak testing |
| [coverage.md](coverage.md) | Coverage policy |
| [coverage-report.md](coverage-report.md) | Latest coverage numbers |

## CI

Every push to `main` runs:

- `ruff check`
- `pip-audit` dependency scan
- `gitleaks` secret scan
- All test layers (browser in separate job)
- `Dockerfile.prod` build
- Evaluation quality gate

CI uses **mock providers** — no API keys required.

## Manual QA

```bash
# Against a running local or production server
python scripts/e2e_qa_manual.py

# Real voice providers (requires keys)
scripts/run_live_tests.sh
```

## Browser tests

```bash
./scripts/run_browser_tests.sh
# or
make test-browser
```

Covers: landing, demo, dashboard login, knowledge upload/search, replay, handoff, logout, 404.
