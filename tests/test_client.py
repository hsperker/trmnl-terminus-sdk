from __future__ import annotations

import base64
import json
import time

import httpx
import pytest
import respx

from trmnl_terminus import Credentials, TerminusClient, TokenPair
from trmnl_terminus.errors import (
    TerminusAuthenticationError,
    TerminusTokenPersistenceError,
    TerminusUnexpectedResponseError,
)

BASE_URL = "https://terminus.example.test"


def _jwt_with_exp(exp: int) -> str:
    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{encode({'alg': 'none'})}.{encode({'exp': exp})}.signature"


class RecordingTokenStore:
    def __init__(self) -> None:
        self.saved: list[TokenPair] = []

    def save(self, tokens: TokenPair) -> None:
        self.saved.append(tokens)


class FailingTokenStore:
    def __init__(self) -> None:
        self.attempts = 0

    def save(self, tokens: TokenPair) -> None:
        self.attempts += 1
        raise OSError("storage unavailable")


@respx.mock
def test_login_uses_raw_authorization_and_does_not_retain_cookie() -> None:
    login = respx.post(f"{BASE_URL}/login").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "access-one", "refresh_token": "refresh-one"},
            headers={"set-cookie": "session=browser-secret; Path=/"},
        )
    )
    models = respx.get(f"{BASE_URL}/api/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    with TerminusClient(
        BASE_URL,
        credentials=Credentials(email="user@example.test", password="secret"),
    ) as client:
        response = client.request("GET", "/api/models")

    assert response.status_code == 200
    assert login.calls[0].request.content == (b'{"login":"user@example.test","password":"secret"}')
    assert models.calls[0].request.headers["Authorization"] == "access-one"
    assert "Cookie" not in models.calls[0].request.headers


@respx.mock
def test_401_recovers_but_does_not_replay_post() -> None:
    playlists = respx.post(f"{BASE_URL}/api/playlists").mock(return_value=httpx.Response(401))
    refresh = respx.post(f"{BASE_URL}/api/jwt").mock(return_value=httpx.Response(401))
    login = respx.post(f"{BASE_URL}/login").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "fresh-access", "refresh_token": "fresh-refresh"},
        )
    )
    models = respx.get(f"{BASE_URL}/api/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    with TerminusClient(
        BASE_URL,
        credentials=Credentials(email="user@example.test", password="secret"),
        tokens=TokenPair(access_token="rejected", refresh_token="stale"),
    ) as client:
        with pytest.raises(TerminusAuthenticationError):
            client.request("POST", "/api/playlists", json={"playlist": {}})
        response = client.request("GET", "/api/models")

    assert response.status_code == 200
    assert playlists.call_count == 1
    assert refresh.call_count == 1
    assert login.call_count == 1
    assert playlists.calls[0].request.headers["Authorization"] == "rejected"
    assert models.calls[0].request.headers["Authorization"] == "fresh-access"


@respx.mock
def test_second_401_is_not_retried() -> None:
    models = respx.get(f"{BASE_URL}/api/models").mock(
        side_effect=[httpx.Response(401), httpx.Response(401)]
    )
    respx.post(f"{BASE_URL}/api/jwt").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "new-access", "refresh_token": "new-refresh"},
        )
    )

    with (
        TerminusClient(
            BASE_URL,
            tokens=TokenPair(access_token="old-access", refresh_token="old-refresh"),
        ) as client,
        pytest.raises(TerminusAuthenticationError),
    ):
        client.request("GET", "/api/models")

    assert models.call_count == 2


@respx.mock
def test_near_expiry_token_refreshes_and_persists_complete_pair() -> None:
    old_access = _jwt_with_exp(int(time.time()) + 30)
    store = RecordingTokenStore()
    refresh = respx.post(f"{BASE_URL}/api/jwt").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "new-access", "refresh_token": "new-refresh"},
        )
    )
    models = respx.get(f"{BASE_URL}/api/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    with TerminusClient(
        BASE_URL,
        tokens=TokenPair(access_token=old_access, refresh_token="old-refresh"),
        token_store=store,
    ) as client:
        client.request("GET", "/api/models")

    assert refresh.call_count == 1
    assert refresh.calls[0].request.headers["Authorization"] == old_access
    assert models.calls[0].request.headers["Authorization"] == "new-access"
    assert len(store.saved) == 1
    assert store.saved[0].access_token.get_secret_value() == "new-access"
    assert store.saved[0].refresh_token.get_secret_value() == "new-refresh"


@respx.mock
def test_token_persistence_failure_blocks_resource_request() -> None:
    store = FailingTokenStore()
    respx.post(f"{BASE_URL}/login").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "new-access", "refresh_token": "new-refresh"},
        )
    )
    models = respx.get(f"{BASE_URL}/api/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    with TerminusClient(
        BASE_URL,
        credentials=Credentials(email="user@example.test", password="secret"),
        token_store=store,
    ) as client:
        with pytest.raises(TerminusTokenPersistenceError):
            client.request("GET", "/api/models")
        with pytest.raises(TerminusTokenPersistenceError):
            client.request("GET", "/api/models")

    assert store.attempts == 2
    assert models.call_count == 0


@respx.mock
def test_500_is_returned_without_retry() -> None:
    models = respx.get(f"{BASE_URL}/api/models").mock(return_value=httpx.Response(500))

    with TerminusClient(
        BASE_URL,
        tokens=TokenPair(access_token="opaque", refresh_token="refresh"),
    ) as client:
        response = client.request("GET", "/api/models")

    assert response.status_code == 500
    assert models.call_count == 1


def test_authenticated_request_rejects_absolute_url() -> None:
    with (
        TerminusClient(
            BASE_URL,
            tokens=TokenPair(access_token="opaque", refresh_token="refresh"),
        ) as client,
        pytest.raises(ValueError, match="relative"),
    ):
        client.request("GET", "https://other.example.test/data")


def test_client_rejects_non_root_base_url() -> None:
    with pytest.raises(ValueError, match="origin root"):
        TerminusClient(
            f"{BASE_URL}/prefix",
            tokens=TokenPair(access_token="opaque", refresh_token="refresh"),
        )


def test_client_rejects_io_after_close() -> None:
    client = TerminusClient(
        BASE_URL,
        tokens=TokenPair(access_token="opaque", refresh_token="refresh"),
    )
    client.close()

    with pytest.raises(RuntimeError, match="closed"):
        client.request("GET", "/api/models")


@respx.mock
def test_malformed_login_response_preserves_response() -> None:
    response = httpx.Response(200, json={"success": "missing tokens"})
    respx.post(f"{BASE_URL}/login").mock(return_value=response)

    with (
        TerminusClient(
            BASE_URL,
            credentials=Credentials(email="user@example.test", password="secret"),
        ) as client,
        pytest.raises(TerminusUnexpectedResponseError) as caught,
    ):
        client.request("GET", "/api/models")

    assert caught.value.response is not None
    assert caught.value.response.status_code == 200
    assert caught.value.response.json() == {"success": "missing tokens"}
    assert caught.value.request_method == "POST"
    assert caught.value.request_url == f"{BASE_URL}/login"
