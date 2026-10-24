"""Unit tests for models module."""

import pytest

from fotoware_client.models import Archive, Asset, SearchResult


class TestArchive:
    """Tests for Archive model."""

    def test_from_json_with_name(self) -> None:
        """Test Archive creation from JSON with name field."""
        data = {
            "href": "https://fotoware.example.com/archive/123",
            "name": "Product Media",
            "displayName": "Product Media Display",
        }
        archive = Archive.from_json(data)
        assert archive.href == "https://fotoware.example.com/archive/123"
        assert archive.name == "Product Media"
        assert archive.data == data

    def test_from_json_with_display_name(self) -> None:
        """Test Archive creation with displayName fallback."""
        data = {
            "href": "https://fotoware.example.com/archive/123",
            "displayName": "Product Media",
        }
        archive = Archive.from_json(data)
        assert archive.name == "Product Media"

    def test_from_json_without_name(self) -> None:
        """Test Archive creation without name fields."""
        data = {
            "href": "https://fotoware.example.com/archive/123",
        }
        archive = Archive.from_json(data)
        assert archive.name == "Unknown"

    def test_from_json_missing_href(self) -> None:
        """Test Archive creation fails without href."""
        data = {"name": "Test"}
        with pytest.raises(KeyError):
            Archive.from_json(data)


class TestAsset:
    """Tests for Asset model."""

    def test_from_json_basic(self) -> None:
        """Test Asset creation from basic JSON."""
        data = {
            "href": "https://fotoware.example.com/asset/456",
            "filename": "product.jpg",
            "metadata": {
                "631": {"value": "12345"},
                "825": {"value": "Dokument"},
            },
            "mimetype": "image/jpeg",
        }
        asset = Asset.from_json(data)
        assert asset.href == "https://fotoware.example.com/asset/456"
        assert asset.filename == "product.jpg"
        assert asset.fields["631"] == "12345"
        assert asset.fields["825"] == "Dokument"
        assert asset.mimetype == "image/jpeg"
        assert asset.data == data

    def test_from_json_direct_field_values(self) -> None:
        """Test Asset with direct field values (not nested)."""
        data = {
            "href": "https://fotoware.example.com/asset/456",
            "filename": "product.jpg",
            "metadata": {
                "631": "12345",  # Direct value
                "825": "Dokument",
            },
        }
        asset = Asset.from_json(data)
        assert asset.fields["631"] == "12345"
        assert asset.fields["825"] == "Dokument"

    def test_from_json_mimetype_from_attributes(self) -> None:
        """Test Asset with mimetype in attributes."""
        data = {
            "href": "https://fotoware.example.com/asset/456",
            "filename": "product.pdf",
            "metadata": {},
            "attributes": {"mimetype": "application/pdf"},
        }
        asset = Asset.from_json(data)
        assert asset.mimetype == "application/pdf"

    def test_from_json_no_filename(self) -> None:
        """Test Asset without filename."""
        data = {
            "href": "https://fotoware.example.com/asset/456",
            "metadata": {},
        }
        asset = Asset.from_json(data)
        assert asset.filename == "unknown"

    def test_get_field(self) -> None:
        """Test get_field method."""
        data = {
            "href": "https://fotoware.example.com/asset/456",
            "filename": "product.jpg",
            "metadata": {"631": "12345"},
        }
        asset = Asset.from_json(data)
        assert asset.get_field("631") == "12345"
        assert asset.get_field("999") is None
        assert asset.get_field("999", "default") == "default"

    def test_get_field_values_single(self) -> None:
        """Test get_field_values with single value."""
        data = {
            "href": "https://fotoware.example.com/asset/456",
            "filename": "product.jpg",
            "metadata": {"631": "12345"},
        }
        asset = Asset.from_json(data)
        assert asset.get_field_values("631") == ["12345"]

    def test_get_field_values_list(self) -> None:
        """Test get_field_values with list value."""
        data = {
            "href": "https://fotoware.example.com/asset/456",
            "filename": "product.jpg",
            "metadata": {"631": ["12345", "67890"]},
        }
        asset = Asset.from_json(data)
        assert asset.get_field_values("631") == ["12345", "67890"]

    def test_get_field_values_missing(self) -> None:
        """Test get_field_values with missing field."""
        data = {
            "href": "https://fotoware.example.com/asset/456",
            "filename": "product.jpg",
            "metadata": {},
        }
        asset = Asset.from_json(data)
        assert asset.get_field_values("631") == []


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_from_json_basic(self) -> None:
        """Test SearchResult creation from JSON."""
        data = {
            "data": [
                {
                    "href": "https://fotoware.example.com/asset/1",
                    "filename": "img1.jpg",
                    "metadata": {},
                },
                {
                    "href": "https://fotoware.example.com/asset/2",
                    "filename": "img2.jpg",
                    "metadata": {},
                },
            ],
            "paging": {"totalAssets": 2},
        }
        result = SearchResult.from_json(data)
        assert len(result.assets) == 2
        assert result.total_count == 2
        assert result.next_href is None

    def test_from_json_with_next_link(self) -> None:
        """Test SearchResult with next page link."""
        data = {
            "data": [],
            "paging": {
                "totalAssets": 100,
                "next": "/fotoweb/archives/5000-Products/?q=dt%3Aimage&p=1",
            },
        }
        result = SearchResult.from_json(data)
        assert result.next_href == "/fotoweb/archives/5000-Products/?q=dt%3Aimage&p=1"

    def test_from_json_skips_malformed_assets(self) -> None:
        """Test SearchResult skips malformed assets."""
        data = {
            "data": [
                {
                    "href": "https://fotoware.example.com/asset/1",
                    "filename": "img1.jpg",
                    "metadata": {},
                },
                {
                    # Missing required href
                    "filename": "bad.jpg",
                    "metadata": {},
                },
            ],
            "paging": {"totalAssets": 2},
        }
        result = SearchResult.from_json(data)
        assert len(result.assets) == 1  # Only valid asset

    def test_from_json_empty(self) -> None:
        """Test SearchResult with no assets."""
        data = {"data": [], "paging": {"totalAssets": 0}}
        result = SearchResult.from_json(data)
        assert len(result.assets) == 0
        assert result.total_count == 0
