"""Tests for tools/books.py — formatting helpers and handler logic."""

from unittest.mock import AsyncMock, patch

from hardcover_mcp.tools.books import _format_search_hit, handle_get_book, handle_search_books


class TestFormatSearchHit:
    def test_extracts_fields_from_document(self):
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
        assert result["pages"] == 476

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

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_caps_per_page_at_25(self, mock_execute):
        mock_execute.return_value = {
            "data": {"search": {"results": {"hits": [], "found": 0}}}
        }

        await handle_search_books({"query": "test", "per_page": 100})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["per_page"] == 25


class TestHandleGetBook:
    async def test_returns_error_on_non_numeric_id(self):
        result = await handle_get_book({"id": "not-a-number"})

        assert "must be an integer" in result[0].text
