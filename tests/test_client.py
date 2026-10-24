"""Unit tests for client module."""

import io
from unittest.mock import Mock, patch

import pytest
import requests

from fotoware_client.client import FotoWareClient
from fotoware_client.exceptions import ConfigurationError
from fotoware_client.limits import QueryTooLargeError


class TestFotoWareClientInitialization:
    """Tests for FotoWareClient initialization."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_valid_initialization(self, mock_auth: Mock) -> None:
        """Test successful client initialization."""
        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )

        assert client.tenant_url == "https://fotoware.example.com"
        mock_auth.assert_called_once()

    def test_missing_tenant_url(self) -> None:
        """Test error when tenant_url is missing."""
        with pytest.raises(ConfigurationError) as exc_info:
            FotoWareClient(
                tenant_url="",
                client_id="test_client",
                client_secret="test_secret",
            )
        assert "tenant_url is required" in str(exc_info.value)

    def test_invalid_tenant_url_no_scheme(self) -> None:
        """Test error when tenant_url has no scheme."""
        with pytest.raises(ConfigurationError) as exc_info:
            FotoWareClient(
                tenant_url="fotoware.example.com",
                client_id="test_client",
                client_secret="test_secret",
            )
        assert "must be absolute" in str(exc_info.value)

    def test_missing_client_id(self) -> None:
        """Test error when client_id is missing."""
        with pytest.raises(ConfigurationError) as exc_info:
            FotoWareClient(
                tenant_url="https://fotoware.example.com",
                client_id="",
                client_secret="test_secret",
            )
        assert "client_id and client_secret are required" in str(exc_info.value)

    def test_missing_client_secret(self) -> None:
        """Test error when client_secret is missing."""
        with pytest.raises(ConfigurationError) as exc_info:
            FotoWareClient(
                tenant_url="https://fotoware.example.com",
                client_id="test_client",
                client_secret="",
            )
        assert "client_id and client_secret are required" in str(exc_info.value)

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_trailing_slash_removed(self, mock_auth: Mock) -> None:
        """Test that trailing slash is removed from tenant_url."""
        client = FotoWareClient(
            tenant_url="https://fotoware.example.com/",
            client_id="test_client",
            client_secret="test_secret",
        )
        assert client.tenant_url == "https://fotoware.example.com"


class TestFotoWareClientContextManager:
    """Tests for context manager protocol."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_context_manager(self, mock_auth: Mock) -> None:
        """Test using client as context manager."""
        with FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        ) as client:
            assert client is not None
            assert hasattr(client, "_session")

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_close_method(self, mock_auth: Mock) -> None:
        """Test close method releases resources."""
        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )

        # Mock the session
        mock_session = Mock()
        client._session = mock_session

        client.close()
        mock_session.close.assert_called_once()


def _page(*filenames: str, next_href: str = "") -> Mock:
    response = Mock()
    response.json.return_value = {
        "data": [
            {"href": f"https://fotoware.example.com/asset/{name}", "filename": name, "metadata": {}}
            for name in filenames
        ],
        "paging": {"next": next_href},
    }
    return response


class TestHrefsFromAnswers:
    """FotoWare answers with paths on the tenant; every call takes them."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_get_asset_resolves_a_path(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        response = Mock()
        response.json.return_value = {
            "href": "/fotoweb/archives/5000-Products/a/1.jpg.info",
            "filename": "1.jpg",
            "metadata": {"631": {"value": "111"}},
            "renditions": [{"display_name": "Original File"}],
        }

        with patch.object(client, "_request", return_value=response) as request:
            asset = client.get_asset("/fotoweb/archives/5000-Products/a/1.jpg.info")

        assert request.call_args.args[1] == (
            "https://fotoware.example.com/fotoweb/archives/5000-Products/a/1.jpg.info"
        )
        assert asset.filename == "1.jpg"
        assert asset.data["renditions"] == [{"display_name": "Original File"}]
        response.close.assert_called_once()

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_a_full_url_stays_as_it_is(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        assert client.resolve("https://other.example.com/x") == "https://other.example.com/x"


class TestSearch:
    """One request per page; the caller follows the pages."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_search_returns_one_page(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        with patch.object(
            client, "_request", return_value=_page("a.jpg", next_href="/fotoweb/archives/5000/?p=1")
        ) as request:
            page = client.search("https://fotoware.example.com/fotoweb/archives/5000", "631:1")

        assert [asset.filename for asset in page.assets] == ["a.jpg"]
        assert page.next_href == "/fotoweb/archives/5000/?p=1"
        request.assert_called_once()
        assert request.call_args.args[1] == "https://fotoware.example.com/fotoweb/archives/5000/"
        assert request.call_args.kwargs["params"] == {"q": "631:1"}

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_an_archive_path_is_resolved_on_the_tenant(self, mock_auth: Mock) -> None:
        """list_archives gives each archive's href as a path."""
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        with patch.object(client, "_request", return_value=_page()) as request:
            client.search("/fotoweb/archives/5000-Products/", "631:1")

        assert (
            request.call_args.args[1]
            == "https://fotoware.example.com/fotoweb/archives/5000-Products/"
        )

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_the_last_page_has_no_next(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        with patch.object(client, "_request", return_value=_page()):
            page = client.search("https://fotoware.example.com/fotoweb/archives/5000/", "631:1")

        assert page.next_href is None

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_a_query_over_the_budget_is_not_sent(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        query = " OR ".join(f"631:{4000000000000 + i}" for i in range(42))

        with patch.object(client, "_request") as request:
            with pytest.raises(QueryTooLargeError) as exc_info:
                client.search("https://fotoware.example.com/fotoweb/archives/5000/", query)

        request.assert_not_called()
        assert exc_info.value.budget == 1500

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_search_pages_are_counted(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        with patch.object(client, "_request", side_effect=[_page("a.jpg"), _page()]):
            client.search("https://fotoware.example.com/fotoweb/archives/5000/", "631:1")
            client.search("https://fotoware.example.com/fotoweb/archives/5000/", "631:2")

        snapshot = client.cost_snapshot()
        assert snapshot["search_pages"] == 2
        assert snapshot["empty_search_pages"] == 1


class TestResponsesAreClosed:
    """Every response goes back to the pool, whatever its body holds."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_an_unreadable_answer_is_closed(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        response = Mock()
        response.json.side_effect = requests.JSONDecodeError("invalid json", "", 0)

        with patch.object(client, "_request", return_value=response):
            with pytest.raises(requests.JSONDecodeError):
                client.get_asset("/a/1.jpg.info")

        response.close.assert_called_once()


class TestPages:
    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_get_page_follows_a_next_href(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        with patch.object(client, "_request", return_value=_page("b.jpg")) as request:
            page = client.get_page("/fotoweb/archives/5000/?p=1")

        assert [asset.filename for asset in page.assets] == ["b.jpg"]
        assert (
            request.call_args.args[1] == "https://fotoware.example.com/fotoweb/archives/5000/?p=1"
        )


class TestRenditionCalls:
    """The two API calls a rendition takes: the request, and its task."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_request_rendition_names_the_task(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        answer = Mock(headers={"Location": "/fotoweb/me/background-tasks/1/0/x.jpg"})

        with patch.object(client, "_request", return_value=answer) as request:
            task = client.request_rendition("/fotoweb/services/renditions", "/r/1")

        assert task == "https://fotoware.example.com/fotoweb/me/background-tasks/1/0/x.jpg"
        assert request.call_args.args[:2] == (
            "POST",
            "https://fotoware.example.com/fotoweb/services/renditions",
        )
        assert request.call_args.kwargs["json"] == {"href": "https://fotoware.example.com/r/1"}
        answer.json.assert_not_called()
        answer.close.assert_called_once()

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_a_task_not_ready_writes_nothing(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        answer = Mock(status_code=202)
        destination = io.BytesIO()

        with patch.object(client, "_request", return_value=answer):
            assert client.get_rendition_task("/t/1", destination) is False

        assert destination.getvalue() == b""
        answer.close.assert_called_once()

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_a_ready_task_writes_its_file_in_the_same_request(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        answer = Mock(status_code=200)
        answer.iter_content.return_value = [b"jp", b"eg"]
        destination = io.BytesIO()

        with patch.object(client, "_request", return_value=answer) as request:
            assert client.get_rendition_task("/t/1", destination) is True

        assert destination.getvalue() == b"jpeg"
        assert request.call_count == 1
        assert request.call_args.kwargs["stream"] is True
        answer.close.assert_called_once()

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_a_ready_task_without_destination_downloads_nothing(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        answer = Mock(status_code=200)

        with patch.object(client, "_request", return_value=answer):
            assert client.get_rendition_task("/t/1") is True

        answer.iter_content.assert_not_called()
        answer.close.assert_called_once()
