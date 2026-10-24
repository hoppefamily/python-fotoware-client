"""FotoWare API client - minimal read-only interface."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any, BinaryIO
from urllib.parse import urljoin

import requests

from fotoware_client.auth import OAuthAuthenticator
from fotoware_client.constants import (
    ACCEPT_ASSET,
    ACCEPT_ASSETLIST,
    ACCEPT_COLLECTIONINFO,
    ACCEPT_COLLECTIONLIST,
    ACCEPT_DOWNLOAD,
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
    """Minimal read-only client for FotoWare API.

    One method call is one request to FotoWare, and what each cost is counted
    (:meth:`cost_snapshot`); the only exceptions are the rendition downloads,
    which poll until FotoWare has prepared the file. Nothing is batched or
    asked again behind the caller's back, apart from the retries the
    :class:`RetryConfig` allows.

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

    def get_asset(self, asset_href: str) -> Asset:
        """One asset, as FotoWare describes it: metadata, renditions, previews.

        One request. ``Asset.data`` holds the whole answer.

        Raises:
            NotFoundError: If there is no such asset
            APIError: If the request fails
        """
        response = self._request("GET", self.resolve(asset_href), headers=ACCEPT_ASSET)
        asset = Asset.from_json(response.json())
        response.close()
        return asset

    def cost_snapshot(self) -> dict[str, object]:
        """What this client has asked of FotoWare so far; see RequestCounters."""
        return self._counters.snapshot()

    def _observe_token_retry(self, event: str, data: dict[str, object]) -> None:
        if event == "retry":
            delay = data.get("delay")
            self._counters.count_retry(
                None, str(data.get("where")), delay if isinstance(delay, float) else 0.0
            )

    def validate_connection(self) -> None:
        """Validate OAuth credentials and API connectivity.

        Makes a lightweight API call to /fotoweb/me to verify:
        - OAuth token can be generated
        - API endpoint is reachable
        - Credentials are valid

        Raises:
            AuthenticationError: If credentials are invalid (401)
            NotFoundError: If API endpoint returns 404
            APIError: If API is unreachable or returns other errors
        """
        logger.debug("Validating FotoWare API connection")
        me_url = urljoin(self.tenant_url + "/", self.settings.api_descriptor_path.lstrip("/"))

        try:
            response = self._request("GET", me_url, headers=ACCEPT_FULL_DESCRIPTOR)
            response.json()  # Validate response is valid JSON
            response.close()
            logger.debug("FotoWare API connection validated successfully")
        except Exception as e:
            logger.error("FotoWare API connection validation failed: %s", e)
            raise

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers with valid access token.

        Returns:
            Dict with Authorization header
        """
        token = self._auth.get_access_token()
        return {"Authorization": f"Bearer {token}"}

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
        self._counters.count_error()
        status_code = response.status_code
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

    def list_archives(self) -> list[Archive]:
        """List all available archives.

        Returns:
            List of Archive instances

        Raises:
            APIError: If request fails
        """
        logger.debug("Listing archives")

        # The API descriptor names the archives list, as a path on the tenant
        me_url = urljoin(self.tenant_url + "/", self.settings.api_descriptor_path.lstrip("/"))
        response = self._request("GET", me_url, headers=ACCEPT_FULL_DESCRIPTOR)
        archives_path = response.json().get("archives")
        response.close()
        if not isinstance(archives_path, str) or not archives_path:
            raise APIError("No archives link found in API descriptor")
        archives_href = urljoin(self.tenant_url + "/", archives_path)

        # Fetch archives
        response = self._request("GET", archives_href, headers=ACCEPT_COLLECTIONLIST)
        archives_data = response.json()
        response.close()

        # Parse archives
        archives = []
        for archive_data in archives_data.get("data", []):
            try:
                archives.append(Archive.from_json(archive_data))
            except (KeyError, TypeError) as e:
                logger.warning("Skipping malformed archive: %s", e)
                continue

        logger.debug("Found %d archives", len(archives))
        return archives

    def get_field_labels(self, archive_href: str) -> dict[str, str]:
        """Field id -> label, as the archive's metadata editor names them.

        FotoWare keeps the field catalog itself: each archive links a metadata
        editor whose regions list every field with its id, label and type. A
        field shown in several regions appears once here.

        Args:
            archive_href: Full URL to archive (from Archive.href)

        Raises:
            APIError: If a request fails, the archive links no editor or the
                editor lists no fields
            KeyError: If the editor's answer has another shape
        """
        response = self._request("GET", self.resolve(archive_href), headers=ACCEPT_COLLECTIONINFO)
        archive = response.json()
        response.close()
        editor_href = (archive.get("metadataEditor") or {}).get("href")
        if not editor_href:
            raise APIError(f"Archive {archive_href} links no metadata editor")

        editor_url = urljoin(self.tenant_url + "/", editor_href.lstrip("/"))
        response = self._request("GET", editor_url, headers=ACCEPT_JSON)
        editor = response.json()
        response.close()

        labels: dict[str, str] = {}
        for region in editor["detailRegions"]:
            for entry in region["fields"]:
                field_def = entry["field"]
                labels.setdefault(str(field_def["id"]), str(field_def["label"]))
        if not labels:
            raise APIError(f"The metadata editor of {archive_href} lists no fields")
        return labels

    def search_assets(self, archive_href: str, query: str) -> SearchResult:
        """One page of a search: at most 25 assets, and the link to the next page.

        One request. The query is estimated first and refused when it is over
        the size budget, because FotoWare would answer it with a 500 or, worse,
        an empty list (see fotoware_client.limits).

        Args:
            archive_href: The archive, as Archive.href gives it (a path on the
                tenant) or as a full URL
            query: FotoWare search query (e.g., '631:12345' for EAN search)

        Raises:
            QueryTooLargeError: If the query is estimated over the budget;
                nothing is sent
            APIError: If the request fails
        """
        check_query_size(query, self.settings.query_size_budget, self.settings.term_overhead)
        search_url = self.resolve(archive_href).rstrip("/") + "/"
        return self._search_page(search_url, params={"q": query})

    def next_page(self, result: SearchResult) -> SearchResult | None:
        """The page after *result*, or None when it was the last. One request.

        Raises:
            APIError: If the request fails
        """
        if not result.next_href:
            return None
        return self._search_page(self.resolve(result.next_href))

    def iter_search(self, archive_href: str, query: str) -> Iterator[SearchResult]:
        """Every page of a search, one request each, until the last.

        Raises:
            QueryTooLargeError: If the query is estimated over the budget
            APIError: If a request fails
        """
        page: SearchResult | None = self.search_assets(archive_href, query)
        while page is not None:
            yield page
            page = self.next_page(page)

    def _search_page(self, url: str, *, params: dict[str, str] | None = None) -> SearchResult:
        response = self._request("GET", url, params=params, headers=ACCEPT_ASSETLIST)
        result = SearchResult.from_json(response.json())
        response.close()
        self._counters.count_search_page(empty=not result.assets)
        return result

    def get_download_url(self, asset_href: str) -> str | None:
        """Get presigned download URL for an asset.

        FotoWare may require two hops:
        1. GET asset.href -> returns download info
        2. Follow download link -> returns presigned URL

        Args:
            asset_href: Full URL to asset (from Asset.href)

        Returns:
            Presigned download URL, or None if not available

        Raises:
            APIError: If request fails
        """
        logger.debug("Getting download URL for: %s", asset_href)

        try:
            # Get asset with download info
            response = self._request("GET", self.resolve(asset_href), headers=ACCEPT_DOWNLOAD)
            data = response.json()
            response.close()

            # Look for direct URL in attributes
            if "attributes" in data and "downloadUrl" in data["attributes"]:
                url: str = data["attributes"]["downloadUrl"]
                return url

            # Look for download link
            for link in data.get("_links", {}).values():
                if isinstance(link, dict) and link.get("rel") == "download":
                    download_href = link.get("href")
                    if download_href:
                        # Fetch presigned URL
                        response = self._request("GET", download_href, headers=ACCEPT_DOWNLOAD)
                        download_data = response.json()
                        response.close()
                        result_url: str | None = download_data.get("url") or download_data.get(
                            "href"
                        )
                        return result_url

            logger.warning("No download URL found for asset: %s", asset_href)
            return None

        except NotFoundError:
            logger.warning("Asset not found: %s", asset_href)
            return None

    def download_bytes(self, url: str) -> bytes:
        """Download asset binary data from URL.

        Args:
            url: Full download URL (from get_download_url)

        Returns:
            Binary data

        Raises:
            APIError: If download fails
        """
        logger.debug("Downloading from: %s", url)

        response = self._request("GET", url, timeout=self.settings.download_timeout)
        data = response.content
        response.close()

        logger.debug("Downloaded %d bytes", len(data))
        return data

    def get_rendition_url(
        self,
        asset_href: str,
        *,
        timeout: int | None = None,
        rendition: str | None = None,
    ) -> str:
        """Get download URL using FotoWare rendition API.

        This method polls the rendition service until the file is ready and returns
        the URL that can be used to download it. Use this when you need a URL
        (e.g., for Shopware's upload_url_to_media) rather than immediate bytes.

        Workflow:
        1. Get asset metadata and find the original rendition
        2. Submit rendition request to rendition service
        3. Poll until ready (202 Accepted → 200 OK)
        4. Return the ready download URL

        Args:
            asset_href: Full URL to asset (from Asset.href or search results)
            timeout: Total timeout for polling (default: settings.download_timeout)

        Returns:
            URL that can be used to download the original file

        Raises:
            APIError: If rendition request fails or times out
            NotFoundError: If asset or original rendition not found

        Example:
            >>> client = FotoWareClient(...)
            >>> asset_href = "/fotoweb/archives/5000-Products/file.pdf.info"
            >>> download_url = client.get_rendition_url(asset_href)
            >>> # Later: download from that URL
        """

        timeout = timeout or self.settings.download_timeout
        start_time = time.time()

        logger.debug("get_rendition_url: Starting for asset=%s", asset_href)

        # Step 1: Get asset metadata with renditions
        response = self._request("GET", self.resolve(asset_href), headers=ACCEPT_ASSET)
        asset_data = response.json()
        response.close()

        # Step 2: Find the rendition asked for, the original unless named
        renditions = asset_data.get("renditions", [])
        original_rendition = None

        for candidate in renditions:
            if not isinstance(candidate, dict):
                continue
            wanted = (
                candidate.get("display_name") == rendition
                if rendition is not None
                else candidate.get("original") is True
                or candidate.get("display_name") == self.settings.original_rendition_name
            )
            if wanted:
                original_rendition = candidate
                break

        if not original_rendition:
            raise APIError(
                f"No {rendition or 'original'} rendition found for asset",
                context={"asset_href": asset_href, "renditions_count": len(renditions)},
            )

        rendition_href = original_rendition.get("href")
        if not rendition_href:
            raise APIError(
                "Original rendition has no href",
                context={"asset_href": asset_href, "rendition": original_rendition},
            )

        logger.debug(
            "get_rendition_url: Found original rendition href=%s", rendition_href[:80] + "..."
        )

        # Step 3: Get rendition service URL
        me_url = urljoin(self.tenant_url + "/", self.settings.api_descriptor_path.lstrip("/"))
        response = self._request("GET", me_url, headers=ACCEPT_FULL_DESCRIPTOR)
        me_data = response.json()
        response.close()

        rendition_service_url = me_data.get("services", {}).get("rendition_request")
        if not rendition_service_url:
            raise APIError(
                "Rendition service URL not found in API descriptor",
                context={"me_url": me_url},
            )

        # Make URLs absolute
        rendition_service_url = urljoin(self.tenant_url + "/", rendition_service_url.lstrip("/"))
        rendition_href = urljoin(self.tenant_url + "/", rendition_href.lstrip("/"))

        logger.debug("get_rendition_url: Rendition service URL=%s", rendition_service_url)

        # Step 4: Submit rendition request
        request_payload = {"href": rendition_href}
        response = self._request(
            "POST",
            rendition_service_url,
            json=request_payload,
            headers={
                "Content-Type": "application/vnd.fotoware.rendition-request+json",
                "Accept": "application/vnd.fotoware.rendition-response+json",
            },
        )

        # Get polling URL from Location header or response body
        polling_url = response.headers.get("Location")
        if not polling_url:
            response_data = response.json()
            response.close()
            polling_url = response_data.get("href")

        if not polling_url:
            raise APIError(
                "No polling URL returned from rendition request",
                context={"asset_href": asset_href, "response_headers": dict(response.headers)},
            )

        logger.debug("get_rendition_url: Polling URL=%s", polling_url)

        # Step 5: Poll until ready (202 → 200) or timeout
        poll_interval = self.settings.rendition_poll_interval
        max_poll_interval = self.settings.rendition_poll_interval_max

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise APIError(
                    f"Rendition polling timed out after {timeout}s",
                    context={"asset_href": asset_href, "polling_url": polling_url},
                )

            # Poll status. Streamed, so the finished file is not downloaded
            # here and then again by the caller.
            response = self._request("GET", polling_url, stream=True)

            if response.status_code == 200:
                # Download ready! Return the URL instead of downloading
                response.close()
                logger.debug(
                    "get_rendition_url: Ready after %.1fs, returning URL",
                    elapsed,
                )
                return polling_url

            elif response.status_code == 202:
                # Still processing - wait and retry
                response.close()
                logger.debug(
                    "get_rendition_url: Still processing (202), waiting %.1fs", poll_interval
                )
                time.sleep(poll_interval)

                # Exponential backoff
                poll_interval = min(poll_interval * 1.5, max_poll_interval)

            else:
                # Unexpected status
                response.close()
                raise APIError(
                    f"Unexpected status {response.status_code} while polling rendition",
                    status_code=response.status_code,
                    context={"asset_href": asset_href, "polling_url": polling_url},
                )

    def download_original(self, asset_href: str, *, timeout: int | None = None) -> bytes:
        """Download original file using FotoWare rendition API (atomic operation).

        This is the recommended way to download original files. It handles the
        complete rendition workflow:
        1. Get asset metadata and find the original rendition
        2. Submit rendition request to rendition service
        3. Poll until ready (handles 202 Accepted → 200 OK)
        4. Download and return bytes

        The operation is atomic (no URL expiration issues) and handles all
        FotoWare-specific complexity internally.

        Args:
            asset_href: Full URL to asset (from Asset.href or search results)
            timeout: Total timeout for the entire operation (default: settings.download_timeout)

        Returns:
            Original file bytes

        Raises:
            APIError: If rendition request fails or times out
            NotFoundError: If asset or original rendition not found

        Example:
            >>> client = FotoWareClient(...)
            >>> asset_href = "/fotoweb/archives/5000-Products/file.jpg.info"
            >>> pdf_bytes = client.download_original(asset_href)
        """

        timeout = timeout or self.settings.download_timeout
        start_time = time.time()

        logger.debug("download_original: Starting for asset=%s", asset_href)

        # Step 1: Get asset metadata with renditions
        response = self._request("GET", self.resolve(asset_href), headers=ACCEPT_ASSET)
        asset_data = response.json()
        response.close()

        # Step 2: Find the original rendition
        renditions = asset_data.get("renditions", [])
        original_rendition = None

        for rendition in renditions:
            if not isinstance(rendition, dict):
                continue
            if (
                rendition.get("original") is True
                or rendition.get("display_name") == self.settings.original_rendition_name
            ):
                original_rendition = rendition
                break

        if not original_rendition:
            raise APIError(
                "No original rendition found for asset",
                context={"asset_href": asset_href, "renditions_count": len(renditions)},
            )

        rendition_href = original_rendition.get("href")
        if not rendition_href:
            raise APIError(
                "Original rendition has no href",
                context={"asset_href": asset_href, "rendition": original_rendition},
            )

        logger.debug(
            "download_original: Found original rendition href=%s", rendition_href[:80] + "..."
        )

        # Step 3: Get rendition service URL
        me_url = urljoin(self.tenant_url + "/", self.settings.api_descriptor_path.lstrip("/"))
        response = self._request("GET", me_url, headers=ACCEPT_FULL_DESCRIPTOR)
        me_data = response.json()
        response.close()

        rendition_service_url = me_data.get("services", {}).get("rendition_request")
        if not rendition_service_url:
            raise APIError(
                "Rendition service URL not found in API descriptor",
                context={"me_url": me_url},
            )

        # Make rendition service URL absolute
        rendition_service_url = urljoin(self.tenant_url + "/", rendition_service_url.lstrip("/"))
        # Make rendition href absolute
        rendition_href = urljoin(self.tenant_url + "/", rendition_href.lstrip("/"))

        logger.debug("download_original: Rendition service URL=%s", rendition_service_url)

        # Step 4: Submit rendition request
        request_payload = {"href": rendition_href}
        response = self._request(
            "POST",
            rendition_service_url,
            json=request_payload,
            headers={
                "Content-Type": "application/vnd.fotoware.rendition-request+json",
                "Accept": "application/vnd.fotoware.rendition-response+json",
            },
        )

        # Get polling URL from Location header or response body
        polling_url = response.headers.get("Location")
        if not polling_url:
            response_data = response.json()
            response.close()
            polling_url = response_data.get("href")

        if not polling_url:
            raise APIError(
                "No polling URL returned from rendition request",
                context={"asset_href": asset_href, "response_headers": dict(response.headers)},
            )

        logger.debug("download_original: Polling URL=%s", polling_url)

        # Step 5: Poll until ready (202 → 200) or timeout
        poll_interval = self.settings.rendition_poll_interval
        max_poll_interval = self.settings.rendition_poll_interval_max

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise APIError(
                    f"Rendition download timed out after {timeout}s",
                    context={"asset_href": asset_href, "polling_url": polling_url},
                )

            # Poll status; the finished file comes with the 200
            response = self._request("GET", polling_url)

            if response.status_code == 200:
                # Download ready!
                response.close()
                logger.debug(
                    "download_original: Ready after %.1fs, downloading %d bytes",
                    elapsed,
                    len(response.content),
                )
                return response.content

            elif response.status_code == 202:
                # Still processing - wait and retry
                response.close()
                logger.debug(
                    "download_original: Still processing (202), waiting %.1fs", poll_interval
                )
                time.sleep(poll_interval)

                # Exponential backoff
                poll_interval = min(poll_interval * 1.5, max_poll_interval)

            else:
                # Unexpected status
                response.close()
                raise APIError(
                    f"Unexpected status {response.status_code} while polling rendition",
                    status_code=response.status_code,
                    context={"asset_href": asset_href, "polling_url": polling_url},
                )

    def download_original_to_file(
        self,
        asset_href: str,
        destination: BinaryIO,
        *,
        timeout: int | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        """Download an original rendition directly into a writable binary file.

        This keeps authentication and rendition handling in the client layer
        while avoiding a large in-memory `bytes` object in the caller.

        Args:
            asset_href: Full URL to asset (from Asset.href or search results)
            destination: Writable binary file-like object
            timeout: Total timeout for the entire operation (default: settings.download_timeout)
            chunk_size: Streaming chunk size in bytes

        Raises:
            APIError: If rendition request or download fails
            NotFoundError: If asset or original rendition not found
        """
        self._stream_to_file(
            self.get_rendition_url(asset_href, timeout=timeout),
            destination,
            timeout=timeout,
            chunk_size=chunk_size,
        )

    def download_rendition_to_file(
        self,
        asset_href: str,
        destination: BinaryIO,
        *,
        rendition: str,
        timeout: int | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        """Download a named rendition, such as "Medium (JPG, 3000px)", directly
        into a writable binary file.

        Raises:
            APIError: If the asset has no such rendition, or its request or
                download fails
        """
        self._stream_to_file(
            self.get_rendition_url(asset_href, timeout=timeout, rendition=rendition),
            destination,
            timeout=timeout,
            chunk_size=chunk_size,
        )

    def _stream_to_file(
        self,
        download_url: str,
        destination: BinaryIO,
        *,
        timeout: int | None,
        chunk_size: int,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        response = self._request(
            "GET",
            download_url,
            timeout=timeout,
            stream=True,
        )
        try:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    destination.write(chunk)
            destination.flush()
        finally:
            response.close()
