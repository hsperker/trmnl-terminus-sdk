from __future__ import annotations

import os
import secrets
import select
import sys
from collections.abc import Callable

from pydantic import SecretStr

from trmnl_terminus import (
    Credentials,
    DevicePatch,
    HtmlSource,
    PlaylistCreate,
    PlaylistPatch,
    ScreenCreate,
    TerminusClient,
)
from trmnl_terminus.errors import TerminusResponseError

REQUIRED_ENVIRONMENT = (
    "TERMINUS_BASE_URL",
    "TERMINUS_EMAIL",
    "TERMINUS_PASSWORD",
    "TERMINUS_DEVICE_ID",
    "TERMINUS_ALLOW_DEVICE_MUTATIONS",
)
ACKNOWLEDGMENT_TIMEOUT_SECONDS = 600.0


class DeviceSmokeFailure(RuntimeError):
    pass


def main(*, input_timeout_seconds: float = ACKNOWLEDGMENT_TIMEOUT_SECONDS) -> int:
    missing = [name for name in REQUIRED_ENVIRONMENT if not os.environ.get(name)]
    if missing:
        print(
            f"Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    if os.environ["TERMINUS_ALLOW_DEVICE_MUTATIONS"] != "1":
        print(
            "TERMINUS_ALLOW_DEVICE_MUTATIONS must equal 1; no requests sent",
            file=sys.stderr,
        )
        return 2

    try:
        device_id = int(os.environ["TERMINUS_DEVICE_ID"])
    except ValueError:
        device_id = 0
    if device_id <= 0:
        print(
            "TERMINUS_DEVICE_ID must be a positive integer; no requests sent",
            file=sys.stderr,
        )
        return 2

    client: TerminusClient | None = None
    original_playlist_id: int | None = None
    temporary_playlist_id: int | None = None
    temporary_screen_id: int | None = None
    failure: tuple[str, BaseException] | None = None
    recovery_failures: list[tuple[str, BaseException]] = []
    failure_stage = "client.create"

    try:
        credentials = Credentials(
            email=os.environ["TERMINUS_EMAIL"],
            password=SecretStr(os.environ["TERMINUS_PASSWORD"]),
        )
        client = TerminusClient(
            os.environ["TERMINUS_BASE_URL"],
            credentials=credentials,
        )

        failure_stage = "device.get"
        device = client.devices.get(device_id)
        failure_stage = "device.assignment-check"
        if device.playlist_id is None or device.playlist_id <= 0:
            raise DeviceSmokeFailure
        original_playlist_id = device.playlist_id

        suffix = secrets.token_hex(6)
        failure_stage = "playlist.create"
        playlist = client.playlists.create(
            PlaylistCreate(
                name=f"sdk_device_proof_{suffix}",
                label=f"SDK Device Proof {suffix}",
                screen_ids=[],
            )
        )
        temporary_playlist_id = playlist.id

        failure_stage = "screen.create"
        screen = client.screens.create(
            ScreenCreate(
                model_id=device.model_id,
                name=f"sdk_device_proof_{suffix}",
                label=f"SDK Device Proof {suffix}",
                source=HtmlSource(html=_proof_html()),
            )
        )
        temporary_screen_id = screen.id

        failure_stage = "playlist.attach"
        client.playlists.update(
            playlist.id,
            PlaylistPatch(
                name=playlist.name,
                label=playlist.label,
                screen_ids=[screen.id],
            ),
        )
        failure_stage = "playlist.verify"
        attached_playlist = client.playlists.get(playlist.id)
        if [item.screen_id for item in attached_playlist.items] != [screen.id]:
            raise DeviceSmokeFailure

        failure_stage = "device.assign"
        assigned = client.devices.update(
            device_id,
            DevicePatch(playlist_id=playlist.id),
        )
        if assigned.playlist_id != playlist.id:
            raise DeviceSmokeFailure
        failure_stage = "device.verify"
        assigned_readback = client.devices.get(device_id)
        if assigned_readback.playlist_id != playlist.id:
            raise DeviceSmokeFailure

        failure_stage = "operator.confirmation"
        print(
            "Temporary display assigned. Wake the device, then type seen:",
            flush=True,
        )
        if not _wait_for_acknowledgment(timeout_seconds=input_timeout_seconds):
            raise DeviceSmokeFailure
    except BaseException as error:
        failure = (failure_stage, error)
    finally:
        if client is not None:
            restoration_verified = False
            if original_playlist_id is not None:
                try:
                    client.devices.update(
                        device_id,
                        DevicePatch(playlist_id=original_playlist_id),
                    )
                    restored = client.devices.get(device_id)
                    if restored.playlist_id != original_playlist_id:
                        raise DeviceSmokeFailure
                except BaseException as error:
                    recovery_failures.append(("device.restore", error))
                else:
                    restoration_verified = True

            if restoration_verified:
                if temporary_playlist_id is not None:
                    try:
                        client.playlists.delete(temporary_playlist_id)
                    except BaseException as error:
                        recovery_failures.append(("playlist.cleanup", error))
                if temporary_screen_id is not None:
                    try:
                        client.screens.delete(temporary_screen_id)
                    except BaseException as error:
                        recovery_failures.append(("screen.cleanup", error))

            try:
                client.close()
            except BaseException as error:
                recovery_failures.append(("client.close", error))

    if failure is not None:
        print(_safe_failure(failure[1], failure[0]), file=sys.stderr)
    for stage, error in recovery_failures:
        print(_safe_failure(error, stage), file=sys.stderr)
    if failure is not None or recovery_failures:
        return 1

    print("PASS: physical display observed and original assignment restored")
    return 0


def _acknowledged(value: str) -> bool:
    return value.strip().casefold() == "seen"


def _wait_for_acknowledgment(
    *,
    timeout_seconds: float = ACKNOWLEDGMENT_TIMEOUT_SECONDS,
    read_line: Callable[[float], str | None] | None = None,
) -> bool:
    reader = read_line or _read_line_with_timeout
    acknowledgment = reader(timeout_seconds)
    return acknowledgment is not None and _acknowledged(acknowledgment)


def _read_line_with_timeout(timeout_seconds: float) -> str | None:
    readable, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
    if not readable:
        return None
    return sys.stdin.readline()


def _proof_html() -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{height:100%;margin:0;background:#fff;color:#000}"
        "body{display:flex;align-items:center;justify-content:center;"
        "font-family:Arial,sans-serif;text-align:center}"
        "h1{border:12px solid #000;padding:36px;font-size:64px}</style>"
        "</head><body><h1>SDK DEVICE PROOF</h1></body></html>"
    )


def _safe_failure(error: BaseException, stage: str) -> str:
    if isinstance(error, TerminusResponseError):
        return f"Device proof failed at {stage}: {type(error).__name__} status={error.status_code}"
    return f"Device proof failed at {stage}: {type(error).__name__}"


if __name__ == "__main__":
    raise SystemExit(main())
