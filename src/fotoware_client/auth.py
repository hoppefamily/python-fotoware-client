"""OAuth 2.0 authentication for FotoWare API."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests
from urllib3.util.ssl_ import create_urllib3_context

from fotoware_client.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


@dataclass
class OAuthToken:
    """OAuth 2.0 access token with expiration tracking.

    Attributes:
        access_token: Bearer token for API requests
        token_type: Token type (usually 'Bearer')
        expires_at: Unix timestamp when token expires
    """

    access_token: str
    token_type: str
    expires_at: float

    @property
    def is_expired(self) -> bool:
        """Check if token is expired or will expire in next 30 seconds."""
        return time.time() >= (self.expires_at - 30)


def _failure_kind(exc: BaseException) -> str:
    """Name the failure the way the log should carry it."""
    if isinstance(exc, requests.exceptions.HTTPError):
        return "server_error"
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    return "network_error"


def _is_transient(exc: BaseException) -> bool:
    """Whether waiting could plausibly change the answer.

    Connection problems, TLS trouble and timeouts: yes. FotoWare answering 5xx or
    429: yes as well -- the credentials are fine, the far end is not.

    A 400 or a 401: no. Seven rounds of backoff would turn a clear answer into
    a ninety second wait and then the same answer, and the run would report a
    network problem where the real one is a credential.

    The read timeout is why this exists. `ConnectTimeout` is a
    `ConnectionError` and was always retried; `ReadTimeout` is not, so FotoWare
    accepting the connection and then staying silent for 30 seconds aborted an
    otherwise healthy run on the first attempt.
    """
    if isinstance(
        exc,
        (
            ConnectionResetError,
            requests.exceptions.ConnectionError,
            requests.exceptions.SSLError,
            requests.exceptions.Timeout,
        ),
    ):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(exc.response, "status_code", None)
        return status is not None and (status >= 500 or status == 429)
    return False


class OAuthAuthenticator:
    """Thread-safe OAuth 2.0 authenticator for FotoWare API.

    Handles token acquisition and automatic refresh when expired.
    """

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        *,
        timeout: int = 30,
        retry_observer: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        """Initialize OAuth authenticator.

        Args:
            token_url: Full URL to OAuth token endpoint
            client_id: OAuth client ID
            client_secret: OAuth client secret
            timeout: Request timeout in seconds

        Raises:
            AuthenticationError: If initial token acquisition fails
        """
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._retry_observer = retry_observer

        self._token: OAuthToken | None = None
        self._lock = threading.Lock()

        # Create session with TLS 1.2 for compatibility with older OpenSSL
        self._session = self._create_session()

        # Acquire initial token
        self._refresh_token()

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> OAuthAuthenticator:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _create_session(self) -> requests.Session:
        """Create requests Session with a custom SSL context.

        This keeps Requests' default TLS negotiation (including TLS 1.3 when
        available) but disables ALPN to avoid HTTP/2 negotiation issues.

        Returns:
            Configured requests Session
        """
        from requests.adapters import HTTPAdapter

        class DefaultTLSNoALPNAdapter(HTTPAdapter):
            """HTTPAdapter that keeps default TLS but disables ALPN."""

            def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
                ctx = create_urllib3_context()
                # Disable ALPN to avoid HTTP/2 negotiation issues
                ctx.set_alpn_protocols([])

                pool_kwargs["ssl_context"] = ctx
                return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

        session = requests.Session()
        session.mount("https://", DefaultTLSNoALPNAdapter())
        return session

    def get_access_token(self) -> str:
        """Get valid access token, refreshing if needed.

        Returns:
            Valid access token

        Raises:
            AuthenticationError: If token refresh fails
        """
        with self._lock:
            if self._token is None or self._token.is_expired:
                self._refresh_token()

            if self._token is None:
                raise AuthenticationError("Failed to acquire access token")

            return self._token.access_token

    def _refresh_token(self) -> None:
        """Refresh OAuth token (must be called with lock held).

        Raises:
            AuthenticationError: If token refresh fails
        """
        logger.debug("Refreshing OAuth token")

        try:
            # Prepare request data
            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }

            # Small delay to mimic initialization timing that made TLS handshakes stable
            time.sleep(0.2)

            # Retry on connection resets (TLS handshake flakiness)
            # This is expected to be extremely rare and mostly CI-only. Prefer waiting
            # a bit longer over failing an otherwise healthy import.
            backoff_delays = [1, 2, 4, 8, 16, 32, 32]
            response = None
            for attempt, delay in enumerate(backoff_delays, start=1):
                try:
                    response = self._session.post(
                        self.token_url,
                        data=data,
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    break
                except (
                    ConnectionResetError,
                    requests.exceptions.RequestException,
                ) as e:
                    if not _is_transient(e):
                        raise
                    kind = _failure_kind(e)
                    payload = {
                        "where": kind,
                        "operation": "oauth_token",
                        "url": self.token_url,
                        "attempt": attempt,
                        "max_attempts": len(backoff_delays),
                        "error": str(e),
                    }
                    if attempt == len(backoff_delays):
                        if self._retry_observer is not None:
                            self._retry_observer(
                                "retry_exhausted",
                                {
                                    **payload,
                                    "failure_kind": kind,
                                    "attempts": attempt,
                                },
                            )
                        raise AuthenticationError(
                            f"OAuth token request failed after retries: {e} "
                            f"(token_url={self.token_url}, client_id={self.client_id})"
                        ) from e
                    jitter = random.uniform(0, 0.5)
                    retry_delay = delay + jitter
                    if self._retry_observer is not None:
                        self._retry_observer(
                            "retry",
                            {
                                **payload,
                                "delay": retry_delay,
                            },
                        )
                    logger.debug(
                        "OAuth token retry scheduled (attempt %d/%d), retrying in %.2fs",
                        attempt,
                        len(backoff_delays),
                        retry_delay,
                    )

                    # Reset the connection pool to avoid reusing any bad state.
                    try:
                        self._session.close()
                    finally:
                        self._session = self._create_session()

                    time.sleep(retry_delay)
            assert response is not None  # for type checkers

            data = response.json()

            # Extract token data
            access_token = data.get("access_token")
            if not access_token:
                raise AuthenticationError("No access_token in OAuth response")

            token_type = data.get("token_type", "Bearer")
            expires_in = data.get("expires_in", 3600)  # Default 1 hour

            # Calculate expiration time
            expires_at = time.time() + expires_in

            self._token = OAuthToken(
                access_token=access_token,
                token_type=token_type,
                expires_at=expires_at,
            )

            logger.debug("OAuth token refreshed successfully (expires in %ds)", expires_in)

        except requests.RequestException as e:
            error_msg = f"OAuth token request failed: {e}"
            logger.error(error_msg)
            raise AuthenticationError(
                error_msg,
                context={"token_url": self.token_url, "client_id": self.client_id},
            ) from e
        except (KeyError, ValueError) as e:
            error_msg = f"Invalid OAuth response: {e}"
            logger.error(error_msg)
            raise AuthenticationError(
                error_msg,
                context={"token_url": self.token_url},
            ) from e

    def invalidate(self) -> None:
        """Invalidate current token to force refresh on next request."""
        with self._lock:
            self._token = None
            logger.debug("OAuth token invalidated")
