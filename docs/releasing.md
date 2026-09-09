# Releasing `trmnl-terminus`

Releases are built and published by
[`release.yml`](../.github/workflows/release.yml). Do not upload a local build
or store a PyPI API token in GitHub.

## One-time setup for the first release

1. Create a GitHub environment named `pypi`. Restrict it to protected tags and,
   if desired, require a maintainer's approval.
2. In your PyPI account's **Publishing** settings, add a pending GitHub
   publisher with these exact values:

   | Field | Value |
   | --- | --- |
   | PyPI project name | `trmnl-terminus` |
   | GitHub owner | `hsperker` |
   | GitHub repository | `trmnl-terminus-sdk` |
   | Workflow filename | `release.yml` |
   | Environment name | `pypi` |

A pending publisher does not reserve the PyPI name. It becomes a normal
publisher when the first upload succeeds.

## Release checklist

1. Set the version with `uv version <version>` and commit the updated
   `pyproject.toml` and `uv.lock`.
2. Run the same checks as CI:

   ```sh
   uv sync --locked
   uv run pytest -q
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy src examples
   uv build --no-sources
   ```

3. Merge the release commit to `main` and wait for CI to pass.
4. Create and push an annotated tag whose value matches `pyproject.toml`:

   ```sh
   version="$(uv version --short)"
   git tag -a "v${version}" -m "v${version}"
   git push origin "v${version}"
   ```

The release workflow checks the tag against the package version, reruns the
source checks, builds the wheel and source distribution, installs and tests
both artifacts, generates attestations, and then publishes through the `pypi`
environment.

After the workflow finishes, verify the project page and install it without a
source checkout:

```sh
uv run --no-project --with trmnl-terminus \
  python -c "import trmnl_terminus; print('install ok')"
```
