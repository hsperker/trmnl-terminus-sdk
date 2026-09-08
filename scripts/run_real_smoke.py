from __future__ import annotations

import os
import secrets
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import SecretStr

from trmnl_terminus import (
    Credentials,
    HtmlSource,
    PlaylistCreate,
    PlaylistPatch,
    ScreenCreate,
    TerminusClient,
    TokenPair,
)
from trmnl_terminus.errors import TerminusResponseError

REQUIRED_ENVIRONMENT = (
    "TERMINUS_BASE_URL",
    "TERMINUS_EMAIL",
    "TERMINUS_PASSWORD",
    "TERMINUS_ALLOW_MUTATION_TESTS",
)


class SmokeFailure(RuntimeError):
    pass


@dataclass
class RecordingTokenStore:
    current: TokenPair | None = None
    saves: int = 0

    def save(self, tokens: TokenPair) -> None:
        self.current = tokens.model_copy(deep=True)
        self.saves += 1


def main() -> int:
    missing = [name for name in REQUIRED_ENVIRONMENT if not os.environ.get(name)]
    if missing:
        print(
            f"Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    if os.environ["TERMINUS_ALLOW_MUTATION_TESTS"] != "1":
        print(
            "TERMINUS_ALLOW_MUTATION_TESTS must equal 1; no requests sent",
            file=sys.stderr,
        )
        return 2

    credentials = Credentials(
        email=os.environ["TERMINUS_EMAIL"],
        password=SecretStr(os.environ["TERMINUS_PASSWORD"]),
    )
    store = RecordingTokenStore()
    client = TerminusClient(
        os.environ["TERMINUS_BASE_URL"],
        credentials=credentials,
        token_store=store,
        refresh_skew_seconds=2,
    )
    cleanup_client = client
    playlist_ids: list[int] = []
    screen_ids: list[int] = []
    failure: BaseException | None = None
    failure_stage = "setup"
    cleanup_failures: list[str] = []

    try:
        suffix = secrets.token_hex(6)
        failure_stage = "models.list"
        models = client.models.list()
        if not models:
            raise SmokeFailure("Terminus has no usable model")

        failure_stage = "playlist.create"
        playlist = client.playlists.create(
            PlaylistCreate(
                name=f"sdk_smoke_{suffix}",
                label=f"SDK Smoke {suffix}",
            )
        )
        playlist_ids.append(playlist.id)

        failure_stage = "screen.create"
        screen = client.screens.create(
            ScreenCreate(
                model_id=models[0].id,
                name=f"sdk_smoke_{suffix}",
                label=f"SDK Smoke {suffix}",
                source=HtmlSource(
                    html=(
                        "<style>*{margin:0}body{font-family:sans-serif}</style>"
                        "<h1>Terminus SDK smoke</h1><p>Rendered by Terminus.</p>"
                    )
                ),
            )
        )
        screen_ids.append(screen.id)

        failure_stage = "screen.list-readback"
        matching_screens = [item for item in client.screens.list() if item.id == screen.id]
        if len(matching_screens) != 1:
            raise SmokeFailure("screen list did not return exactly the created resource")
        fetched = matching_screens[0]

        with tempfile.TemporaryDirectory(prefix="terminus-sdk-smoke-") as directory:
            destination = Path(directory) / "rendered-image"
            failure_stage = "screen.download"
            client.screens.download(fetched, destination)
            if not destination.read_bytes():
                raise SmokeFailure("rendered image was empty")

        failure_stage = "playlist.update"
        updated = client.playlists.update(
            playlist.id,
            PlaylistPatch(
                name=playlist.name,
                label=playlist.label,
                screen_ids=[screen.id],
            ),
        )
        if [item.screen_id for item in updated.items] != [screen.id]:
            raise SmokeFailure("playlist update did not preserve screen order")
        failure_stage = "playlist.get"
        fetched_playlist = client.playlists.get(playlist.id)
        if [item.screen_id for item in fetched_playlist.items] != [screen.id]:
            raise SmokeFailure("playlist read did not preserve screen order")

        failure_stage = "auth.refresh"
        _prove_refresh_when_requested(client, store)
    except BaseException as error:
        failure = error
    finally:
        for playlist_id in reversed(playlist_ids):
            try:
                cleanup_client.playlists.delete(playlist_id)
            except BaseException as error:
                cleanup_failures.append(f"playlist {playlist_id}: {type(error).__name__}")
        for screen_id in reversed(screen_ids):
            try:
                cleanup_client.screens.delete(screen_id)
            except BaseException as error:
                cleanup_failures.append(f"screen {screen_id}: {type(error).__name__}")
        client.close()

    if failure is not None:
        print(_safe_failure(failure, failure_stage), file=sys.stderr)
    if cleanup_failures:
        print(f"Cleanup failed: {', '.join(cleanup_failures)}", file=sys.stderr)
    if failure is not None or cleanup_failures:
        return 1

    print("PASS: real screen, image, playlist, and cleanup")
    return 0


def _prove_refresh_when_requested(
    client: TerminusClient,
    store: RecordingTokenStore,
) -> None:
    raw_wait = os.environ.get("TERMINUS_REFRESH_WAIT_SECONDS")
    if raw_wait is None:
        return
    try:
        wait_seconds = float(raw_wait)
    except ValueError as error:
        raise SmokeFailure("TERMINUS_REFRESH_WAIT_SECONDS must be numeric") from error
    if wait_seconds <= 0:
        raise SmokeFailure("TERMINUS_REFRESH_WAIT_SECONDS must be positive")
    before = store.current
    if before is None:
        raise SmokeFailure("no token pair was captured before refresh proof")
    before_access = before.access_token.get_secret_value()
    before_refresh = before.refresh_token.get_secret_value()
    time.sleep(wait_seconds)
    client.models.list()
    after = store.current
    if after is None:
        raise SmokeFailure("no token pair was captured after refresh proof")
    if after.access_token.get_secret_value() == before_access:
        raise SmokeFailure("access token did not rotate")
    if after.refresh_token.get_secret_value() == before_refresh:
        raise SmokeFailure("refresh token did not rotate")


def _safe_failure(error: BaseException, stage: str) -> str:
    if isinstance(error, TerminusResponseError):
        return f"Smoke failed at {stage}: {type(error).__name__} status={error.status_code}"
    return f"Smoke failed at {stage}: {type(error).__name__}"


if __name__ == "__main__":
    raise SystemExit(main())
