from __future__ import annotations

import base64
import binascii
import json
import ssl
import time
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .errors import (
    TerminusAuthenticationError,
    TerminusTokenPersistenceError,
    TerminusTransportError,
    TerminusUnexpectedResponseError,
)
from .models import Credentials, TokenPair, TokenStore

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=30.0, pool=5.0)


class TerminusClient:
    def __init__(
        self,
        base_url: str,
        *,
        credentials: Credentials | None = None,
        tokens: TokenPair | None = None,
        token_store: TokenStore | None = None,
        timeout: httpx.Timeout | None = None,
        verify: bool | ssl.SSLContext = True,
        refresh_skew_seconds: int = 60,
    ) -> None:
        if refresh_skew_seconds < 0:
            raise ValueError("refresh_skew_seconds must be non-negative")
        self.base_url = _normalize_base_url(base_url)
        self._credentials = credentials
        self._tokens = tokens
        self._token_store = token_store
        self._pending_persistence = False
        self._refresh_skew_seconds = refresh_skew_seconds
        self._http = httpx.Client(
            timeout=timeout or DEFAULT_TIMEOUT,
            verify=verify,
            follow_redirects=False,
        )
        from .resources import ModelsManager, PlaylistsManager, ScreensManager

        self.models = ModelsManager(self)
        self.screens = ScreensManager(self)
        self.playlists = PlaylistsManager(self)
        self._closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._http.close()
            self._closed = True

    def request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **httpx_request_options: Any,
    ) -> httpx.Response:
        self._require_open()
        options = dict(httpx_request_options)

        if authenticated:
            if _is_absolute_url(path):
                raise ValueError("authenticated request path must be relative")
            self._reject_conflicting_auth(options)
            self._prepare_authentication()
            response = self._send_authenticated(method, path, options)
            if response.status_code == 401:
                raise TerminusAuthenticationError(
                    "authentication failed after one recovery attempt",
                    response=response,
                )
            return response

        return self._send(method, self._url(path), options)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("TerminusClient is closed")

    def _reject_conflicting_auth(self, options: dict[str, Any]) -> None:
        if "auth" in options:
            raise ValueError("authenticated requests cannot override auth")
        headers = httpx.Headers(options.get("headers"))
        if "Authorization" in headers or "Cookie" in headers:
            raise ValueError("authenticated requests cannot override authorization or cookies")

    def _prepare_authentication(self) -> None:
        if self._pending_persistence:
            self._persist_tokens()
        if self._tokens is None:
            self._login()
        elif self._access_token_needs_refresh():
            self._refresh_or_login()

    def _send_authenticated(
        self,
        method: str,
        path: str,
        options: dict[str, Any],
    ) -> httpx.Response:
        response = self._send_with_current_token(method, path, options)
        if response.status_code != 401:
            return response

        self._refresh_or_login()
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            raise TerminusAuthenticationError(
                "authentication recovered; mutating request was not replayed",
                response=response,
            )
        return self._send_with_current_token(method, path, options)

    def _send_with_current_token(
        self,
        method: str,
        path: str,
        options: dict[str, Any],
    ) -> httpx.Response:
        if self._tokens is None:
            raise TerminusAuthenticationError("no usable credentials or tokens")
        request_options = dict(options)
        headers = httpx.Headers(request_options.pop("headers", None))
        headers["Authorization"] = self._tokens.access_token.get_secret_value()
        request_options["headers"] = headers
        return self._send(method, self._url(path), request_options)

    def _login(self) -> None:
        if self._credentials is None:
            raise TerminusAuthenticationError("no usable credentials or tokens")
        response = self._send(
            "POST",
            self._url("/login"),
            {
                "json": {
                    "login": self._credentials.email,
                    "password": self._credentials.password.get_secret_value(),
                }
            },
        )
        if not response.is_success:
            raise TerminusAuthenticationError("login failed", response=response)
        self._replace_tokens(response, "login")

    def _refresh_or_login(self) -> None:
        if self._tokens is None:
            self._login()
            return
        response = self._send(
            "POST",
            self._url("/api/jwt"),
            {
                "headers": {
                    "Authorization": self._tokens.access_token.get_secret_value(),
                },
                "json": {
                    "refresh_token": self._tokens.refresh_token.get_secret_value(),
                },
            },
        )
        if response.status_code in {400, 401, 403}:
            if self._credentials is None:
                raise TerminusAuthenticationError(
                    "refresh credentials were rejected",
                    response=response,
                )
            self._login()
            return
        if not response.is_success:
            raise TerminusUnexpectedResponseError("token refresh failed", response=response)
        self._replace_tokens(response, "token refresh")

    def _replace_tokens(self, response: httpx.Response, operation: str) -> None:
        try:
            payload = response.json()
            tokens = TokenPair(
                access_token=payload["access_token"],
                refresh_token=payload["refresh_token"],
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as error:
            raise TerminusUnexpectedResponseError(
                f"{operation} returned an invalid token payload",
                response=response,
            ) from error
        self._tokens = tokens
        self._persist_tokens()

    def _persist_tokens(self) -> None:
        if self._token_store is None or self._tokens is None:
            self._pending_persistence = False
            return
        try:
            self._token_store.save(self._tokens)
        except Exception as error:
            self._pending_persistence = True
            raise TerminusTokenPersistenceError("rotated tokens could not be persisted") from error
        self._pending_persistence = False

    def _access_token_needs_refresh(self) -> bool:
        if self._tokens is None:
            return False
        token = self._tokens.access_token.get_secret_value()
        try:
            payload_part = token.split(".")[1]
            padding = "=" * (-len(payload_part) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_part + padding))
            expires_at = payload.get("exp")
        except (IndexError, ValueError, TypeError, json.JSONDecodeError, binascii.Error):
            return False
        return isinstance(expires_at, int | float) and (
            expires_at <= time.time() + self._refresh_skew_seconds
        )

    def _send(
        self,
        method: str,
        url: str,
        options: dict[str, Any],
    ) -> httpx.Response:
        try:
            response = self._http.request(method, url, **options)
        except httpx.TransportError as error:
            raise TerminusTransportError(f"{method.upper()} request failed") from error
        finally:
            self._http.cookies.clear()
        return response

    def _url(self, path: str) -> str:
        if _is_absolute_url(path):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"


def _normalize_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url must contain only an origin")
    if parsed.path not in {"", "/"}:
        raise ValueError("base_url must point to the origin root")
    return base_url.rstrip("/")


def _is_absolute_url(value: str) -> bool:
    return bool(urlsplit(value).scheme)
