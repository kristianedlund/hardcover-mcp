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
            assert "privacy" in lst

        data = json.loads(result[0].text)
        assert isinstance(data, list)
