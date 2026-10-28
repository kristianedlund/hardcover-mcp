"""Unit tests for tools/editions.py — formatting helpers and handler logic."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.editions import _format_edition, fetch_edition


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


class TestFetchEdition:
    @pytest.mark.parametrize(
        ("key", "value", "where"),
        [
            ("isbn_13", "9780547928227", {"isbn_13": {"_eq": "9780547928227"}}),
            ("asin", "B007978NPG", {"asin": {"_eq": "B007978NPG"}}),
            ("edition_id", "99", {"id": {"_eq": 99}}),
        ],
    )
    async def test_looks_up_by_the_key_given(self, key, value, where):
        found = {"data": {"editions": [{"id": 99, "title": "A Book", "book": None}]}}
        mock = AsyncMock(return_value=found)
        with patch("hardcover_mcp.tools.editions.execute", new=mock):
            result = await fetch_edition(key, value)

        assert json.loads(result[0].text)["id"] == 99
        assert mock.call_args[0][1] == {"where": where}

    async def test_non_numeric_edition_id_is_an_error(self):
        with pytest.raises(ToolError, match="'edition_id' must be an integer"):
            await fetch_edition("edition_id", "not-a-number")

    async def test_nothing_found(self):
        mock = AsyncMock(return_value={"data": {"editions": []}})
        with patch("hardcover_mcp.tools.editions.execute", new=mock):
            result = await fetch_edition("isbn_13", "9780000000000")

        assert result[0].text == "No edition found."


_RAW_EDITION = {
    "id": 1,
    "title": "T",
    "edition_format": "Hardcover",
    "language": {"language": "English"},
    "publisher": {"id": 5, "name": "Pub", "slug": "pub"},
    "reading_format": {"format": "Read"},
    "book": {"id": 9, "title": "B", "slug": "b"},
    "users_count": 3,
}


class TestOneEditionShape:
    """Every tool that returns an edition uses the keys of ``format_edition``."""

    def test_every_tool_shares_the_core_keys(self):
        from hardcover_mcp.tools.books import _format_edition_summary
        from hardcover_mcp.tools.editions import _format_edition, format_edition
        from hardcover_mcp.tools.library import _format_user_book_detail
        from hardcover_mcp.tools.publishers import _format_publisher

        core = format_edition(_RAW_EDITION)
        ub = {"id": 1, "book_id": 9, "status_id": 1, "book": {}, "edition": _RAW_EDITION}
        shaped = [
            _format_edition(_RAW_EDITION),
            _format_edition_summary(_RAW_EDITION),
            _format_user_book_detail(ub)["edition"],
            _format_publisher({"editions": [_RAW_EDITION]})["editions"][0],
        ]

        for edition in shaped:
            assert {k: edition[k] for k in core} == core
        assert core["language"] == "English"
        assert core["publisher"] == {"id": 5, "name": "Pub", "slug": "pub"}
