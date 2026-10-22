"""Tests for tools/lists.py — formatting helpers and input building."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.lists import (
    _build_list_input,
    _format_list_book,
    _format_list_summary,
    handle_get_list,
    handle_set_list,
    handle_set_list_book,
)


class TestFormatListSummary:
    def test_maps_privacy_setting_id(self):
        lst = {
            "id": 1,
            "name": "My List",
            "slug": "my-list",
            "description": None,
            "books_count": 5,
            "privacy_setting_id": 1,
            "updated_at": "2025-01-01",
        }
        result = _format_list_summary(lst)

        assert result["privacy"] == "public"
        assert result["books_count"] == 5

    def test_unknown_privacy_id(self):
        lst = {
            "id": 1,
            "name": "X",
            "slug": "x",
            "books_count": 0,
            "privacy_setting_id": 99,
        }
        result = _format_list_summary(lst)

        assert result["privacy"] == "unknown"


class TestFormatListBook:
    def test_flattens_book_and_authors(self):
        lb = {
            "position": 1,
            "book": {
                "id": 42,
                "title": "Test",
                "slug": "test",
                "contributions": [{"author": {"name": "A"}}],
            },
        }
        result = _format_list_book(lb)

        assert result["position"] == 1
        assert result["book_id"] == 42
        assert result["authors"] == ["A"]


class TestBuildListInput:
    def test_builds_from_name_and_privacy(self):
        result = _build_list_input({"name": "New", "privacy": "private"})

        assert result["name"] == "New"
        assert result["privacy_setting_id"] == 3

    def test_accepts_numeric_privacy(self):
        result = _build_list_input({"name": "X", "privacy": "2"})

        assert result["privacy_setting_id"] == 2

    def test_raises_on_invalid_privacy(self):
        with pytest.raises(ToolError, match="Unknown privacy"):
            _build_list_input({"privacy": "secret"})

    def test_returns_empty_when_no_fields(self):
        assert _build_list_input({}) == {}


def _found(*ids: int) -> dict:
    return {"data": {"list_books": [{"id": i} for i in ids]}}


class TestHandleSetListBook:
    async def test_rejects_missing_on_list(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_list_book({"list_id": 1, "book_id": 2})
        assert "'on_list'" in str(exc.value)

    async def test_rejects_missing_ids(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_list_book({"list_id": 1, "on_list": True})
        assert "'list_id' and 'book_id'" in str(exc.value)

    async def test_adds_when_absent(self):
        mock = AsyncMock(
            side_effect=[
                _found(),
                {"data": {"insert_list_book": {"list_book": {"id": 9, "position": 3}}}},
            ]
        )
        with patch("hardcover_mcp.tools.lists.execute", new=mock):
            result = await handle_set_list_book(
                {"list_id": 1, "book_id": 2, "on_list": True, "position": 3}
            )

        data = json.loads(result[0].text)
        assert data["changed"] is True
        assert data["list_book_id"] == 9
        assert mock.call_args_list[1][0][1] == {
            "object": {"list_id": 1, "book_id": 2, "position": 3}
        }

    async def test_add_when_present_is_noop(self):
        mock = AsyncMock(return_value=_found(9))
        with patch("hardcover_mcp.tools.lists.execute", new=mock):
            result = await handle_set_list_book({"list_id": 1, "book_id": 2, "on_list": True})

        data = json.loads(result[0].text)
        assert data["changed"] is False
        assert data["list_book_id"] == 9
        assert mock.call_count == 1

    async def test_removes_when_present(self):
        mock = AsyncMock(side_effect=[_found(9), {"data": {"delete_list_book": {}}}])
        with patch("hardcover_mcp.tools.lists.execute", new=mock):
            result = await handle_set_list_book({"list_id": 1, "book_id": 2, "on_list": False})

        data = json.loads(result[0].text)
        assert data["changed"] is True
        assert data["list_book_id"] is None
        assert mock.call_args_list[1][0][1] == {"id": 9}

    async def test_remove_when_absent_is_noop(self):
        mock = AsyncMock(return_value=_found())
        with patch("hardcover_mcp.tools.lists.execute", new=mock):
            result = await handle_set_list_book({"list_id": 1, "book_id": 2, "on_list": False})

        assert json.loads(result[0].text)["changed"] is False
        assert mock.call_count == 1


class TestHandleSetList:
    async def test_create_requires_name(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_list({"description": "x"})
        assert "'name' is required" in str(exc.value)

    async def test_without_id_creates(self):
        created = {"list": {"id": 5, "name": "N", "slug": "n", "privacy_setting_id": 1}}
        mock = AsyncMock(return_value={"data": {"insert_list": created}})
        with patch("hardcover_mcp.tools.lists.execute", new=mock):
            result = await handle_set_list({"name": "N"})

        assert json.loads(result[0].text)["id"] == 5
        assert "insert_list" in mock.call_args[0][0]

    async def test_with_id_updates(self):
        updated = {"list": {"id": 5, "name": "New", "slug": "n", "privacy_setting_id": 3}}
        mock = AsyncMock(return_value={"data": {"update_list": updated}})
        with patch("hardcover_mcp.tools.lists.execute", new=mock):
            result = await handle_set_list({"id": 5, "name": "New", "privacy": "private"})

        assert json.loads(result[0].text)["privacy"] == "private"
        assert "update_list" in mock.call_args[0][0]

    async def test_update_requires_a_field(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_list({"id": 5})
        assert "at least one" in str(exc.value)


class TestHandleGetList:
    async def test_without_id_lists_own_lists(self):
        lst = {"id": 1, "name": "A", "slug": "a", "books_count": 0, "privacy_setting_id": 1}
        with (
            patch(
                "hardcover_mcp.tools.lists.get_current_user",
                new=AsyncMock(return_value={"id": 42}),
            ),
            patch(
                "hardcover_mcp.tools.lists.execute",
                new=AsyncMock(return_value={"data": {"lists": [lst]}}),
            ) as mock,
        ):
            result = await handle_get_list({"limit": 5})

        assert json.loads(result[0].text)[0]["name"] == "A"
        assert mock.call_args[0][1] == {"user_id": 42, "limit": 5, "offset": 0}
