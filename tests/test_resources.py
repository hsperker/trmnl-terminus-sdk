from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from trmnl_terminus import (
    HtmlSource,
    PlaylistCreate,
    PlaylistPatch,
    Screen,
    ScreenCreate,
    TerminusClient,
    TokenPair,
)
from trmnl_terminus.errors import (
    TerminusNotFoundError,
    TerminusUnexpectedResponseError,
)

BASE_URL = "https://terminus.example.test"
NOW = "2026-09-08T10:00:00+00:00"
MODEL = {
    "id": 7,
    "default_palette_id": None,
    "name": "og",
    "label": "OG",
    "description": None,
    "kind": "terminus",
    "mime_type": "image/png",
    "colors": 2,
    "bit_depth": 1,
    "rotation": 0,
    "offset_x": 0,
    "offset_y": 0,
    "scale_factor": 1.0,
    "css": {},
    "width": 800,
    "height": 480,
    "created_at": NOW,
    "updated_at": NOW,
}
SCREEN = {
    "id": 11,
    "model_id": 7,
    "name": "codex-smoke",
    "label": "Codex Smoke",
    "created_at": NOW,
    "updated_at": NOW,
    "filename": "screen.png",
    "mime_type": "image/png",
    "bit_depth": 1,
    "width": 800,
    "height": 480,
    "size": 123,
    "uri": "/uploads/screen.png",
}
PLAYLIST = {
    "id": 13,
    "name": "codex-playlist",
    "label": "Codex Playlist",
    "current_item_id": None,
    "mode": "automatic",
    "created_at": NOW,
    "updated_at": NOW,
    "items": [
        {
            "id": 17,
            "screen_id": 11,
            "position": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
    ],
}


def _client() -> TerminusClient:
    return TerminusClient(
        BASE_URL,
        tokens=TokenPair(access_token="access", refresh_token="refresh"),
    )


@respx.mock
def test_models_list_decodes_envelope_and_preserves_unknown_fields() -> None:
    payload = {**MODEL, "upstream_added": "kept"}
    route = respx.get(f"{BASE_URL}/api/models").mock(
        return_value=httpx.Response(200, json={"data": [payload]})
    )

    with _client() as client:
        models = client.models.list()

    assert route.call_count == 1
    assert models[0].id == 7
    assert models[0].upstream_added == "kept"


@respx.mock
def test_screen_create_wraps_exact_payload() -> None:
    route = respx.post(f"{BASE_URL}/api/screens").mock(
        return_value=httpx.Response(200, json={"data": SCREEN})
    )

    with _client() as client:
        screen = client.screens.create(
            ScreenCreate(
                model_id=7,
                name="codex-smoke",
                label="Codex Smoke",
                source=HtmlSource(html="<h1>hello</h1>"),
            )
        )

    assert screen.id == 11
    assert json.loads(route.calls[0].request.content) == {
        "screen": {
            "model_id": 7,
            "name": "codex-smoke",
            "label": "Codex Smoke",
            "content": "<h1>hello</h1>",
        }
    }


@respx.mock
def test_screen_get_and_delete_use_native_show_route() -> None:
    show = respx.get(f"{BASE_URL}/api/screens/11").mock(
        return_value=httpx.Response(200, json={"data": SCREEN})
    )
    delete = respx.delete(f"{BASE_URL}/api/screens/11").mock(
        return_value=httpx.Response(200, json={"data": SCREEN})
    )

    with _client() as client:
        fetched = client.screens.get(11)
        deleted = client.screens.delete(11)

    assert fetched.id == 11
    assert deleted is not None and deleted.id == 11
    assert show.call_count == 1
    assert delete.call_count == 1


@respx.mock
def test_playlist_lifecycle_uses_one_request_per_operation() -> None:
    create = respx.post(f"{BASE_URL}/api/playlists").mock(
        return_value=httpx.Response(200, json={"data": {**PLAYLIST, "items": []}})
    )
    show = respx.get(f"{BASE_URL}/api/playlists/13").mock(
        return_value=httpx.Response(200, json={"data": PLAYLIST})
    )
    listing = respx.get(f"{BASE_URL}/api/playlists").mock(
        return_value=httpx.Response(200, json={"data": [PLAYLIST]})
    )
    update = respx.patch(f"{BASE_URL}/api/playlists/13").mock(
        return_value=httpx.Response(200, json={"data": PLAYLIST})
    )
    delete = respx.delete(f"{BASE_URL}/api/playlists/13").mock(
        return_value=httpx.Response(200, json={"data": PLAYLIST})
    )

    with _client() as client:
        created = client.playlists.create(
            PlaylistCreate(name="codex-playlist", label="Codex Playlist")
        )
        fetched = client.playlists.get(13)
        playlists = client.playlists.list()
        updated = client.playlists.update(
            13,
            PlaylistPatch(
                name="codex-playlist",
                label="Codex Playlist",
                screen_ids=[11],
            ),
        )
        deleted = client.playlists.delete(13)

    assert created.id == fetched.id == updated.id == 13
    assert playlists[0].items[0].screen_id == 11
    assert deleted is not None and deleted.id == 13
    assert create.call_count == show.call_count == listing.call_count == 1
    assert update.call_count == delete.call_count == 1
    assert json.loads(update.calls[0].request.content) == {
        "playlist": {
            "name": "codex-playlist",
            "label": "Codex Playlist",
            "items": [{"screen_id": 11}],
        }
    }


@respx.mock
def test_empty_delete_payload_normalizes_to_none() -> None:
    respx.delete(f"{BASE_URL}/api/playlists/99").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )

    with _client() as client:
        assert client.playlists.delete(99) is None


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, json={"wrong": []}), "missing data"),
        (httpx.Response(200, content=b"not-json"), "invalid JSON"),
        (httpx.Response(200, json={"data": {}}), "expected a list"),
    ],
)
@respx.mock
def test_invalid_list_envelopes_fail_loudly(response: httpx.Response, message: str) -> None:
    respx.get(f"{BASE_URL}/api/models").mock(return_value=response)

    with _client() as client, pytest.raises(TerminusUnexpectedResponseError, match=message):
        client.models.list()


@respx.mock
def test_not_found_maps_to_specific_error() -> None:
    respx.get(f"{BASE_URL}/api/screens/99").mock(
        return_value=httpx.Response(
            404,
            json={"type": "about:blank", "status": 404, "title": "Not Found"},
        )
    )

    with _client() as client, pytest.raises(TerminusNotFoundError) as caught:
        client.screens.get(99)

    assert caught.value.status_code == 404


@respx.mock
def test_image_read_is_same_origin_and_unauthenticated() -> None:
    route = respx.get(f"{BASE_URL}/uploads/screen.png").mock(
        return_value=httpx.Response(200, content=b"png-bytes")
    )

    with _client() as client:
        content = client.screens.read_bytes(Screen.model_validate(SCREEN))

    assert content == b"png-bytes"
    assert "Authorization" not in route.calls[0].request.headers
    assert "Cookie" not in route.calls[0].request.headers


def test_cross_origin_image_is_rejected_by_default() -> None:
    screen = {**SCREEN, "uri": "https://images.example.test/screen.png"}

    with _client() as client, pytest.raises(ValueError, match="cross-origin"):
        client.screens.read_bytes(Screen.model_validate(screen))


@respx.mock
def test_image_redirect_is_not_followed() -> None:
    first = respx.get(f"{BASE_URL}/uploads/screen.png").mock(
        return_value=httpx.Response(302, headers={"location": "/uploads/final.png"})
    )
    final = respx.get(f"{BASE_URL}/uploads/final.png").mock(
        return_value=httpx.Response(200, content=b"should-not-be-read")
    )

    with _client() as client, pytest.raises(TerminusUnexpectedResponseError):
        client.screens.read_bytes(Screen.model_validate(SCREEN))

    assert first.call_count == 1
    assert final.call_count == 0


@respx.mock
def test_download_replaces_destination_after_success(tmp_path: Path) -> None:
    destination = tmp_path / "screen.png"
    destination.write_bytes(b"old")
    respx.get(f"{BASE_URL}/uploads/screen.png").mock(
        return_value=httpx.Response(200, content=b"new-image")
    )

    with _client() as client:
        result = client.screens.download(
            Screen.model_validate(SCREEN),
            destination,
        )

    assert result == destination
    assert destination.read_bytes() == b"new-image"
    assert list(tmp_path.iterdir()) == [destination]


@respx.mock
def test_failed_download_preserves_destination(tmp_path: Path) -> None:
    destination = tmp_path / "screen.png"
    destination.write_bytes(b"old")
    respx.get(f"{BASE_URL}/uploads/screen.png").mock(return_value=httpx.Response(500))

    with _client() as client, pytest.raises(TerminusUnexpectedResponseError):
        client.screens.download(
            Screen.model_validate(SCREEN),
            destination,
        )

    assert destination.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [destination]
