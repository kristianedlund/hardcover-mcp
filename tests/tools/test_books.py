"""Tests for tools/books.py — formatting helpers and handler logic."""

from unittest.mock import AsyncMock, patch

from hardcover_mcp.tools.books import (
    _format_author_hit,
    _format_book_hit,
    _format_search_hit,
    _format_series_hit,
    handle_get_book,
    handle_search_books,
)


class TestFormatBookHit:
    def test_extracts_fields_from_document(self):
        doc = {
            "id": 42,
            "title": "Project Hail Mary",
            "slug": "project-hail-mary",
            "author_names": ["Andy Weir"],
            "release_year": 2021,
            "rating": 4.5,
            "pages": 476,
            "featured_series": "Standalone",
        }
        result = _format_book_hit(doc)

        assert result["id"] == 42
        assert result["title"] == "Project Hail Mary"
        assert result["authors"] == ["Andy Weir"]
        assert result["pages"] == 476

    def test_handles_missing_fields_gracefully(self):
        result = _format_book_hit({})

        assert result["id"] is None
        assert result["title"] is None
        assert result["authors"] == []


class TestFormatAuthorHit:
    def test_extracts_fields_from_document(self):
        doc = {
            "id": 100,
            "name": "Brandon Sanderson",
            "slug": "brandon-sanderson",
            "books_count": 50,
            "image": "https://example.com/img.jpg",
        }
        result = _format_author_hit(doc)

        assert result["id"] == 100
        assert result["name"] == "Brandon Sanderson"
        assert result["slug"] == "brandon-sanderson"
        assert result["books_count"] == 50

    def test_handles_missing_fields_gracefully(self):
        result = _format_author_hit({})

        assert result["id"] is None
        assert result["name"] is None
        assert result["books_count"] is None


class TestFormatSeriesHit:
    def test_extracts_fields_from_document(self):
        doc = {
            "id": 7,
            "name": "The Stormlight Archive",
            "slug": "the-stormlight-archive",
            "books_count": 5,
        }
        result = _format_series_hit(doc)

        assert result["id"] == 7
        assert result["name"] == "The Stormlight Archive"
        assert result["slug"] == "the-stormlight-archive"
        assert result["books_count"] == 5


class TestFormatSearchHit:
    def test_dispatches_to_book_formatter_by_default(self):
        hit = {
            "document": {
                "id": 42,
                "title": "Project Hail Mary",
                "slug": "project-hail-mary",
                "author_names": ["Andy Weir"],
                "release_year": 2021,
                "rating": 4.5,
                "pages": 476,
                "featured_series": "Standalone",
            }
        }
        result = _format_search_hit(hit)

        assert result["id"] == 42
        assert result["title"] == "Project Hail Mary"
        assert result["authors"] == ["Andy Weir"]

    def test_dispatches_to_author_formatter(self):
        hit = {"document": {"id": 1, "name": "Andy Weir", "slug": "andy-weir"}}
        result = _format_search_hit(hit, query_type="Author")

        assert result["id"] == 1
        assert result["name"] == "Andy Weir"
        assert "title" not in result

    def test_dispatches_to_series_formatter(self):
        hit = {"document": {"id": 5, "name": "Mistborn", "slug": "mistborn"}}
        result = _format_search_hit(hit, query_type="Series")

        assert result["name"] == "Mistborn"
        assert "title" not in result

    def test_handles_missing_document_gracefully(self):
        result = _format_search_hit({})

        assert result["id"] is None
        assert result["title"] is None
        assert result["authors"] == []


class TestHandleSearchBooks:
    async def test_returns_error_on_empty_query(self):
        result = await handle_search_books({"query": ""})

        assert len(result) == 1
        assert "required" in result[0].text.lower()

    async def test_returns_error_on_missing_query(self):
        result = await handle_search_books({})

        assert "required" in result[0].text.lower()

    async def test_returns_error_on_invalid_query_type(self):
        result = await handle_search_books({"query": "test", "query_type": "Planet"})

        assert "invalid query_type" in result[0].text.lower()

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_caps_per_page_at_25(self, mock_execute):
        mock_execute.return_value = {"data": {"search": {"results": {"hits": [], "found": 0}}}}

        await handle_search_books({"query": "test", "per_page": 100})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["per_page"] == 25

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_default_query_type_is_book(self, mock_execute):
        mock_execute.return_value = {"data": {"search": {"results": {"hits": [], "found": 0}}}}

        await handle_search_books({"query": "test"})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["query_type"] == "Book"

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_passes_query_type_to_execute(self, mock_execute):
        mock_execute.return_value = {"data": {"search": {"results": {"hits": [], "found": 0}}}}

        await handle_search_books({"query": "Andy Weir", "query_type": "Author"})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["query_type"] == "Author"

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_author_results_keyed_as_authors(self, mock_execute):
        mock_execute.return_value = {
            "data": {
                "search": {
                    "results": {
                        "hits": [
                            {"document": {"id": 1, "name": "Andy Weir", "slug": "andy-weir"}}
                        ],
                        "found": 1,
                    }
                }
            }
        }

        import json

        result = await handle_search_books({"query": "Andy Weir", "query_type": "Author"})
        data = json.loads(result[0].text)

        assert "authors" in data
        assert data["authors"][0]["name"] == "Andy Weir"

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_series_results_keyed_as_series(self, mock_execute):
        mock_execute.return_value = {
            "data": {
                "search": {
                    "results": {
                        "hits": [{"document": {"id": 7, "name": "Mistborn", "slug": "mistborn"}}],
                        "found": 1,
                    }
                }
            }
        }

        import json

        result = await handle_search_books({"query": "Mistborn", "query_type": "Series"})
        data = json.loads(result[0].text)

        assert "series" in data
        assert data["series"][0]["name"] == "Mistborn"

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_book_results_keyed_as_books(self, mock_execute):
        mock_execute.return_value = {
            "data": {
                "search": {
                    "results": {
                        "hits": [
                            {
                                "document": {
                                    "id": 42,
                                    "title": "Project Hail Mary",
                                    "slug": "project-hail-mary",
                                    "author_names": ["Andy Weir"],
                                }
                            }
                        ],
                        "found": 1,
                    }
                }
            }
        }

        import json

        result = await handle_search_books({"query": "Project Hail Mary"})
        data = json.loads(result[0].text)

        assert "books" in data
        assert data["books"][0]["title"] == "Project Hail Mary"


class TestHandleGetBook:
    async def test_returns_error_on_non_numeric_id(self):
        result = await handle_get_book({"id": "not-a-number"})

        assert "must be an integer" in result[0].text
