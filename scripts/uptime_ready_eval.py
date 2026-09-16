#!/usr/bin/env python3
"""Evaluate /api/v1/ready JSON for uptime monitors.

Default: HTTP 200 with status=ok or status=degraded is success when Postgres
and Redis report ok (matches the API when READY_FAIL_ON_DEGRADED is unset).

Set FAIL_ON_DEGRADED=true (or READY_FAIL_ON_DEGRADED=true) to fail on
status=degraded so optional-dep failures page operators.

Usage:
  echo '{"status":"ok","database":"ok","redis":"ok"}' | python3 scripts/uptime_ready_eval.py
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from typing import Any


def fail_on_degraded_from_env(env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    for key in ("FAIL_ON_DEGRADED", "READY_FAIL_ON_DEGRADED"):
        if source.get(key, "").strip().lower() in {"1", "true", "yes"}:
            return True
    return False


def evaluate_ready_payload(data: dict[str, Any], *, fail_on_degraded: bool = False) -> None:
    """Exit 0 if the monitor should stay green; raise SystemExit on failure."""
    db = data.get("database")
    redis = data.get("redis")
    if db != "ok" or redis != "ok":
        raise SystemExit(f"database={db!r} redis={redis!r}")
    status = data.get("status")
    allowed = ("ok",) if fail_on_degraded else ("ok", "degraded")
    if status not in allowed:
        raise SystemExit(f"status={status!r}")


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("ready payload must be a JSON object")
    evaluate_ready_payload(data, fail_on_degraded=fail_on_degraded_from_env())


if __name__ == "__main__":
    main()
