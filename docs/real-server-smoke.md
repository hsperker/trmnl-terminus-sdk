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

## Developer evidence

An existing server can prove that the user-facing path works in that deployment.
It cannot prove release compatibility unless its Terminus tag and resolved
commit are known independently.

The default developer run proves:

- login and raw-token authorization;
- model listing;
- playlist and HTML-screen creation;
- native screen retrieval;
- a real rendered-image download;
- ordered playlist replacement and readback;
- one stale-token POST recovery with exactly one created resource;
- cleanup.

Set `TERMINUS_REFRESH_WAIT_SECONDS` only when the server has a short access-token
lifetime. The runner then waits, makes another request, and requires both access
and refresh tokens to rotate.

To prepare the POST-recovery proof, the runner rotates the current token pair by
calling the refresh endpoint through the raw public client and deliberately does
not install the returned pair. The next playlist POST must be rejected before
its handler, recover through login, and create one resource. A malformed fake
JWT is not used because Terminus correctly reports malformed JWTs as bad
requests, not expired authentication.

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
