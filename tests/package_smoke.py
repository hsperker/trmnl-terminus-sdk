from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from pydantic import SecretStr

import trmnl_terminus
from trmnl_terminus import TerminusClient, TokenPair


def main() -> None:
    assert version("trmnl-terminus")
    assert Path(trmnl_terminus.__file__).with_name("py.typed").is_file()

    expected_exports = {
        "Credentials",
        "Device",
        "DevicePatch",
        "HtmlSource",
        "Model",
        "Playlist",
        "PlaylistCreate",
        "PlaylistPatch",
        "ProblemDetails",
        "Screen",
        "ScreenCreate",
        "TerminusClient",
        "TerminusError",
        "TokenPair",
        "TokenStore",
    }
    assert expected_exports <= set(trmnl_terminus.__all__)

    tokens = TokenPair(
        access_token=SecretStr("package-smoke-access"),
        refresh_token=SecretStr("package-smoke-refresh"),
    )
    with TerminusClient("https://example.test", tokens=tokens) as client:
        assert client.base_url == "https://example.test"
        assert client.devices is not None
        assert client.models is not None
        assert client.screens is not None
        assert client.playlists is not None

    print("PASS: installed package exports the documented typed client")


if __name__ == "__main__":
    main()
