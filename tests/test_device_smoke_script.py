from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from trmnl_terminus.errors import TerminusNotFoundError

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_device_smoke.py"


def _load_script() -> ModuleType:
    assert SCRIPT.exists(), "the physical-device proof runner must exist"
    spec = importlib.util.spec_from_file_location("run_device_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _guarded_environment(*, device_id: str = "23", mutation_guard: str = "1") -> dict[str, str]:
    return {
        **os.environ,
        "TERMINUS_BASE_URL": "https://must-not-be-used.example.test",
        "TERMINUS_EMAIL": "operator@example.test",
        "TERMINUS_PASSWORD": "synthetic-secret",
        "TERMINUS_DEVICE_ID": device_id,
        "TERMINUS_ALLOW_DEVICE_MUTATIONS": mutation_guard,
    }


def test_device_smoke_exits_before_network_when_environment_is_missing() -> None:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("TERMINUS_"):
            environment.pop(name)

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
        "TERMINUS_DEVICE_ID, TERMINUS_ALLOW_DEVICE_MUTATIONS\n"
    )


def test_device_smoke_requires_explicit_mutation_permission() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=_guarded_environment(mutation_guard="0"),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == ("TERMINUS_ALLOW_DEVICE_MUTATIONS must equal 1; no requests sent\n")


@pytest.mark.parametrize("device_id", ["0", "-1", "not-an-integer"])
def test_device_smoke_rejects_non_positive_device_id_before_network(device_id: str) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=_guarded_environment(device_id=device_id),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "TERMINUS_DEVICE_ID must be a positive integer; no requests sent\n"


@pytest.mark.parametrize("acknowledgment", ["seen", " SEEN\n", "\tSeEn  "])
def test_acknowledgment_accepts_trimmed_case_insensitive_seen(acknowledgment: str) -> None:
    module = _load_script()

    assert module._acknowledged(acknowledgment)


@pytest.mark.parametrize("acknowledgment", ["", "see", "seen now", "unseen"])
def test_acknowledgment_rejects_everything_except_seen(acknowledgment: str) -> None:
    module = _load_script()

    assert not module._acknowledged(acknowledgment)


def test_acknowledgment_wait_times_out_after_default_600_seconds_without_blocking() -> None:
    module = _load_script()
    observed_timeouts: list[float] = []

    def immediate_timeout(timeout_seconds: float) -> str | None:
        observed_timeouts.append(timeout_seconds)
        return None

    assert not module._wait_for_acknowledgment(read_line=immediate_timeout)
    assert observed_timeouts == [600.0]


def test_safe_failure_names_only_stage_exception_class_and_status() -> None:
    module = _load_script()
    response = httpx.Response(
        404,
        request=httpx.Request("PATCH", "https://private.example.test/api/devices/23"),
        json={"detail": "private response body"},
    )
    error = TerminusNotFoundError(
        "not found",
        response=response,
        problem=response.json(),
    )

    message = module._safe_failure(error, "device.assign")

    assert message == "Device proof failed at device.assign: TerminusNotFoundError status=404"
    assert "private.example.test" not in message
    assert "private response body" not in message
