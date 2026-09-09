from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from .errors import (
    TerminusConflictError,
    TerminusNotFoundError,
    TerminusUnexpectedResponseError,
    TerminusValidationError,
)
from .models import (
    Device,
    DevicePatch,
    Model,
    Playlist,
    PlaylistCreate,
    PlaylistPatch,
    Screen,
    ScreenCreate,
)

if TYPE_CHECKING:
    from os import PathLike

    from .client import TerminusClient


class ModelsManager:
    def __init__(self, client: TerminusClient) -> None:
        self._client = client

    def list(self) -> list[Model]:
        response = self._client.request("GET", "/api/models")
        return _decode_list(response, Model)


class DevicesManager:
    def __init__(self, client: TerminusClient) -> None:
        self._client = client

    def list(self) -> list[Device]:
        response = self._client.request("GET", "/api/devices")
        return _decode_list(response, Device)

    def get(self, device_id: int) -> Device:
        _require_positive_id(device_id)
        response = self._client.request("GET", f"/api/devices/{device_id}")
        return _decode_one(response, Device)

    def update(self, device_id: int, request: DevicePatch) -> Device:
        _require_positive_id(device_id)
        response = self._client.request(
            "PATCH",
            f"/api/devices/{device_id}",
            json={"device": request.to_payload()},
        )
        return _decode_one(response, Device)


class ScreensManager:
    def __init__(self, client: TerminusClient) -> None:
        self._client = client

    def list(self) -> list[Screen]:
        response = self._client.request("GET", "/api/screens")
        return _decode_list(response, Screen)

    def create(self, request: ScreenCreate) -> Screen:
        response = self._client.request(
            "POST",
            "/api/screens",
            json={"screen": request.to_payload()},
        )
        return _decode_one(response, Screen)

    def delete(self, screen_id: int) -> Screen | None:
        _require_positive_id(screen_id)
        response = self._client.request("DELETE", f"/api/screens/{screen_id}")
        return _decode_delete(response, Screen)

    def read_bytes(self, screen: Screen, *, allow_cross_origin: bool = False) -> bytes:
        url = self._image_url(screen, allow_cross_origin=allow_cross_origin)
        response = self._client.request("GET", url, authenticated=False)
        if not response.is_success:
            raise TerminusUnexpectedResponseError(
                "rendered image request returned an unexpected status",
                response=response,
            )
        return response.content

    def download(
        self,
        screen: Screen,
        destination: str | PathLike[str],
        *,
        allow_cross_origin: bool = False,
    ) -> Path:
        content = self.read_bytes(screen, allow_cross_origin=allow_cross_origin)
        target = Path(destination)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
        except BaseException:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
        return target

    def _image_url(self, screen: Screen, *, allow_cross_origin: bool) -> str:
        if screen.uri is None:
            raise TerminusUnexpectedResponseError("screen has no rendered image URI")
        url = urljoin(f"{self._client.base_url}/", screen.uri)
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("rendered image URI must use HTTP(S)")
        if not allow_cross_origin and _origin(url) != _origin(self._client.base_url):
            raise ValueError("cross-origin rendered image URI requires explicit opt-in")
        return url


class PlaylistsManager:
    def __init__(self, client: TerminusClient) -> None:
        self._client = client

    def list(self) -> list[Playlist]:
        response = self._client.request("GET", "/api/playlists")
        return _decode_list(response, Playlist)

    def create(self, request: PlaylistCreate) -> Playlist:
        response = self._client.request(
            "POST",
            "/api/playlists",
            json={"playlist": request.to_payload()},
        )
        return _decode_one(response, Playlist)

    def get(self, playlist_id: int) -> Playlist:
        _require_positive_id(playlist_id)
        response = self._client.request("GET", f"/api/playlists/{playlist_id}")
        return _decode_one(response, Playlist)

    def update(self, playlist_id: int, request: PlaylistPatch) -> Playlist:
        _require_positive_id(playlist_id)
        response = self._client.request(
            "PATCH",
            f"/api/playlists/{playlist_id}",
            json={"playlist": request.to_payload()},
        )
        return _decode_one(response, Playlist)

    def delete(self, playlist_id: int) -> Playlist | None:
        _require_positive_id(playlist_id)
        response = self._client.request("DELETE", f"/api/playlists/{playlist_id}")
        return _decode_delete(response, Playlist)


def _decode_list[ResponseModel: BaseModel](
    response: httpx.Response,
    model: type[ResponseModel],
) -> list[ResponseModel]:
    data = _data(response)
    if not isinstance(data, list):
        raise TerminusUnexpectedResponseError("expected a list in response data", response=response)
    try:
        return [model.model_validate(item) for item in data]
    except ValidationError as error:
        raise TerminusUnexpectedResponseError(
            "response data is incompatible with the SDK model",
            response=response,
        ) from error


def _decode_one[ResponseModel: BaseModel](
    response: httpx.Response,
    model: type[ResponseModel],
) -> ResponseModel:
    data = _data(response)
    if not isinstance(data, dict) or not data:
        raise TerminusUnexpectedResponseError(
            "expected an object in response data",
            response=response,
        )
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise TerminusUnexpectedResponseError(
            "response data is incompatible with the SDK model",
            response=response,
        ) from error


def _decode_delete[ResponseModel: BaseModel](
    response: httpx.Response,
    model: type[ResponseModel],
) -> ResponseModel | None:
    data = _data(response)
    if data == {}:
        return None
    if not isinstance(data, dict):
        raise TerminusUnexpectedResponseError(
            "expected an object in response data",
            response=response,
        )
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise TerminusUnexpectedResponseError(
            "response data is incompatible with the SDK model",
            response=response,
        ) from error


def _data(response: httpx.Response) -> Any:
    _raise_for_status(response)
    try:
        payload = response.json()
    except ValueError as error:
        raise TerminusUnexpectedResponseError(
            "response contained invalid JSON",
            response=response,
        ) from error
    if not isinstance(payload, dict) or "data" not in payload:
        raise TerminusUnexpectedResponseError("response is missing data", response=response)
    return payload["data"]


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    if response.status_code == 404:
        raise TerminusNotFoundError(
            "Terminus returned an error response",
            response=response,
        )
    if response.status_code in {400, 422}:
        raise TerminusValidationError(
            "Terminus returned an error response",
            response=response,
        )
    if response.status_code == 409:
        raise TerminusConflictError(
            "Terminus returned an error response",
            response=response,
        )
    raise TerminusUnexpectedResponseError(
        "Terminus returned an error response",
        response=response,
    )


def _require_positive_id(resource_id: int) -> None:
    if resource_id <= 0:
        raise ValueError("resource ID must be positive")


def _origin(url: str) -> tuple[str, str | None, int | None]:
    parsed = urlsplit(url)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme.lower(), parsed.hostname.lower() if parsed.hostname else None, port
