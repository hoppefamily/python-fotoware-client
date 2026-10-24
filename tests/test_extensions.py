"""Sequences of API calls, against a fake client that answers the API methods."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, BinaryIO
from unittest.mock import patch

import pytest

from fotoware_client import APIError, Archive, Asset, SearchResult, ServerSettings
from fotoware_client.extensions import Rendition, field_labels, iter_search, list_archives


class FakeClient:
    """The API methods the extensions call, recorded."""

    def __init__(self) -> None:
        self.settings = ServerSettings(rendition_poll_interval=0.001)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.renditions: list[dict[str, Any]] = [
            {"original": True, "display_name": "Original File", "href": "/r/original"},
            {"display_name": "Medium (JPG, 3000px)", "href": "/r/medium"},
        ]
        # What each task answers, poll by poll: False (202), True (200), or an error.
        self.task_answers: list[Any] = [False, True]
        self.tasks = 0

    def get_api_descriptor(self) -> dict[str, Any]:
        self.calls.append(("get_api_descriptor", ()))
        return {
            "archives": "/fotoweb/me/archives/",
            "services": {"rendition_request": "/fotoweb/services/renditions"},
        }

    def get_archives(self, href: str) -> list[Archive]:
        self.calls.append(("get_archives", (href,)))
        return [Archive(href="/fotoweb/archives/5000-Products/", name="Products", data={})]

    def get_archive(self, href: str) -> dict[str, Any]:
        self.calls.append(("get_archive", (href,)))
        return {"metadataEditor": {"href": "/fotoweb/editors/1"}}

    def get_metadata_editor(self, href: str) -> dict[str, Any]:
        self.calls.append(("get_metadata_editor", (href,)))
        return {
            "detailRegions": [
                {"fields": [{"field": {"id": 631, "label": "EAN"}}]},
                {"fields": [{"field": {"id": 631, "label": "EAN again"}}]},
                {"fields": [{"field": {"id": 659, "label": "Bildart"}}]},
            ]
        }

    def search(self, archive: str, query: str) -> SearchResult:
        self.calls.append(("search", (archive, query)))
        return SearchResult(assets=[], total_count=0, next_href="/p/1", data={})

    def get_page(self, href: str) -> SearchResult:
        self.calls.append(("get_page", (href,)))
        return SearchResult(assets=[], total_count=0, next_href=None, data={})

    def get_asset(self, href: str) -> Asset:
        self.calls.append(("get_asset", (href,)))
        return Asset(
            href=href,
            filename="x.jpg",
            fields={},
            mimetype=None,
            data={"renditions": self.renditions},
        )

    def request_rendition(self, service: str, rendition: str) -> str:
        self.tasks += 1
        self.calls.append(("request_rendition", (service, rendition)))
        return f"/t/{self.tasks}"

    def get_rendition_task(self, task: str, destination: BinaryIO | None = None) -> bool:
        self.calls.append(("get_rendition_task", (task,)))
        answer = self.task_answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if answer and destination is not None:
            destination.write(f"file of {task}".encode())
        return bool(answer)

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


def _gone() -> APIError:
    return APIError("HTTP 410 error", status_code=410)


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


def test_list_archives_reads_the_descriptor_then_the_list(client: FakeClient) -> None:
    archives = list_archives(client)  # type: ignore[arg-type]

    assert [archive.name for archive in archives] == ["Products"]
    assert client.calls == [
        ("get_api_descriptor", ()),
        ("get_archives", ("/fotoweb/me/archives/",)),
    ]


def test_field_labels_read_the_archive_then_its_editor(client: FakeClient) -> None:
    labels = field_labels(client, "/fotoweb/archives/5000-Products/")  # type: ignore[arg-type]

    assert labels == {"631": "EAN", "659": "Bildart"}
    assert client.names() == ["get_archive", "get_metadata_editor"]


def test_iter_search_follows_every_page(client: FakeClient) -> None:
    pages = list(iter_search(client, "/a/", "631:1"))  # type: ignore[arg-type]

    assert len(pages) == 2
    assert client.calls == [("search", ("/a/", "631:1")), ("get_page", ("/p/1",))]


def test_the_original_is_written_by_the_poll_that_finds_it_ready(client: FakeClient) -> None:
    data = Rendition(client, "/a/1.jpg.info").read()  # type: ignore[arg-type]

    assert data == b"file of /t/1"
    assert client.calls == [
        ("get_asset", ("/a/1.jpg.info",)),
        ("get_api_descriptor", ()),
        ("request_rendition", ("/fotoweb/services/renditions", "/r/original")),
        ("get_rendition_task", ("/t/1",)),
        ("get_rendition_task", ("/t/1",)),
    ]


def test_a_named_rendition_is_requested_by_its_display_name(client: FakeClient) -> None:
    Rendition(client, "/a/1.jpg.info", "Medium (JPG, 3000px)").read()  # type: ignore[arg-type]

    assert ("request_rendition", ("/fotoweb/services/renditions", "/r/medium")) in client.calls


def test_a_renamed_original_without_the_flag_is_found(client: FakeClient) -> None:
    client.settings = ServerSettings(
        original_rendition_name="Originaldatei", rendition_poll_interval=0.001
    )
    client.renditions = [
        {"display_name": "Vorschau", "href": "/r/1"},
        {"display_name": "Originaldatei", "href": "/r/2"},
    ]

    Rendition(client, "/a/1.jpg.info").read()  # type: ignore[arg-type]

    assert ("request_rendition", ("/fotoweb/services/renditions", "/r/2")) in client.calls


def test_an_unknown_rendition_is_an_error(client: FakeClient) -> None:
    with pytest.raises(APIError, match="No Large rendition"):
        Rendition(client, "/a/1.jpg.info", "Large").read()  # type: ignore[arg-type]


def test_url_polls_without_downloading(client: FakeClient) -> None:
    assert Rendition(client, "/a/1.jpg.info").url() == "/t/1"  # type: ignore[arg-type]


def test_save_writes_the_file(client: FakeClient, tmp_path: Path) -> None:
    path = Rendition(client, "/a/1.jpg.info").save(tmp_path / "x.jpg")  # type: ignore[arg-type]

    assert path.read_bytes() == b"file of /t/1"


def test_a_gone_task_is_requested_anew_once(client: FakeClient) -> None:
    client.task_answers = [_gone(), True]
    destination = io.BytesIO()

    Rendition(client, "/a/1.jpg.info").write_to(destination)  # type: ignore[arg-type]

    assert destination.getvalue() == b"file of /t/2"
    assert client.tasks == 2


def test_a_task_gone_twice_is_an_error(client: FakeClient) -> None:
    client.task_answers = [_gone(), _gone()]

    with pytest.raises(APIError) as exc_info:
        Rendition(client, "/a/1.jpg.info").read()  # type: ignore[arg-type]

    assert exc_info.value.status_code == 410
    assert client.tasks == 2


def test_other_errors_are_not_repeated(client: FakeClient) -> None:
    client.task_answers = [APIError("HTTP 403 error", status_code=403)]

    with pytest.raises(APIError):
        Rendition(client, "/a/1.jpg.info").read()  # type: ignore[arg-type]

    assert client.tasks == 1


def test_a_rendition_not_ready_in_time_is_an_error(client: FakeClient) -> None:
    client.settings = ServerSettings(
        download_timeout=1, rendition_poll_interval=0.4, rendition_poll_interval_max=0.4
    )
    client.task_answers = [False] * 10
    clock = iter(range(0, 100))

    with (
        patch("fotoware_client.extensions.time.sleep"),
        patch("fotoware_client.extensions.time.monotonic", side_effect=lambda: next(clock)),
    ):
        with pytest.raises(APIError, match="not ready after 1s"):
            Rendition(client, "/a/1.jpg.info").read()  # type: ignore[arg-type]
