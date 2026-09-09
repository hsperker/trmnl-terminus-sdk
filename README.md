# TRMNL Terminus Python SDK

`trmnl-terminus` is a synchronous Python SDK for a Terminus Server. SDK v0.1
supports exactly Terminus tag `0.71.0` at commit
`e0cf90d8ef6d7bc16dfbac8ebab910a9fda9de56`; it makes no compatibility claim
for Terminus `main`, older releases, or later releases.

Install it with:

```sh
pip install trmnl-terminus
```

## First use

This example mutates Terminus: it creates a playlist and screen, assigns the
playlist to an existing device, then restores that device's original playlist.
Use a server and device you are allowed to change.

Set `TERMINUS_BASE_URL`, `TERMINUS_EMAIL`, `TERMINUS_PASSWORD`, and
`TERMINUS_DEVICE_ID` in your environment. The base URL must be the server
origin, such as `https://terminus.example.test`; TLS verification stays enabled.

```python
import os
from pathlib import Path

from pydantic import SecretStr

from trmnl_terminus import (
    Credentials,
    DevicePatch,
    HtmlSource,
    Playlist,
    PlaylistCreate,
    PlaylistPatch,
    Screen,
    ScreenCreate,
    TerminusClient,
)

credentials = Credentials(
    email=os.environ["TERMINUS_EMAIL"],
    password=SecretStr(os.environ["TERMINUS_PASSWORD"]),
)
device_id = int(os.environ["TERMINUS_DEVICE_ID"])
if device_id <= 0:
    raise ValueError("TERMINUS_DEVICE_ID must be positive")

with TerminusClient(os.environ["TERMINUS_BASE_URL"], credentials=credentials) as client:
    device = client.devices.get(device_id)
    original_playlist_id = device.playlist_id
    if not isinstance(original_playlist_id, int) or original_playlist_id <= 0:
        raise RuntimeError(
            "Device has no positive original playlist assignment; refusing to mutate it"
        )

    models = client.models.list()
    if not models:
        raise RuntimeError("Terminus has no models; cannot create a screen")

    model = next((item for item in models if item.id == device.model_id), None)
    if model is None:
        raise RuntimeError("Terminus has no model compatible with the configured device")

    playlist: Playlist | None = None
    screen: Screen | None = None
    device_assignment_started = False
    restored = False
    try:
        playlist = client.playlists.create(PlaylistCreate(name="sdk-example", label="SDK example"))
        screen = client.screens.create(
            ScreenCreate(
                model_id=model.id,
                name="sdk-example-screen",
                label="SDK example screen",
                source=HtmlSource(html="<h1>SDK example</h1>"),
            )
        )
        client.playlists.update(
            playlist.id,
            PlaylistPatch(
                name=playlist.name,
                label=playlist.label,
                screen_ids=[screen.id],
            ),
        )
        client.screens.download(screen, Path("sdk-example.png"))

        device_assignment_started = True
        client.devices.update(device.id, DevicePatch(playlist_id=playlist.id))
        assigned_device = client.devices.get(device.id)
        if assigned_device.playlist_id != playlist.id:
            raise RuntimeError("Terminus did not assign the temporary playlist")
        input("Wake or manually refresh the device, then press Enter after it shows SDK example: ")
    finally:
        if device_assignment_started:
            client.devices.update(device.id, DevicePatch(playlist_id=original_playlist_id))
            restored_device = client.devices.get(device.id)
            if restored_device.playlist_id != original_playlist_id:
                raise RuntimeError("Terminus did not restore the original playlist assignment")
            restored = True

        if not device_assignment_started or restored:
            try:
                if screen is not None:
                    client.screens.delete(screen.id)
            finally:
                if playlist is not None:
                    client.playlists.delete(playlist.id)
```

Playlist assignment does not wake a physical device. It takes effect on the
device's next scheduled poll, power cycle, or manual refresh. If restoration
fails, the example deliberately leaves the temporary playlist and screen in
place so the device can be recovered without losing its assigned content.

Credentials and token pairs are caller-owned secrets. Keep them out of source
control and logs; if you persist rotated tokens, use a caller-owned `TokenStore`.

See the [full SDK specification](docs/specs/terminus-sdk.md) and the
[real-server smoke and device-proof guide](docs/real-server-smoke.md) for the
complete contract and live verification procedure.
