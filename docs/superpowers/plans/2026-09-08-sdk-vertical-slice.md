# Terminus SDK Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove login, model listing, screen rendering, image download, playlist update, authentication recovery, and cleanup through the public Python SDK against a real Terminus server.

**Architecture:** `TerminusClient` owns one synchronous `httpx.Client`, token state, and three small resource managers for this slice. Pydantic models describe only the vertical-slice request and response contracts. Mocked HTTP tests establish deterministic wire behavior; an environment-driven script proves the same public API against a real server.

**Tech Stack:** Python 3.12+, httpx 0.27+, Pydantic 2, pytest, respx, ruff, mypy, uv

**Spec:** `docs/specs/terminus-sdk.md`

## Global Constraints

- Distribution name is `trmnl-terminus`; import package is `trmnl_terminus`.
- The client is synchronous and not safe for concurrent use.
- Authorization uses the raw JWT without a `Bearer` prefix.
- Do not retain cookies, follow redirects, retry transport failures, or write secrets to tracked files.
- Credentials and server URLs enter the real smoke test through environment variables only.
- A real server run is developer evidence unless its Terminus tag and commit are independently verified.
- Production behavior is added test-first. Each test must fail for the missing behavior before implementation.

---

### Task 1: Package and request-model foundation

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `src/trmnl_terminus/__init__.py`
- Create: `src/trmnl_terminus/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Credentials`, `TokenPair`, `HtmlSource`, `Model`, `Screen`, `PlaylistItem`, `Playlist`, `ScreenCreate`, `PlaylistCreate`, and `PlaylistPatch`.
- Produces: strict request serialization through `model_dump(exclude_unset=True, mode="json")`.

- [ ] **Step 1: Protect local secrets and generated files**

Add `.env`, `.env.*`, `.venv/`, Python caches, build output, coverage output, and downloaded smoke artifacts to `.gitignore`. Do not add a real server URL or sample credentials.

- [ ] **Step 2: Write failing model tests**

Create tests that instantiate the public values and assert literal payloads:

```python
def test_screen_create_serializes_html_source() -> None:
    request = ScreenCreate(
        model_id=7,
        name="codex-smoke",
        label="Codex Smoke",
        source=HtmlSource(html="<h1>hello</h1>"),
    )
    assert request.to_payload() == {
        "model_id": 7,
        "name": "codex-smoke",
        "label": "Codex Smoke",
        "content": "<h1>hello</h1>",
    }


def test_playlist_patch_distinguishes_omitted_and_empty_screen_ids() -> None:
    assert "items" not in PlaylistPatch(name="n", label="l").to_payload()
    assert PlaylistPatch(name="n", label="l", screen_ids=[]).to_payload()["items"] == []
```

- [ ] **Step 3: Verify the model tests fail for missing imports**

Run `uv run --with pytest --with 'pydantic>=2,<3' pytest tests/test_models.py -q`. Expected: collection fails because `trmnl_terminus` does not exist.

- [ ] **Step 4: Add package metadata and minimal models**

Configure a `src` layout in `pyproject.toml` with Python `>=3.12`, runtime dependencies `httpx>=0.27,<1` and `pydantic>=2,<3`, plus pytest, respx, ruff, and mypy development dependencies. Implement strict request models, extra-preserving response models, positive IDs, non-empty names, HTML-to-`content` serialization, and ordered playlist item serialization.

- [ ] **Step 5: Run model tests and static checks**

Run `uv run pytest tests/test_models.py -q`, `uv run ruff check .`, and `uv run mypy src`.

- [ ] **Step 6: Commit the foundation**

Commit `.gitignore`, `pyproject.toml`, `src/trmnl_terminus/__init__.py`, `src/trmnl_terminus/models.py`, and `tests/test_models.py` with `feat: add SDK value and request models`.

### Task 2: Authenticated transport

**Files:**
- Create: `src/trmnl_terminus/errors.py`
- Create: `src/trmnl_terminus/client.py`
- Modify: `src/trmnl_terminus/__init__.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `Credentials`, `TokenPair`.
- Produces: `TokenStore.save(tokens)`, `TerminusClient.request(method, path, authenticated=True, **options)`, context-manager lifecycle, bounded login/refresh/replay, and response-derived exceptions.

- [ ] **Step 1: Write failing login and cookie-isolation tests**

Use `respx` to return a login payload with `Set-Cookie`, then a models response. Assert the login body is literal JSON, the resource request has raw `Authorization`, and no `Cookie` header is sent.

```python
assert login_request.content == b'{"login":"user@example.test","password":"secret"}'
assert models_request.headers["Authorization"] == "access-one"
assert "Cookie" not in models_request.headers
```

- [ ] **Step 2: Verify the auth tests fail for the missing client**

Run `uv run pytest tests/test_client.py -q`. Expected: collection fails because `TerminusClient` is missing.

- [ ] **Step 3: Implement client lifecycle, login, and errors**

Validate a root-only HTTP(S) base URL. Construct one `httpx.Client` with redirects disabled and the specified default timeout. Implement lazy login, raw authorization, cookie-jar clearing after every response, secret-safe exceptions, `close()`, and context management.

- [ ] **Step 4: Add failing bounded-recovery tests**

Cover one 401 followed by login and one replay, a second 401 that raises, no replay for 5xx or transport failure, and complete token replacement after refresh. For a POST recovery test, assert the mock receives exactly two POSTs: one rejected before handling and one accepted after authentication.

- [ ] **Step 5: Implement bounded refresh and replay**

Decode JWT `exp` without signature verification only as a scheduling hint. Refresh once when near expiry. On rejected refresh, log in once only when credentials exist. Replay an original 401 once. Preserve new tokens in memory before invoking `TokenStore.save`; block later network access while a rotated pair remains unpersisted.

- [ ] **Step 6: Run transport tests and static checks**

Run `uv run pytest tests/test_client.py -q`, `uv run ruff check .`, and `uv run mypy src`.

- [ ] **Step 7: Commit the transport**

Commit the client, errors, exports, and tests with `feat: add authenticated Terminus transport`.

### Task 3: Model, screen, and playlist managers

**Files:**
- Create: `src/trmnl_terminus/resources.py`
- Modify: `src/trmnl_terminus/client.py`
- Modify: `src/trmnl_terminus/__init__.py`
- Test: `tests/test_resources.py`

**Interfaces:**
- Consumes: `TerminusClient.request` and vertical-slice models.
- Produces: `client.models.list()`, `client.screens.create/get/delete/read_bytes/download`, and `client.playlists.create/get/list/update/delete`.

- [ ] **Step 1: Write failing manager wire-contract tests**

For each manager method, register the exact route and return a complete upstream-shaped `data` envelope. Assert the returned Pydantic object and hand-written request JSON. Include missing `data`, invalid JSON, an empty delete payload, and an unknown response field.

- [ ] **Step 2: Verify manager tests fail for missing managers**

Run `uv run pytest tests/test_resources.py -q`. Expected: imports or attribute access fail because the managers do not exist.

- [ ] **Step 3: Implement envelope decoding and managers**

Keep each manager as a thin wrapper over `TerminusClient.request`. Unwrap `data`, validate lists versus objects, preserve unknown response fields, serialize singular resource wrappers, and normalize `{}` delete results to `None`.

- [ ] **Step 4: Add failing image security and atomic-write tests**

Assert same-origin upload reads are unauthenticated, cross-origin reads fail by default, redirects are not followed, a failed read leaves an existing destination unchanged, and a successful download atomically replaces it.

- [ ] **Step 5: Implement rendered-image reads and downloads**

Resolve relative upload URIs against the server origin. Fetch without Terminus authorization. Write downloads to a temporary sibling, flush and close them, then replace the destination only after the complete 2xx body is available.

- [ ] **Step 6: Run all local tests and static checks**

Run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src`.

- [ ] **Step 7: Commit resource managers**

Commit the managers and tests with `feat: add screen and playlist vertical slice`.

### Task 4: Environment-only real-server proof

**Files:**
- Create: `scripts/run_real_smoke.py`
- Create: `docs/real-server-smoke.md`
- Test: `tests/test_smoke_script.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: public SDK imports and `TERMINUS_BASE_URL`, `TERMINUS_EMAIL`, `TERMINUS_PASSWORD`, `TERMINUS_ALLOW_MUTATION_TESTS`.
- Produces: an exit-zero end-to-end proof with unique resources and unconditional cleanup; prints IDs and status only, never URLs or credentials.

- [ ] **Step 1: Write a failing smoke safety test**

Run the script in a subprocess with all `TERMINUS_*` variables removed. Assert a
non-zero exit, a message naming only the missing variable names, and no attempted
network connection. Run `uv run pytest tests/test_smoke_script.py -q` and confirm
it fails because the runner does not exist.

- [ ] **Step 2: Write the smoke runner with fail-closed guards**

Exit before network access unless all required variables exist and mutation permission equals `1`. Generate unique names with `secrets.token_hex`. Track every created ID and delete it in `finally`; report cleanup failure as a failed run.

- [ ] **Step 3: Exercise the public vertical slice**

List models, create a playlist, create self-contained HTML, fetch the screen, download and assert non-empty rendered bytes, attach the screen to the playlist, read the playlist back, and assert item order.

- [ ] **Step 4: Exercise rejected-auth POST recovery**

Capture a valid pair through an in-memory `TokenStore`, rotate it once through a raw public call to `/api/jwt` without installing the returned pair, then create a uniquely named playlist with the stale pair. Require an authentication recovery, and assert by listing that exactly one matching playlist exists. Do not use a malformed fake JWT: Terminus reports malformed tokens as bad requests rather than expired authentication.

- [ ] **Step 5: Document disposable and developer modes**

Document the upstream tag/SHA requirement, first-user registration, model prerequisite, and coordinated `API_ACCESS_TOKEN_PERIOD`, `SESSION_LIFETIME_LIMIT`, and `SESSION_INACTIVITY_LIMIT` settings. Show variable names without concrete values. State that an existing server run is not release evidence without independent build identification.

- [ ] **Step 6: Run local verification**

Run the smoke script with no environment and assert it exits before network access. Run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `git diff --check`.

- [ ] **Step 7: Run developer smoke when credentials are available**

Export the four environment variables outside the repository and run `uv run python scripts/run_real_smoke.py`. Record only pass/fail and non-secret resource IDs. If credentials are absent, report the real-server gate as blocked rather than substituting mocks.

- [ ] **Step 8: Commit the smoke infrastructure**

Commit the runner and documentation with `test: add real Terminus vertical-slice smoke`.

### Task 5: Final review and publication

**Files:**
- Modify only files required by verified defects.

**Interfaces:**
- Produces: a clean, reviewed feature branch ready to merge.

- [ ] **Step 1: Re-read the specification against the implementation**

Check every implemented vertical-slice behavior against `docs/specs/terminus-sdk.md`. List full-SDK requirements intentionally left for later instead of claiming v0.1 completion.

- [ ] **Step 2: Run the complete verification suite fresh**

Run `uv sync`, `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `git diff --check`.

- [ ] **Step 3: Inspect the committed diff for secrets**

Review `git diff origin/main...HEAD` and verify it contains no server hostname, credentials, tokens, device identifiers, downloaded images, or `.env` files.

- [ ] **Step 4: Push the feature branch**

Push `codex/sdk-vertical-slice`. Do not merge while the real-server gate is unrun or failing; report missing credentials as the explicit blocker.
