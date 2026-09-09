from __future__ import annotations

from datetime import datetime, time

import pytest
from pydantic import AwareDatetime, SecretStr, ValidationError

from trmnl_terminus import (
    Credentials,
    Device,
    DevicePatch,
    HtmlSource,
    Model,
    PlaylistPatch,
    Screen,
    ScreenCreate,
    TokenPair,
)

DEVICE = {
    "id": 23,
    "model_id": 7,
    "playlist_id": 13,
    "label": "Office display",
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "firmware_version": "1.2.3",
    "wake_reason": "timer",
    "api_key": "device-secret",
    "firmware_profile": True,
    "firmware_update": False,
    "firmware_reset": False,
    "wifi_band": 2.4,
    "battery_charge": 94.5,
    "battery_voltage": 4.08,
    "wifi_signal": -55,
    "refresh_rate": 900,
    "image_timeout": 60,
    "wake_duration": 30,
    "width": 800,
    "height": 480,
    "charging": False,
    "image_cached": True,
    "display_compatibility": True,
    "display_profile": "default",
    "command": "refresh",
    "touch_bar": "enabled",
    "sleep_start_at": "22:00:00",
    "sleep_stop_at": "07:00:00",
    "synced_at": "2026-09-08T10:00:00+00:00",
    "created_at": "2026-09-08T09:00:00+00:00",
    "updated_at": "2026-09-08T10:00:00+00:00",
    "upstream_added": "kept",
}

DEVICE_FIELD_TYPES = {
    "id": int,
    "model_id": int,
    "playlist_id": int | None,
    "label": str | None,
    "mac_address": str | None,
    "firmware_version": str | None,
    "wake_reason": str | None,
    "api_key": SecretStr | None,
    "firmware_profile": bool,
    "firmware_update": bool,
    "firmware_reset": bool,
    "wifi_band": float,
    "battery_charge": float,
    "battery_voltage": float,
    "wifi_signal": int,
    "refresh_rate": int,
    "image_timeout": int,
    "wake_duration": int,
    "width": int,
    "height": int,
    "charging": bool,
    "image_cached": bool,
    "display_compatibility": bool,
    "display_profile": str,
    "command": str,
    "touch_bar": str,
    "sleep_start_at": time | None,
    "sleep_stop_at": time | None,
    "synced_at": AwareDatetime | None,
    "created_at": AwareDatetime,
    "updated_at": AwareDatetime,
}


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


def test_screen_create_serializes_dither_mode() -> None:
    request = ScreenCreate(
        model_id=7,
        name="photo",
        label="Photo",
        source=HtmlSource(html="<img src='photo.jpg'>"),
        mode="dither",
    )

    assert request.to_payload() == {
        "model_id": 7,
        "name": "photo",
        "label": "Photo",
        "content": "<img src='photo.jpg'>",
        "mode": "dither",
    }


def test_screen_create_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        ScreenCreate(
            model_id=7,
            name="photo",
            label="Photo",
            source=HtmlSource(html="<img src='photo.jpg'>"),
            mode="automatic",
        )


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


def test_response_models_reject_naive_timestamps() -> None:
    """A missing offset in a server response must fail instead of becoming local time."""
    with pytest.raises(ValidationError):
        Model.model_validate(
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
                "created_at": "2026-09-08T10:00:00",
                "updated_at": "2026-09-08T10:00:00+00:00",
            }
        )


def test_device_preserves_pinned_response_data_and_redacts_api_key() -> None:
    device = Device.model_validate(DEVICE)

    assert device.id == 23
    assert device.playlist_id == 13
    assert device.sleep_start_at == time(22, 0)
    assert device.created_at.utcoffset() is not None
    assert device.upstream_added == "kept"
    assert "device-secret" not in repr(device)


def test_device_declares_the_complete_pinned_response_schema() -> None:
    assert {
        name: field.annotation for name, field in Device.model_fields.items()
    } == DEVICE_FIELD_TYPES


def test_device_patch_serializes_a_positive_playlist_assignment() -> None:
    assert DevicePatch(playlist_id=13).to_payload() == {"playlist_id": 13}


@pytest.mark.parametrize("playlist_id", [True, 1.0, "1"])
def test_device_patch_rejects_values_that_only_coerce_to_integers(
    playlist_id: object,
) -> None:
    with pytest.raises(ValidationError):
        DevicePatch(playlist_id=playlist_id)


@pytest.mark.parametrize("playlist_id", [0, -1, None])
def test_device_patch_rejects_non_positive_or_null_playlist_ids(
    playlist_id: int | None,
) -> None:
    with pytest.raises(ValidationError):
        DevicePatch(playlist_id=playlist_id)


def test_device_patch_rejects_unknown_request_fields() -> None:
    with pytest.raises(ValidationError):
        DevicePatch(playlist_id=13, label="not supported")


@pytest.mark.parametrize("model_id", [True, 1.0, "1"])
def test_screen_create_rejects_model_ids_that_only_coerce_to_integers(
    model_id: object,
) -> None:
    with pytest.raises(ValidationError):
        ScreenCreate(
            model_id=model_id,
            name="strict-model-id",
            label="Strict model ID",
            source=HtmlSource(html="<h1>strict</h1>"),
        )


@pytest.mark.parametrize("playlist_id", [True, 1.0, "1"])
def test_screen_create_rejects_playlist_ids_that_only_coerce_to_integers(
    playlist_id: object,
) -> None:
    with pytest.raises(ValidationError):
        ScreenCreate(
            model_id=7,
            name="strict-playlist-id",
            label="Strict playlist ID",
            source=HtmlSource(html="<h1>strict</h1>"),
            playlist_id=playlist_id,
        )


@pytest.mark.parametrize("screen_id", [True, 1.0, "1"])
def test_playlist_patch_rejects_screen_ids_that_only_coerce_to_integers(
    screen_id: object,
) -> None:
    with pytest.raises(ValidationError):
        PlaylistPatch(name="strict", label="Strict", screen_ids=[screen_id])


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
