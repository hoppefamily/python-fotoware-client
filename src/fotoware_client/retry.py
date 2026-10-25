"""Retry policy for FotoWare requests, run by urllib3.

:class:`RetryConfig` says what is retried and how long to wait; urllib3's
``Retry``, mounted on the client's session, does the retrying. That is the
standard for ``requests``, and it honours ``Retry-After``. :class:`ObservedRetry`
adds a callback per retry, because a retry that succeeds is otherwise invisible
to the caller and to the cost counters.

**500 is not retried.** Measured on FotoWeb 8.1.1223.0 (2026-10-23): a 500
never appeared below the query size limit and always reappeared above it, so a
repeat only costs time. 429 and 502/503/504 are transient and are retried.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

from urllib3.connectionpool import ConnectionPool
from urllib3.exceptions import InvalidHeader
from urllib3.response import BaseHTTPResponse
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryConfig:
    """What is retried, and how long to wait in between.

    Attributes:
        max_attempts: Total attempts, the first one included. 1 means no retry.
        base_delay: Wait before the first retry, in seconds; doubled for each
            further one.
        max_delay: Longest wait between two attempts, in seconds.
        retry_on_status: Status codes retried. 500 deliberately not, see above.
        max_retry_after: Longest ``Retry-After`` honoured, in seconds; a longer
            one is cut to this.
        jitter: How much of each wait is left to chance, 0 to 1. With the
            default 0.5 a wait of 2 s becomes 1 to 2 s. Callers running many
            requests in parallel would otherwise all ask again at the same
            moment, just as the server recovers.
            A ``Retry-After`` the server sends is kept as it is.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    retry_on_status: frozenset[int] = field(default_factory=lambda: frozenset({429, 502, 503, 504}))
    max_retry_after: float = 60.0
    jitter: float = 0.5

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.base_delay < 0 or self.max_delay < 0 or self.max_retry_after < 0:
            raise ValueError("delays must be >= 0")
        if not 0 <= self.jitter <= 1:
            raise ValueError(f"jitter must be between 0 and 1, got {self.jitter}")

    def delay(self, retry_number: int) -> float:
        """The wait before retry *retry_number* (1 for the first), with jitter."""
        full = float(min(self.max_delay, self.base_delay * 2 ** (retry_number - 1)))
        return random.uniform(full * (1 - self.jitter), full)


STANDARD_RETRY = RetryConfig()
NO_RETRY = RetryConfig(max_attempts=1)

# Called once per retry, before the wait: the status that caused it (None for a
# network error), the error's type name (None for a status), and the wait in
# seconds.
RetryListener = Callable[[int | None, str | None, float], None]


class ObservedRetry(Retry):
    """urllib3's ``Retry`` with a :class:`RetryConfig`'s waits and a callback.

    A ``Retry-After`` the server sends takes precedence over the backoff, up to
    ``config.max_retry_after``; one that cannot be read is logged and the
    backoff used instead. Only ``config.retry_on_status`` is retried: urllib3
    would also retry a 413, 429 or 503 whenever it carries a ``Retry-After``,
    whatever the status list says; that is switched off.
    """

    RETRY_AFTER_STATUS_CODES = frozenset()

    def __init__(
        self,
        *args: Any,
        config: RetryConfig,
        on_retry: RetryListener | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.config = config
        self.on_retry = on_retry
        # Fixed when the retry is decided, so the wait reported and the wait
        # slept are the same number.
        self.planned_delay: float | None = None

    def new(self, **kw: Any) -> Self:
        kw.setdefault("config", self.config)
        kw.setdefault("on_retry", self.on_retry)
        return super().new(**kw)

    def get_retry_after(self, response: BaseHTTPResponse) -> float | None:
        # urllib3 raises on a header it cannot parse, which would turn a 503
        # into a network error. increment() logs it; here it is just absent.
        try:
            return super().get_retry_after(response)
        except InvalidHeader:
            return None

    def get_backoff_time(self) -> float:
        if self.planned_delay is not None:
            return self.planned_delay
        return self.config.delay(len(self.history))

    def increment(
        self,
        method: str | None = None,
        url: str | None = None,
        response: BaseHTTPResponse | None = None,
        error: Exception | None = None,
        _pool: ConnectionPool | None = None,
        _stacktrace: TracebackType | None = None,
    ) -> Self:
        # Raises MaxRetryError when the budget is spent; nothing to report then.
        retried = super().increment(method, url, response, error, _pool, _stacktrace)
        retry_after = retried.get_retry_after(response) if response is not None else None
        if retry_after is None and response is not None and response.headers.get("Retry-After"):
            logger.warning(
                "Unreadable Retry-After %r, backing off instead",
                response.headers.get("Retry-After"),
            )
        delay = retry_after if retry_after is not None else self.config.delay(len(retried.history))
        # Also for a Retry-After of 0, which urllib3 treats as "not slept" and
        # falls back to the backoff for.
        retried.planned_delay = delay
        if self.on_retry is not None:
            self.on_retry(
                response.status if response is not None else None,
                type(error).__name__ if error is not None else None,
                delay,
            )
        return retried


def urllib3_retry(config: RetryConfig, on_retry: RetryListener | None = None) -> ObservedRetry:
    """The urllib3 policy a :class:`RetryConfig` describes.

    Every method is retried: the client only reads, and its one POST asks for a
    rendition, which FotoWare prepares again without harm. Once the retries are
    spent the last response is returned, not raised, so the client maps its
    status like any other.
    """
    retries = config.max_attempts - 1
    return ObservedRetry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        other=retries,
        allowed_methods=None,
        status_forcelist=config.retry_on_status,
        respect_retry_after_header=True,
        retry_after_max=config.max_retry_after,
        raise_on_status=False,
        config=config,
        on_retry=on_retry,
    )
