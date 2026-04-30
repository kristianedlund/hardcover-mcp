"""Integration tests that hit the real Hardcover API.

Requires HARDCOVER_API_TOKEN in the environment (loaded from .env by conftest.py).
Skipped automatically when the token is absent.

Run locally:
    uv run python -m pytest tests/integration/ -v
"""

import json

import pytest

pytestmark = pytest.mark.integration


# ── Read tools ──


class TestMe:
    async def test_returns_authenticated_user(self):
        from hardcover_mcp.tools.user import handle_me

        result = await handle_me()

        data = json.loads(result[0].text)
        assert "id" in data
        assert "username" in data
        assert isinstance(data["id"], int)


class TestSearchBooks:
    async def test_search_returns_results(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Project Hail Mary"})

        data = json.loads(result[0].text)
        assert data["found"] > 0
        assert len(data["books"]) > 0
        assert data["books"][0]["title"] is not None

    async def test_search_respects_per_page(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Sanderson", "per_page": 2})

        data = json.loads(result[0].text)
        assert len(data["books"]) <= 2


class TestGetBook:
    async def test_get_book_by_slug(self):
        from hardcover_mcp.tools.books import handle_get_book

        result = await handle_get_book({"slug": "project-hail-mary"})

        data = json.loads(result[0].text)
        assert data["title"] == "Project Hail Mary"
        assert data["id"] is not None

    async def test_get_book_by_id(self):
        from hardcover_mcp.tools.books import handle_get_book

        result = await handle_get_book({"slug": "project-hail-mary"})
        book_id = json.loads(result[0].text)["id"]

        result = await handle_get_book({"id": book_id})
        data = json.loads(result[0].text)
        assert data["title"] == "Project Hail Mary"


class TestGetUserLibrary:
    async def test_returns_library_entries(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({})

        data = json.loads(result[0].text)
        assert "books" in data
        assert "total" in data
        assert isinstance(data["books"], list)

    async def test_filter_by_status(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({"status": "Want to Read"})

        data = json.loads(result[0].text)
        assert "books" in data
        assert isinstance(data["books"], list)

    async def test_pagination(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({"limit": 2, "offset": 0})

        data = json.loads(result[0].text)
        assert data["returned"] <= 2


class TestGetAuthor:
    async def test_get_author_by_slug(self):
        from hardcover_mcp.tools.authors import handle_get_author

        result = await handle_get_author({"slug": "brandon-sanderson"})

        data = json.loads(result[0].text)
        assert data["name"] == "Brandon Sanderson"
        assert data["slug"] == "brandon-sanderson"
        assert isinstance(data["books"], list)
        assert len(data["books"]) > 0

    async def test_get_author_by_name(self):
        from hardcover_mcp.tools.authors import handle_get_author

        result = await handle_get_author({"name": "Andy Weir"})

        data = json.loads(result[0].text)
        assert data["name"] == "Andy Weir"
        assert isinstance(data["books"], list)

    async def test_get_author_respects_books_limit(self):
        from hardcover_mcp.tools.authors import handle_get_author

        result = await handle_get_author({"slug": "brandon-sanderson", "books_limit": 3})

        data = json.loads(result[0].text)
        assert len(data["books"]) <= 3

    async def test_unknown_author_returns_not_found(self):
        from hardcover_mcp.tools.authors import handle_get_author

        result = await handle_get_author({"slug": "zzz-does-not-exist-zzz"})

        assert "No author found" in result[0].text


class TestGetMyLists:
    async def test_returns_lists(self):
        from hardcover_mcp.tools.lists import handle_get_my_lists

        result = await handle_get_my_lists({})

        data = json.loads(result[0].text)
        assert isinstance(data, list)

    async def test_list_has_expected_fields(self):
        from hardcover_mcp.tools.lists import handle_get_my_lists

        result = await handle_get_my_lists({"limit": 1})

        data = json.loads(result[0].text)
        if data:
            lst = data[0]
            assert "id" in lst
            assert "name" in lst


class TestGetSeries:
    async def test_get_series_by_slug(self):
        from hardcover_mcp.tools.series import handle_get_series

        result = await handle_get_series({"slug": "the-stormlight-archive"})

        data = json.loads(result[0].text)
        assert data["name"] == "The Stormlight Archive"
        assert data["slug"] == "the-stormlight-archive"
        assert len(data["books"]) > 0
        # Books are sorted by position; first position should be the lowest
        assert data["books"][0]["position"] is not None

    async def test_get_series_by_name(self):
        from hardcover_mcp.tools.series import handle_get_series

        result = await handle_get_series({"name": "Harry Potter"})

        data = json.loads(result[0].text)
        assert "Harry Potter" in data["name"]
        assert data["books_count"] > 0

    async def test_get_series_returns_error_without_args(self):
        from hardcover_mcp.tools.series import handle_get_series

        result = await handle_get_series({})

        assert "Error" in result[0].text


class TestGetEdition:
    async def test_get_edition_by_isbn13(self):
        from hardcover_mcp.tools.editions import handle_get_edition

        result = await handle_get_edition({"isbn_13": "9780547928227"})

        data = json.loads(result[0].text)
        assert "id" in data
        assert data["isbn_13"] == "9780547928227"
        assert isinstance(data["book"], dict)
        assert data["book"]["id"] is not None
        assert "slug" in data["book"]
        assert "title" in data["book"]

    async def test_get_edition_returns_not_found_for_unknown_isbn(self):
        from hardcover_mcp.tools.editions import handle_get_edition

        result = await handle_get_edition({"isbn_13": "9780000000000"})

        assert "No edition found" in result[0].text

    async def test_get_edition_error_on_no_args(self):
        from hardcover_mcp.tools.editions import handle_get_edition

        result = await handle_get_edition({})

        assert "Error" in result[0].text

    async def test_get_edition_error_on_multiple_args(self):
        from hardcover_mcp.tools.editions import handle_get_edition

        result = await handle_get_edition({"isbn_13": "9780547928227", "asin": "B007978NPG"})

        assert "Error" in result[0].text


class TestSearchEntities:
    async def test_search_author_returns_results(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Brandon Sanderson", "query_type": "Author"})

        data = json.loads(result[0].text)
        assert data["found"] > 0
        assert len(data["authors"]) > 0
        assert data["authors"][0]["name"] is not None

    async def test_search_author_result_has_expected_fields(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Andy Weir", "query_type": "Author"})

        data = json.loads(result[0].text)
        assert data["found"] > 0
        author = data["authors"][0]
        assert "id" in author
        assert "name" in author
        assert "slug" in author

    async def test_search_series_returns_results(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Stormlight", "query_type": "Series"})

        data = json.loads(result[0].text)
        assert data["found"] > 0
        assert len(data["series"]) > 0
        assert data["series"][0]["name"] is not None

    async def test_search_series_result_has_expected_fields(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Mistborn", "query_type": "Series"})

        data = json.loads(result[0].text)
        assert data["found"] > 0
        series = data["series"][0]
        assert "id" in series
        assert "name" in series
        assert "slug" in series


class TestGetReadingStats:
    async def test_returns_required_fields(self):
        from hardcover_mcp.tools.stats import handle_get_reading_stats

        result = await handle_get_reading_stats({})

        data = json.loads(result[0].text)
        assert "total_books" in data
        assert "by_status" in data
        assert "average_rating" in data
        assert "books_read_this_year" in data
        assert "year" in data

    async def test_by_status_has_all_statuses(self):
        from hardcover_mcp.tools.stats import handle_get_reading_stats

        result = await handle_get_reading_stats({})

        data = json.loads(result[0].text)
        by_status = data["by_status"]
        assert "want_to_read" in by_status
        assert "currently_reading" in by_status
        assert "read" in by_status
        assert "did_not_finish" in by_status
        assert "paused" in by_status
        assert "ignored" in by_status

    async def test_total_books_is_non_negative(self):
        from hardcover_mcp.tools.stats import handle_get_reading_stats

        result = await handle_get_reading_stats({})

        data = json.loads(result[0].text)
        assert isinstance(data["total_books"], int)
        assert data["total_books"] >= 0

    async def test_year_filter_changes_books_read_count(self):
        from hardcover_mcp.tools.stats import handle_get_reading_stats

        result_past = await handle_get_reading_stats({"year": 1900})

        data = json.loads(result_past[0].text)
        # No books were read in 1900 — count should be 0
        assert data["books_read_this_year"] == 0
        assert data["year"] == 1900
