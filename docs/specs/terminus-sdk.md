# TRMNL Terminus Python SDK

## Goal

Build a small, strongly typed Python SDK for the current Terminus Server API.

The SDK must make common operations easy and predictable while remaining faithful to the actual Terminus HTTP API.

It must not invent remote resources or capabilities that Terminus does not expose.

Working distribution name: `trmnl-terminus`  
Python import package: `trmnl_terminus`

## Target

- Python >= 3.12
- `httpx`
- Pydantic >= 2
- `pytest`
- `respx` for HTTP tests
- `ruff`
- `mypy`

Keep dependencies small.

## Authoritative sources

Use the current `main` branch of `usetrmnl/terminus`.

Implementation behavior wins over documentation when they disagree.

Primary source files:

- `doc/api.adoc`
- `config/routes.rb`
- `app/actions/api/**`
- `app/contracts/**`
- `app/schemas/**`
- `app/serializers/**`
- `app/aspects/screens/**`
- `app/aspects/devices/**`

Do not infer endpoints from the Web UI routes.

## Scope

Implement:

- Authentication
- Devices
- Models
- Screens
- Playlists
- Raw authenticated HTTP escape hatch

Explicitly defer:

- Firmware CRUD
- Firmware device protocol (`/api/setup`, `/api/display`, `/api/log`)
- Extensions
- Designs
- Marketplace/private plugins
- TRMNL cloud webhook API
- Palette API
- Template authoring framework

These can be added later without changing the core abstractions.

---

# Design principles

1. Every remote resource maps to a real Terminus Server API resource.
2. Higher-level conveniences may compose multiple real API calls.
3. Domain objects do not silently perform network I/O.
4. Make invalid combinations difficult to express.
5. Preserve unknown response fields for forward compatibility.
6. Do not automatically retry mutating HTTP requests.
7. Preserve the original HTTP/problem response on errors.
8. Authentication and token refresh should normally be transparent.
9. Provide a raw authenticated HTTP escape hatch.
10. Never claim Terminus supports an endpoint merely because its docs mention it.
11. The SDK should expose Terminus semantics, not merely mirror JSON payloads.
12. Higher-level abstractions must be traceable to real Terminus API behavior.

---

# HTTP contract

## Authentication

### Login

`POST /login`

Request:

```json
{
  "login": "<email>",
  "password": "<password>"
}
```

Response:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "success": "..."
}
```

### Refresh

`POST /api/jwt`

Header:

```text
Authorization: <access_token>
```

Body:

```json
{
  "refresh_token": "<refresh-token>"
}
```

Response contains a new access token **and** a new refresh token.

The new refresh token replaces the previous refresh token.

Do **not** send:

```text
Authorization: Bearer <token>
```

Terminus expects the raw token in the `Authorization` header.

Default access-token lifetime is approximately 30 minutes.  
Refresh tokens are documented as valid for 14 days.

### Authentication precedence

For an authenticated request, the SDK should use this precedence:

1. Use an existing access token if it is still sufficiently valid.
2. Otherwise refresh using the current refresh token.
3. Otherwise, if credentials are configured, log in again.
4. Otherwise raise `TerminusAuthenticationError`.

### Proactive refresh

When tokens are configured, inspect the JWT access token's `exp` claim locally.

The SDK does not need to verify the JWT signature for this purpose; it is only using the claim as a local scheduling hint.

Before an authenticated request:

- if the access token is expired, refresh first;
- if the access token is within a small refresh window of expiration, refresh first;
- otherwise use the existing access token.

Use a small default refresh skew such as 60 seconds.

Successful refresh:

- replaces the access token;
- replaces the refresh token;
- calls the configured `TokenStore`, if any, with the new pair.

A `401` response may trigger one authentication recovery attempt, but 401-driven refresh is a fallback rather than the primary refresh mechanism.

Never retry authentication indefinitely.

### Token-only startup limitation

A client initialized only with `TokenPair` is not a durable credential mechanism.

If it remains unused beyond the refresh token's validity period, it may no longer be able to authenticate.

Long-lived automations should additionally provide `Credentials`, unless Terminus gains a dedicated long-lived service/API-key mechanism.

No background refresh thread or timer is required. Refresh happens lazily when the SDK is next used.

---

# Client

Expose:

```python
TerminusClient(
    base_url: str,
    *,
    credentials: Credentials | None = None,
    tokens: TokenPair | None = None,
    token_store: TokenStore | None = None,
    timeout: httpx.Timeout | None = None,
    verify: bool | str | SSLContext = True,
    refresh_skew_seconds: int = 60,
)
```

Requirements:

- Normalize base URL by removing trailing `/`.
- HTTPS certificate verification enabled by default.
- Lazy authentication is acceptable.
- Support startup with credentials, tokens, or both.
- Existing tokens are preferred when usable.
- Before authenticated requests, proactively refresh access tokens that are expired or near expiry.
- Successful refresh replaces both access and refresh tokens.
- Persist newly rotated tokens through `TokenStore`, if configured.
- If refresh fails or the refresh token is no longer usable and credentials are configured, transparently re-authenticate once.
- A `401` may trigger one recovery attempt.
- Retry the original request at most once after successful auth recovery.
- Never endlessly retry.
- Never include passwords/access tokens/refresh tokens in repr/log output.
- Do not implement built-in plaintext credential/token persistence.
- Domain objects must not make implicit HTTP calls.

Expose resource managers:

```python
client.devices
client.models
client.screens
client.playlists
client.raw
```

Also expose:

```python
client.resolve_uri(relative_or_absolute_uri: str) -> str
```

for resolving returned Terminus URIs against the configured base URL.

---

# Authentication value objects

## Credentials

```python
Credentials(
    email: str,
    password: SecretStr,
)
```

Requirements:

- password is secret/redacted in repr;
- credentials are durable fallback credentials;
- credentials are never written to disk by the SDK.

## TokenPair

```python
TokenPair(
    access_token: SecretStr,
    refresh_token: SecretStr,
)
```

Requirements:

- both tokens are secret/redacted in repr;
- the SDK replaces the full pair after refresh;
- callers should never assume the refresh token is stable.

## TokenStore protocol

Define a minimal persistence hook:

```python
class TokenStore(Protocol):
    def save(self, tokens: TokenPair) -> None: ...
```

The SDK calls `save()` after:

- successful login;
- successful refresh.

The SDK should not prescribe the storage backend.

Examples may show callers implementing storage via:

- keyring;
- encrypted application storage;
- secrets manager;
- NAS secret store.

Do not provide plaintext file storage as the default example.

---

# Domain models

All models should preserve unknown response properties, e.g. Pydantic `extra="allow"`.

## Device

Represent every currently serialized Terminus Device field, including:

- `id`
- `model_id`
- `playlist_id`
- `label`
- `mac_address`
- `api_key`
- `firmware_profile`
- `firmware_update`
- `firmware_reset`
- `firmware_version`
- `wifi_band`
- `wifi_signal`
- `battery_charge`
- `battery_voltage`
- `charging`
- `refresh_rate`
- `image_cached`
- `image_timeout`
- `wake_reason`
- `wake_duration`
- `width`
- `height`
- `display_compatibility`
- `display_profile`
- `command`
- `touch_bar`
- `sleep_start_at`
- `sleep_stop_at`
- `synced_at`
- `created_at`
- `updated_at`

`api_key` must be represented as a secret value and omitted/redacted from repr.

Provide **pure** computed projections:

```python
device.status -> DeviceStatus
device.settings -> DeviceSettings
```

These perform no HTTP requests.

`DeviceStatus` should contain observational/runtime information such as:

- `firmware_version`
- `wifi_band`
- `wifi_signal`
- `battery_charge`
- `battery_voltage`
- `charging`
- `image_cached`
- `wake_reason`
- `wake_duration`
- `width`
- `height`
- `synced_at`

`DeviceSettings` should expose server-controlled configuration such as:

- `model_id`
- `playlist_id`
- `label`
- `refresh_rate`
- `image_timeout`
- `display_compatibility`
- `display_profile`
- `firmware_update`
- `firmware_reset`
- `firmware_profile`
- `command`
- `touch_bar`
- `sleep_start_at`
- `sleep_stop_at`

Keep the complete underlying `Device` available.

## Model

Represent:

- `default_palette_id`
- `id`
- `name`
- `label`
- `description`
- `kind`
- `mime_type`
- `colors`
- `bit_depth`
- `rotation`
- `offset_x`
- `offset_y`
- `scale_factor`
- `css`
- `width`
- `height`
- `created_at`
- `updated_at`

Expose a pure:

```python
model.render_target -> RenderTarget
```

`RenderTarget`:

- `model_id`
- `width`
- `height`
- `mime_type`
- `colors`
- `bit_depth`
- `rotation`
- `offset_x`
- `offset_y`
- `scale_factor`
- `default_palette_id`
- `css`

Do not invent named palette colors. Terminus exposes `default_palette_id` but currently has no Server API for palettes.

`RenderTarget` is not a remote resource. It is a projection of the Terminus `Model`.

## Screen

Represent:

- `id`
- `model_id`
- `label`
- `name`
- `created_at`
- `updated_at`
- `filename`
- `mime_type`
- `bit_depth`
- `width`
- `height`
- `size`
- `uri`

Expose:

```python
screen.rendered -> RenderedImage
```

`RenderedImage` is a value object containing:

- `uri`
- `filename`
- `mime_type`
- `bit_depth`
- `width`
- `height`
- `size`

It is **not** a remote Terminus resource.

Provide pure URL resolution:

```python
client.resolve_uri(screen.rendered.uri)
```

and explicit I/O:

```python
client.screens.download(screen, destination)
client.screens.read_bytes(screen)
```

## PlaylistItem

- `id`
- `screen_id`
- `position`
- `created_at`
- `updated_at`

## Playlist

- `id`
- `name`
- `label`
- `current_item_id`
- `mode`
- `created_at`
- `updated_at`
- `items: list[PlaylistItem]`

Important: `current_item_id` is a **PlaylistItem ID**, not a Screen ID.

---

# Screen source model

Do **not** expose `content`, `uri`, and `preprocessed` as three unrelated nullable parameters.

Define mutually exclusive source variants:

```python
HtmlSource(html: str)

ImageSource(uri: str)

PreprocessedImageSource(uri: str)
```

and:

```python
ScreenProcessing.DITHER
```

Create signature:

```python
client.screens.create(
    *,
    model_id: int,
    name: str,
    label: str,
    source: ScreenSource,
    playlist_id: int | None = None,
    processing: ScreenProcessing | None = None,
) -> Screen
```

Serialization:

### `HtmlSource`

```text
content = html
```

### `ImageSource`

```text
uri = uri
preprocessed omitted
```

### `PreprocessedImageSource`

```text
uri = uri
preprocessed = true
```

Exactly one source must be supplied by construction.

Do not expose `file_name` in v0.1 because the current API action contract does not accept it even though `doc/api.adoc` mentions it.

HTML must be sent as provided.

Do **not** sanitize it client-side.

Terminus currently sanitizes HTML before rendering using its own sanitizer. The SDK should not attempt to duplicate Terminus's changing sanitizer policy.

Document that sanitized HTML can still contain JavaScript/styles/external resources and should therefore not be treated as a security sandbox.

The SDK should treat Terminus as the rendering authority.

---

# Resource APIs

## Devices

Native API:

```text
GET    /api/devices
GET    /api/devices/:id
POST   /api/devices
PATCH  /api/devices/:id
DELETE /api/devices/:id
```

Expose:

```python
devices.list() -> list[Device]
devices.get(id) -> Device
devices.create(request: DeviceCreate) -> Device
devices.update(id, request: DevicePatch) -> Device
devices.delete(id) -> Device | None
```

`DeviceCreate` must require:

```python
model_id: int
playlist_id: int | None
```

`DevicePatch` must mirror the fields currently accepted by the Terminus Patch schema.

Important:

- Creating a device permits `playlist_id=None`.
- The current PATCH schema does **not** permit `playlist_id=None`.
- Do not fake support for detaching a playlist.

Do not duplicate Terminus's generated defaults such as default MAC address, refresh rate, etc. Omit optional fields and allow Terminus to choose them.

## Models

Native API:

```text
GET    /api/models
GET    /api/models/:id
POST   /api/models
PATCH  /api/models/:id
DELETE /api/models/:id
```

The API documentation currently contains a `PUT` example for update, but the actual route is `PATCH`. Use `PATCH`.

Expose:

```python
models.list()
models.get(id)
models.create(...)
models.update(id, ...)
models.delete(id)
```

Model create requires:

- `name`
- `label`

`kind` is server-assigned for Terminus-created models and should not be a create parameter.

## Screens

Native API actually implemented:

```text
GET    /api/screens
POST   /api/screens
PATCH  /api/screens/:id
DELETE /api/screens/:id
```

There is currently **no** `GET /api/screens/:id` route despite it being documented.

Expose:

```python
screens.list() -> list[Screen]
screens.get(id) -> Screen
```

Implement `screens.get(id)` as a transparent composition:

1. `GET /api/screens`
2. find matching `id`
3. raise `TerminusNotFoundError` if absent

Do **not** send `GET /api/screens/:id`.

Also expose:

```python
screens.create(...)
screens.update(id, ...)
screens.delete(id)
screens.download(...)
screens.read_bytes(...)
```

Create must reject locally:

- missing source
- multiple source kinds
- empty name/label
- invalid model ID <= 0

Terminus enforces uniqueness of `(model_id, name)` when creating screens. Map its RFC problem response into `TerminusValidationError`.

`processing=ScreenProcessing.DITHER` serializes:

```text
mode="dither"
```

Do not invent other processing modes.

## Playlists

Native API:

```text
GET    /api/playlists
GET    /api/playlists/:id
POST   /api/playlists
PATCH  /api/playlists/:id
DELETE /api/playlists/:id
```

Expose:

```python
playlists.list()
playlists.get(id)
playlists.create(name, label, *, mode=None, screen_ids=None)
playlists.update(...)
playlists.replace_screens(id, screen_ids)
playlists.clear(id)
playlists.delete(id)
```

Request item ordering determines server-side `PlaylistItem.position`.

The current PATCH action unexpectedly requires both `name` and `label`.

Therefore public `playlists.update()` should provide proper partial semantics:

1. `GET` current playlist.
2. Merge supplied `name`/`label` with current values.
3. `PATCH` the resulting payload.

If `items` is not supplied, omit it and preserve existing items.

If `items=[]`, Terminus deletes all playlist items.

If items are supplied, Terminus replaces/recreates the playlist's items.

Make this two-request behavior explicit in documentation.

Do not automatically retry the PATCH.

---

# Error model

Base:

```python
TerminusError
```

Subclasses:

```python
TerminusAuthenticationError
TerminusNotFoundError
TerminusValidationError
TerminusConflictError
TerminusTransportError
TerminusUnexpectedResponseError
```

Represent RFC API Problem responses with:

```python
ProblemDetails(
    type: str | None,
    status: int | None,
    title: str | None,
    detail: str | None,
    instance: str | None,
    extensions: dict[str, Any],
)
```

Validation errors should expose server-side `errors` if present.

Every exception arising from an HTTP response should preserve:

- status code;
- `ProblemDetails`, if parseable;
- request method/path;
- original `httpx.Response`.

Do not reduce errors to strings.

Authentication-specific errors should distinguish at least:

- no usable credentials/tokens available;
- refresh failed and no credentials fallback exists;
- login failed;
- repeated authentication failure after one recovery attempt.

---

# Forward compatibility

The Terminus Server API is explicitly evolving.

Requirements:

- tolerate unknown JSON response fields;
- preserve unknown fields on models;
- do not reject unknown enum/string values received **from** the server;
- only constrain values we **send** when the current Terminus API has a real invariant;
- provide `client.raw.request()` for new endpoints/fields.

Example:

```python
client.raw.request(
    "GET",
    "/api/something-added-later",
)
```

Raw requests should still participate in normal authentication unless `authenticated=False` is explicitly requested.

---

# Render/download behavior

A `Screen` response includes the actual rendered image metadata and a URI.

Do not render HTML locally.

Terminus is the rendering authority.

Construct rendered image URLs by resolving returned `uri` against `base_url`.

The Terminus router exposes `/uploads` as static files.

HTML rendering can take materially longer than ordinary API calls because Terminus invokes Chromium and waits for page/network rendering.

Use sensible HTTP timeouts, for example:

```text
connect: 5 seconds
read:    60 seconds
write:   30 seconds
pool:    5 seconds
```

Do not impose a short 10-second timeout on screen rendering requests.

Downloading a rendered image should be explicit I/O:

```python
data = client.screens.read_bytes(screen)
client.screens.download(screen, "preview.png")
```

The SDK should not automatically download images merely because a `Screen` was fetched.

---

# HTML and rendering security model

Terminus sanitizes incoming HTML before rendering, but intentionally permits rich rendering capabilities including HTML, CSS, JavaScript, SVG, and external resources.

Therefore:

- do not implement a second sanitizer in the SDK;
- do not claim Terminus's sanitizer makes arbitrary hostile HTML safe;
- do not silently escape entire trusted HTML templates;
- application code should escape untrusted data before interpolating it into trusted HTML;
- externally referenced resources must be reachable from the Terminus rendering environment;
- HTML rendering should be considered executable/trusted rendering input.

The SDK may later add higher-level safe-template helpers, but those are explicitly deferred from v0.1.

---

# Security requirements

- TLS verification enabled by default.
- Support custom CA verification through the underlying `httpx` configuration.
- Passwords and tokens use secret/redacted representations.
- Device API keys use secret/redacted representations.
- Never log `Authorization` headers.
- Never log login request bodies.
- Do not add `verify=False` examples to documentation.
- Do not implement client-side HTML sanitization and imply it is equivalent to Terminus's rendering policy.
- Document that Terminus sanitizes HTML but intentionally permits rich HTML/CSS/JS capabilities.
- Do not persist credentials or tokens unless the caller explicitly supplies a `TokenStore`.
- Successful refresh must persist the newly rotated refresh token through `TokenStore`, if configured.

---

# Network semantics

Domain/value objects perform no implicit requests.

Calls that perform I/O are reachable through:

```python
client.devices.*
client.models.*
client.screens.*
client.playlists.*
client.raw.*
```

A property such as:

```python
screen.rendered
```

is pure.

A method such as:

```python
client.screens.download(screen)
```

clearly performs I/O.

A property such as:

```python
model.render_target
```

must be pure and locally derived.

---

# Initial package structure

```text
src/trmnl_terminus/
    __init__.py
    client.py
    auth.py
    transport.py
    errors.py
    problem.py
    uri.py

    domain/
        device.py
        model.py
        screen.py
        playlist.py

    resources/
        devices.py
        models.py
        screens.py
        playlists.py

tests/
    unit/
        test_auth.py
        test_transport.py
        test_devices.py
        test_models.py
        test_screens.py
        test_playlists.py
        test_errors.py
        test_uri.py

    integration/
        test_read_only.py

pyproject.toml
README.md
```

Keep files focused and reasonably small.

---

# Required contract tests

Tests must lock down these known Terminus behaviors:

1. `Authorization` header is raw JWT, not `Bearer`.
2. Login stores both access and refresh tokens.
3. Refresh replaces **both** access and refresh tokens.
4. Rotated tokens are persisted via `TokenStore`.
5. A sufficiently valid access token is reused without refresh.
6. An expired access token is proactively refreshed before the request.
7. A near-expiry access token is proactively refreshed before the request.
8. `401` auth recovery happens at most once.
9. Failed refresh falls back to credentials when configured.
10. Failed refresh without credentials raises `TerminusAuthenticationError`.
11. Token-only startup works while the refresh token remains usable.
12. No background refresh thread/timer is created.
13. Models update with `PATCH`, not `PUT`.
14. `screens.get(id)` does not call `/api/screens/:id`.
15. `HtmlSource` produces `content`.
16. `ImageSource` produces `uri` without `preprocessed=true`.
17. `PreprocessedImageSource` produces `uri` + `preprocessed=true`.
18. Multiple screen source types cannot be represented.
19. Dither maps to `mode="dither"`.
20. Screen response exposes rendered image metadata and URI.
21. Rendered image URL resolves correctly against base URL.
22. Playlist item order is preserved.
23. `playlists.update(label=...)` first reads the existing playlist, then PATCHes with both required `name` and `label`.
24. `items=None` preserves items.
25. `items=[]` sends an empty array and clears items.
26. Device create accepts `playlist_id=None`.
27. Device patch does not permit `playlist_id=None`.
28. Unknown response fields survive decoding.
29. RFC problem errors remain inspectable on SDK exceptions.
30. Secrets are absent/redacted from repr.
31. Login request bodies are not logged.
32. Authorization headers are not logged.

---

# Optional integration test

Provide an integration test skipped by default unless:

```text
TERMINUS_BASE_URL
TERMINUS_EMAIL
TERMINUS_PASSWORD
```

are set.

Read-only integration test:

- login;
- list devices;
- list models;
- list playlists;
- list screens;
- resolve each returned `device.model_id` through `models.get()`.

No mutation in default integration tests.

Mutation tests must require a second explicit flag such as:

```text
TERMINUS_ALLOW_MUTATION_TESTS=1
```

and must create/delete their own uniquely named resources.

---

# README first-use example

The README should demonstrate approximately:

```python
import os

from trmnl_terminus import Credentials, HtmlSource, TerminusClient


client = TerminusClient(
    "https://terminus.example.test",
    credentials=Credentials(
        email=os.environ["TERMINUS_EMAIL"],
        password=os.environ["TERMINUS_PASSWORD"],
    ),
)

device = client.devices.list()[0]
model = client.models.get(device.model_id)

screen = client.screens.create(
    model_id=model.id,
    name="morning-message",
    label="Morning Message",
    source=HtmlSource(
        """
        <style>
          * { margin: 0; }
        </style>
        <h1>Good morning</h1>
        <p>Build the experiment before improving the plan.</p>
        """
    ),
)

client.screens.download(screen, "morning-preview.png")

playlist = client.playlists.get(device.playlist_id)

client.playlists.replace_screens(
    playlist.id,
    [screen.id],
)
```

The README must explain that this changes Terminus state.

The physical TRMNL updates only on its next `/api/display` poll/wake cycle.

## README token-startup example

Also demonstrate that an automation may start from an existing token pair:

```python
client = TerminusClient(
    "https://terminus.example.test",
    tokens=TokenPair(
        access_token=os.environ["TERMINUS_ACCESS_TOKEN"],
        refresh_token=os.environ["TERMINUS_REFRESH_TOKEN"],
    ),
    token_store=my_token_store,
)
```

Document:

- token refresh is transparent;
- both tokens rotate;
- the rotated pair must be persisted;
- token-only startup is not durable if the client stays unused past refresh-token expiry;
- durable automations should also provide `Credentials` as fallback unless Terminus later provides a dedicated service credential.

---

# Acceptance criteria

The work is complete when:

- all unit tests pass;
- `mypy` passes;
- `ruff` passes;
- public API is documented;
- no undocumented/native Terminus endpoint has been invented;
- all known documentation-vs-code discrepancies above are covered by tests;
- an HTML screen can be created and its Terminus-rendered image downloaded;
- a screen can be placed in a playlist;
- a device's Model can be resolved into a `RenderTarget`;
- token refresh is transparent and proactive on use;
- refresh correctly rotates both tokens;
- rotated tokens can be persisted through `TokenStore`;
- expired refresh credentials can fall back to username/password when configured;
- token-only startup behavior and its durability limitation are documented.
