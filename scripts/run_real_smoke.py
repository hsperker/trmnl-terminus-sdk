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
    cleanup_failures: list[str] = []

    try:
        suffix = secrets.token_hex(6)
        models = client.models.list()
        if not models:
            raise SmokeFailure("Terminus has no usable model")

        playlist = client.playlists.create(
            PlaylistCreate(
                name=f"sdk_smoke_{suffix}",
                label=f"SDK Smoke {suffix}",
            )
        )
        playlist_ids.append(playlist.id)

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

        fetched = client.screens.get(screen.id)
        if fetched.id != screen.id:
            raise SmokeFailure("screen show returned the wrong resource")

        with tempfile.TemporaryDirectory(prefix="terminus-sdk-smoke-") as directory:
            destination = Path(directory) / "rendered-image"
            client.screens.download(fetched, destination)
            if not destination.read_bytes():
                raise SmokeFailure("rendered image was empty")

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
        fetched_playlist = client.playlists.get(playlist.id)
        if [item.screen_id for item in fetched_playlist.items] != [screen.id]:
            raise SmokeFailure("playlist read did not preserve screen order")

        _prove_refresh_when_requested(client, store)
        if store.current is None:
            raise SmokeFailure("login did not publish a token pair to TokenStore")

        saves_before_recovery = store.saves
        rotated_out_of_band = client.request(
            "POST",
            "/api/jwt",
            json={"refresh_token": store.current.refresh_token.get_secret_value()},
        )
        if not rotated_out_of_band.is_success:
            raise SmokeFailure("could not prepare stale-token recovery proof")
        recovery_name = f"sdk_recovery_{suffix}"
        recovered = client.playlists.create(
            PlaylistCreate(name=recovery_name, label=f"SDK Recovery {suffix}")
        )
        playlist_ids.append(recovered.id)
        if store.saves <= saves_before_recovery:
            raise SmokeFailure("the server accepted a stale token; 401 recovery was not exercised")
        matches = [item for item in client.playlists.list() if item.name == recovery_name]
        if [item.id for item in matches] != [recovered.id]:
            raise SmokeFailure("rejected-auth POST did not create exactly one resource")
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
        print(_safe_failure(failure), file=sys.stderr)
    if cleanup_failures:
        print(f"Cleanup failed: {', '.join(cleanup_failures)}", file=sys.stderr)
    if failure is not None or cleanup_failures:
        return 1

    print("PASS: real screen, image, playlist, auth recovery, and cleanup")
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


def _safe_failure(error: BaseException) -> str:
    if isinstance(error, TerminusResponseError):
        return f"Smoke failed: {type(error).__name__} status={error.status_code}"
    return f"Smoke failed: {type(error).__name__}"


if __name__ == "__main__":
    raise SystemExit(main())
