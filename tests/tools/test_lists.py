"""Tests for tools/lists.py — formatting helpers and input building."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.client import HardcoverAPIError
from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.lists import (
    _build_list_input,
    _format_list_book,
    _format_list_summary,
    handle_delete_list,
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

        assert result["privacy"] == "unknown (99)"


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

    @pytest.mark.parametrize("privacy", ["followers", "Followers", "followers_only", 2])
    def test_accepts_every_followers_spelling(self, privacy):
        assert _build_list_input({"privacy": privacy})["privacy_setting_id"] == 2

    def test_raises_on_invalid_privacy(self):
        with pytest.raises(ToolError, match="'privacy' must be"):
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

    async def test_rejects_missing_book_id(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_list_book({"list_id": 1, "on_list": True})
        assert "'book_id'" in str(exc.value)

    @pytest.mark.parametrize(
        "lists", [{}, {"list_id": 1, "list_ids": [2]}], ids=["neither", "both"]
    )
    async def test_needs_exactly_one_of_list_id_and_list_ids(self, lists):
        with pytest.raises(ToolError, match="either 'list_id' or 'list_ids'"):
            await handle_set_list_book({"book_id": 2, "on_list": True, **lists})

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
        mock = AsyncMock(
            side_effect=[{"data": {"lists": [{"id": 5}]}}, {"data": {"update_list": updated}}]
        )
        with (
            patch(
                "hardcover_mcp.tools.lists.get_current_user",
                new=AsyncMock(return_value={"id": 42}),
            ),
            patch("hardcover_mcp.tools.lists.execute", new=mock),
        ):
            result = await handle_set_list({"id": 5, "name": "New", "privacy": "private"})

        assert json.loads(result[0].text)["privacy"] == "private"
        assert mock.call_args_list[0][0][1] == {"id": 5, "user_id": 42}
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
                new=AsyncMock(
                    return_value={
                        "data": {
                            "lists": [lst],
                            "lists_aggregate": {"aggregate": {"count": 12}},
                        }
                    }
                ),
            ) as mock,
        ):
            result = await handle_get_list({"limit": 5})

        data = json.loads(result[0].text)
        assert {k: data[k] for k in ("total", "returned", "offset")} == {
            "total": 12,
            "returned": 1,
            "offset": 0,
        }
        assert data["lists"][0]["name"] == "A"
        assert mock.call_args[0][1] == {"user_id": 42, "limit": 5, "offset": 0}

    async def test_with_id_pages_books_with_books_limit_and_offset(self):
        lst = {"id": 3, "name": "A", "slug": "a", "books_count": 9, "list_books": []}
        mock = AsyncMock(return_value={"data": {"lists": [lst]}})
        with patch("hardcover_mcp.tools.lists.execute", new=mock):
            await handle_get_list({"id": 3, "books_limit": 4, "books_offset": 8})

        assert mock.call_args[0][1] == {"id": 3, "books_limit": 4, "books_offset": 8}


def _own(lists: list[int], entries: dict[int, int] | None = None) -> dict:
    """FindOwnListBooks response: your lists among the ids, and the book's entries on them."""
    list_books = [{"id": lb_id, "list_id": lid} for lid, lb_id in (entries or {}).items()]
    return {"data": {"lists": [{"id": i} for i in lists], "list_books": list_books}}


def _inserted(list_book_id: int) -> dict:
    return {"data": {"insert_list_book": {"list_book": {"id": list_book_id}}}}


class TestHandleSetListBookMany:
    async def _run(self, arguments: dict, *responses) -> tuple[dict, AsyncMock]:
        mock = AsyncMock(side_effect=list(responses))
        self.mock = mock
        with (
            patch(
                "hardcover_mcp.tools.lists.get_current_user",
                new=AsyncMock(return_value={"id": 7}),
            ),
            patch("hardcover_mcp.tools.lists.execute", new=mock),
        ):
            result = await handle_set_list_book({"book_id": 42, **arguments})
        return json.loads(result[0].text), mock

    async def test_adds_where_missing_and_leaves_the_rest(self):
        data, mock = await self._run(
            {"list_ids": [1, 2, 3], "on_list": True},
            _own([1, 2, 3], {2: 512}),
            _inserted(900),
            _inserted(901),
        )

        assert data == {
            "book_id": 42,
            "on_list": True,
            "results": [
                {"list_id": 1, "changed": True, "list_book_id": 900},
                {"list_id": 2, "changed": False, "list_book_id": 512},
                {"list_id": 3, "changed": True, "list_book_id": 901},
            ],
        }
        assert mock.call_args_list[0][0][1] == {"list_ids": [1, 2, 3], "book_id": 42, "user_id": 7}
        assert mock.call_args_list[1][0][1] == {"object": {"list_id": 1, "book_id": 42}}
        assert mock.call_args_list[2][0][1] == {"object": {"list_id": 3, "book_id": 42}}

    async def test_removes_where_present(self):
        data, mock = await self._run(
            {"list_ids": [1, 2], "on_list": False},
            _own([1, 2], {1: 512}),
            {"data": {"delete_list_book": {}}},
        )

        assert data["results"] == [
            {"list_id": 1, "changed": True, "list_book_id": None},
            {"list_id": 2, "changed": False, "list_book_id": None},
        ]
        assert mock.call_args_list[1][0][1] == {"id": 512}
        assert mock.call_count == 2

    async def test_list_that_is_not_yours_is_reported_and_not_written(self):
        data, mock = await self._run(
            {"list_ids": [1, 99], "on_list": True}, _own([1]), _inserted(900)
        )

        assert data["results"][1] == {
            "list_id": 99,
            "changed": False,
            "error": "not one of your lists.",
        }
        assert mock.call_count == 2  # lookup + one insert, nothing for list 99

    async def test_one_failing_list_does_not_stop_the_others(self):
        data, _ = await self._run(
            {"list_ids": [1, 2, 3], "on_list": True},
            _own([1, 2, 3]),
            _inserted(900),
            HardcoverAPIError("GraphQL error: boom"),
            _inserted(902),
        )

        assert [r["changed"] for r in data["results"]] == [True, False, True]
        assert data["results"][1]["error"] == "GraphQL error: boom"
        assert data["results"][2]["list_book_id"] == 902

    async def test_duplicate_ids_are_handled_once(self):
        data, _ = await self._run({"list_ids": [1, "1", 1], "on_list": True}, _own([1], {1: 512}))

        assert data["results"] == [{"list_id": 1, "changed": False, "list_book_id": 512}]

    async def test_single_list_id_keeps_the_flat_result(self):
        data, _ = await self._run({"list_id": 1, "on_list": True}, _found(9))

        assert data == {
            "list_id": 1,
            "book_id": 42,
            "on_list": True,
            "changed": False,
            "list_book_id": 9,
        }

    @pytest.mark.parametrize(
        ("list_ids", "message"),
        [
            ([], "non-empty array"),
            (5, "non-empty array"),
            (["x"], "'list_ids' must be an integer"),
            (list(range(21)), "at most 20"),
        ],
    )
    async def test_rejects_bad_list_ids_before_api_calls(self, list_ids, message):
        with pytest.raises(ToolError, match=message):
            await self._run({"list_ids": list_ids, "on_list": True})
        self.mock.assert_not_awaited()

    async def test_rejects_position_with_list_ids(self):
        with pytest.raises(ToolError, match="'position' only works"):
            await self._run({"list_ids": [1, 2], "on_list": True, "position": 3})
        self.mock.assert_not_awaited()


async def test_set_list_without_a_returned_list_is_an_error():
    mock = AsyncMock(return_value={"data": {"insert_list": {"id": 1, "list": None}}})
    with (
        patch("hardcover_mcp.tools.lists.execute", new=mock),
        pytest.raises(ToolError, match="didn't return the list"),
    ):
        await handle_set_list({"name": "X"})


@pytest.mark.parametrize(
    "call",
    [
        lambda: handle_set_list({"id": 5, "name": "New"}),
        lambda: handle_delete_list({"id": 5}),
    ],
    ids=["update", "delete"],
)
async def test_a_list_that_isnt_yours_is_an_error_and_not_changed(call):
    mock = AsyncMock(return_value={"data": {"lists": []}})
    with (
        patch(
            "hardcover_mcp.tools.lists.get_current_user", new=AsyncMock(return_value={"id": 42})
        ),
        patch("hardcover_mcp.tools.lists.execute", new=mock),
        pytest.raises(ToolError, match="no list of yours with that id"),
    ):
        await call()
    assert mock.call_count == 1
