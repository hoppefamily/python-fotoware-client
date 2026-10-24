"""What a FotoWare installation may set differently, and the client must follow.

The defaults are what FotoWeb 8.1.1223.0 does out of the box, measured on
2026-10-23 (see fotoware_client.limits). An installation that renamed its
original rendition, serves FotoWeb under another path, prepares renditions
slowly or translates queries differently passes its own ServerSettings.

What is FotoWare's API itself -- the media types, the query syntax, paging
through ``paging.next`` -- is not here: it is the same everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from fotoware_client.limits import QUERY_SIZE_BUDGET, TERM_OVERHEAD


@dataclass(frozen=True)
class ServerSettings:
    """A FotoWare installation's own settings, as the client must know them.

    Attributes:
        oauth_token_path: Where the installation issues OAuth tokens.
        api_descriptor_path: The API descriptor, which links the archives.
        original_rendition_name: The display name of the original-file
            rendition. Asked only when the rendition list does not mark one
            ``original``; display names are configurable and translated.
        download_timeout: Seconds a file download or a rendition may take.
        rendition_poll_interval: First wait, in seconds, while FotoWare
            prepares a rendition; it grows by half each time.
        rendition_poll_interval_max: Longest wait between two polls.
        query_size_budget: Largest estimated query size sent; see
            fotoware_client.limits.
        term_overhead: What a search term adds to FotoWare's translated query
            besides its value; see fotoware_client.limits.
    """

    oauth_token_path: str = "/fotoweb/oauth2/token"
    api_descriptor_path: str = "/fotoweb/me"
    original_rendition_name: str = "Original File"
    download_timeout: int = 120
    rendition_poll_interval: float = 0.1
    rendition_poll_interval_max: float = 2.0
    query_size_budget: int = QUERY_SIZE_BUDGET
    term_overhead: int = TERM_OVERHEAD

    def __post_init__(self) -> None:
        if self.download_timeout <= 0:
            raise ValueError("download_timeout must be positive")
        if not 0 < self.rendition_poll_interval <= self.rendition_poll_interval_max:
            raise ValueError("rendition poll intervals must satisfy 0 < first <= max")
        if self.query_size_budget <= 0 or self.term_overhead < 0:
            raise ValueError("query_size_budget must be positive, term_overhead >= 0")
