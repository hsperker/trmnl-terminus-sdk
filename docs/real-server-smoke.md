# Real-server smoke test

The smoke test creates and deletes screens and playlists. It never changes a
device or its assigned playlist.

Run it only against a server intended for mutation. Supply configuration through
the process environment; do not create a repository `.env` file:

```sh
export TERMINUS_BASE_URL='https://terminus.example.test'
export TERMINUS_EMAIL='smoke-user@example.test'
read -rs TERMINUS_PASSWORD
export TERMINUS_PASSWORD
export TERMINUS_ALLOW_MUTATION_TESTS=1
uv run python scripts/run_real_smoke.py
```

The runner prints no configured URL, email, password, or tokens. It gives every
resource a random suffix and deletes all created resources even when an assertion
fails. Cleanup failure makes the run fail.

## Physical-device proof

The guarded device runner temporarily assigns its own playlist and screen to one
existing device, waits for visual confirmation, then restores the device's original
playlist assignment:

```sh
export TERMINUS_BASE_URL='https://terminus.example.test'
export TERMINUS_EMAIL='device-proof-user@example.test'
read -rs TERMINUS_PASSWORD
export TERMINUS_PASSWORD
export TERMINUS_DEVICE_ID=123
export TERMINUS_ALLOW_DEVICE_MUTATIONS=1
uv run python scripts/run_device_smoke.py
```

Use a positive device ID for a device that already has a playlist. An unassigned
device cannot be used because SDK v0.1 intentionally cannot restore
`playlist_id: null`.

Playlist assignment does not wake a physical device. When the runner says the
temporary display is assigned, use the device's normal manual refresh or power-cycle
action. Type `seen` only after the device visibly shows the heading
`SDK DEVICE PROOF`; the prompt times out after ten minutes.

The runner restores the original assignment and verifies it before deleting the
temporary playlist and screen. Any proof, restoration, or cleanup failure makes the
run fail. If restoration cannot be verified, deletion is skipped and the uniquely
SDK-prefixed resources remain for manual recovery. The runner does not print
configuration values, resource identifiers, labels, HTML, device details, response
bodies, passwords, or tokens.

## Latest developer evidence

On 2026-09-09, the guarded physical-device proof passed against public Terminus
commit `2d91851b2c038f9964ffb066e4a765b3e88121d2`. Through the public typed SDK, the
runner created and attached a temporary screen and playlist, assigned the
playlist, and verified the assignment by reading it back.

After a manual device wake, the user saw the black `SDK DEVICE PROOF` heading
centered on a white background within a solid black frame. The runner then
restored and read back the original assignment, deleted both temporary resources,
and exited zero. An independent audit through `devices.list()`, `screens.list()`,
and `playlists.list()` required exactly one device, confirmed a non-null current
playlist assignment, and found zero screens or playlists with the proof prefix.

That Terminus revision is an untagged commit after 0.71.0. This is developer
evidence only; it is not the release proof required against a clean 0.71.0
instance with controlled session settings.

## Developer evidence

An existing server can prove that the user-facing path works in that deployment.
It cannot prove release compatibility unless its Terminus tag and resolved
commit are known independently.

The default developer run proves:

- login and raw-token authorization;
- model listing;
- playlist and HTML-screen creation;
- screen-list readback of the created resource;
- a real rendered-image download;
- ordered playlist replacement and readback;
- cleanup.

Set `TERMINUS_REFRESH_WAIT_SECONDS` only when the server has a short access-token
lifetime. The runner then waits, makes another request, and requires both access
and refresh tokens to rotate.

Mutation replay is intentionally absent. Terminus 0.71.0 can keep a previously
issued access token valid after refresh, and without session expiration that
token is long-lived. The SDK recovers after a mutating 401 but leaves any retry
to the caller because the server-side conditions for safe automatic replay
cannot be proven.

## Release evidence

A release run starts with clean storage and a Terminus checkout at the proposed
tag and resolved commit. Register the first user through Terminus's supported
registration flow; Terminus verifies the first account automatically. Confirm
that startup seeded at least one model.

Use matching short values for `API_ACCESS_TOKEN_PERIOD`,
`SESSION_LIFETIME_LIMIT`, and `SESSION_INACTIVITY_LIMIT`, then set
`TERMINUS_REFRESH_WAIT_SECONDS` long enough to enter the SDK's two-second refresh
window. Record the tag, commit, image identifier if used, and smoke result in the
release evidence. Never record credentials or tokens.

### Terminus 0.71.0 release proof

On 2026-09-08, the upstream `0.71.0` tag independently resolved to commit
`e0cf90d8ef6d7bc16dfbac8ebab910a9fda9de56`. The official image was
`ghcr.io/usetrmnl/terminus:0.71.0` with canonical multi-platform index digest
`sha256:18b672e4958a5a274822b6e34e76b92bcd0a8b483b7728fa559d4fab342262c7`;
the exercised ARM64 manifest digest was
`sha256:a5e2f322ea30fbaa5c2630ae02dcbaa6bfc44d889d92228050f4df8d7bb0c462`.
The image labels reported the same version and commit.

The proof used a uniquely named disposable project, fresh PostgreSQL and Valkey
volumes, and a localhost-only web binding. The first account was created through
the CSRF-protected `/register` form, and the SDK returned at least one synchronized
model. `API_ACCESS_TOKEN_PERIOD`, `SESSION_LIFETIME_LIMIT`, and
`SESSION_INACTIVITY_LIMIT` were each 60 seconds. With a 49.2-second refresh wait
and the runner's two-second skew, the unchanged smoke runner reported
`PASS: real screen, image, playlist, and cleanup` after requiring both access and
refresh token values to change.

That run covered HTML-screen rendering, a non-empty rendered-image download,
screen list readback, ordered playlist replacement and readback, and deletion of
the created screen and playlist. A separate clean-stack pass followed cleanup
with an API check and found no matching smoke resources. Final host-side
inspection found zero project containers, networks, volumes, or temporary runtime
files.
