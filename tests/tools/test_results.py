"""Tests for tools/_results.py — the shared list-result shape."""

import json

from hardcover_mcp.tools._results import list_result


def _decode(content) -> dict:
    return json.loads(content[0].text)


def test_page_without_total():
    assert _decode(list_result("entries", [{"id": 1}, {"id": 2}], offset=10)) == {
        "returned": 2,
        "offset": 10,
        "entries": [{"id": 1}, {"id": 2}],
    }


def test_page_with_total_comes_first():
    data = _decode(list_result("lists", [], offset=0, total=7))

    assert list(data) == ["total", "returned", "offset", "lists"]
    assert data == {"total": 7, "returned": 0, "offset": 0, "lists": []}


def test_zero_total_is_kept():
    assert _decode(list_result("books", [], offset=0, total=0))["total"] == 0
