"""Constants for FotoWare API client."""

# FotoWare API Accept headers for different content types
ACCEPT_JSON = {"Accept": "application/json"}
ACCEPT_FULL_DESCRIPTOR = {"Accept": "application/vnd.fotoware.full-api-descriptor+json"}
ACCEPT_COLLECTIONLIST = {"Accept": "application/vnd.fotoware.collectionlist+json"}
ACCEPT_COLLECTIONINFO = {"Accept": "application/vnd.fotoware.collectioninfo+json"}
ACCEPT_ASSETLIST = {"Accept": "application/vnd.fotoware.assetlist+json"}
ACCEPT_ASSET = {"Accept": "application/vnd.fotoware.asset+json"}
ACCEPT_DOWNLOAD = {"Accept": "application/vnd.fotoware.download+json"}

# OAuth endpoint path (relative to tenant URL)
OAUTH_TOKEN_PATH = "/fotoweb/oauth2/token"

# API endpoint path (relative to tenant URL)
API_ME_PATH = "/fotoweb/me"

# Request timeouts (in seconds)
DEFAULT_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 120
