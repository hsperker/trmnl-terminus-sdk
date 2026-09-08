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

On 2026-09-08, the automated smoke passed against Terminus commit
`2d91851b2c038f9964ffb066e4a765b3e88121d2`. A separate reversible check assigned
the generated playlist to one physical device, and the rendered “SDK DEVICE
PROOF” screen was visually confirmed. The device's prior playlist assignment was
restored, and a follow-up query found no SDK-prefixed screens or playlists.

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
