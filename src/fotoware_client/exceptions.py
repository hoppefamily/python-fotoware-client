"""Exception hierarchy for FotoWare client.

All exceptions inherit from FotoWareError for easy catching.
"""

from __future__ import annotations

from typing import Any


class FotoWareError(Exception):
    """Base exception for all FotoWare client errors."""

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        """Initialize error with message and optional context.

        Args:
            message: Human-readable error message
            context: Optional dict with additional error context
        """
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        if self.context:
            ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} ({ctx_str})"
        return self.message


class AuthenticationError(FotoWareError):
    """OAuth authentication failed."""

    pass


class RateLimitError(FotoWareError):
    """API rate limit exceeded (HTTP 429)."""

    pass


class NotFoundError(FotoWareError):
    """Resource not found (HTTP 404)."""

    pass


class APIError(FotoWareError):
    """HTTP error from FotoWare API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_text: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize API error with HTTP details.

        Args:
            message: Human-readable error message
            status_code: HTTP status code
            response_text: Response body text
            context: Optional dict with additional error context
        """
        ctx = context or {}
        if status_code:
            ctx["status_code"] = status_code
        if response_text:
            ctx["response_text"] = response_text[:200]  # Truncate to 200 chars
        super().__init__(message, context=ctx)
        self.status_code = status_code
        self.response_text = response_text


class ConfigurationError(FotoWareError):
    """Invalid client configuration."""

    pass


class RetryExhaustedError(FotoWareError):
    """All retry attempts failed."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_error: Exception | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize retry exhausted error.

        Args:
            message: Human-readable error message
            attempts: Number of attempts made
            last_error: The last exception that occurred
            context: Optional dict with additional error context
        """
        ctx = context or {}
        ctx["attempts"] = attempts
        if last_error:
            ctx["last_error"] = str(last_error)
        super().__init__(message, context=ctx)
        self.attempts = attempts
        self.last_error = last_error
