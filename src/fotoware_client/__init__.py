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
    PAGE_SIZE,
    QUERY_SIZE_BUDGET,
    QUERY_SIZE_LIMIT,
    QueryTooLargeError,
    estimate_query_size,
)
from fotoware_client.models import Archive, Asset, SearchResult
from fotoware_client.retry import NO_RETRY, STANDARD_RETRY, RetryConfig

__version__ = "0.4.0"

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
    # Credentials
    "credentials_file",
    "load_credentials",
    # Limits
    "PAGE_SIZE",
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
