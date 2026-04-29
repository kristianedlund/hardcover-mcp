"""Unit tests for tools/editions.py — formatting helpers and handler logic."""

import json
from unittest.mock import AsyncMock, patch

from hardcover_mcp.tools.editions import _format_edition, handle_get_edition


class TestFormatEdition:
    def test_formats_full_edition(self):
        raw = {
            "id": 1,
            "title": "The Hobbit",
            "subtitle": None,
            "isbn_13": "9780547928227",
            "isbn_10": "054792822X",
            "asin": "B007978NPG",
            "pages": 310,
            "audio_seconds": None,
            "release_date": "2012-09-18",
            "edition_format": "Hardcover",
            "physical_format": "Hardcover",
            "publisher": {
                "id": 10,
                "name": "Houghton Mifflin Harcourt",
                "slug": "houghton-mifflin",
            },
            "language": {"language": "English"},
            "reading_format": {"format": "Physical"},
            "book": {"id": 42, "slug": "the-hobbit", "title": "The Hobbit", "rating": 4.6},
        }

        result = _format_edition(raw)

        assert result["id"] == 1
        assert result["title"] == "The Hobbit"
        assert result["isbn_13"] == "9780547928227"
        assert result["isbn_10"] == "054792822X"
        assert result["asin"] == "B007978NPG"
        assert result["pages"] == 310
        assert result["release_date"] == "2012-09-18"
        assert result["edition_format"] == "Hardcover"
        assert result["publisher"]["name"] == "Houghton Mifflin Harcourt"
        assert result["language"] == "English"
        assert result["reading_format"] == "Physical"
        assert result["book"]["slug"] == "the-hobbit"
        assert result["book"]["rating"] == 4.6

    def test_handles_null_publisher(self):
        raw = {
            "id": 2,
            "title": "Unknown Edition",
            "subtitle": None,
            "isbn_13": None,
            "isbn_10": None,
            "asin": None,
            "pages": None,
            "audio_seconds": None,
            "release_date": None,
            "edition_format": None,
            "physical_format": None,
            "publisher": None,
            "language": None,
            "reading_format": None,
            "book": None,
        }

        result = _format_edition(raw)

        assert result["publisher"] is None
        assert result["language"] is None
        assert result["reading_format"] is None
        assert result["book"] is None

    def test_handles_empty_nested_objects(self):
        raw = {
            "id": 3,
            "title": "Some Book",
            "subtitle": None,
            "isbn_13": "9780000000000",
            "isbn_10": None,
            "asin": None,
            "pages": 200,
            "audio_seconds": None,
            "release_date": None,
            "edition_format": None,
            "physical_format": None,
            "publisher": {},
            "language": {},
            "reading_format": {},
            "book": {},
        }

        result = _format_edition(raw)

        # Empty dicts are falsy — same as None. The API always returns a full object or
        # null; empty dicts should never occur in practice but are handled defensively.
        assert result["publisher"] is None
        assert result["language"] is None
        assert result["reading_format"] is None
        assert result["book"] is None


class TestHandleGetEdition:
    async def test_returns_error_when_no_args(self):
        result = await handle_get_edition({})

        assert "exactly one" in result[0].text.lower()

    async def test_returns_error_when_multiple_args(self):
        result = await handle_get_edition({"isbn_13": "9780547928227", "asin": "B007978NPG"})

        assert "exactly one" in result[0].text.lower()

    async def test_returns_error_on_non_numeric_id(self):
        result = await handle_get_edition({"id": "not-a-number"})

        assert "must be an integer" in result[0].text

    @patch("hardcover_mcp.tools.editions.execute", new_callable=AsyncMock)
    async def test_lookup_by_isbn13(self, mock_execute):
        mock_execute.return_value = {
            "data": {
                "editions": [
                    {
                        "id": 1,
                        "title": "The Hobbit",
                        "subtitle": None,
                        "isbn_13": "9780547928227",
                        "isbn_10": None,
                        "asin": None,
                        "pages": 310,
                        "audio_seconds": None,
                        "release_date": "2012-09-18",
                        "edition_format": None,
                        "physical_format": None,
                        "publisher": None,
                        "language": None,
                        "reading_format": None,
                        "book": {
                            "id": 42,
                            "slug": "the-hobbit",
                            "title": "The Hobbit",
                            "rating": 4.6,
                        },
                    }
                ]
            }
        }

        result = await handle_get_edition({"isbn_13": "9780547928227"})

        data = json.loads(result[0].text)
        assert data["isbn_13"] == "9780547928227"
        assert data["title"] == "The Hobbit"
        call_vars = mock_execute.call_args[0][1]
        assert call_vars["isbn_13"] == "9780547928227"

    @patch("hardcover_mcp.tools.editions.execute", new_callable=AsyncMock)
    async def test_lookup_by_asin(self, mock_execute):
        mock_execute.return_value = {"data": {"editions": []}}

        result = await handle_get_edition({"asin": "B007978NPG"})

        assert "No edition found" in result[0].text
        call_vars = mock_execute.call_args[0][1]
        assert call_vars["asin"] == "B007978NPG"

    @patch("hardcover_mcp.tools.editions.execute", new_callable=AsyncMock)
    async def test_lookup_by_id(self, mock_execute):
        mock_execute.return_value = {
            "data": {
                "editions": [
                    {
                        "id": 99,
                        "title": "A Book",
                        "subtitle": None,
                        "isbn_13": None,
                        "isbn_10": None,
                        "asin": None,
                        "pages": 100,
                        "audio_seconds": None,
                        "release_date": None,
                        "edition_format": None,
                        "physical_format": None,
                        "publisher": None,
                        "language": None,
                        "reading_format": None,
                        "book": None,
                    }
                ]
            }
        }

        result = await handle_get_edition({"id": 99})

        data = json.loads(result[0].text)
        assert data["id"] == 99
        call_vars = mock_execute.call_args[0][1]
        assert call_vars["id"] == 99

    @patch("hardcover_mcp.tools.editions.execute", new_callable=AsyncMock)
    async def test_returns_no_edition_found_when_empty(self, mock_execute):
        mock_execute.return_value = {"data": {"editions": []}}

        result = await handle_get_edition({"isbn_13": "9780000000000"})

        assert "No edition found" in result[0].text
