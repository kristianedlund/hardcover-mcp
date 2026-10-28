"""Unit tests for tools.series."""

import json
from unittest.mock import AsyncMock, patch

from hardcover_mcp.tools.series import _format_series


class TestFormatSeries:
    def test_formats_full_series(self):
        raw = {
            "id": 42,
            "name": "The Stormlight Archive",
            "slug": "the-stormlight-archive",
            "description": "Epic fantasy series",
            "books_count": 10,
            "primary_books_count": 4,
            "is_completed": False,
            "author": {"name": "Brandon Sanderson", "slug": "brandon-sanderson"},
            "book_series": [
                {
                    "position": 1,
                    "book": {
                        "id": 100,
                        "slug": "the-way-of-kings",
                        "title": "The Way of Kings",
                        "release_year": 2010,
                        "rating": 4.65,
                        "users_count": 50000,
                    },
                },
                {
                    "position": 2,
                    "book": {
                        "id": 101,
                        "slug": "words-of-radiance",
                        "title": "Words of Radiance",
                        "release_year": 2014,
                        "rating": 4.76,
                        "users_count": 40000,
                    },
                },
            ],
        }

        result = _format_series(raw)

        assert result["id"] == 42
        assert result["name"] == "The Stormlight Archive"
        assert result["slug"] == "the-stormlight-archive"
        assert result["authors"] == ["Brandon Sanderson"]
        assert "author" not in result
        assert result["is_completed"] is False
        assert result["primary_books_count"] == 4
        assert len(result["books"]) == 2
        assert result["books"][0]["position"] == 1
        assert result["books"][0]["title"] == "The Way of Kings"
        assert result["books"][1]["position"] == 2

    def test_handles_missing_author(self):
        raw = {
            "id": 1,
            "name": "Test Series",
            "slug": "test-series",
            "description": None,
            "books_count": 0,
            "primary_books_count": None,
            "is_completed": None,
            "author": None,
            "book_series": [],
        }

        result = _format_series(raw)

        assert result["authors"] == []
        assert result["books"] == []

    def test_excludes_users_count_from_output(self):
        raw = {
            "id": 1,
            "name": "S",
            "slug": "s",
            "books_count": 1,
            "author": None,
            "book_series": [
                {
                    "position": 1,
                    "book": {
                        "id": 10,
                        "slug": "b",
                        "title": "B",
                        "release_year": 2020,
                        "rating": 4.0,
                        "users_count": 999,
                    },
                },
            ],
        }

        result = _format_series(raw)

        assert "users_count" not in result["books"][0]


class TestSeriesPositions:
    def test_unnumbered_books_are_all_kept_and_positions_once(self):
        from hardcover_mcp.tools.series import _format_series

        def entry(position, book_id):
            return {"position": position, "book": {"id": book_id, "slug": "s", "title": "T"}}

        raw = {
            "id": 1,
            "name": "S",
            "slug": "s",
            "books_count": 5,
            "book_series": [
                entry(1, 10),
                entry(1, 11),
                entry(2, 12),
                entry(None, 13),
                entry(None, 14),
            ],
        }

        assert [b["book_id"] for b in _format_series(raw)["books"]] == [10, 12, 13, 14]


_SERIES = {"id": 4, "name": "S", "slug": "s", "books_count": 0, "book_series": []}


class TestHandleGetSeries:
    async def _run(self, arguments: dict, found: list, resolved=None):
        from hardcover_mcp.tools.series import handle_get_series

        mock = AsyncMock(return_value={"data": {"series": found}})
        with (
            patch("hardcover_mcp.tools.series.execute", new=mock),
            patch(
                "hardcover_mcp.tools.series.resolve_id_by_name",
                new=AsyncMock(return_value=resolved),
            ),
        ):
            result = await handle_get_series(arguments)
        return result[0].text, mock

    async def test_name_resolves_to_an_id_lookup(self):
        text, mock = await self._run({"name": "S"}, [_SERIES], resolved=4)
        assert json.loads(text)["id"] == 4
        assert mock.call_args[0][1] == {"id": 4}

    async def test_slug_uses_the_slug_query(self):
        _, mock = await self._run({"slug": "s"}, [_SERIES])
        assert mock.call_args[0][1] == {"slug": "s"}
        assert "{slug: {_eq: $slug}}" in mock.call_args[0][0]

    async def test_unknown_series_is_not_found(self):
        text, _ = await self._run({"slug": "nope"}, [])
        assert text == "No series found."
