"""Unit tests for exceptions module."""

from fotoware_client.exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    FotoWareError,
    NotFoundError,
    RateLimitError,
    RetryExhaustedError,
)


class TestFotoWareError:
    """Tests for base FotoWareError."""

    def test_error_with_message_only(self) -> None:
        """Test error with just a message."""
        error = FotoWareError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.context == {}

    def test_error_with_context(self) -> None:
        """Test error with context dict."""
        error = FotoWareError("Error", context={"key": "value", "count": 42})
        assert "Error" in str(error)
        assert "key=value" in str(error)
        assert "count=42" in str(error)
        assert error.context["key"] == "value"
        assert error.context["count"] == 42


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_inherits_from_base(self) -> None:
        """Test that AuthenticationError inherits from FotoWareError."""
        error = AuthenticationError("Auth failed")
        assert isinstance(error, FotoWareError)


class TestAPIError:
    """Tests for APIError."""

    def test_error_with_status_code(self) -> None:
        """Test API error with status code."""
        error = APIError("Request failed", status_code=404)
        assert error.status_code == 404
        assert "status_code=404" in str(error)

    def test_error_with_response_text(self) -> None:
        """Test API error with response text."""
        response_text = "Not found"
        error = APIError("Request failed", response_text=response_text)
        assert error.response_text == response_text
        assert "response_text=Not found" in str(error)

    def test_error_truncates_long_response(self) -> None:
        """Test that response text is truncated to 200 chars."""
        long_text = "a" * 300
        error = APIError("Request failed", response_text=long_text)
        assert len(error.context["response_text"]) == 200

    def test_error_with_all_details(self) -> None:
        """Test API error with all details."""
        error = APIError(
            "Request failed",
            status_code=500,
            response_text="Internal error",
            context={"url": "https://example.com"},
        )
        assert error.status_code == 500
        assert error.response_text == "Internal error"
        assert error.context["url"] == "https://example.com"


class TestRetryExhaustedError:
    """Tests for RetryExhaustedError."""

    def test_error_with_attempts(self) -> None:
        """Test retry error with attempts count."""
        error = RetryExhaustedError("All retries failed", attempts=3)
        assert error.attempts == 3
        assert "attempts=3" in str(error)

    def test_error_with_last_error(self) -> None:
        """Test retry error with last error."""
        last_error = ValueError("Original error")
        error = RetryExhaustedError("All retries failed", attempts=3, last_error=last_error)
        assert error.last_error is last_error
        assert "last_error=Original error" in str(error)


class TestOtherErrors:
    """Tests for other exception types."""

    def test_rate_limit_error(self) -> None:
        """Test RateLimitError."""
        error = RateLimitError("Rate limit exceeded")
        assert isinstance(error, FotoWareError)

    def test_not_found_error(self) -> None:
        """Test NotFoundError."""
        error = NotFoundError("Resource not found")
        assert isinstance(error, FotoWareError)

    def test_configuration_error(self) -> None:
        """Test ConfigurationError."""
        error = ConfigurationError("Invalid config")
        assert isinstance(error, FotoWareError)
