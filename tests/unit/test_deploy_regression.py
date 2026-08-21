"""Regression tests for production deployment scripts and compose config."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = ROOT / "deploy.sh"
COMPOSE_FILE = ROOT / "docker-compose.prod.yml"
PROD_ENV = ROOT / ".env.production"
PROD_ENV_EXAMPLE = ROOT / ".env.production.example"


def _require_docker() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker not available")


@pytest.fixture
def prod_compose_env() -> Iterator[None]:
    """Ensure .env.production exists for docker compose config (CI has no local secrets file)."""
    created = False
    backup: bytes | None = None
    if PROD_ENV.exists():
        backup = PROD_ENV.read_bytes()
    else:
        created = True
    if not PROD_ENV_EXAMPLE.is_file():
        pytest.skip(".env.production.example missing")
    shutil.copy(PROD_ENV_EXAMPLE, PROD_ENV)
    try:
        yield
    finally:
        if created:
            PROD_ENV.unlink(missing_ok=True)
        elif backup is not None:
            PROD_ENV.write_bytes(backup)


@pytest.mark.parametrize(
    "pattern",
    [
        "--entrypoint certbot certbot certonly",
        "--entrypoint certbot certbot renew",
    ],
)
def test_deploy_sh_uses_certbot_entrypoint_override(pattern: str) -> None:
    text = DEPLOY_SH.read_text()
    assert pattern in text


def test_docker_compose_prod_parses_with_defaults(prod_compose_env: None) -> None:
    _require_docker()
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "config", "--quiet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "POSTGRES_PASSWORD": "test-secret", "REDIS_PASSWORD": "test-redis"},
    )
    assert result.returncode == 0, result.stderr


def test_docker_compose_cpu_limits_are_configurable(prod_compose_env: None) -> None:
    _require_docker()
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "POSTGRES_PASSWORD": "test-secret",
            "REDIS_PASSWORD": "test-redis",
            "COMPOSE_CPU_APP": "0.25",
            "COMPOSE_MEM_APP": "768M",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "cpus: 0.25" in result.stdout


def test_ensure_demo_account_script_exists() -> None:
    assert (ROOT / "scripts" / "ensure_demo_account.py").is_file()


def test_docker_entrypoint_skips_missing_demo_script() -> None:
    text = (ROOT / "scripts" / "docker-entrypoint.sh").read_text()
    assert "[ -f /app/scripts/ensure_demo_account.py ]" in text


def test_deploy_sh_auto_generates_env_file() -> None:
    text = DEPLOY_SH.read_text()
    assert "setup-production-env.sh" in text


def test_deploy_sh_stages_nginx_tls_snippets() -> None:
    text = DEPLOY_SH.read_text()
    assert "deploy/nginx/staged" in text
    assert 'rm -f "$NGINX_CONF_DIR/voxforge-http.conf"' in text
