from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_real_smoke.py"
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
