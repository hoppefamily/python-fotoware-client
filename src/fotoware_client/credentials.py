"""Where a FotoWare client's credentials come from, when the caller does not pass them.

The environment first: FOTOWARE_TENANT_URL, FOTOWARE_CLIENT_ID and
FOTOWARE_CLIENT_SECRET. Where it lacks them, the credentials file,
``$XDG_CONFIG_HOME/fotoware/credentials`` (``~/.config/fotoware/credentials``),
one ``NAME=value`` per line. The file is refused when others may read it.

Never from a command line: a secret there lands in the process list and the
shell history.
"""

from __future__ import annotations

import os
from pathlib import Path

from fotoware_client.exceptions import ConfigurationError

ENV_TENANT_URL = "FOTOWARE_TENANT_URL"
ENV_CLIENT_ID = "FOTOWARE_CLIENT_ID"
ENV_CLIENT_SECRET = "FOTOWARE_CLIENT_SECRET"
_NAMES = (ENV_TENANT_URL, ENV_CLIENT_ID, ENV_CLIENT_SECRET)


def credentials_file() -> Path:
    """The credentials file's place."""
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config_home) / "fotoware" / "credentials"


def load_credentials() -> tuple[str, str, str]:
    """Tenant URL, client id and client secret.

    Raises:
        ConfigurationError: If neither the environment nor the file has all
            three, or the file may be read by others
    """
    values = {name: os.environ.get(name, "") for name in _NAMES}
    if not all(values.values()):
        values = _read_file(credentials_file())
    return values[ENV_TENANT_URL], values[ENV_CLIENT_ID], values[ENV_CLIENT_SECRET]


def _read_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ConfigurationError(
            f"No FotoWare credentials: set {', '.join(_NAMES)} or create {path}"
        )
    if path.stat().st_mode & 0o077:
        raise ConfigurationError(f"{path} may be read by others; run: chmod 600 {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            values[key.strip()] = value.strip().strip('"')
    missing = [name for name in _NAMES if not values.get(name)]
    if missing:
        raise ConfigurationError(f"{path} lacks {', '.join(missing)}")
    return values
