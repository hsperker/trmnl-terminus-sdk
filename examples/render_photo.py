from __future__ import annotations

import html
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr

from trmnl_terminus import Credentials, HtmlSource, ScreenCreate, TerminusClient

REQUIRED_ENVIRONMENT = (
    "TERMINUS_BASE_URL",
    "TERMINUS_EMAIL",
    "TERMINUS_PASSWORD",
    "TERMINUS_MODEL_ID",
)


def build_screen_request(model_id: int, image_url: str, suffix: str) -> ScreenCreate:
    escaped_url = html.escape(image_url, quote=True)
    content = f"""\
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <style>
      html, body {{ width: 100%; height: 100%; margin: 0; background: white; }}
      img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
    </style>
  </head>
  <body>
    <img src="{escaped_url}" alt="">
  </body>
</html>
"""
    return ScreenCreate(
        model_id=model_id,
        name=f"python_photo_{suffix}",
        label=f"Python photo {suffix}",
        source=HtmlSource(html=content),
        mode="dither",
    )


def _is_valid_image_url(image_url: str) -> bool:
    if not image_url or any(character.isspace() for character in image_url):
        return False
    try:
        parsed = urlsplit(image_url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and (port is None or port > 0)
    )


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print(
            "Usage: render_photo.py IMAGE_URL [OUTPUT]; no requests sent",
            file=sys.stderr,
        )
        return 2

    image_url = sys.argv[1]
    if not _is_valid_image_url(image_url):
        print(
            "IMAGE_URL must be a valid HTTP(S) image URL; no requests sent",
            file=sys.stderr,
        )
        return 2

    missing = [name for name in REQUIRED_ENVIRONMENT if not os.environ.get(name)]
    if missing:
        print(
            f"Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    try:
        model_id = int(os.environ["TERMINUS_MODEL_ID"])
    except ValueError:
        model_id = 0
    if model_id <= 0:
        print(
            "TERMINUS_MODEL_ID must be a positive integer; no requests sent",
            file=sys.stderr,
        )
        return 2
    if os.environ.get("TERMINUS_ALLOW_MUTATIONS") != "1":
        print(
            "TERMINUS_ALLOW_MUTATIONS must equal 1; no requests sent",
            file=sys.stderr,
        )
        return 2

    destination = Path(sys.argv[2]) if len(sys.argv) == 3 else Path("terminus-photo.png")
    destination.parent.mkdir(parents=True, exist_ok=True)

    credentials = Credentials(
        email=os.environ["TERMINUS_EMAIL"],
        password=SecretStr(os.environ["TERMINUS_PASSWORD"]),
    )
    with TerminusClient(
        os.environ["TERMINUS_BASE_URL"],
        credentials=credentials,
    ) as client:
        suffix = secrets.token_hex(6)
        screen = client.screens.create(build_screen_request(model_id, image_url, suffix))
        try:
            client.screens.download(screen, destination)
        finally:
            client.screens.delete(screen.id)

    print(f"Rendered photo written to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
