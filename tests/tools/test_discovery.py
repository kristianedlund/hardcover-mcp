"""Unit tests for tools.discovery (query rendering + validation)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.discovery import (
    _TRENDING_DURATIONS,
    _render_vibes_query,
    handle_get_trending_books,
    handle_get_vibes,
)


class TestRenderVibesQuery:
    def test_featured_only_adds_where(self):
        assert "featured: {_eq: true}" in _render_vibes_query(True)

    def test_all_vibes_omits_where(self):
        assert "featured: {_eq: true}" not in _render_vibes_query(False)


class TestTrendingValidation:
    async def test_rejects_bad_duration(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_trending_books({"duration": "fortnight"})
        assert "invalid duration" in str(exc.value)

    async def test_duration_set_matches_schema_enum(self):
        from hardcover_mcp.tools.discovery import TOOLS

        tool = next(spec.tool for spec in TOOLS if spec.tool.name == "get_trending_books")
        assert tool.input_schema["properties"]["duration"]["enum"] == list(_TRENDING_DURATIONS)

    async def test_rejects_non_int_limit(self):
        with pytest.raises(ToolError):
            await handle_get_trending_books({"limit": "lots"})


class TestVibesValidation:
    async def test_rejects_non_int_books_per_vibe(self):
        with pytest.raises(ToolError):
            await handle_get_vibes({"books_per_vibe": "many"})


_BOOK = {"book_id": 7, "title": "T", "slug": "t", "authors": [], "rating": 4.0}


class TestResultShapes:
    async def test_trending_is_a_page_of_books(self):
        trending = AsyncMock(
            return_value={"data": {"books_trending": {"ids": [7], "error": None}}}
        )
        with (
            patch("hardcover_mcp.tools.discovery.execute", new=trending),
            patch(
                "hardcover_mcp.tools.discovery.fetch_books_by_ids",
                new=AsyncMock(return_value=[_BOOK]),
            ),
        ):
            result = await handle_get_trending_books({"offset": 3})

        assert json.loads(result[0].text) == {"returned": 1, "offset": 3, "books": [_BOOK]}

    async def test_vibes_is_a_page_of_vibes(self):
        vibe = {"id": 1, "slug": "v", "title": "V", "featured": True, "cached_book_ids": [7]}
        with (
            patch(
                "hardcover_mcp.tools.discovery.execute",
                new=AsyncMock(return_value={"data": {"vibes": [vibe]}}),
            ),
            patch(
                "hardcover_mcp.tools.discovery.fetch_books_by_ids",
                new=AsyncMock(return_value=[_BOOK]),
            ),
        ):
            result = await handle_get_vibes({})

        data = json.loads(result[0].text)
        assert {k: data[k] for k in ("returned", "offset")} == {"returned": 1, "offset": 0}
        assert data["vibes"][0]["books"] == [_BOOK]


async def test_null_trending_result_is_an_empty_page():
    with (
        patch(
            "hardcover_mcp.tools.discovery.execute",
            new=AsyncMock(return_value={"data": {"books_trending": None}}),
        ),
        patch("hardcover_mcp.tools.discovery.fetch_books_by_ids", new=AsyncMock(return_value=[])),
    ):
        result = await handle_get_trending_books({})

    assert json.loads(result[0].text) == {"returned": 0, "offset": 0, "books": []}
