from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from pydantic import SecretStr

from trmnl_terminus import Credentials, HtmlSource, ScreenCreate, TerminusClient

HTML = """\
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <style>
      body { font-family: sans-serif; margin: 3rem; }
      h1 { font-size: 4rem; }
    </style>
  </head>
  <body>
    <h1>Hello from Python</h1>
    <p>Rendered by Terminus.</p>
  </body>
</html>
"""
REQUIRED_ENVIRONMENT = (
    "TERMINUS_BASE_URL",
    "TERMINUS_EMAIL",
    "TERMINUS_PASSWORD",
    "TERMINUS_MODEL_ID",
)


def main() -> int:
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

    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("terminus-screen.png")
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
        screen = client.screens.create(
            ScreenCreate(
                model_id=model_id,
                name=f"python_example_{suffix}",
                label=f"Python example {suffix}",
                source=HtmlSource(html=HTML),
            )
        )
        try:
            client.screens.download(screen, destination)
        finally:
            client.screens.delete(screen.id)

    print(f"Rendered image written to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
