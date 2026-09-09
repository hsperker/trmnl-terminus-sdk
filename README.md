# TRMNL Terminus Python SDK

`trmnl-terminus` is a small, synchronous Python client for automating a
self-hosted [Terminus](https://github.com/usetrmnl/terminus) server. It handles
authentication and token rotation, validates requests and responses, and keeps
the underlying HTTP contract visible.

> **Release status:** `0.1.0` is ready for its first PyPI release but has not
> been published yet. Install from a source checkout until that release lands.

## Compatibility

SDK `0.1.x` supports exactly Terminus tag `0.71.0`, commit
[`e0cf90d8ef6d7bc16dfbac8ebab910a9fda9de56`](https://github.com/usetrmnl/terminus/commit/e0cf90d8ef6d7bc16dfbac8ebab910a9fda9de56).
It makes no compatibility claim for Terminus `main`, older releases, or later
releases.

Python 3.12 or newer is required.

## Install

After the first PyPI release, add the SDK to an uv project:

```sh
uv add trmnl-terminus
```

Or install it with pip:

```sh
python -m pip install trmnl-terminus
```

For now, clone this repository and create its locked environment:

```sh
git clone https://github.com/hsperker/trmnl-terminus-sdk.git
cd trmnl-terminus-sdk
uv sync --locked
```

## Quick start

Terminus authenticates with an email address and password. Keep both outside
your source code:

```sh
export TERMINUS_BASE_URL="https://terminus.example.test"
export TERMINUS_EMAIL="you@example.test"
export TERMINUS_PASSWORD="..."
```

Then inspect your devices without changing the server:

```python
import os

from pydantic import SecretStr

from trmnl_terminus import Credentials, TerminusClient

credentials = Credentials(
    email=os.environ["TERMINUS_EMAIL"],
    password=SecretStr(os.environ["TERMINUS_PASSWORD"]),
)

with TerminusClient(
    os.environ["TERMINUS_BASE_URL"],
    credentials=credentials,
) as client:
    for device in client.devices.list():
        print(device.id, device.label, device.playlist_id)
```

The client logs in on demand. It rotates access and refresh tokens when needed
and never writes them to disk unless you supply a `TokenStore`.

## Examples

The repository includes two runnable examples:

| Example | What it proves | Server changes |
| --- | --- | --- |
| [`examples/list_resources.py`](https://github.com/hsperker/trmnl-terminus-sdk/blob/main/examples/list_resources.py) | Lists models, devices, screens, and playlists | None |
| [`examples/render_screen.py`](https://github.com/hsperker/trmnl-terminus-sdk/blob/main/examples/render_screen.py) | Creates an HTML screen, downloads its rendered image, then deletes the screen | Temporary screen |

Run the read-only example after setting the three variables above:

```sh
uv run python examples/list_resources.py
```

Rendering requires an explicit mutation opt-in. Remote-screen deletion runs in
a `finally` block, so cleanup is attempted even when the image download fails:

```sh
TERMINUS_ALLOW_MUTATIONS=1 \
  uv run python examples/render_screen.py rendered-screen.png
```

To prove the full path on real hardware, use the guarded
[`physical-device proof workflow`](https://github.com/hsperker/trmnl-terminus-sdk/blob/main/scripts/run_device_smoke.py).
It creates a temporary playlist and screen, assigns them to an existing device,
waits for visual confirmation, restores the original playlist, and cleans up.
Read the
[`real-server smoke guide`](https://github.com/hsperker/trmnl-terminus-sdk/blob/main/docs/real-server-smoke.md)
before running it.

Playlist assignment does not wake a device. The new image appears on its next
scheduled poll, power cycle, or manual refresh.

## Supported API

| Resource | Operations in `0.1` |
| --- | --- |
| `client.models` | `list()` |
| `client.devices` | `list()`, `get(id)`, `update(id, DevicePatch(...))` |
| `client.screens` | `list()`, `create(...)`, `delete(id)`, `read_bytes(...)`, `download(...)` |
| `client.playlists` | `list()`, `get(id)`, `create(...)`, `update(...)`, `delete(id)` |
| `client.request(...)` | Raw escape hatch for unsupported Server API endpoints |

Device updates deliberately support playlist assignment only. Terminus
`0.71.0` also lacks a native screen lookup endpoint, so the SDK does not fake
one by fetching every screen. The
[SDK specification](https://github.com/hsperker/trmnl-terminus-sdk/blob/main/docs/specs/terminus-sdk.md)
defines the complete boundary and wire contract.

## Errors and secrets

HTTP failures raise typed `TerminusError` subclasses. Server responses that use
RFC Problem Details are available as structured `ProblemDetails` on response
errors. The original `httpx.Response` remains available for debugging, but
exception strings do not include credentials, tokens, request bodies, or
response bodies.

TLS certificate verification is enabled by default. For a private certificate
authority, pass an `ssl.SSLContext`; the examples never disable verification.

## Development

uv owns the development environment and lockfile:

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src examples
uv build --no-sources
```

The test suite uses mocked HTTP boundaries. Live server and physical-device
checks are separate, guarded workflows because they create and delete real
resources.

Maintainers should follow the
[`release checklist`](https://github.com/hsperker/trmnl-terminus-sdk/blob/main/docs/releasing.md);
publishing uses a GitHub environment and PyPI Trusted Publishing instead of a
stored API token.

## License

MIT. See
[`LICENSE`](https://github.com/hsperker/trmnl-terminus-sdk/blob/main/LICENSE).
