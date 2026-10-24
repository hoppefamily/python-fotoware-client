"""Unit tests for client module."""

import io
from unittest.mock import Mock, patch

import pytest

from fotoware_client.client import FotoWareClient
from fotoware_client.exceptions import APIError, ConfigurationError
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


class TestFotoWareClientListArchives:
    """Tests for list_archives method."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_list_archives_success(self, mock_auth: Mock) -> None:
        """Test successful archive listing."""
        mock_auth.return_value.get_access_token.return_value = "token123"

        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )

        # Mock API responses
        me_response = Mock()
        me_response.json.return_value = {"archives": "/fotoweb/me/archives/"}

        archives_response = Mock()
        archives_response.json.return_value = {
            "data": [
                {
                    "href": "https://fotoware.example.com/archive/1",
                    "name": "Archive 1",
                },
                {
                    "href": "https://fotoware.example.com/archive/2",
                    "displayName": "Archive 2",
                },
            ]
        }

        with patch.object(
            client, "_request", side_effect=[me_response, archives_response]
        ) as request:
            archives = client.list_archives()

        assert request.call_args.args[1] == "https://fotoware.example.com/fotoweb/me/archives/"

        assert len(archives) == 2
        assert archives[0].name == "Archive 1"
        assert archives[1].name == "Archive 2"

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_list_archives_no_link(self, mock_auth: Mock) -> None:
        """Test error when no archives link found."""
        mock_auth.return_value.get_access_token.return_value = "token123"

        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )

        me_response = Mock()
        me_response.json.return_value = {}

        with patch.object(client, "_request", return_value=me_response):
            with pytest.raises(APIError) as exc_info:
                client.list_archives()

        assert "No archives link found" in str(exc_info.value)


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
    def test_get_field_labels_resolves_an_archive_path(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        archive = Mock()
        archive.json.return_value = {"metadataEditor": {"href": "/fotoweb/editors/1"}}
        editor = Mock()
        editor.json.return_value = {
            "detailRegions": [{"fields": [{"field": {"id": 631, "label": "EAN"}}]}]
        }

        with patch.object(client, "_request", side_effect=[archive, editor]) as request:
            labels = client.get_field_labels("/fotoweb/archives/5000-Products/")

        assert request.call_args_list[0].args[1] == (
            "https://fotoware.example.com/fotoweb/archives/5000-Products/"
        )
        assert labels == {"631": "EAN"}

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_a_full_url_stays_as_it_is(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        assert client.resolve("https://other.example.com/x") == "https://other.example.com/x"


class TestFotoWareClientSearchAssets:
    """One request per page; the caller follows the pages."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_search_assets_returns_one_page(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        with patch.object(
            client, "_request", return_value=_page("a.jpg", next_href="/fotoweb/archives/5000/?p=1")
        ) as request:
            page = client.search_assets(
                "https://fotoware.example.com/fotoweb/archives/5000", "631:1"
            )

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
            client.search_assets("/fotoweb/archives/5000-Products/", "631:1")

        assert (
            request.call_args.args[1]
            == "https://fotoware.example.com/fotoweb/archives/5000-Products/"
        )

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_iter_search_follows_the_pages(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        pages = [_page("a.jpg", next_href="/fotoweb/archives/5000/?p=1"), _page("b.jpg")]

        with patch.object(client, "_request", side_effect=pages) as request:
            found = [
                asset.filename
                for page in client.iter_search(
                    "https://fotoware.example.com/fotoweb/archives/5000/", "*"
                )
                for asset in page.assets
            ]

        assert found == ["a.jpg", "b.jpg"]
        assert (
            request.call_args.args[1] == "https://fotoware.example.com/fotoweb/archives/5000/?p=1"
        )

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_the_last_page_has_no_next(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        with patch.object(client, "_request", return_value=_page()):
            page = client.search_assets(
                "https://fotoware.example.com/fotoweb/archives/5000/", "631:1"
            )

        assert client.next_page(page) is None

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_a_query_over_the_budget_is_not_sent(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")
        query = " OR ".join(f"631:{4000000000000 + i}" for i in range(42))

        with patch.object(client, "_request") as request:
            with pytest.raises(QueryTooLargeError) as exc_info:
                client.search_assets("https://fotoware.example.com/fotoweb/archives/5000/", query)

        request.assert_not_called()
        assert exc_info.value.budget == 1500

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_search_pages_are_counted(self, mock_auth: Mock) -> None:
        client = FotoWareClient("https://fotoware.example.com", "id", "secret")

        with patch.object(client, "_request", side_effect=[_page("a.jpg"), _page()]):
            client.search_assets("https://fotoware.example.com/fotoweb/archives/5000/", "631:1")
            client.search_assets("https://fotoware.example.com/fotoweb/archives/5000/", "631:2")

        snapshot = client.cost_snapshot()
        assert snapshot["search_pages"] == 2
        assert snapshot["empty_search_pages"] == 1


class TestFotoWareClientGetDownloadUrl:
    """Tests for get_download_url method."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_get_download_url_direct(self, mock_auth: Mock) -> None:
        """Test getting download URL directly from attributes."""
        mock_auth.return_value.get_access_token.return_value = "token123"

        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )

        response = Mock()
        response.json.return_value = {
            "attributes": {"downloadUrl": "https://cdn.example.com/asset.jpg"}
        }

        with patch.object(client, "_request", return_value=response):
            url = client.get_download_url("https://fotoware.example.com/asset/1")

        assert url == "https://cdn.example.com/asset.jpg"

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_get_download_url_via_link(self, mock_auth: Mock) -> None:
        """Test getting download URL via download link."""
        mock_auth.return_value.get_access_token.return_value = "token123"

        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )

        asset_response = Mock()
        asset_response.json.return_value = {
            "_links": {
                "download": {"rel": "download", "href": "https://fotoware.example.com/download/1"}
            }
        }

        download_response = Mock()
        download_response.json.return_value = {"url": "https://cdn.example.com/asset.jpg"}

        with patch.object(client, "_request", side_effect=[asset_response, download_response]):
            url = client.get_download_url("https://fotoware.example.com/asset/1")

        assert url == "https://cdn.example.com/asset.jpg"


class TestFotoWareClientDownloadBytes:
    """Tests for download_bytes method."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_download_bytes_success(self, mock_auth: Mock) -> None:
        """Test successful binary download."""
        mock_auth.return_value.get_access_token.return_value = "token123"

        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )

        response = Mock()
        response.content = b"binary data"

        with patch.object(client, "_request", return_value=response):
            data = client.download_bytes("https://cdn.example.com/asset.jpg")

        assert data == b"binary data"


class TestFotoWareClientDownloadOriginalToFile:
    """Tests for download_original_to_file method."""

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_download_original_to_file_success(self, mock_auth: Mock) -> None:
        """Stream the original rendition into a writable file object."""
        mock_auth.return_value.get_access_token.return_value = "token123"

        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )

        response = Mock()
        response.iter_content.return_value = [b"binary ", b"data"]
        response.close = Mock()
        destination = io.BytesIO()

        with (
            patch.object(
                client,
                "get_rendition_url",
                return_value="https://fotoware.example.com/renditions/file.bin",
            ) as mock_get_rendition_url,
            patch.object(
                client,
                "_request",
                return_value=response,
            ) as mock_request,
        ):
            client.download_original_to_file(
                "https://fotoware.example.com/asset/1.info",
                destination,
                timeout=45,
                chunk_size=4,
            )

        assert destination.getvalue() == b"binary data"
        mock_get_rendition_url.assert_called_once_with(
            "https://fotoware.example.com/asset/1.info",
            timeout=45,
        )
        mock_request.assert_called_once_with(
            "GET",
            "https://fotoware.example.com/renditions/file.bin",
            timeout=45,
            stream=True,
        )
        response.close.assert_called_once()

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_download_rendition_to_file_asks_for_the_named_rendition(self, mock_auth: Mock) -> None:
        mock_auth.return_value.get_access_token.return_value = "token123"
        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )
        response = Mock()
        response.iter_content.return_value = [b"jpeg"]
        destination = io.BytesIO()

        with (
            patch.object(
                client,
                "get_rendition_url",
                return_value="https://fotoware.example.com/renditions/medium.jpg",
            ) as mock_get_rendition_url,
            patch.object(client, "_request", return_value=response),
        ):
            client.download_rendition_to_file(
                "https://fotoware.example.com/asset/1.info",
                destination,
                rendition="Medium (JPG, 3000px)",
                timeout=45,
            )

        assert destination.getvalue() == b"jpeg"
        mock_get_rendition_url.assert_called_once_with(
            "https://fotoware.example.com/asset/1.info",
            timeout=45,
            rendition="Medium (JPG, 3000px)",
        )


class TestFotoWareClientRenditionChoice:
    """get_rendition_url picks the rendition by its display name."""

    @staticmethod
    def asset_response() -> Mock:
        response = Mock()
        response.json.return_value = {
            "renditions": [
                {"display_name": "Original File", "original": True, "href": "/r/orig"},
                {"display_name": "Medium (JPG, 3000px)", "href": "/r/medium"},
            ]
        }
        return response

    @patch("fotoware_client.client.OAuthAuthenticator")
    def test_an_unknown_rendition_is_an_error(self, mock_auth: Mock) -> None:
        mock_auth.return_value.get_access_token.return_value = "token123"
        client = FotoWareClient(
            tenant_url="https://fotoware.example.com",
            client_id="test_client",
            client_secret="test_secret",
        )

        with (
            patch.object(client, "_request", return_value=self.asset_response()),
            pytest.raises(APIError, match="No Large rendition"),
        ):
            client.get_rendition_url("https://fotoware.example.com/asset/1.info", rendition="Large")
