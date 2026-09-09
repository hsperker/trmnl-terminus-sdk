from __future__ import annotations

import httpx
import pytest
import respx

from trmnl_terminus import (
    Credentials,
    ProblemDetails,
    TerminusAuthenticationError,
    TerminusClient,
    TerminusConflictError,
    TerminusError,
    TerminusNotFoundError,
    TerminusResponseError,
    TerminusTokenPersistenceError,
    TerminusTransportError,
    TerminusUnexpectedResponseError,
    TerminusValidationError,
    TokenPair,
)

BASE_URL = "https://terminus.example.test"


def _client() -> TerminusClient:
    return TerminusClient(
        BASE_URL,
        tokens=TokenPair(access_token="access", refresh_token="refresh"),
    )


def test_public_error_types_are_exported_from_package_root() -> None:
    assert issubclass(TerminusResponseError, TerminusError)
    assert issubclass(TerminusAuthenticationError, TerminusResponseError)
    assert issubclass(TerminusTokenPersistenceError, TerminusError)
    assert issubclass(TerminusNotFoundError, TerminusResponseError)
    assert issubclass(TerminusValidationError, TerminusResponseError)
    assert issubclass(TerminusConflictError, TerminusResponseError)
    assert issubclass(TerminusTransportError, TerminusError)
    assert issubclass(TerminusUnexpectedResponseError, TerminusResponseError)


@respx.mock
def test_validation_response_exposes_structured_problem_and_errors() -> None:
    payload = {
        "type": "https://example.test/problems/invalid",
        "status": 422,
        "title": "Invalid request",
        "detail": "One or more fields are invalid",
        "instance": "/api/devices/23",
        "errors": {"playlist_id": ["is invalid"]},
        "trace_id": "trace-1",
    }
    response = httpx.Response(422, json=payload)
    respx.get(f"{BASE_URL}/api/models").mock(return_value=response)

    with _client() as client, pytest.raises(TerminusValidationError) as caught:
        client.models.list()

    error = caught.value
    assert error.problem == ProblemDetails(
        type="https://example.test/problems/invalid",
        status=422,
        title="Invalid request",
        detail="One or more fields are invalid",
        instance="/api/devices/23",
        extensions={
            "errors": {"playlist_id": ["is invalid"]},
            "trace_id": "trace-1",
        },
    )
    assert error.problem is not None
    assert error.errors is error.problem.extensions["errors"]
    assert error.errors == {"playlist_id": ["is invalid"]}
    assert error.response is not None
    assert error.status_code == 422
    assert error.request_method == "GET"
    assert error.request_url == f"{BASE_URL}/api/models"


@respx.mock
def test_non_object_problem_body_is_ignored_without_replacing_response_error() -> None:
    response = httpx.Response(404, json=["not", "a", "problem"])
    respx.get(f"{BASE_URL}/api/playlists/99").mock(return_value=response)

    with _client() as client, pytest.raises(TerminusNotFoundError) as caught:
        client.playlists.get(99)

    assert caught.value.problem is None
    assert caught.value.response is not None
    assert caught.value.status_code == 404
    assert caught.value.request_method == "GET"
    assert caught.value.request_url == f"{BASE_URL}/api/playlists/99"


@respx.mock
def test_login_failure_exposes_structured_problem() -> None:
    payload = {
        "type": "https://example.test/problems/authentication",
        "status": 401,
        "title": "Authentication failed",
        "detail": "The supplied credentials were rejected",
        "instance": "/login",
        "trace_id": "trace-login",
    }
    response = httpx.Response(401, json=payload)
    respx.post(f"{BASE_URL}/login").mock(return_value=response)

    with (
        TerminusClient(
            BASE_URL,
            credentials=Credentials(email="user@example.test", password="password-secret"),
        ) as client,
        pytest.raises(TerminusAuthenticationError) as caught,
    ):
        client.models.list()

    assert caught.value.problem == ProblemDetails(
        type="https://example.test/problems/authentication",
        status=401,
        title="Authentication failed",
        detail="The supplied credentials were rejected",
        instance="/login",
        extensions={"trace_id": "trace-login"},
    )
    assert caught.value.response is not None
    assert caught.value.request_method == "POST"
    assert caught.value.request_url == f"{BASE_URL}/login"


def test_response_error_text_and_repr_do_not_disclose_request_or_response_secrets() -> None:
    secrets = {
        "password": "recognizable-password-secret",
        "token": "recognizable-token-secret",
        "api_key": "recognizable-api-key-secret",
        "authorization": "recognizable-authorization-secret",
    }
    request = httpx.Request(
        "POST",
        f"{BASE_URL}/login",
        headers={
            "Authorization": secrets["authorization"],
            "X-API-Key": secrets["api_key"],
        },
        json={"password": secrets["password"], "token": secrets["token"]},
    )
    response = httpx.Response(
        401,
        request=request,
        headers={"X-API-Key": secrets["api_key"]},
        json={"detail": "Authentication failed", "token": secrets["token"]},
    )

    error = TerminusAuthenticationError(
        "login failed",
        response=response,
        problem=ProblemDetails(
            detail="Authentication failed",
            extensions={"token": secrets["token"]},
        ),
    )
    rendered = f"{error!s}\n{error!r}"

    assert error.response is response
    for secret in secrets.values():
        assert secret not in rendered
