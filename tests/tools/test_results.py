"""Tests for tools/_results.py — the shared list-result shape."""

import json

import pytest

from hardcover_mcp.tools._results import list_result, mutation_payload, returned_object
from hardcover_mcp.tools._validation import ToolError


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


def test_mutation_payload_returns_the_payload():
    assert mutation_payload({"data": {"insert_list": {"id": 1}}}, "insert_list") == {"id": 1}


@pytest.mark.parametrize("result", [{"data": {"insert_list": None}}, {"data": None}, {}])
def test_mutation_payload_null_is_an_error(result):
    with pytest.raises(ToolError, match="didn't confirm the change"):
        mutation_payload(result, "insert_list")


def test_returned_object_missing_is_an_error():
    assert returned_object({"list": {"id": 1}}, "list", "list") == {"id": 1}
    with pytest.raises(ToolError, match="didn't return the list"):
        returned_object({"list": None}, "list", "list")
