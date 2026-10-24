"""Constants for FotoWare API client."""

# FotoWare API Accept headers for different content types
ACCEPT_JSON = {"Accept": "application/json"}
ACCEPT_FULL_DESCRIPTOR = {"Accept": "application/vnd.fotoware.full-api-descriptor+json"}
ACCEPT_COLLECTIONLIST = {"Accept": "application/vnd.fotoware.collectionlist+json"}
ACCEPT_COLLECTIONINFO = {"Accept": "application/vnd.fotoware.collectioninfo+json"}
ACCEPT_ASSETLIST = {"Accept": "application/vnd.fotoware.assetlist+json"}
ACCEPT_ASSET = {"Accept": "application/vnd.fotoware.asset+json"}
ACCEPT_DOWNLOAD = {"Accept": "application/vnd.fotoware.download+json"}

# Request timeouts (in seconds)
DEFAULT_TIMEOUT = 30
