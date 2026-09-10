"""Integration tests for discovery tools against the real Hardcover API.

Requires HARDCOVER_API_TOKEN in the environment (loaded from .env by conftest.py).
Skipped automatically when the token is absent.
"""

import json

import pytest

pytestmark = pytest.mark.integration


class TestTrendingBooks:
    async def test_returns_book_summaries(self):
        from hardcover_mcp.tools.discovery import handle_get_trending_books

        result = await handle_get_trending_books({"duration": "week", "limit": 3})

        books = json.loads(result[0].text)
        assert isinstance(books, list)
        assert 0 < len(books) <= 3
        assert books[0]["title"]
        assert "authors" in books[0]


class TestVibes:
    async def test_featured_vibes_include_books(self):
        from hardcover_mcp.tools.discovery import handle_get_vibes

        result = await handle_get_vibes({"limit": 1, "books_per_vibe": 2})

        vibes = json.loads(result[0].text)
        assert isinstance(vibes, list)
        assert len(vibes) == 1
        assert vibes[0]["title"]
        assert len(vibes[0]["books"]) <= 2


class TestSearchSortFilter:
    async def test_filter_by_narrows_results(self):
        from hardcover_mcp.tools.books import handle_search_books

        unfiltered = json.loads(
            (await handle_search_books({"query": "fantasy", "per_page": 1}))[0].text
        )
        filtered = json.loads(
            (
                await handle_search_books(
                    {"query": "fantasy", "per_page": 1, "filter_by": "release_year:>2020"}
                )
            )[0].text
        )
        # Filtering by year must not return more hits than the unfiltered query.
        assert filtered["found"] <= unfiltered["found"]

    async def test_sort_by_rating_desc(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books(
            {"query": "fantasy", "per_page": 2, "sort": "rating:desc"}
        )
        books = json.loads(result[0].text)["books"]
        ratings = [b["rating"] for b in books if b.get("rating") is not None]
        assert ratings == sorted(ratings, reverse=True)
