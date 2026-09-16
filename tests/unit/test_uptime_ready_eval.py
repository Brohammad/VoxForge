"""JSON evaluation for scripts/uptime-ready-check.sh."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_SCRIPT = REPO_ROOT / "scripts" / "uptime_ready_eval.py"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "uptime-ready-check.sh"


def _load_eval() -> ModuleType:
    spec = importlib.util.spec_from_file_location("uptime_ready_eval", EVAL_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


eval_mod = _load_eval()

OK_PAYLOAD = {"status": "ok", "database": "ok", "redis": "ok"}
DEGRADED_PAYLOAD = {
    "status": "degraded",
    "database": "ok",
    "redis": "ok",
    "mcp_registry": "degraded",
}


def test_fail_on_degraded_env_flag() -> None:
    assert eval_mod.fail_on_degraded_from_env({}) is False
    assert eval_mod.fail_on_degraded_from_env({"FAIL_ON_DEGRADED": "true"}) is True
    assert eval_mod.fail_on_degraded_from_env({"READY_FAIL_ON_DEGRADED": "1"}) is True
    assert eval_mod.fail_on_degraded_from_env({"FAIL_ON_DEGRADED": "false"}) is False


def test_default_accepts_ok_and_degraded() -> None:
    eval_mod.evaluate_ready_payload(OK_PAYLOAD)
    eval_mod.evaluate_ready_payload(DEGRADED_PAYLOAD)


def test_fail_on_degraded_rejects_degraded() -> None:
    with pytest.raises(SystemExit, match="status='degraded'"):
        eval_mod.evaluate_ready_payload(DEGRADED_PAYLOAD, fail_on_degraded=True)


def test_critical_deps_always_required() -> None:
    with pytest.raises(SystemExit, match="redis"):
        eval_mod.evaluate_ready_payload(
            {"status": "ok", "database": "ok", "redis": "error: timeout"}
        )
    with pytest.raises(SystemExit, match="database"):
        eval_mod.evaluate_ready_payload(
            {"status": "unavailable", "database": "error: timeout", "redis": "ok"}
        )


def _run_eval(
    payload: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **(extra_env or {})}
    return subprocess.run(
        ["python3", str(EVAL_SCRIPT)],
        input=payload,
        text=True,
        capture_output=True,
        env=merged,
        check=False,
    )


def test_eval_script_stdin_default_accepts_degraded() -> None:
    result = _run_eval('{"status":"degraded","database":"ok","redis":"ok"}')
    assert result.returncode == 0, result.stderr


def test_eval_script_stdin_fail_on_degraded() -> None:
    result = _run_eval(
        '{"status":"degraded","database":"ok","redis":"ok"}',
        extra_env={"FAIL_ON_DEGRADED": "true"},
    )
    assert result.returncode == 1
    assert "status=" in result.stderr


MOCK_CURL = r"""#!/usr/bin/env python3
import os
import sys

args = sys.argv[1:]
print(os.environ.get("MOCK_READY_BODY", ""))
"""


def test_check_script_default_ok_on_degraded(tmp_path: Path) -> None:
    curl = tmp_path / "curl"
    curl.write_text(MOCK_CURL)
    curl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MOCK_READY_BODY": json.dumps(DEGRADED_PAYLOAD),
    }
    result = subprocess.run(
        ["bash", str(CHECK_SCRIPT), "http://example.test"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "OK:" in result.stdout


def test_check_script_fail_on_degraded(tmp_path: Path) -> None:
    curl = tmp_path / "curl"
    curl.write_text(MOCK_CURL)
    curl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MOCK_READY_BODY": json.dumps(DEGRADED_PAYLOAD),
        "FAIL_ON_DEGRADED": "true",
    }
    result = subprocess.run(
        ["bash", str(CHECK_SCRIPT), "http://example.test"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 1
    assert "FAIL:" in result.stderr
