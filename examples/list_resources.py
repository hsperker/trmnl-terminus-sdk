from __future__ import annotations

import os
import sys

from pydantic import SecretStr

from trmnl_terminus import Credentials, TerminusClient

REQUIRED_ENVIRONMENT = (
    "TERMINUS_BASE_URL",
    "TERMINUS_EMAIL",
    "TERMINUS_PASSWORD",
)


def main() -> int:
    missing = [name for name in REQUIRED_ENVIRONMENT if not os.environ.get(name)]
    if missing:
        print(
            f"Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    credentials = Credentials(
        email=os.environ["TERMINUS_EMAIL"],
        password=SecretStr(os.environ["TERMINUS_PASSWORD"]),
    )
    with TerminusClient(
        os.environ["TERMINUS_BASE_URL"],
        credentials=credentials,
    ) as client:
        models = client.models.list()
        devices = client.devices.list()
        screens = client.screens.list()
        playlists = client.playlists.list()

    print(f"Models: {len(models)}")
    for model in models:
        print(f"  {model.id}: {model.label} ({model.width}x{model.height})")

    print(f"Devices: {len(devices)}")
    for device in devices:
        print(f"  {device.id}: {device.label or 'unlabelled'}")

    print(f"Screens: {len(screens)}")
    for screen in screens:
        print(f"  {screen.id}: {screen.label}")

    print(f"Playlists: {len(playlists)}")
    for playlist in playlists:
        print(f"  {playlist.id}: {playlist.label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
