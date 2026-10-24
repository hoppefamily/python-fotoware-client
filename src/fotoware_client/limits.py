"""What a FotoWare search may ask, and what it cost.

Measured on 2026-10-23 against a FotoWeb 8.1.1223.0 tenant. Check these again
when the server version changes; an installation that differs passes its own
values in fotoware_client.ServerSettings.

- **The answers came in pages of 25**, and ``pageSize`` was ignored. FotoWare
  guarantees no page size ("do not assume the number of elements per page"),
  so the client counts nothing and follows ``paging.next`` until it ends.
- **The cost is per answer, not per asset.** An answer with hits took about
  0.4 s one after another and about 1 s at 15 in parallel, whether it held 1
  asset or 25. An empty answer took 130-220 ms.
- **The search has a size limit, and over it FotoWare answers wrongly.** The
  limit applies to FotoWare's internal translation of the query, about 2,000
  characters ("search query string is limited to 2000 characters" in its
  documentation). Over it the answer is HTTP 500 or, worse, HTTP 200 with an
  empty list, which looks exactly like "no hits". Nothing in the answer tells
  them apart, so the only remedy is not to send such a query:
  :func:`estimate_query_size` estimates it and the client refuses a query over
  :data:`QUERY_SIZE_BUDGET` with :class:`QueryTooLargeError`.

The estimate: every term costs the length of its value plus
:data:`TERM_OVERHEAD`. With 13-digit EANs 40 terms worked and 42 did not, with
2-digit values 52 and 56; both edges sit at about 2,000 by this count. Other
query forms (wildcards, ranges, full text) were not measured.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

from fotoware_client.exceptions import FotoWareError

TERM_OVERHEAD = 33
"""What a term adds to the translated query besides its value (measured default)."""

QUERY_SIZE_LIMIT = 2000
"""Where FotoWare starts to answer wrongly, by :func:`estimate_query_size`."""

QUERY_SIZE_BUDGET = 1500
"""The largest estimate the client sends, kept well below the limit."""

_OPERATORS = frozenset({"AND", "OR", "NOT"})
_TOKEN = re.compile(r"[^\s()]+")


def estimate_query_size(query: str, term_overhead: int = TERM_OVERHEAD) -> int:
    """The size FotoWare's translation of *query* will have, estimated.

    Each term counts the length of its value (after ``field:``, if it has one)
    plus *term_overhead*. Operators, brackets and spaces count nothing.
    """
    size = 0
    for token in _TOKEN.findall(query):
        if token in _OPERATORS:
            continue
        _, _, value = token.rpartition(":")
        size += len(value) + term_overhead
    return size


class QueryTooLargeError(FotoWareError):
    """A search the client refuses to send, because FotoWare would answer it wrongly."""

    def __init__(self, *, estimated_size: int, budget: int) -> None:
        super().__init__(
            "Search query too large for FotoWare: an answer to it may be empty or a 500 "
            "although assets match. Split it into smaller queries.",
            context={"estimated_size": estimated_size, "budget": budget},
        )
        self.estimated_size = estimated_size
        self.budget = budget


def check_query_size(
    query: str, budget: int = QUERY_SIZE_BUDGET, term_overhead: int = TERM_OVERHEAD
) -> None:
    """Raise :class:`QueryTooLargeError` when *query* is estimated over *budget*."""
    size = estimate_query_size(query, term_overhead)
    if size > budget:
        raise QueryTooLargeError(estimated_size=size, budget=budget)


@dataclass
class RequestCounters:
    """What the client has asked of FotoWare so far. Thread-safe.

    ``requests`` counts calls, ``retries`` the repeats on top of them, so the
    HTTP requests sent are their sum. ``search_pages`` and ``empty_search_pages``
    are the search answers among the requests; an empty one is cheap, a full or
    partial one costs the same.
    """

    requests: int = 0
    retries: int = 0
    errors: int = 0
    search_pages: int = 0
    empty_search_pages: int = 0
    retries_by_status: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def count_request(self) -> None:
        with self._lock:
            self.requests += 1

    def count_error(self) -> None:
        with self._lock:
            self.errors += 1

    def count_search_page(self, *, empty: bool) -> None:
        with self._lock:
            self.search_pages += 1
            if empty:
                self.empty_search_pages += 1

    def count_retry(self, status: int | None, error: str | None, delay: float) -> None:
        key = str(status) if status is not None else (error or "network")
        with self._lock:
            self.retries += 1
            self.retries_by_status[key] = self.retries_by_status.get(key, 0) + 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "requests": self.requests,
                "retries": self.retries,
                "errors": self.errors,
                "search_pages": self.search_pages,
                "empty_search_pages": self.empty_search_pages,
                "retries_by_status": dict(self.retries_by_status),
            }
