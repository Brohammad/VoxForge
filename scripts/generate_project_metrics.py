#!/usr/bin/env python3
"""Regenerate docs/project-metrics.md from repository state."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTEST = ROOT / ".venv" / "bin" / "pytest"
PYTEST_CMD = [str(VENV_PYTEST)] if VENV_PYTEST.exists() else [sys.executable, "-m", "pytest"]
API_DIR = ROOT / "src" / "voxforge" / "api"
MODULES_DIR = ROOT / "src" / "voxforge" / "modules"
VERIFIED_COMMIT = "5d0571689ffc4d50aaf9c94dd2ecada856530033"
VERIFIED_CI_RUN = "https://github.com/Brohammad/VoxForge/actions/runs/33298953452"
VERIFIED_CI_RUN_ID = VERIFIED_CI_RUN.rsplit("/", 1)[-1]
VERIFIED_CI_DATE = "2026-08-30"
VERIFIED_COVERAGE_PERCENT = 76.40
TEST_ENV = {
    "STT_PROVIDER": "mock",
    "LLM_PROVIDER": "mock",
    "TTS_PROVIDER": "mock",
    "EMBEDDING_PROVIDER": "mock",
    "MEMORY_ENABLED": "false",
    "EVALUATION_HALLUCINATION_ENABLED": "false",
    "TOOLS_ENABLED": "false",
}


@dataclass(frozen=True)
class TestMetrics:
    non_browser_collected: int
    non_browser_passed: int
    non_browser_skipped: int
    browser_collected: int


def count_rest_endpoints() -> int:
    pattern = re.compile(r"@router\.(get|post|put|patch|delete)\(")
    total = 0
    for path in API_DIR.rglob("*.py"):
        total += len(pattern.findall(path.read_text()))
    return total


def count_websocket_endpoints() -> int:
    pattern = re.compile(r"@router\.websocket\(")
    total = 0
    for path in API_DIR.rglob("*.py"):
        total += len(pattern.findall(path.read_text()))
    return total


def run_pytest(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*PYTEST_CMD, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**subprocess.os.environ, **TEST_ENV, "PYTHONPATH": str(ROOT)},
        check=False,
    )
    if result.returncode != 0:
        details = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        raise RuntimeError(f"pytest failed ({' '.join(args)}):\n{details}")
    return result


def parse_collected(result: subprocess.CompletedProcess[str]) -> int:
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"(\d+) tests collected", output)
    if not match:
        raise RuntimeError(f"Could not parse collected test count:\n{output}")
    return int(match.group(1))


def collect_test_metrics() -> TestMetrics:
    non_browser_collected = parse_collected(
        run_pytest("--collect-only", "-q", "--ignore=tests/browser")
    )
    browser_collected = parse_collected(run_pytest("tests/browser", "--collect-only", "-q"))

    result = run_pytest("-q", "--ignore=tests/browser")
    output = f"{result.stdout}\n{result.stderr}"
    passed_match = re.search(r"(\d+) passed", output)
    skipped_match = re.search(r"(\d+) skipped", output)
    if not passed_match:
        raise RuntimeError(f"Could not parse passed test count:\n{output}")

    return TestMetrics(
        non_browser_collected=non_browser_collected,
        non_browser_passed=int(passed_match.group(1)),
        non_browser_skipped=int(skipped_match.group(1)) if skipped_match else 0,
        browser_collected=browser_collected,
    )


def git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def main() -> None:
    tests = collect_test_metrics()
    revision = git_revision()
    coverage = (
        f"{VERIFIED_COVERAGE_PERCENT:.2f}%"
        if revision == VERIFIED_COMMIT
        else "Unverified for this revision"
    )
    modules = sorted(
        p.name
        for p in MODULES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("_") and p.name != "__pycache__"
    )
    adrs = sorted((ROOT / "docs" / "adr").glob("ADR-*.md"))
    arch_docs = sorted((ROOT / "docs" / "architecture").glob("*.md"))
    benchmarks = sorted((ROOT / "docs" / "benchmarks").glob("*.md"))

    content = f"""# VoxForge Project Metrics

> Single source of truth for repository engineering metrics.
> Last updated: {datetime.now(UTC).strftime("%Y-%m-%d")}
> Repository revision: `{revision}`
> Regenerate: `python3 scripts/generate_project_metrics.py`

The local results below distinguish **collected**, **passed**, and **skipped** tests.
Browser tests are collection-verified here; they are executed separately by the Playwright CI job.
Coverage and CI evidence are pinned to the verified commit above; coverage is marked
unverified if this document is regenerated at another revision.

## Summary

| Metric | Value |
|--------|------:|
| Application modules | {len(modules)} |
| REST endpoints | {count_rest_endpoints()} |
| WebSocket endpoints | {count_websocket_endpoints()} |
| Non-browser tests collected | {tests.non_browser_collected} |
| Non-browser tests passed | {tests.non_browser_passed} |
| Non-browser tests skipped | {tests.non_browser_skipped} |
| Browser tests collected | {tests.browser_collected} |
| Total tests collected | {tests.non_browser_collected + tests.browser_collected} |
| Verified coverage (`src/voxforge`, non-browser suite) | {coverage} |
| ADRs | {len(adrs)} |
| Architecture documents | {len(arch_docs)} |
| Benchmark documents | {len(benchmarks)} |

## Verification evidence

- Local non-browser command: `PYTHONPATH=. pytest -q --ignore=tests/browser --cov=src/voxforge`
- Browser collection command: `PYTHONPATH=. pytest tests/browser --collect-only -q`
- Verified GitHub CI: [run {VERIFIED_CI_RUN_ID}]({VERIFIED_CI_RUN}) passed on
  {VERIFIED_CI_DATE} for commit [`{VERIFIED_COMMIT[:8]}`](https://github.com/Brohammad/VoxForge/commit/{VERIFIED_COMMIT}).

## Application modules ({len(modules)})

{chr(10).join(f"- `{m}`" for m in modules)}

## API surface

| Transport | Count | Entry points |
|-----------|------:|--------------|
| REST | {count_rest_endpoints()} | `/api/v1/*` routers |
| WebSocket | {count_websocket_endpoints()} | `/api/v1/ws/voice`, `/lk/{{path}}` |

## Tests

Run non-browser tests: `make test`
Run Playwright tests: `make test-browser`

| Category | Location |
|----------|----------|
| Unit | `tests/unit/` |
| Integration | `tests/integration/` |

## Architecture decision records ({len(adrs)})

{chr(10).join(f"- [{a.name}](adr/{a.name})" for a in adrs)}

## Architecture documents ({len(arch_docs)})

{chr(10).join(f"- [{a.name}](architecture/{a.name})" for a in arch_docs)}

## Benchmarks ({len(benchmarks)})

{chr(10).join(f"- [{b.name}](benchmarks/{b.name})" for b in benchmarks)}

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
"""
    (ROOT / "docs" / "project-metrics.md").write_text(content)
    print("Wrote docs/project-metrics.md")


if __name__ == "__main__":
    main()
