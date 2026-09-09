from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
TERMINUS_ENVIRONMENT_PREFIX = "TERMINUS_"


def _run_example(name: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    clean_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(TERMINUS_ENVIRONMENT_PREFIX)
    }
    clean_environment.update(environment)
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "examples" / name)],
        cwd=PROJECT_ROOT,
        env=clean_environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def test_list_resources_names_missing_configuration() -> None:
    result = _run_example("list_resources.py", {})

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Missing required environment variables" in result.stderr
    assert "TERMINUS_BASE_URL" in result.stderr
    assert "TERMINUS_EMAIL" in result.stderr
    assert "TERMINUS_PASSWORD" in result.stderr


def test_render_screen_requires_explicit_mutation_opt_in_before_network() -> None:
    result = _run_example(
        "render_screen.py",
        {
            "TERMINUS_BASE_URL": "https://example.test",
            "TERMINUS_EMAIL": "example@example.test",
            "TERMINUS_PASSWORD": "not-a-real-secret",
            "TERMINUS_ALLOW_MUTATIONS": "0",
        },
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "TERMINUS_ALLOW_MUTATIONS" in result.stderr
    assert "no requests sent" in result.stderr
