from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import httpx

from trmnl_terminus.errors import TerminusNotFoundError

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_real_smoke.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("run_real_smoke", SCRIPT)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
SCRIPT_MODULE = importlib.util.module_from_spec(SCRIPT_SPEC)
sys.modules[SCRIPT_SPEC.name] = SCRIPT_MODULE
SCRIPT_SPEC.loader.exec_module(SCRIPT_MODULE)
_safe_failure = SCRIPT_MODULE._safe_failure
REQUIRED = (
    "TERMINUS_BASE_URL",
    "TERMINUS_EMAIL",
    "TERMINUS_PASSWORD",
    "TERMINUS_ALLOW_MUTATION_TESTS",
)


def test_smoke_exits_before_network_when_environment_is_missing() -> None:
    environment = os.environ.copy()
    for name in REQUIRED:
        environment.pop(name, None)

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "Missing required environment variables: "
        "TERMINUS_BASE_URL, TERMINUS_EMAIL, TERMINUS_PASSWORD, "
        "TERMINUS_ALLOW_MUTATION_TESTS\n"
    )


def test_smoke_requires_explicit_mutation_permission() -> None:
    environment = {
        **os.environ,
        "TERMINUS_BASE_URL": "https://must-not-be-used.example.test",
        "TERMINUS_EMAIL": "user@example.test",
        "TERMINUS_PASSWORD": "secret",
        "TERMINUS_ALLOW_MUTATION_TESTS": "0",
    }

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "TERMINUS_ALLOW_MUTATION_TESTS must equal 1; no requests sent\n"


def test_safe_failure_names_stage_without_response_details() -> None:
    response = httpx.Response(
        404,
        request=httpx.Request("POST", "https://private.example.test/api/screens"),
        json={"error": "private server detail"},
    )
    error = TerminusNotFoundError(
        "not found",
        response=response,
        problem=response.json(),
    )

    message = _safe_failure(error, "screen.create")

    assert message == "Smoke failed at screen.create: TerminusNotFoundError status=404"
    assert "private.example.test" not in message
    assert "private server detail" not in message
