from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field


class ProblemDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    status: int | None = None
    title: str | None = None
    detail: str | None = None
    instance: str | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)


_STANDARD_PROBLEM_MEMBERS = {"type", "status", "title", "detail", "instance"}


def _optional_string(payload: dict[str, Any], name: str) -> str | None:
    value = payload.get(name)
    return value if isinstance(value, str) else None


def _parse_problem_details(response: httpx.Response) -> ProblemDetails | None:
    try:
        payload = response.json()
        if not isinstance(payload, dict):
            return None

        raw_status = payload.get("status")
        status = (
            raw_status
            if isinstance(raw_status, int) and not isinstance(raw_status, bool)
            else None
        )

        return ProblemDetails(
            type=_optional_string(payload, "type"),
            status=status,
            title=_optional_string(payload, "title"),
            detail=_optional_string(payload, "detail"),
            instance=_optional_string(payload, "instance"),
            extensions={
                key: value for key, value in payload.items() if key not in _STANDARD_PROBLEM_MEMBERS
            },
        )
    except Exception:
        return None


class TerminusError(Exception):
    """Base class for SDK errors."""


class TerminusResponseError(TerminusError):
    def __init__(
        self,
        message: str,
        *,
        response: httpx.Response | None = None,
        problem: ProblemDetails | None = None,
    ) -> None:
        super().__init__(message)
        self.response = response
        self.problem = (
            problem
            if problem is not None or response is None
            else _parse_problem_details(response)
        )
        self.status_code = response.status_code if response is not None else None
        self.request_method = None
        self.request_url = None
        if response is not None:
            try:
                self.request_method = response.request.method
                self.request_url = str(response.request.url)
            except RuntimeError:
                pass


class TerminusAuthenticationError(TerminusResponseError):
    """Authentication could not be established or recovered."""


class TerminusTokenPersistenceError(TerminusError):
    """A rotated token pair could not be persisted."""


class TerminusNotFoundError(TerminusResponseError):
    """A requested resource does not exist."""


class TerminusValidationError(TerminusResponseError):
    """Terminus rejected a resource payload."""

    @property
    def errors(self) -> Any | None:
        if self.problem is None:
            return None
        return self.problem.extensions.get("errors")


class TerminusConflictError(TerminusResponseError):
    """Terminus reported a resource conflict."""


class TerminusTransportError(TerminusError):
    """The HTTP transport failed before a response was available."""


class TerminusUnexpectedResponseError(TerminusResponseError):
    """Terminus returned an undocumented status or response shape."""
