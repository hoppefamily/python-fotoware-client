"""Data models for FotoWare API responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Archive:
    """Represents a FotoWare archive.

    Attributes:
        href: Full URL to the archive
        name: Human-readable archive name
        data: Complete raw JSON data from API
    """

    href: str
    name: str
    data: dict[str, Any] = field(repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Archive:
        """Create Archive from API JSON response.

        Args:
            data: Raw JSON data from FotoWare API

        Returns:
            Archive instance

        Raises:
            KeyError: If required fields are missing
        """
        return cls(
            href=data["href"],
            name=data.get("name", data.get("displayName", "Unknown")),
            data=data,
        )


@dataclass
class Asset:
    """Represents a FotoWare asset (image, document, etc.).

    Attributes:
        href: Full URL to the asset
        filename: Asset filename
        fields: Metadata fields (dict mapping field IDs to values)
        mimetype: MIME type (e.g., 'image/jpeg', 'application/pdf')
        data: Complete raw JSON data from API
    """

    href: str
    filename: str
    fields: dict[str, Any]
    mimetype: str | None
    data: dict[str, Any] = field(repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Asset:
        """Create Asset from API JSON response.

        Args:
            data: Raw JSON data from FotoWare API

        Returns:
            Asset instance

        Raises:
            KeyError: If required fields are missing
        """
        # Extract filename from metadata
        filename = data.get("filename", "unknown")

        # Extract and flatten metadata fields
        fields: dict[str, Any] = {}
        metadata = data.get("metadata", {})

        # Handle both direct field values and nested structures
        for field_id, field_data in metadata.items():
            if isinstance(field_data, dict):
                # Extract value from nested structure
                value = field_data.get("value")
                if value is not None:
                    fields[field_id] = value
            else:
                # Direct value
                fields[field_id] = field_data

        # Get MIME type
        mimetype = data.get("mimetype") or data.get("attributes", {}).get("mimetype")

        return cls(
            href=data["href"],
            filename=filename,
            fields=fields,
            mimetype=mimetype,
            data=data,
        )

    def get_field(self, field_id: str, default: Any = None) -> Any:
        """Get metadata field value by field ID.

        Args:
            field_id: FotoWare field ID (e.g., '631' for EAN)
            default: Default value if field not found

        Returns:
            Field value or default
        """
        return self.fields.get(field_id, default)

    def get_field_values(self, field_id: str) -> list[Any]:
        """Get metadata field values as list (handles multi-value fields).

        Args:
            field_id: FotoWare field ID

        Returns:
            List of values (empty list if field not found)
        """
        value = self.fields.get(field_id)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @property
    def doctype(self) -> str | None:
        """Get asset doctype (e.g., 'image', 'document', 'graphic').

        Returns:
            Doctype string or None if not present
        """
        return self.data.get("doctype")


@dataclass
class SearchResult:
    """Represents paginated search results from FotoWare.

    Attributes:
        assets: List of Asset instances
        total_count: Total number of matching assets
        next_href: URL to fetch next page (None if last page)
        data: Complete raw JSON data from API
    """

    assets: list[Asset]
    total_count: int
    next_href: str | None
    data: dict[str, Any] = field(repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SearchResult:
        """Create SearchResult from API JSON response.

        Args:
            data: Raw JSON data from FotoWare API

        Returns:
            SearchResult instance
        """
        # Parse assets from data
        assets = []
        for asset_data in data.get("data", []):
            try:
                assets.append(Asset.from_json(asset_data))
            except KeyError, TypeError:
                # Skip malformed assets
                continue

        # Get total count
        paging = data.get("paging") or {}
        total_count = paging.get("totalAssets", len(assets))

        # Get next page link from paging object
        next_href = paging.get("next") or None
        if next_href == "":  # Empty string means no next page
            next_href = None

        return cls(
            assets=assets,
            total_count=total_count,
            next_href=next_href,
            data=data,
        )
