"""FotoWare API Client - Layer 1: Pure API."""

from fotoware_client.auth import OAuthAuthenticator, OAuthToken
from fotoware_client.client import FotoWareClient
from fotoware_client.constants import DEFAULT_TIMEOUT
from fotoware_client.credentials import credentials_file, load_credentials
from fotoware_client.exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    FotoWareError,
    NotFoundError,
    RateLimitError,
    RetryExhaustedError,
)
from fotoware_client.limits import (
    QUERY_SIZE_BUDGET,
    QUERY_SIZE_LIMIT,
    QueryTooLargeError,
    estimate_query_size,
)
from fotoware_client.models import Archive, Asset, SearchResult
from fotoware_client.retry import NO_RETRY, STANDARD_RETRY, RetryConfig
from fotoware_client.settings import ServerSettings

__version__ = "0.2.0"

__all__ = [
    # Client
    "FotoWareClient",
    # Models
    "Archive",
    "Asset",
    "SearchResult",
    # Auth
    "OAuthAuthenticator",
    "OAuthToken",
    # Exceptions
    "FotoWareError",
    "AuthenticationError",
    "RateLimitError",
    "NotFoundError",
    "APIError",
    "ConfigurationError",
    "RetryExhaustedError",
    "QueryTooLargeError",
    # Installation
    "ServerSettings",
    # Credentials
    "credentials_file",
    "load_credentials",
    # Limits
    "QUERY_SIZE_BUDGET",
    "QUERY_SIZE_LIMIT",
    "estimate_query_size",
    # Retry
    "RetryConfig",
    "STANDARD_RETRY",
    "NO_RETRY",
    # Constants
    "DEFAULT_TIMEOUT",
]
