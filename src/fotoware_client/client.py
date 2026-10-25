"""FotoWare API client - minimal read-only interface."""

from __future__ import annotations

import logging
import time
from typing import Any, BinaryIO
from urllib.parse import urljoin

import requests

from fotoware_client.auth import OAuthAuthenticator
from fotoware_client.constants import (
    ACCEPT_ASSET,
    ACCEPT_ASSETLIST,
    ACCEPT_COLLECTIONINFO,
    ACCEPT_COLLECTIONLIST,
    ACCEPT_FULL_DESCRIPTOR,
    ACCEPT_JSON,
    DEFAULT_TIMEOUT,
)
from fotoware_client.credentials import load_credentials
from fotoware_client.exceptions import (
    APIError,
    ConfigurationError,
    NotFoundError,
    RateLimitError,
    RetryExhaustedError,
)
from fotoware_client.limits import RequestCounters, check_query_size
from fotoware_client.models import Archive, Asset, SearchResult
from fotoware_client.retry import STANDARD_RETRY, RetryConfig, urllib3_retry
from fotoware_client.settings import ServerSettings

logger = logging.getLogger(__name__)


class FotoWareClient:
    """The FotoWare API, read-only: one method per API call, one request each.

    Nothing is batched, combined or asked again behind the caller's back,
    apart from the retries the :class:`RetryConfig` allows, and what each
    request cost is counted (:meth:`cost_snapshot`). Sequences of calls --
    every page of a search, a rendition from request to file, an archive's
    field labels -- are in :mod:`fotoware_client.extensions`.

    Supports context manager protocol for proper resource cleanup.
    """

    def __init__(
        self,
        tenant_url: str,
        client_id: str,
        client_secret: str,
        *,
        retry_config: RetryConfig = STANDARD_RETRY,
        timeout: int = DEFAULT_TIMEOUT,
        settings: ServerSettings | None = None,
    ) -> None:
        """Initialize FotoWare client.

        Args:
            tenant_url: Full URL to FotoWare tenant (e.g., 'https://fotoware.example.com')
            client_id: OAuth client ID
            client_secret: OAuth client secret
            retry_config: Retry configuration for API requests
            timeout: Default request timeout in seconds
            settings: What the installation sets differently from FotoWeb's
                defaults; see ServerSettings

        Raises:
            ConfigurationError: If tenant_url is invalid or credentials missing
        """
        # Validate tenant URL
        if not tenant_url:
            raise ConfigurationError("tenant_url is required")

        if not (tenant_url.startswith("http://") or tenant_url.startswith("https://")):
            raise ConfigurationError("tenant_url must be absolute (include scheme)")

        # Validate credentials
        if not client_id or not client_secret:
            raise ConfigurationError("client_id and client_secret are required")

        # Normalize tenant URL (remove trailing slash)
        self.tenant_url = tenant_url.rstrip("/")
        self.timeout = timeout
        self.retry_config = retry_config
        self.settings = settings or ServerSettings()
        self._counters = RequestCounters()

        # Build OAuth token URL
        token_url = urljoin(self.tenant_url + "/", self.settings.oauth_token_path.lstrip("/"))

        # Initialize OAuth authenticator
        self._auth = OAuthAuthenticator(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            timeout=timeout,
            retry_observer=self._observe_token_retry,
        )

        # Initialize HTTP session with connection pool sized for parallel requests
        self._session = requests.Session()
        # Configure adapter with larger pool to support 15+ parallel workers
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=urllib3_retry(retry_config, self._counters.count_retry),
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        logger.debug("FotoWare client initialized for tenant: %s", self.tenant_url)

    @classmethod
    def from_env(cls, **kwargs: Any) -> FotoWareClient:
        """A client for the tenant the environment or the credentials file names.

        Reads FOTOWARE_TENANT_URL, FOTOWARE_CLIENT_ID and FOTOWARE_CLIENT_SECRET,
        or, where the environment lacks them, the credentials file; see
        fotoware_client.credentials. Other arguments go to the constructor.

        Raises:
            ConfigurationError: If neither has the credentials, or the file
                may be read by others
        """
        tenant_url, client_id, client_secret = load_credentials()
        return cls(tenant_url, client_id, client_secret, **kwargs)

    def __enter__(self) -> FotoWareClient:
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager and cleanup resources."""
        self.close()

    def close(self) -> None:
        """Close HTTP session and release resources."""
        if self._session:
            self._session.close()
            logger.debug("FotoWare client closed")

    def resolve(self, href: str) -> str:
        """*href* as a full URL: FotoWare answers with paths on the tenant.

        Every call that takes an href from an answer accepts either form.
        """
        return urljoin(self.tenant_url + "/", href)

    def cost_snapshot(self) -> dict[str, object]:
        """What this client has asked of FotoWare so far; see RequestCounters."""
        return self._counters.snapshot()

    def _observe_token_retry(self, event: str, data: dict[str, object]) -> None:
        if event == "retry":
            delay = data.get("delay")
            self._counters.count_retry(
                None, str(data.get("where")), delay if isinstance(delay, float) else 0.0
            )

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers with valid access token.

        Returns:
            Dict with Authorization header
        """
        token = self._auth.get_access_token()
        return {"Authorization": f"Bearer {token}"}

    def _get_json(self, url: str, **kwargs: Any) -> Any:
        """GET *url* and return its JSON; the response is closed either way.

        Raises:
            requests.JSONDecodeError: If the answer is no JSON
            The errors of _request
        """
        response = self._request("GET", url, **kwargs)
        try:
            return response.json()
        finally:
            response.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Make HTTP request with authentication and retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            headers: Additional headers (merged with auth headers)
            timeout: Request timeout in seconds (uses default if None)
            **kwargs: Additional arguments passed to requests

        Returns:
            Response object

        Raises:
            RateLimitError: A 429 that outlasted the retries.
            RetryExhaustedError: A 502, 503 or 504, a connection error, a
                timeout or an answer broken off that outlasted the retries.
            NotFoundError: A 404.
            APIError: Any other error status, which is not retried; a 500
                among them.
        """

        request_headers = self._get_auth_headers()
        if headers:
            request_headers.update(headers)
        self._counters.count_request()
        context = {"method": method, "url": url}
        attempts = self.retry_config.max_attempts
        for attempt in range(1, attempts + 1):
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    headers=request_headers,
                    timeout=timeout or self.timeout,
                    **kwargs,
                )
                break
            # The body broke off after urllib3 had handed the response over.
            # urllib3 retries only up to the headers, so this is repeated here.
            except requests.exceptions.ChunkedEncodingError as e:
                if attempt == attempts:
                    self._counters.count_error()
                    raise RetryExhaustedError(
                        f"FotoWare broke off the answer: {e}",
                        attempts=attempt,
                        last_error=e,
                        context=context,
                    ) from e
                delay = self.retry_config.delay(attempt)
                self._counters.count_retry(None, type(e).__name__, delay)
                time.sleep(delay)
            # urllib3 has retried a connection error or a timeout as often as allowed.
            except (requests.ConnectionError, requests.Timeout) as e:
                self._counters.count_error()
                raise RetryExhaustedError(
                    f"FotoWare unreachable: {e}",
                    attempts=attempts,
                    last_error=e,
                    context=context,
                ) from e
            # Nothing was sent: a malformed URL, say.
            except requests.RequestException as e:
                self._counters.count_error()
                raise APIError(f"Request not sent: {e}", context=context) from e

        if response.status_code < 400:
            return response
        status_code = response.status_code
        if status_code == 410:
            self._counters.count_gone()
        else:
            self._counters.count_error()
        response_text = response.text
        response.close()
        if status_code == 429:
            raise RateLimitError(
                "Rate limit exceeded and retries exhausted",
                context={**context, "attempts": self.retry_config.max_attempts},
            )
        if status_code == 404:
            raise NotFoundError("HTTP 404: not found", context=context)
        if status_code in self.retry_config.retry_on_status:
            raise RetryExhaustedError(
                f"HTTP {status_code} error",
                attempts=self.retry_config.max_attempts,
                context={**context, "status_code": status_code},
            )
        raise APIError(
            f"HTTP {status_code} error",
            status_code=status_code,
            response_text=response_text,
            context=context,
        )

    # --- The API: one method per FotoWare call --------------------------------

    def get_api_descriptor(self) -> dict[str, Any]:
        """The API descriptor (``/fotoweb/me``): the archives' and services' addresses."""
        descriptor: dict[str, Any] = self._get_json(
            self.resolve(self.settings.api_descriptor_path), headers=ACCEPT_FULL_DESCRIPTOR
        )
        return descriptor

    def get_archives(self, archives_href: str) -> list[Archive]:
        """The archives listed at *archives_href* (the descriptor's ``archives``)."""
        data = self._get_json(self.resolve(archives_href), headers=ACCEPT_COLLECTIONLIST)
        archives = []
        for archive_data in data.get("data", []):
            try:
                archives.append(Archive.from_json(archive_data))
            except (KeyError, TypeError) as e:
                logger.warning("Skipping malformed archive: %s", e)
        return archives

    def get_archive(self, archive_href: str) -> dict[str, Any]:
        """One archive's description, which links its metadata editor."""
        archive: dict[str, Any] = self._get_json(
            self.resolve(archive_href), headers=ACCEPT_COLLECTIONINFO
        )
        return archive

    def get_metadata_editor(self, editor_href: str) -> dict[str, Any]:
        """A metadata editor: its regions list every field with id, label and type."""
        editor: dict[str, Any] = self._get_json(self.resolve(editor_href), headers=ACCEPT_JSON)
        return editor

    def search(self, archive_href: str, query: str) -> SearchResult:
        """One page of a search and the link to the next.

        The query is estimated first and refused when it is over the size
        budget, because FotoWare would answer it with a 500 or, worse, an
        empty list (see fotoware_client.limits).

        Raises:
            QueryTooLargeError: If the query is estimated over the budget;
                nothing is sent
        """
        check_query_size(query, self.settings.query_size_budget, self.settings.term_overhead)
        search_url = self.resolve(archive_href).rstrip("/") + "/"
        return self._search_page(search_url, params={"q": query})

    def get_page(self, page_href: str) -> SearchResult:
        """The page a search answer's ``next_href`` points to."""
        return self._search_page(self.resolve(page_href))

    def get_asset(self, asset_href: str) -> Asset:
        """One asset: metadata, renditions, previews. ``Asset.data`` holds the answer."""
        return Asset.from_json(self._get_json(self.resolve(asset_href), headers=ACCEPT_ASSET))

    def request_rendition(self, service_href: str, rendition_href: str) -> str:
        """Ask FotoWare to prepare a rendition; the address of its background task.

        *service_href* is the descriptor's ``services.rendition_request``,
        *rendition_href* one of an asset's ``renditions``.
        """
        response = self._request(
            "POST",
            self.resolve(service_href),
            json={"href": self.resolve(rendition_href)},
            headers={
                "Content-Type": "application/vnd.fotoware.rendition-request+json",
                "Accept": "application/vnd.fotoware.rendition-response+json",
            },
        )
        try:
            task_href = response.headers.get("Location") or response.json().get("href")
        finally:
            response.close()
        if not task_href:
            raise APIError(
                "The rendition request named no task",
                context={"rendition_href": rendition_href},
            )
        return self.resolve(task_href)

    def get_rendition_task(
        self,
        task_href: str,
        destination: BinaryIO | None = None,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> bool:
        """Ask a rendition task once; True when the file is ready.

        While FotoWare prepares the file it answers 202, and this returns
        False. Once it is ready it answers 200 with the file, which is written
        to *destination* when one is given. A task FotoWare has cleaned up
        answers 410 Gone; a new rendition request is the only remedy.

        Raises:
            APIError: 410 when the task is gone, or another failure
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        response = self._request(
            "GET", self.resolve(task_href), timeout=self.settings.download_timeout, stream=True
        )
        try:
            if response.status_code == 202:
                return False
            if destination is not None:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        destination.write(chunk)
                destination.flush()
            return True
        finally:
            response.close()

    def _search_page(self, url: str, *, params: dict[str, str] | None = None) -> SearchResult:
        result = SearchResult.from_json(
            self._get_json(url, params=params, headers=ACCEPT_ASSETLIST)
        )
        self._counters.count_search_page(empty=not result.assets)
        return result
