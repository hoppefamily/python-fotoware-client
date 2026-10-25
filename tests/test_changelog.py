"""The changelog has a section for every version the package can be released as."""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("changelog", ROOT / "scripts" / "changelog.py")
assert _spec is not None and _spec.loader is not None
changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changelog)

TEXT = """# Changelog

## [Unreleased]

## [0.2.0] - 2026-10-24

### Added

- Something.

## [0.1.0] - 2026-10-23

[0.2.0]: https://example.com/compare/v0.1.0...v0.2.0
"""


def test_the_current_version_has_its_section() -> None:
    """A version bump comes with its entry, or this fails before the release does."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]

    assert changelog.section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version)


def test_a_section_ends_at_the_next_version() -> None:
    assert changelog.section(TEXT, "0.2.0") == "### Added\n\n- Something."


def test_a_missing_version_is_an_error() -> None:
    with pytest.raises(LookupError, match=r"no section ## \[0.3.0\]"):
        changelog.section(TEXT, "0.3.0")


def test_an_empty_section_is_an_error() -> None:
    """The last section ends at the link definitions, and this one has nothing."""
    with pytest.raises(LookupError, match="is empty"):
        changelog.section(TEXT, "0.1.0")


def test_a_version_is_matched_whole() -> None:
    with pytest.raises(LookupError):
        changelog.section(TEXT, "0.2")
