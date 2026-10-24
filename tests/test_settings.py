"""An installation's own settings reach every request that depends on them."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from fotoware_client import FotoWareClient, QueryTooLargeError, ServerSettings, estimate_query_size
from fotoware_client.extensions import list_archives


def _client(settings: ServerSettings) -> FotoWareClient:
    with patch("fotoware_client.client.OAuthAuthenticator") as auth:
        auth.return_value.get_access_token.return_value = "token"
        client = FotoWareClient("https://fotoware.example.com", "id", "secret", settings=settings)
    return client


def test_the_defaults_are_fotowebs() -> None:
    settings = ServerSettings()

    assert settings.oauth_token_path == "/fotoweb/oauth2/token"
    assert settings.original_rendition_name == "Original File"
    assert settings.query_size_budget == 1500


@patch("fotoware_client.client.OAuthAuthenticator")
def test_the_token_path_is_the_installations(mock_auth: Mock) -> None:
    FotoWareClient(
        "https://fotoware.example.com",
        "id",
        "secret",
        settings=ServerSettings(oauth_token_path="/dam/oauth2/token"),
    )

    assert (
        mock_auth.call_args.kwargs["token_url"] == "https://fotoware.example.com/dam/oauth2/token"
    )


def test_the_api_descriptor_path_is_the_installations() -> None:
    client = _client(ServerSettings(api_descriptor_path="/dam/me"))
    me = Mock()
    me.json.return_value = {"archives": "/dam/me/archives/"}
    archives = Mock()
    archives.json.return_value = {"data": []}

    with patch.object(client, "_request", side_effect=[me, archives]) as request:
        list_archives(client)

    assert request.call_args_list[0].args[1] == "https://fotoware.example.com/dam/me"


def test_the_query_budget_and_term_overhead_are_the_installations() -> None:
    client = _client(ServerSettings(query_size_budget=100, term_overhead=40))

    with patch.object(client, "_request") as request:
        with pytest.raises(QueryTooLargeError) as exc_info:
            client.search("/fotoweb/archives/5000-Products/", "631:1 OR 631:2 OR 631:3")

    request.assert_not_called()
    assert exc_info.value.estimated_size == estimate_query_size("631:1 OR 631:2 OR 631:3", 40)
    assert exc_info.value.budget == 100


@pytest.mark.parametrize(
    "kwargs",
    [
        {"download_timeout": 0},
        {"rendition_poll_interval": 0},
        {"rendition_poll_interval": 3.0, "rendition_poll_interval_max": 2.0},
        {"query_size_budget": 0},
        {"term_overhead": -1},
    ],
)
def test_settings_that_cannot_work_are_refused(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        ServerSettings(**kwargs)  # type: ignore[arg-type]
