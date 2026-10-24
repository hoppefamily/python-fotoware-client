"""The size estimate against the edges measured on FotoWeb 8.1.1223.0 (2026-10-23)."""

from __future__ import annotations

import pytest

from fotoware_client.limits import (
    QUERY_SIZE_BUDGET,
    QUERY_SIZE_LIMIT,
    QueryTooLargeError,
    check_query_size,
    estimate_query_size,
)

IMAGE_FILTER = "(dt:image OR dt:graphic) AND NOT 699:5"


def _ean_query(values: list[str]) -> str:
    terms = " OR ".join(f"631:{value}" for value in values)
    return f"({terms}) AND ({IMAGE_FILTER})"


def _eans(count: int) -> list[str]:
    return [str(4000000000000 + i) for i in range(count)]


def test_a_term_costs_its_value_plus_the_overhead() -> None:
    assert estimate_query_size("631:4000000000001") == 13 + 33


def test_operators_brackets_and_spaces_cost_nothing() -> None:
    assert estimate_query_size("(631:1 OR 631:2) AND NOT  699:5") == 3 * 34


@pytest.mark.parametrize(
    ("values", "worked"),
    [
        (_eans(40), True),
        (_eans(42), False),
        ([f"{i:02d}" for i in range(52)], True),
        ([f"{i:02d}" for i in range(56)], False),
    ],
)
def test_the_measured_edges_fall_on_the_limit(values: list[str], worked: bool) -> None:
    assert (estimate_query_size(_ean_query(values)) <= QUERY_SIZE_LIMIT) is worked


def test_the_budget_takes_thirty_eans_with_the_image_filter() -> None:
    check_query_size(_ean_query(_eans(30)))
    with pytest.raises(QueryTooLargeError) as exc_info:
        check_query_size(_ean_query(_eans(31)))

    assert exc_info.value.budget == QUERY_SIZE_BUDGET
    assert exc_info.value.estimated_size > QUERY_SIZE_BUDGET
