from __future__ import annotations

from datetime import time
from typing import Annotated, Any, Protocol

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


_PositiveInt = Annotated[int, Field(strict=True, gt=0)]


class Credentials(_StrictModel):
    email: str
    password: SecretStr

    @field_validator("email")
    @classmethod
    def _email_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("email must not be empty")
        return value


class TokenPair(_StrictModel):
    access_token: SecretStr
    refresh_token: SecretStr

    @field_validator("access_token", "refresh_token")
    @classmethod
    def _token_must_not_be_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("token must not be empty")
        return value


class TokenStore(Protocol):
    def save(self, tokens: TokenPair) -> None: ...


class HtmlSource(_StrictModel):
    html: str

    @field_validator("html")
    @classmethod
    def _html_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("html must not be empty")
        return value


class ScreenCreate(_StrictModel):
    model_id: _PositiveInt
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    source: HtmlSource
    playlist_id: _PositiveInt | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model_id": self.model_id,
            "name": self.name,
            "label": self.label,
            "content": self.source.html,
        }
        if self.playlist_id is not None:
            payload["playlist_id"] = self.playlist_id
        return payload


class PlaylistCreate(_StrictModel):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    screen_ids: list[_PositiveInt] | None = None

    @field_validator("screen_ids")
    @classmethod
    def _screen_ids_must_be_positive(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and any(item <= 0 for item in value):
            raise ValueError("screen IDs must be positive")
        return value

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "label": self.label}
        if self.screen_ids is not None:
            payload["items"] = [{"screen_id": item} for item in self.screen_ids]
        return payload


class PlaylistPatch(PlaylistCreate):
    pass


class DevicePatch(_StrictModel):
    playlist_id: _PositiveInt

    def to_payload(self) -> dict[str, Any]:
        return {"playlist_id": self.playlist_id}


class Device(_ResponseModel):
    id: int
    model_id: int
    playlist_id: int | None
    label: str | None
    mac_address: str | None
    firmware_version: str | None
    wake_reason: str | None
    api_key: SecretStr | None
    firmware_profile: bool
    firmware_update: bool
    firmware_reset: bool
    wifi_band: float
    battery_charge: float
    battery_voltage: float
    wifi_signal: int
    refresh_rate: int
    image_timeout: int
    wake_duration: int
    width: int
    height: int
    charging: bool
    image_cached: bool
    display_compatibility: bool
    display_profile: str
    command: str
    touch_bar: str
    sleep_start_at: time | None
    sleep_stop_at: time | None
    synced_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Model(_ResponseModel):
    id: int
    default_palette_id: int | None
    name: str
    label: str
    description: str | None
    kind: str
    mime_type: str
    colors: int
    bit_depth: int
    rotation: int
    offset_x: int
    offset_y: int
    scale_factor: float
    css: dict[str, Any] | None
    width: int
    height: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Screen(_ResponseModel):
    id: int
    model_id: int
    label: str
    name: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    filename: str | None = None
    mime_type: str | None = None
    bit_depth: int | None = None
    width: int | None = None
    height: int | None = None
    size: int | None = None
    uri: str | None = None


class PlaylistItem(_ResponseModel):
    id: int
    screen_id: int
    position: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Playlist(_ResponseModel):
    id: int
    name: str
    label: str
    current_item_id: int | None
    mode: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    items: list[PlaylistItem]
