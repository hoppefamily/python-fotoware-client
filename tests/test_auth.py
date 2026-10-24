"""Unit tests for auth module."""

import time
from unittest.mock import Mock, patch

import pytest
import requests

from fotoware_client.auth import OAuthAuthenticator, OAuthToken
from fotoware_client.exceptions import AuthenticationError


class TestOAuthToken:
    """Tests for OAuthToken model."""

    def test_not_expired(self) -> None:
        """Test token that is not expired."""
        future_time = time.time() + 3600  # Expires in 1 hour
        token = OAuthToken(
            access_token="token123",
            token_type="Bearer",
            expires_at=future_time,
        )
        assert not token.is_expired

    def test_expired(self) -> None:
        """Test token that is expired."""
        past_time = time.time() - 60  # Expired 1 minute ago
        token = OAuthToken(
            access_token="token123",
            token_type="Bearer",
            expires_at=past_time,
        )
        assert token.is_expired

    def test_expires_soon(self) -> None:
        """Test token that expires within 30 seconds (considered expired)."""
        soon_time = time.time() + 20  # Expires in 20 seconds
        token = OAuthToken(
            access_token="token123",
            token_type="Bearer",
            expires_at=soon_time,
        )
        assert token.is_expired


class TestOAuthAuthenticator:
    """Tests for OAuthAuthenticator."""

    @patch("fotoware_client.auth.time.sleep", return_value=None)
    @patch.object(OAuthAuthenticator, "_create_session")
    def test_initialization_success(
        self,
        mock_create_session: Mock,
        _mock_sleep: Mock,
    ) -> None:
        """Test successful initialization with token acquisition."""
        session = Mock()
        session.headers = {}
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "access_token": "test_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        session.post.return_value = mock_response
        mock_create_session.return_value = session

        auth = OAuthAuthenticator(
            token_url="https://example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
        )

        assert auth._token is not None
        assert auth._token.access_token == "test_token"
        session.post.assert_called_once()

    @patch("fotoware_client.auth.time.sleep", return_value=None)
    @patch.object(OAuthAuthenticator, "_create_session")
    def test_initialization_failure(
        self,
        mock_create_session: Mock,
        _mock_sleep: Mock,
    ) -> None:
        """Test initialization failure when token request fails."""
        session = Mock()
        session.headers = {}
        session.post.side_effect = requests.exceptions.ConnectionError("Connection error")
        mock_create_session.return_value = session

        with pytest.raises(AuthenticationError) as exc_info:
            OAuthAuthenticator(
                token_url="https://example.com/oauth/token",
                client_id="test_client",
                client_secret="test_secret",
            )

        assert "OAuth token request failed" in str(exc_info.value)

    @patch("fotoware_client.auth.time.sleep", return_value=None)
    @patch.object(OAuthAuthenticator, "_create_session")
    def test_get_access_token_valid(
        self,
        mock_create_session: Mock,
        _mock_sleep: Mock,
    ) -> None:
        """Test getting access token when current token is valid."""
        session = Mock()
        session.headers = {}
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "access_token": "test_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        session.post.return_value = mock_response
        mock_create_session.return_value = session

        auth = OAuthAuthenticator(
            token_url="https://example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
        )

        # Get token (should not refresh)
        token = auth.get_access_token()
        assert token == "test_token"
        assert session.post.call_count == 1  # Only initial call

    @patch("fotoware_client.auth.time.sleep", return_value=None)
    @patch.object(OAuthAuthenticator, "_create_session")
    def test_get_access_token_expired(
        self,
        mock_create_session: Mock,
        _mock_sleep: Mock,
    ) -> None:
        """Test getting access token when current token is expired."""
        session = Mock()
        session.headers = {}
        # First call (initialization)
        first_response = Mock()
        first_response.raise_for_status.return_value = None
        first_response.json.return_value = {
            "access_token": "expired_token",
            "token_type": "Bearer",
            "expires_in": 0,  # Expires immediately
        }

        # Second call (refresh)
        second_response = Mock()
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            "access_token": "new_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        session.post.side_effect = [first_response, second_response]
        mock_create_session.return_value = session

        auth = OAuthAuthenticator(
            token_url="https://example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
        )

        # Token should be expired, trigger refresh
        token = auth.get_access_token()
        assert token == "new_token"
        assert session.post.call_count == 2  # Initial + refresh

    @patch("fotoware_client.auth.time.sleep", return_value=None)
    @patch.object(OAuthAuthenticator, "_create_session")
    def test_invalidate_token(
        self,
        mock_create_session: Mock,
        _mock_sleep: Mock,
    ) -> None:
        """Test invalidating token to force refresh."""
        session = Mock()
        session.headers = {}
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "access_token": "test_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        session.post.return_value = mock_response
        mock_create_session.return_value = session

        auth = OAuthAuthenticator(
            token_url="https://example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
        )

        # Invalidate token
        auth.invalidate()
        assert auth._token is None

        # Next get_access_token should refresh
        token = auth.get_access_token()
        assert token == "test_token"
        assert session.post.call_count == 2  # Initial + refresh

    @patch("fotoware_client.auth.time.sleep", return_value=None)
    @patch.object(OAuthAuthenticator, "_create_session")
    def test_missing_access_token_in_response(
        self,
        mock_create_session: Mock,
        _mock_sleep: Mock,
    ) -> None:
        """Test error when OAuth response is missing access_token."""
        session = Mock()
        session.headers = {}
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "token_type": "Bearer",
            "expires_in": 3600,
            # Missing access_token
        }
        session.post.return_value = mock_response
        mock_create_session.return_value = session

        with pytest.raises(AuthenticationError) as exc_info:
            OAuthAuthenticator(
                token_url="https://example.com/oauth/token",
                client_id="test_client",
                client_secret="test_secret",
            )

        assert "No access_token" in str(exc_info.value)

    @patch("fotoware_client.auth.time.sleep", return_value=None)
    @patch.object(OAuthAuthenticator, "_create_session")
    def test_thread_safety(
        self,
        mock_create_session: Mock,
        _mock_sleep: Mock,
    ) -> None:
        """Test that token refresh is thread-safe."""
        # This is a basic test - full thread safety testing would require
        # more complex concurrent testing
        session = Mock()
        session.headers = {}
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "access_token": "test_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        session.post.return_value = mock_response
        mock_create_session.return_value = session

        auth = OAuthAuthenticator(
            token_url="https://example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
        )

        # Verify lock exists
        assert hasattr(auth, "_lock")
        assert auth._lock is not None
