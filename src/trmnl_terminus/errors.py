from __future__ import annotations

from typing import Any

import httpx


class TerminusError(Exception):
    """Base class for SDK errors."""


class TerminusResponseError(TerminusError):
    def __init__(
        self,
        message: str,
        *,
        response: httpx.Response | None = None,
        problem: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.response = response
        self.problem = problem
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


class TerminusConflictError(TerminusResponseError):
    """Terminus reported a resource conflict."""


class TerminusTransportError(TerminusError):
    """The HTTP transport failed before a response was available."""


class TerminusUnexpectedResponseError(TerminusResponseError):
    """Terminus returned an undocumented status or response shape."""
