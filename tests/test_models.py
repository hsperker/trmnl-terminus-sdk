from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from trmnl_terminus import (
    Credentials,
    HtmlSource,
    Model,
    PlaylistPatch,
    Screen,
    ScreenCreate,
    TokenPair,
)


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


def test_playlist_patch_preserves_screen_order() -> None:
    request = PlaylistPatch(name="n", label="l", screen_ids=[3, 1, 2])

    assert request.to_payload()["items"] == [
        {"screen_id": 3},
        {"screen_id": 1},
        {"screen_id": 2},
    ]


def test_response_models_preserve_unknown_fields() -> None:
    model = Model.model_validate(
        {
            "id": 1,
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
            "created_at": "2026-09-08T10:00:00+00:00",
            "updated_at": "2026-09-08T10:00:00+00:00",
            "future_field": "kept",
        }
    )

    assert model.future_field == "kept"
    assert isinstance(model.created_at, datetime)
    assert model.created_at.tzinfo is not None


def test_model_accepts_null_css_from_terminus_response() -> None:
    model = Model.model_validate(
        {
            "id": 1,
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
            "css": None,
            "width": 800,
            "height": 480,
            "created_at": "2026-09-08T10:00:00+00:00",
            "updated_at": "2026-09-08T10:00:00+00:00",
        }
    )

    assert model.css is None


def test_screen_render_metadata_can_be_absent() -> None:
    screen = Screen.model_validate(
        {
            "id": 2,
            "model_id": 1,
            "name": "empty",
            "label": "Empty",
            "created_at": "2026-09-08T10:00:00+00:00",
            "updated_at": "2026-09-08T10:00:00+00:00",
        }
    )

    assert screen.uri is None
    assert screen.size is None


@pytest.mark.parametrize("resource_id", [0, -1])
def test_resource_ids_must_be_positive(resource_id: int) -> None:
    with pytest.raises(ValidationError):
        ScreenCreate(
            model_id=resource_id,
            name="screen",
            label="Screen",
            source=HtmlSource(html="<p>x</p>"),
        )


def test_secret_values_are_redacted() -> None:
    credentials = Credentials(email="user@example.test", password="password-value")
    tokens = TokenPair(access_token="access-value", refresh_token="refresh-value")

    combined = repr(credentials) + repr(tokens) + str(credentials) + str(tokens)
    assert "password-value" not in combined
    assert "access-value" not in combined
    assert "refresh-value" not in combined
