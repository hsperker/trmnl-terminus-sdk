# TRMNL Terminus Python SDK

Status: implementation specification for SDK v0.1.

## Goal

Build a small synchronous Python SDK for automating a Terminus Server.

A user must be able to authenticate, inspect models, create rendered screens and
playlists, assign a playlist to an existing device, and download a rendered
screen without writing HTTP or JSON plumbing. The SDK must remain a thin, typed
representation of the real Terminus API.

Distribution name: `trmnl-terminus`

Python import package: `trmnl_terminus`

## Compatibility contract

SDK v0.1 supports this exact upstream release:

```text
repository: https://github.com/usetrmnl/terminus
tag:        0.71.0
commit:     e0cf90d8ef6d7bc16dfbac8ebab910a9fda9de56
```

Pinning both values gives users a recognizable release and gives tests an
immutable source revision. Terminus `main` later added `GET /api/screens/:id`,
but tag `0.71.0` does not contain that route. SDK v0.1 therefore exposes the
native screen list, create, and delete operations only. Do not synthesize
`screens.get()` by listing every screen, and do not claim support for an
unreleased commit merely to expose that convenience method.

The SDK makes no blanket claim of compatibility with Terminus `main`, older
tags, or later tags.

Before changing the SDK's native resource behavior:

1. inspect the supported tag's routes, API actions, schemas, and serializers;
2. update the supported tag and resolved commit deliberately;
3. update contract fixtures and the real-server smoke test in the same change.

Implementation behavior wins over upstream documentation when they disagree.
Unknown response fields are preserved, but that only covers additive response
changes. It does not make renamed fields, changed routes, or new request
requirements compatible.

Authoritative files at the supported release tag:

- `doc/api.adoc`
- `config/routes.rb`
- `app/actions/api/**`
- `app/contracts/**`
- `app/schemas/**`
- `app/serializers/**`
- `app/aspects/screens/**`
- `app/aspects/devices/**`

Do not infer Server API endpoints from Web UI routes.

## Runtime and dependencies

- Python >= 3.12
- `httpx` >= 0.27, < 1
- Pydantic >= 2, < 3
- `pytest`
- `respx`
- `ruff`
- `mypy`

The v0.1 client is synchronous. It owns one `httpx.Client`, is reusable across
requests, and is not safe for concurrent use from multiple threads or tasks.
Async support and concurrent use are deferred until a concrete consumer needs
them.

## Scope

Implement:

- login, refresh-token rotation, and one-shot authentication recovery;
- device listing, lookup, and playlist assignment;
- model listing;
- HTML screen listing, creation, deletion, and rendered-image access;
- playlist listing, lookup, creation, replacement, and deletion;
- explicit rendered-image reads and downloads;
- RFC Problem Details errors;
- a raw HTTP escape hatch for unsupported Server API endpoints.

Defer:

- firmware and firmware device-protocol endpoints;
- device creation, deletion, and updates other than playlist assignment;
- model lookup and mutation;
- screen updates and URI-based screen sources;
- extensions, designs, plugins, palettes, and the cloud webhook API;
- template authoring and local HTML rendering;
- async and background token refresh;
- built-in token or credential storage;
- local projections that duplicate remote models, including `DeviceStatus`,
  `DeviceSettings`, `RenderTarget`, and `RenderedImage`;
- convenience aliases such as `replace_screens()` and `clear()` when
  `playlists.update(..., screen_ids=...)` already expresses the operation.

## Public client

```python
TerminusClient(
    base_url: str,
    *,
    credentials: Credentials | None = None,
    tokens: TokenPair | None = None,
    token_store: TokenStore | None = None,
    timeout: httpx.Timeout | None = None,
    verify: bool | SSLContext = True,
    refresh_skew_seconds: int = 60,
)
```

`refresh_skew_seconds` must be non-negative.

The client exposes:

```python
client.devices
client.models
client.screens
client.playlists
```

It also implements `close()`, `__enter__()`, and `__exit__()`. Calling any I/O
method after `close()` raises `RuntimeError`. The README uses the client as a
context manager.

The SDK uses header-based JWT authentication only. It does not retain or send
cookies returned by Terminus. Native requests do not follow redirects; a
redirect is an unexpected response.

### Base URL

`base_url` must be an absolute `http` or `https` URL containing only scheme,
host, optional port, and an optional trailing slash. Reject user information,
query strings, fragments, and non-root paths. Strip the trailing slash.
Reject malformed ports, invalid HTTPX URL syntax, and whitespace during client
construction rather than leaking a delayed `httpx.InvalidURL` from a request.

Terminus is served at the origin root in the supported configuration. Rejecting
path prefixes avoids ambiguous URL joining.

### Timeouts and TLS

TLS verification is enabled by default. A caller may provide an `SSLContext`
for a private CA. Documentation must not show `verify=False`.

When `timeout` is `None`, create:

```python
httpx.Timeout(connect=5.0, read=60.0, write=30.0, pool=5.0)
```

Screen rendering can invoke Chromium and is the reason for the 60-second read
timeout. A caller-supplied timeout replaces the complete default.

## Input and response model rules

Outbound request models are strict and reject unknown fields. Managers serialize
them with `exclude_unset=True`, preserving the difference between an omitted
field and an explicit `null`. A field may be sent as `null` only where its
request type is nullable and this specification does not define omission
instead.

Response models:

- preserve unknown fields with Pydantic `extra="allow"`;
- parse RFC 3339 timestamps into aware `datetime` values;
- retain unknown strings received from Terminus instead of forcing response
  enums;
- never perform network I/O;
- redact secrets from `repr()` and `str()`.

Every successful native resource response has a top-level `data` member.
Managers unwrap that member before validation. A missing `data` member, invalid
JSON, or an incompatible payload raises `TerminusUnexpectedResponseError` and
preserves the response.

List endpoints require `data` to be an array. Single-resource endpoints require
an object. A successful delete may return `data: {}`; managers normalize that to
`None`.

Positive resource IDs are required for public manager arguments and outbound ID
fields. Outbound ID fields are strict integers: reject booleans, floats, and
numeric strings rather than coercing them. Empty names and labels are rejected
locally.

## Authentication

### Values

```python
Credentials(email: str, password: SecretStr)
TokenPair(access_token: SecretStr, refresh_token: SecretStr)

class TokenStore(Protocol):
    def save(self, tokens: TokenPair) -> None: ...
```

Credential and token strings must be non-empty. Their model representations are
redacted. Managers unwrap them only while constructing the required wire header
or body.

The SDK does not load from `TokenStore`. The caller loads persisted secrets and
passes `TokenPair` during construction. The SDK calls `save()` after every login
and successful refresh.

If `save()` fails, retain the new pair in memory and raise
`TerminusTokenPersistenceError` with the storage exception as its cause. Do not
continue the original API request. Mark the pair as pending persistence. Before
any later authenticated request, retry `save()` and perform no network I/O until
it succeeds. The failure must be visible because the server may already have
invalidated the old refresh token. A `TokenStore` must replace its stored pair
atomically.

Do not share one persisted token pair between concurrent clients or processes.
Terminus rotates refresh tokens, so external coordination belongs to the caller.
A token-only client can recover only while its refresh credentials remain
usable. Long-lived automation should also provide credentials unless its owner
has another explicit recovery mechanism.

### Wire contract

Login:

```text
POST /login
Content-Type: application/json

{"login": "<email>", "password": "<password>"}
```

The response must contain string `access_token` and `refresh_token` members.
An unsuccessful login raises `TerminusAuthenticationError`; a malformed 2xx
login response raises `TerminusUnexpectedResponseError`.

Refresh:

```text
POST /api/jwt
Authorization: <raw-access-token>
Content-Type: application/json

{"refresh_token": "<refresh-token>"}
```

Never prefix the token with `Bearer`. A successful refresh replaces both tokens.
A malformed 2xx refresh response raises `TerminusUnexpectedResponseError` and
does not replace the current pair.

### Request state machine

Before an authenticated request:

1. If no token pair exists, log in once when credentials exist; otherwise raise
   `TerminusAuthenticationError`.
2. Decode the access token's JWT payload without signature verification. This is
   only a scheduling hint.
3. If `exp` is a numeric timestamp and is at or before
   `now + refresh_skew_seconds`, attempt one refresh.
4. If the JWT is opaque, malformed, or lacks a usable `exp`, send it unchanged
   and rely on one-shot 401 recovery. Do not reject a token solely because it
   cannot be decoded locally.

When refresh returns 400, 401, or 403, the refresh credentials are unusable. Log
in once if credentials exist; otherwise raise `TerminusAuthenticationError`.
Do not turn timeouts, connection failures, or 5xx refresh responses into login
attempts. Preserve those failures as transport or unexpected-response errors.

When the original authenticated request returns 401:

1. refresh once when a refresh token exists;
2. if refresh credentials are rejected, log in once when credentials exist;
3. replay the original request once only when its method is `GET`, `HEAD`, or
   `OPTIONS`;
4. if a replay also returns 401, raise `TerminusAuthenticationError`;
5. for every other method, keep the recovered token pair but raise
   `TerminusAuthenticationError` against the original 401 instead of replaying.

No mutating request is automatically replayed. Terminus 0.71.0 does not provide
a practical way to invalidate a well-formed access token on demand, so the
server-side ordering needed to prove mutation replay cannot be verified. A
caller may inspect the error and retry deliberately. No response other than 401
triggers authentication recovery. Transport failures, 408, 429, and 5xx
responses are never retried by v0.1.

There is no background thread or timer. Authentication happens lazily on use.

## Native HTTP contract

All methods below authenticate unless stated otherwise. Request bodies wrap
their attributes under the singular resource name shown in the Payload column.

| Manager method | HTTP request | Payload | Result |
| --- | --- | --- | --- |
| `devices.list()` | `GET /api/devices` | none | `list[Device]` |
| `devices.get(id)` | `GET /api/devices/:id` | none | `Device` |
| `devices.update(id, request)` | `PATCH /api/devices/:id` | `{"device": ...}` | `Device` |
| `models.list()` | `GET /api/models` | none | `list[Model]` |
| `screens.list()` | `GET /api/screens` | none | `list[Screen]` |
| `screens.create(request)` | `POST /api/screens` | `{"screen": ...}` | `Screen` |
| `screens.delete(id)` | `DELETE /api/screens/:id` | none | `Screen | None` |
| `playlists.list()` | `GET /api/playlists` | none | `list[Playlist]` |
| `playlists.get(id)` | `GET /api/playlists/:id` | none | `Playlist` |
| `playlists.create(request)` | `POST /api/playlists` | `{"playlist": ...}` | `Playlist` |
| `playlists.update(id, request)` | `PATCH /api/playlists/:id` | `{"playlist": ...}` | `Playlist` |
| `playlists.delete(id)` | `DELETE /api/playlists/:id` | none | `Playlist | None` |

No manager synthesizes a missing native endpoint. In particular, v0.1 has no
`screens.get(id)` because Terminus 0.71.0 has no screen show route.

### Device

`Device` contains:

| Field | Type |
| --- | --- |
| `id`, `model_id` | `int` |
| `playlist_id` | `int | None` |
| `label`, `mac_address`, `firmware_version`, `wake_reason` | `str | None` |
| `api_key` | `SecretStr | None` |
| `firmware_profile`, `firmware_update`, `firmware_reset` | `bool` |
| `wifi_band`, `battery_charge`, `battery_voltage` | `float` |
| `wifi_signal`, `refresh_rate`, `image_timeout`, `wake_duration`, `width`, `height` | `int` |
| `charging`, `image_cached`, `display_compatibility` | `bool` |
| `display_profile`, `command`, `touch_bar` | `str` |
| `sleep_start_at`, `sleep_stop_at` | `time | None` |
| `synced_at` | `datetime | None` |
| `created_at`, `updated_at` | `datetime` |

`DevicePatch` contains one required field: `playlist_id: int`. IDs must be
positive. Terminus 0.71.0 accepts many other device updates, but v0.1 exposes
only the assignment operation used by the demonstrated workflow. The pinned
PATCH schema rejects `playlist_id: null`, so the SDK cannot detach a playlist.
Callers must preserve the prior integer playlist ID when a temporary assignment
needs to be restored.

Changing the assignment does not wake a physical device. The new playlist is
used on the device's next scheduled poll, power cycle, or manual refresh.

### Model

`Model` contains:

| Field | Type |
| --- | --- |
| `id` | `int` |
| `default_palette_id` | `int | None` |
| `name`, `label`, `kind`, `mime_type` | `str` |
| `description` | `str | None` |
| `colors`, `bit_depth`, `rotation`, `offset_x`, `offset_y`, `width`, `height` | `int` |
| `scale_factor` | `float` |
| `css` | `dict[str, Any] | None` |
| `created_at`, `updated_at` | `datetime` |

The response permits `css: null`; this occurs on the deployed Terminus server
even though model create and patch bodies use an object when `css` is present.

Models are read-only in SDK v0.1. `models.list()` supplies the model ID required
to render a screen. Model lookup and mutation remain available through the raw
HTTP escape hatch until a concrete consumer justifies typed methods.

### Screen

`Screen` contains:

| Field | Type |
| --- | --- |
| `id`, `model_id` | `int` |
| `label`, `name` | `str` |
| `created_at`, `updated_at` | `datetime` |
| `filename`, `mime_type`, `uri` | `str | None` |
| `bit_depth`, `width`, `height`, `size` | `int | None` |

Rendered metadata is nullable because the pinned database permits a screen with
empty image data and the serializer omits metadata in that case.

Define `HtmlSource(html: str)`. Empty HTML is invalid.

`ScreenCreate` requires:

```python
model_id: int
name: str
label: str
source: HtmlSource
playlist_id: int | None = None
```

For `ScreenCreate`, `playlist_id=None` means omission. Terminus does not accept
an explicit null. Serialize the source as `content=<html>`. Do not send
`file_name`; the pinned API action does not accept it.

Send HTML unchanged. Terminus owns rendering and sanitization. The SDK must not
claim that Terminus makes hostile HTML safe: rendering intentionally permits
HTML, CSS, JavaScript, SVG, and external resources. Applications must escape
untrusted values before interpolating them into trusted templates.

### Rendered-image I/O

```python
client.screens.read_bytes(screen: Screen, *, allow_cross_origin: bool = False) -> bytes
client.screens.download(
    screen: Screen,
    destination: str | PathLike[str],
    *,
    allow_cross_origin: bool = False,
) -> Path
```

URI resolution is internal. Relative URIs resolve against `base_url`; absolute
HTTP(S) URIs remain absolute, and other schemes are rejected.

Image reads are explicit unauthenticated GETs. Never attach the Terminus
`Authorization` header to an upload URI. By default, reject an absolute URI whose
origin differs from `base_url`; the caller must opt in with
`allow_cross_origin=True`. Do not follow redirects in v0.1.

Raise `TerminusUnexpectedResponseError` when the screen has no URI or the image
response is not 2xx. `read_bytes()` returns the complete body. `download()`
writes to a temporary sibling and atomically replaces the destination only
after a complete successful read. Existing destination files are replaced.

### Playlist

`PlaylistItem` contains `id`, `screen_id`, and `position` as `int`, plus aware
`created_at` and `updated_at` datetimes.

`Playlist` contains:

```python
id: int
name: str
label: str
current_item_id: int | None  # a PlaylistItem ID, not a Screen ID
mode: str
created_at: datetime
updated_at: datetime
items: list[PlaylistItem]
```

`PlaylistCreate` requires non-empty `name` and `label`. Optional fields are:

```python
screen_ids: list[int]
```

Serialize `screen_ids=[1, 2]` as
`items=[{"screen_id": 1}, {"screen_id": 2}]`. Order is significant. Omission
creates a playlist with no items; an empty list has the same result.

`PlaylistPatch` requires the complete current `name` and `label`, matching the
pinned API. It may also contain:

```python
screen_ids: list[int]
```

The SDK does not issue a preliminary GET to invent partial update semantics.
Omitted `screen_ids` preserves items. An empty list replaces them with no items.
Playlist mode and current-item mutation are deferred; response values remain
visible on `Playlist`.

## Raw HTTP

```python
client.request(
    method: str,
    path: str,
    *,
    authenticated: bool = True,
    **httpx_request_options: Any,
) -> httpx.Response
```

For `authenticated=True`, `path` must be relative to `base_url`; reject absolute
URLs. Reject a caller-supplied `Authorization` header, `Cookie` header, or
`auth=` option. The SDK supplies the raw-token header and applies normal
one-shot authentication recovery.

For `authenticated=False`, relative and absolute HTTP(S) URLs are accepted and
the SDK adds neither Terminus authorization nor retained cookies. Caller-supplied
authentication remains the caller's responsibility. Return the `httpx.Response`
without envelope decoding or status translation. Transport failures still
raise `TerminusTransportError`.

## Errors

```text
TerminusError
├── TerminusAuthenticationError
├── TerminusTokenPersistenceError
├── TerminusNotFoundError
├── TerminusValidationError
├── TerminusConflictError
├── TerminusTransportError
└── TerminusUnexpectedResponseError
```

Map native resource responses as follows:

| Condition | Exception |
| --- | --- |
| exhausted authentication or final 401 | `TerminusAuthenticationError` |
| 404 | `TerminusNotFoundError` |
| 400 or 422 | `TerminusValidationError` |
| 409 | `TerminusConflictError` |
| `httpx.TransportError` | `TerminusTransportError` |
| other non-2xx or an invalid response body | `TerminusUnexpectedResponseError` |

Authentication endpoint failures follow the authentication state machine before
this general mapping.

Represent RFC Problem Details with:

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

All keys other than the five standard members belong in `extensions`.
`TerminusValidationError` also exposes `errors` from extensions when present.

Every response-derived exception preserves status, parsed problem details,
request method and URL, and the original `httpx.Response`. Exception `str()` and
`repr()` must not contain passwords, tokens, API keys, authorization headers, or
login request bodies. Do not log those values anywhere in the SDK.

## Contract tests

Mocked HTTP tests must prove:

1. base URL validation and default timeout/TLS/redirect behavior;
2. client close and context-manager behavior;
3. raw JWT authorization without `Bearer`;
4. login and refresh replace and persist the complete token pair;
5. malformed or opaque access tokens are used without local rejection;
6. expired and near-expiry JWTs refresh before the resource request;
7. refresh-token rejection logs in only when credentials exist;
8. refresh transport errors and 5xx responses do not trigger login;
9. a 401 causes at most one recovery; safe reads replay once, while mutations
   are never replayed automatically;
10. token persistence failure is loud and retains the new in-memory pair;
11. no background thread or timer is created;
12. every manager uses the method, route, wrapper, and response shape in the
    native HTTP contract table;
13. HTML screen creation serializes exactly as specified;
14. playlist order is preserved, omission preserves items, and an empty list
    clears them;
15. playlist update makes one PATCH request and no preliminary GET;
16. device update accepts only a positive, non-null `playlist_id` and makes one
    PATCH request;
17. unknown response fields and unknown response strings survive decoding;
18. response envelopes, empty delete results, and malformed responses follow
    the specified behavior;
19. RFC problem data and validation errors remain inspectable;
20. secret values are absent from models, exceptions, and captured logs;
21. image downloads never send authorization, reject cross-origin URLs by
    default, do not follow redirects, and replace destinations atomically;
22. raw authenticated requests reject absolute URLs and conflicting auth;
23. cookies received during login never appear on resource, raw, or download
    requests.

## First implementation checkpoint

The implemented checkpoint covers login, model listing, playlist creation, HTML
screen creation, screen-list readback, rendered-image download, playlist update,
and cleanup against a real Terminus server. Before release, extend that public
SDK path with typed device listing, lookup, temporary playlist assignment,
physical display confirmation, and restoration.

## Real-server release smoke test

Mocks do not prove compatibility. A release is blocked until a smoke test passes
against a disposable Terminus instance built from the supported tag's resolved
commit.

The release workflow must start a clean Terminus instance from the supported tag
and resolved commit. Its setup must create the first account through Terminus's
supported registration flow so the account is verified, and must confirm that
at least one usable model exists. Keep credentials in environment variables;
never write them to tracked files or command output.

Configure a short access-token lifetime so refresh rotation can be observed
without a long wait. Set `API_ACCESS_TOKEN_PERIOD`, `SESSION_LIFETIME_LIMIT`, and
`SESSION_INACTIVITY_LIMIT` to compatible test values; changing only the access
token period does not reproduce the supported session behavior.

A developer smoke test may target an existing server. It must not claim release
compatibility unless the server's tag and resolved commit are independently
verified.

The smoke test must:

1. log in and list models;
2. create a uniquely named playlist;
3. create a self-contained HTML screen using the existing model;
4. list screens and find exactly the screen just created by its returned ID;
5. download the real Terminus-rendered image and assert non-empty bytes;
6. update the playlist with the screen, read it back, and verify order;
7. allow the access token to enter the refresh window, make another authenticated
   request, and prove that both tokens rotated;
8. delete all created screens and playlists in `finally` cleanup;
9. fail the run if cleanup fails.

The test may be skipped in ordinary local test runs. The release workflow must
run it with:

```text
TERMINUS_BASE_URL
TERMINUS_EMAIL
TERMINUS_PASSWORD
TERMINUS_ALLOW_MUTATION_TESTS=1
```

The release record must identify the Terminus tag, resolved commit, and image if
one was used. A passing mock suite is not a substitute.

## README first use

The first example must use a context manager, handle an empty model list, create
its own playlist, create a screen, download the image, attach the screen to the
playlist, and state that it mutates Terminus.

The example must not index blindly into `devices.list()` or assume a device has
a playlist. It must explain that a physical TRMNL updates on its next display
poll or wake cycle.

A second example may show token-only startup. It must explain rotation,
persistence, the lack of cross-process coordination, and the need for
credentials if the persisted refresh token becomes unusable.

## Acceptance criteria

SDK v0.1 is complete when:

- unit and mocked contract tests pass;
- `mypy` and `ruff` pass;
- the public API and supported Terminus tag and commit are documented;
- no endpoint or remote resource has been invented;
- the real-server release smoke test passes against the supported tag's resolved
  commit;
- the typed device-assignment workflow has been displayed on a physical device
  and the prior assignment restored;
- all four managers match the deliberately narrow native HTTP contract table;
- authentication recovery is bounded and token rotation is persisted;
- transport and persistence failures fail loudly;
- rendered-image downloads cannot leak the API authorization header;
- no deferred projection, alias, async layer, or storage backend has slipped
  into v0.1.
