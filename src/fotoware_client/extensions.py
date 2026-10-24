"""Sequences of FotoWare API calls, built from the client's API methods alone.

The client (:class:`~fotoware_client.client.FotoWareClient`) makes one request
per method. What takes several -- every page of a search, an archive's field
labels, a rendition from request to file -- is here, and does nothing the
API methods could not do one by one. Every request still shows in the
client's :meth:`~fotoware_client.client.FotoWareClient.cost_snapshot`.
"""

from __future__ import annotations

import io
import logging
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO

from fotoware_client.client import FotoWareClient
from fotoware_client.exceptions import APIError
from fotoware_client.models import Archive, SearchResult

logger = logging.getLogger(__name__)


def list_archives(client: FotoWareClient) -> list[Archive]:
    """The archives the account may read: the descriptor, then its archive list."""
    archives_href = client.get_api_descriptor().get("archives")
    if not isinstance(archives_href, str) or not archives_href:
        raise APIError("The API descriptor names no archive list")
    return client.get_archives(archives_href)


def field_labels(client: FotoWareClient, archive_href: str) -> dict[str, str]:
    """Field id -> label, as the archive's metadata editor names them.

    The archive links its editor, whose regions list every field; a field
    shown in several regions appears once.

    Raises:
        APIError: If the archive links no editor or the editor lists no fields
        KeyError: If the editor's answer has another shape
    """
    editor_href = (client.get_archive(archive_href).get("metadataEditor") or {}).get("href")
    if not editor_href:
        raise APIError(f"Archive {archive_href} links no metadata editor")
    editor = client.get_metadata_editor(editor_href)
    labels: dict[str, str] = {}
    for region in editor["detailRegions"]:
        for entry in region["fields"]:
            field_def = entry["field"]
            labels.setdefault(str(field_def["id"]), str(field_def["label"]))
    if not labels:
        raise APIError(f"The metadata editor of {archive_href} lists no fields")
    return labels


def iter_search(client: FotoWareClient, archive_href: str, query: str) -> Iterator[SearchResult]:
    """Every page of a search, one request each, until the last.

    Raises:
        QueryTooLargeError: If the query is estimated over the size budget
    """
    page = client.search(archive_href, query)
    while True:
        yield page
        if not page.next_href:
            return
        page = client.get_page(page.next_href)


class Rendition:
    """An asset's file as FotoWare prepares it: the original, or a named rendition.

    FotoWare makes a rendition in a background task: the asset lists its
    renditions, a request starts the task, and the task's address answers 202
    until the file is ready and then 200 with the file. Each method below runs
    that sequence once and downloads the file in the same request that finds
    it ready.

    A task FotoWare has already cleaned up answers 410 Gone. Asking it again
    is pointless; the whole sequence is repeated once, with a new task. That
    was seen for a few renditions in a hundred on 2026-10-24 while FotoWare
    was otherwise healthy.

    The waits between polls and the time a rendition may take come from the
    client's ServerSettings.

    Args:
        client: The FotoWare client.
        asset_href: The asset, as a path on the tenant or a full URL.
        name: The rendition's display name, such as "Medium (JPG, 3000px)";
            None for the original file.
    """

    def __init__(self, client: FotoWareClient, asset_href: str, name: str | None = None) -> None:
        self._client = client
        self.asset_href = asset_href
        self.name = name

    def url(self) -> str:
        """The address the prepared file can be fetched from, for a while.

        Fetch it promptly: FotoWare cleans the task up, and then the address
        answers 410 Gone.
        """
        return self._renewing_gone(lambda: self._prepare(None))

    def write_to(self, destination: BinaryIO) -> None:
        """Write the file into an open binary file.

        A 410 arrives before any byte is written, so *destination* is
        untouched when the sequence is repeated.
        """
        self._renewing_gone(lambda: self._prepare(destination))

    def read(self) -> bytes:
        """The file, in memory. For large files prefer write_to or save."""
        buffer = io.BytesIO()
        self.write_to(buffer)
        return buffer.getvalue()

    def save(self, path: str | Path) -> Path:
        """Write the file to *path*; the path written."""
        target = Path(path)
        with target.open("wb") as handle:
            self.write_to(handle)
        return target

    def _prepare(self, destination: BinaryIO | None) -> str:
        """Request the rendition and poll its task until the file is ready."""
        settings = self._client.settings
        rendition_href = self._rendition_href()
        service_href = (self._client.get_api_descriptor().get("services") or {}).get(
            "rendition_request"
        )
        if not service_href:
            raise APIError("The API descriptor names no rendition service")
        task_href = self._client.request_rendition(service_href, rendition_href)
        deadline = time.monotonic() + settings.download_timeout
        wait = settings.rendition_poll_interval
        while not self._client.get_rendition_task(task_href, destination):
            if time.monotonic() + wait > deadline:
                raise APIError(
                    f"Rendition not ready after {settings.download_timeout}s",
                    context={"asset_href": self.asset_href, "task_href": task_href},
                )
            time.sleep(wait)
            wait = min(wait * 1.5, settings.rendition_poll_interval_max)
        return task_href

    def _rendition_href(self) -> str:
        """The href of the rendition asked for among the asset's renditions."""
        renditions = self._client.get_asset(self.asset_href).data.get("renditions", [])
        original_name = self._client.settings.original_rendition_name
        for candidate in renditions:
            if not isinstance(candidate, dict):
                continue
            if self.name is not None:
                wanted = candidate.get("display_name") == self.name
            else:
                wanted = (
                    candidate.get("original") is True
                    or candidate.get("display_name") == original_name
                )
            href = candidate.get("href")
            if wanted and isinstance(href, str) and href:
                return href
        raise APIError(
            f"No {self.name or 'original'} rendition for the asset",
            context={"asset_href": self.asset_href, "renditions": len(renditions)},
        )

    def _renewing_gone[T](self, attempt: Callable[[], T]) -> T:
        try:
            return attempt()
        except APIError as exc:
            if exc.status_code != 410:
                raise
            logger.info("Rendition task gone (410); requesting it anew: %s", self.asset_href)
            return attempt()
