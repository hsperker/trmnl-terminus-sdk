from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
TERMINUS_ENVIRONMENT_PREFIX = "TERMINUS_"


def _run_example(
    name: str,
    environment: dict[str, str],
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    clean_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(TERMINUS_ENVIRONMENT_PREFIX)
    }
    clean_environment.update(environment)
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "examples" / name), *arguments],
        cwd=PROJECT_ROOT,
        env=clean_environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def test_list_resources_names_missing_configuration() -> None:
    result = _run_example("list_resources.py", {})

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Missing required environment variables" in result.stderr
    assert "TERMINUS_BASE_URL" in result.stderr
    assert "TERMINUS_EMAIL" in result.stderr
    assert "TERMINUS_PASSWORD" in result.stderr


def test_render_screen_requires_explicit_mutation_opt_in_before_network() -> None:
    result = _run_example(
        "render_screen.py",
        {
            "TERMINUS_BASE_URL": "https://example.test",
            "TERMINUS_EMAIL": "example@example.test",
            "TERMINUS_PASSWORD": "not-a-real-secret",
            "TERMINUS_ALLOW_MUTATIONS": "0",
        },
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "TERMINUS_ALLOW_MUTATIONS" in result.stderr
    assert "no requests sent" in result.stderr


def test_render_photo_requires_an_image_url_before_network() -> None:
    result = _run_example("render_photo.py", {})

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Usage:" in result.stderr
    assert "IMAGE_URL" in result.stderr
    assert "no requests sent" in result.stderr


def test_render_photo_builds_a_dithered_full_frame_screen() -> None:
    render_photo = runpy.run_path(PROJECT_ROOT / "examples" / "render_photo.py")

    request = render_photo["build_screen_request"](
        7,
        "https://images.example.test/photo.png?caption=<Hello>&size=large",
        "abc123",
    )

    assert request.to_payload() == {
        "model_id": 7,
        "name": "python_photo_abc123",
        "label": "Python photo abc123",
        "content": """\
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <style>
      html, body { width: 100%; height: 100%; margin: 0; background: white; }
      img { width: 100%; height: 100%; object-fit: contain; display: block; }
    </style>
  </head>
  <body>
    <img src="https://images.example.test/photo.png?caption=&lt;Hello&gt;&amp;size=large" alt="">
  </body>
</html>
""",
        "mode": "dither",
    }


def test_render_photo_rejects_malformed_image_urls_before_network() -> None:
    environment = {
        "TERMINUS_BASE_URL": "https://example.test",
        "TERMINUS_EMAIL": "example@example.test",
        "TERMINUS_PASSWORD": "not-a-real-secret",
        "TERMINUS_ALLOW_MUTATIONS": "1",
    }

    for image_url in (
        "file:///tmp/photo.png",
        "https://example.test/photo image.png",
        "http://example.test:bad/photo.png",
    ):
        result = _run_example("render_photo.py", environment, image_url)

        assert result.returncode == 2
        assert result.stdout == ""
        assert "valid HTTP(S) image URL" in result.stderr
        assert "no requests sent" in result.stderr


def test_render_photo_requires_explicit_mutation_opt_in_before_network() -> None:
    result = _run_example(
        "render_photo.py",
        {
            "TERMINUS_BASE_URL": "https://example.test",
            "TERMINUS_EMAIL": "example@example.test",
            "TERMINUS_PASSWORD": "not-a-real-secret",
            "TERMINUS_ALLOW_MUTATIONS": "0",
        },
        "https://example.test/photo.png",
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "TERMINUS_ALLOW_MUTATIONS" in result.stderr
    assert "no requests sent" in result.stderr
