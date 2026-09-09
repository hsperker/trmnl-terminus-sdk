# Release Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before completion claims. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `trmnl-terminus` ready for a trustworthy first PyPI release with
an uv-first workflow, useful examples, concise documentation, and automated
build and release checks.

**Architecture:** Keep the SDK API unchanged. Add only distribution metadata,
typed-package metadata, standalone examples that call the public API, and
GitHub workflows. Publish from a version tag through PyPI Trusted Publishing;
the build job never receives publishing permission.

**Tech Stack:** Python 3.12+, uv, hatchling, pytest, Ruff, mypy, GitHub Actions,
PyPI Trusted Publishing

**Spec:** `docs/specs/terminus-sdk.md`

## Global Constraints

- Support exactly Terminus tag `0.71.0`, commit
  `e0cf90d8ef6d7bc16dfbac8ebab910a9fda9de56`.
- Do not add endpoints or change the public SDK contract.
- Keep TLS verification enabled in every example.
- Keep real hosts, credentials, tokens, and device IDs out of Git.
- Use uv as the primary contributor workflow and retain a pip install note for
  users who do not use uv.
- Do not create or push a release tag and do not publish to PyPI in this plan.

---

### Task 1: Complete package metadata

**Files:**

- Create: `LICENSE`
- Create: `src/trmnl_terminus/py.typed`
- Modify: `pyproject.toml`

**Produces:** A package whose declared MIT license and typing support are
present in both wheel and source distribution.

- [x] Add the MIT license text and the PEP 561 marker.
- [x] Add project URLs, classifiers, keywords, authorship metadata, and modern
  license-file metadata without changing runtime dependencies.
- [x] Build with `uv build --no-sources` and inspect both archives for the
  license, README, and `py.typed` marker.

### Task 2: Add runnable public-API examples

**Files:**

- Create: `examples/list_resources.py`
- Create: `examples/render_screen.py`
- Create: `tests/test_examples.py`

**Produces:** One read-only discovery example and one guarded, self-cleaning
screen-render example.

- [x] Write subprocess tests proving missing configuration and a missing
  mutation opt-in stop before network access; confirm the tests fail because
  the examples do not exist.
- [x] Add two self-contained examples with small inline environment guards.
- [x] Run the focused example tests, Ruff, and mypy.

### Task 3: Rewrite the README around first success

**Files:**

- Modify: `README.md`

**Produces:** An uv-first guide with a short read-only quick start, links to
the runnable examples, explicit compatibility and safety boundaries, a compact
API map, and contributor commands.

- [x] Replace the long mutating inline example with a read-only quick start.
- [x] Document `uv add trmnl-terminus` as the release install and pip as the
  alternative; clearly label source-checkout commands for pre-release use.
- [x] Link the render and physical-device proofs instead of duplicating them.
- [x] Run the prose edit pass and verify every command and link locally.

### Task 4: Add CI and Trusted Publishing

**Files:**

- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `tests/package_smoke.py`

**Produces:** Pull-request and main-branch verification across supported Python
versions, plus a tag-triggered two-job release that smoke-tests both artifacts
before publishing with a short-lived identity token.

- [x] Add a package smoke script that imports the installed distribution and
  checks the documented public surface.
- [x] Add CI for lockfile sync, tests, Ruff, formatting, mypy, and an isolated
  distribution build.
- [x] Add a tag-only build/publish workflow with immutable action references,
  artifact attestations, and `id-token: write` only in the publish job.
- [x] Run the full local verification suite, build both artifacts, smoke-test
  each artifact in isolation, and inspect the final diff for secrets.
