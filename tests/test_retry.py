"""Retries run by urllib3 on the client's session, against a local HTTP server.

A mocked session would skip urllib3 and with it the retries, so these tests
answer real requests with scripted statuses.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest

from fotoware_client.client import FotoWareClient
from fotoware_client.exceptions import APIError, RateLimitError, RetryExhaustedError
from fotoware_client.retry import RetryConfig

# No waiting between attempts, so the tests run fast.
FAST = RetryConfig(base_delay=0.0)


class _Server:
    def __init__(self) -> None:
        # (status, headers); a status of -1 sends a 200 whose body breaks off.
        self.script: list[tuple[int, dict[str, str]]] = []
        self.hits = 0
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                server.hits += 1
                status, headers = server.script.pop(0) if server.script else (200, {})
                body = b'{"data": [], "paging": null}'
                broken = status == -1
                self.send_response(200 if broken else status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body) + (100 if broken else 0)))
                self.end_headers()
                self.wfile.write(body)
                if broken:
                    self.close_connection = True

            def log_message(self, *args: object) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"


@pytest.fixture
def server() -> Iterator[_Server]:
    srv = _Server()
    thread = threading.Thread(target=srv.httpd.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.httpd.shutdown()
    srv.httpd.server_close()


def _client(server: _Server, config: RetryConfig = FAST) -> FotoWareClient:
    with patch("fotoware_client.client.OAuthAuthenticator") as auth:
        auth.return_value.get_access_token.return_value = "token"
        return FotoWareClient(server.url, "id", "secret", retry_config=config)


def _search(client: FotoWareClient, server: _Server) -> None:
    client.search(f"{server.url}/fotoweb/archives/5000/", "631:1")


@pytest.mark.parametrize("status", [502, 503, 504])
def test_a_transient_status_is_retried(server: _Server, status: int) -> None:
    server.script = [(status, {})]
    client = _client(server)

    _search(client, server)

    assert server.hits == 2
    snapshot = client.cost_snapshot()
    assert snapshot["requests"] == 1
    assert snapshot["retries"] == 1
    assert snapshot["retries_by_status"] == {str(status): 1}
    assert snapshot["errors"] == 0


def test_a_500_is_not_retried(server: _Server) -> None:
    """Above the size limit a 500 comes back every time; below it, never."""
    server.script = [(500, {})]
    client = _client(server)

    with pytest.raises(APIError) as exc_info:
        _search(client, server)

    assert exc_info.value.status_code == 500
    assert server.hits == 1
    assert client.cost_snapshot()["errors"] == 1


def test_a_429_waits_as_retry_after_says(server: _Server) -> None:
    """The backoff would be 30 s; Retry-After says 1."""
    server.script = [(429, {"Retry-After": "1"})]
    client = _client(server, RetryConfig(base_delay=30.0))

    started = time.monotonic()
    _search(client, server)
    elapsed = time.monotonic() - started

    assert server.hits == 2
    assert 1.0 <= elapsed < 5.0


def test_an_unreadable_retry_after_falls_back_to_the_backoff(server: _Server) -> None:
    server.script = [(503, {"Retry-After": "soon"})]
    client = _client(server)

    _search(client, server)

    assert server.hits == 2


def test_an_answer_that_breaks_off_is_asked_again(server: _Server) -> None:
    """urllib3 retries only up to the headers; the body is read later."""
    server.script = [(-1, {})]
    client = _client(server)

    _search(client, server)

    assert server.hits == 2
    assert client.cost_snapshot()["retries_by_status"] == {"ChunkedEncodingError": 1}


def test_an_answer_that_keeps_breaking_off_is_exhausted(server: _Server) -> None:
    server.script = [(-1, {})] * 3
    client = _client(server)

    with pytest.raises(RetryExhaustedError) as exc_info:
        _search(client, server)

    assert exc_info.value.attempts == 3
    assert server.hits == 3


def test_a_request_that_cannot_be_sent_is_not_called_unreachable(server: _Server) -> None:
    client = _client(server)

    with pytest.raises(APIError, match="not sent"):
        client.get_asset("ftp://example.com/asset.info")

    assert server.hits == 0


def test_a_429_that_outlasts_the_retries_is_a_rate_limit_error(server: _Server) -> None:
    server.script = [(429, {})] * 3
    client = _client(server)

    with pytest.raises(RateLimitError):
        _search(client, server)

    assert server.hits == 3


def test_a_503_that_outlasts_the_retries_is_exhausted(server: _Server) -> None:
    server.script = [(503, {})] * 3
    client = _client(server)

    with pytest.raises(RetryExhaustedError) as exc_info:
        _search(client, server)

    assert exc_info.value.attempts == 3
    assert server.hits == 3


def test_an_unreachable_server_is_exhausted() -> None:
    with patch("fotoware_client.client.OAuthAuthenticator") as auth:
        auth.return_value.get_access_token.return_value = "token"
        client = FotoWareClient("http://127.0.0.1:9", "id", "secret", retry_config=FAST)

    with pytest.raises(RetryExhaustedError):
        client.search("http://127.0.0.1:9/fotoweb/archives/5000/", "631:1")

    assert client.cost_snapshot()["retries"] == 2


def test_the_waits_double_up_to_the_cap() -> None:
    config = RetryConfig(base_delay=1.0, max_delay=5.0, jitter=0)

    assert [config.delay(n) for n in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 5.0]


def test_jitter_spreads_the_waits_below_the_full_backoff() -> None:
    """Parallel workers must not all ask again at the same moment."""
    config = RetryConfig(base_delay=2.0, max_delay=30.0)

    waits = {config.delay(1) for _ in range(200)}

    assert all(1.0 <= wait <= 2.0 for wait in waits)
    assert len(waits) > 100


def test_jitter_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ValueError):
        RetryConfig(jitter=1.5)


def test_at_least_one_attempt() -> None:
    with pytest.raises(ValueError):
        RetryConfig(max_attempts=0)
