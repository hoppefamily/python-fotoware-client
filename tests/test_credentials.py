"""Where the client's credentials come from without arguments."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fotoware_client import FotoWareClient, load_credentials
from fotoware_client.exceptions import ConfigurationError

NAMES = ("FOTOWARE_TENANT_URL", "FOTOWARE_CLIENT_ID", "FOTOWARE_CLIENT_SECRET")


@pytest.fixture
def no_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "fotoware" / "credentials"


def _write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


def test_the_environment_comes_first(monkeypatch: pytest.MonkeyPatch, no_env: Path) -> None:
    _write(
        no_env, "FOTOWARE_TENANT_URL=file\nFOTOWARE_CLIENT_ID=file\nFOTOWARE_CLIENT_SECRET=file\n"
    )
    for name, value in zip(NAMES, ("https://env.example.com", "id", "secret"), strict=True):
        monkeypatch.setenv(name, value)

    assert load_credentials() == ("https://env.example.com", "id", "secret")


def test_the_file_fills_in_for_the_environment(no_env: Path) -> None:
    _write(
        no_env,
        '# tenant\nFOTOWARE_TENANT_URL=https://fotoware.example.com\nFOTOWARE_CLIENT_ID=id\nFOTOWARE_CLIENT_SECRET="s3cret"\n',
    )

    assert load_credentials() == ("https://fotoware.example.com", "id", "s3cret")


def test_no_credentials_names_both_ways(no_env: Path) -> None:
    with pytest.raises(ConfigurationError) as exc_info:
        load_credentials()

    assert "FOTOWARE_TENANT_URL" in str(exc_info.value)
    assert str(no_env) in str(exc_info.value)


def test_a_file_others_may_read_is_refused(no_env: Path) -> None:
    _write(no_env, "FOTOWARE_TENANT_URL=x\nFOTOWARE_CLIENT_ID=y\nFOTOWARE_CLIENT_SECRET=z\n", 0o644)

    with pytest.raises(ConfigurationError, match="chmod 600"):
        load_credentials()


def test_an_incomplete_file_says_what_it_lacks(no_env: Path) -> None:
    _write(no_env, "FOTOWARE_TENANT_URL=x\n")

    with pytest.raises(ConfigurationError, match="FOTOWARE_CLIENT_ID, FOTOWARE_CLIENT_SECRET"):
        load_credentials()


@patch("fotoware_client.client.OAuthAuthenticator")
def test_from_env_builds_the_client(mock_auth: object, no_env: Path) -> None:
    _write(
        no_env,
        "FOTOWARE_TENANT_URL=https://fotoware.example.com/\nFOTOWARE_CLIENT_ID=id\nFOTOWARE_CLIENT_SECRET=s\n",
    )

    client = FotoWareClient.from_env(timeout=5)

    assert client.tenant_url == "https://fotoware.example.com"
    assert client.timeout == 5
