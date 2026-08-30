from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

MOCK_CURL = r"""#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
url = next((arg for arg in args if arg.startswith("http")), "")
with open(os.environ["MOCK_CURL_LOG"], "a") as log:
    log.write(url + "\n")

if url.endswith("/api/v1/demo/info") and os.environ.get("MOCK_DEMO_INFO") == "unavailable":
    raise SystemExit(22)

responses = {
    "/api/v1/health": {"status": "ok"},
    "/api/v1/ready": {"status": "ok", "database": "ok", "redis": "ok"},
    "/api/v1/demo/info": {"providers_mode": os.environ.get("MOCK_PROVIDERS_MODE", "live")},
    "/api/v1/onboarding/run-sample-call": {
        "status": "test_call_passed",
        "test_session_id": "session-1",
    },
    "/api/v1/sessions/session-1/messages": {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
    },
    "/api/v1/sessions/session-1/evaluations": {"evaluations": []},
    "/api/v1/demo/trust-loop": {
        "status": "trust_loop_ok",
        "session_id": "session-2",
        "citations": [{"document_title": "Refund policy"}],
        "handoff_id": "handoff-1",
        "replay_url": "/replay/session-2",
    },
}

if url.endswith("/api/v1/auth/login"):
    status = os.environ.get("MOCK_LOGIN_STATUS", "200")
    body = {"access_token": "login-token"} if status.startswith("2") else {"detail": "invalid"}
elif url.endswith("/api/v1/auth/register"):
    status = os.environ.get("MOCK_REGISTER_STATUS", "201")
    body = (
        {"tokens": {"access_token": "register-token"}}
        if status.startswith("2")
        else {"detail": "registration disabled"}
    )
else:
    status = "200"
    body = next((value for suffix, value in responses.items() if url.endswith(suffix)), {})

print(json.dumps(body))
if "-w" in args:
    print(status)
"""


@pytest.fixture
def proof_env(tmp_path: Path) -> dict[str, str]:
    curl = tmp_path / "curl"
    curl.write_text(MOCK_CURL)
    curl.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MOCK_CURL_LOG": str(tmp_path / "curl.log"),
        "PROVE_EMAIL": "operator@example.com",
        "PROVE_PASSWORD": "not-printed",
    }


def run_proof(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/prove-real-voice.sh", "https://voice.example"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_proof_logs_in_on_invite_only_host(proof_env: dict[str, str]) -> None:
    result = run_proof({**proof_env, "PROVE_AUTH_MODE": "login"})

    assert result.returncode == 0, result.stderr
    assert "real-provider programmatic voice turn passed" in result.stdout
    assert "not-printed" not in result.stdout + result.stderr


def test_proof_auto_mode_falls_back_to_registration(proof_env: dict[str, str]) -> None:
    result = run_proof(
        {
            **proof_env,
            "PROVE_AUTH_MODE": "auto",
            "MOCK_LOGIN_STATUS": "401",
            "MOCK_REGISTER_STATUS": "201",
        }
    )

    assert result.returncode == 0, result.stderr
    assert "trying registration" in result.stdout


def test_proof_rejects_non_live_provider_mode(proof_env: dict[str, str]) -> None:
    result = run_proof({**proof_env, "MOCK_PROVIDERS_MODE": "mock"})

    assert result.returncode == 1
    assert "expected live" in result.stderr
