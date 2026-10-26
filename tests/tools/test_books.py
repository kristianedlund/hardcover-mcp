"""Tests for tools/books.py — formatting helpers and handler logic."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.books import (
    _format_character,
    _format_search_hit,
    author_names,
    contributors,
    handle_get_book,
    handle_search_books,
)


class TestFormatSearchHit:
    def test_book_extracts_fields_from_document(self):
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
        assert result["series"] == "Standalone"

    def test_book_authors_leave_out_narrators(self):
        hit = {
            "document": {
                "id": 44186,
                "title": "Educated",
                "author_names": ["Tara Westover", "Julia Whelan"],
                "contributions": [
                    {"author": {"name": "Tara Westover"}, "contribution": "Author"},
                    {"author": {"name": "Julia Whelan"}, "contribution": "Narrator"},
                ],
            }
        }
        assert _format_search_hit(hit)["authors"] == ["Tara Westover"]

    def test_author_extracts_fields_from_document(self):
        hit = {
            "document": {
                "id": 100,
                "name": "Brandon Sanderson",
                "slug": "brandon-sanderson",
                "books_count": 50,
                "image": "https://example.com/img.jpg",
            }
        }
        result = _format_search_hit(hit, query_type="Author")

        assert result["id"] == 100
        assert result["name"] == "Brandon Sanderson"
        assert result["books_count"] == 50
        assert result["image"] == "https://example.com/img.jpg"

    def test_series_extracts_fields_from_document(self):
        hit = {
            "document": {
                "id": 7,
                "name": "The Stormlight Archive",
                "slug": "the-stormlight-archive",
                "books_count": 5,
            }
        }
        result = _format_search_hit(hit, query_type="Series")

        assert result["id"] == 7
        assert result["name"] == "The Stormlight Archive"
        assert result["books_count"] == 5
        assert "title" not in result

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
        with pytest.raises(ToolError) as exc:
            await handle_search_books({"query": ""})

        assert "required" in str(exc.value)

    async def test_returns_error_on_missing_query(self):
        with pytest.raises(ToolError) as exc:
            await handle_search_books({})

        assert "required" in str(exc.value)

    async def test_returns_error_on_invalid_query_type(self):
        with pytest.raises(ToolError) as exc:
            await handle_search_books({"query": "test", "query_type": "Planet"})

        assert "invalid query_type" in str(exc.value)

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_caps_per_page_at_25(self, mock_execute):
        mock_execute.return_value = {"data": {"search": {"results": {"hits": [], "found": 0}}}}

        await handle_search_books({"query": "test", "per_page": 100})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["per_page"] == 25

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_result_has_total_returned_and_page(self, mock_execute):
        hit = {"document": {"id": 1, "title": "T", "slug": "t", "author_names": ["A"]}}
        mock_execute.return_value = {"data": {"search": {"results": {"hits": [hit], "found": 42}}}}

        data = json.loads((await handle_search_books({"query": "t", "page": 2}))[0].text)

        assert {k: data[k] for k in ("total", "returned", "page")} == {
            "total": 42,
            "returned": 1,
            "page": 2,
        }
        assert "found" not in data
        assert data["books"][0]["title"] == "T"

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

        result = await handle_search_books({"query": "Project Hail Mary"})
        data = json.loads(result[0].text)

        assert "books" in data
        assert data["books"][0]["title"] == "Project Hail Mary"


class TestHandleGetBook:
    async def test_returns_error_on_non_numeric_id(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_book({"id": "not-a-number"})

        assert "must be an integer" in str(exc.value)


class TestFormatCharacter:
    def test_flattens_book_character_row(self):
        row = {
            "spoiler": True,
            "only_mentioned": False,
            "character": {
                "id": 1,
                "name": "Kvothe",
                "slug": "kvothe",
                "biography": "The main protagonist.",
            },
        }
        result = _format_character(row)

        assert result == {
            "id": 1,
            "name": "Kvothe",
            "slug": "kvothe",
            "biography": "The main protagonist.",
            "spoiler": True,
            "only_mentioned": False,
        }

    def test_handles_missing_fields_gracefully(self):
        result = _format_character({})

        assert result["id"] is None
        assert result["name"] is None
        assert result["biography"] is None
        assert result["spoiler"] is None


def _book() -> dict:
    return {"data": {"books": [{"id": 123, "title": "T", "contributions": []}]}}


def _chars() -> dict:
    return {
        "data": {
            "book_characters": [
                {
                    "spoiler": False,
                    "only_mentioned": False,
                    "character": {"id": 1, "name": "Kvothe", "slug": "kvothe", "biography": "x"},
                },
                {
                    "spoiler": True,
                    "only_mentioned": True,
                    "character": {"id": 2, "name": "Denna", "slug": "denna", "biography": None},
                },
            ]
        }
    }


class TestHandleGetBookIncludeCharacters:
    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_omits_characters_by_default(self, mock_execute):
        mock_execute.return_value = _book()

        data = json.loads((await handle_get_book({"id": 123}))[0].text)

        assert "characters" not in data
        assert mock_execute.call_count == 1

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_includes_characters_when_requested(self, mock_execute):
        mock_execute.side_effect = [_book(), _chars()]

        data = json.loads((await handle_get_book({"id": 123, "include_characters": True}))[0].text)

        assert [c["name"] for c in data["characters"]] == ["Kvothe", "Denna"]
        assert mock_execute.call_args_list[1][0][1] == {"book_id": 123}

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_empty_characters_is_empty_list(self, mock_execute):
        mock_execute.side_effect = [_book(), {"data": {"book_characters": []}}]

        data = json.loads((await handle_get_book({"id": 123, "include_characters": True}))[0].text)

        assert data["characters"] == []


def _c(name: str, role: str | None) -> dict:
    return {"author": {"name": name}, "contribution": role}


class TestAuthorNames:
    def test_reads_contributions_relation(self):
        book = {"contributions": [_c("A", "Author"), {"author": None}, {}]}
        assert author_names(book) == ["A"]

    def test_prefers_cached_contributors(self):
        book = {
            "cached_contributors": [
                {"author": {"id": 1, "name": "Neil Gaiman"}, "contribution": "Author"},
                {"author": {"id": 2, "name": "Terry Pratchett"}, "contribution": "Author"},
            ],
            "contributions": [_c("ignored", "Author")],
        }
        assert author_names(book) == ["Neil Gaiman", "Terry Pratchett"]

    def test_leaves_out_other_roles(self):
        book = {
            "cached_contributors": [
                _c("John Mackey", "Author"),
                _c("Bill George", "Foreword"),
                _c("Ray Porter", "Narrator"),
                _c("Raj Sisodia", "Author"),
                _c("Joel Martinsen", "Translator"),
            ]
        }
        assert author_names(book) == ["John Mackey", "Raj Sisodia"]

    def test_empty_role_counts_as_author(self):
        book = {"cached_contributors": [_c("Old Record", None), _c("N", "Narrator")]}
        assert author_names(book) == ["Old Record"]

    def test_missing_role_key_counts_as_author(self):
        assert author_names({"contributions": [{"author": {"name": "A"}}]}) == ["A"]

    def test_no_author_role_falls_back_to_first_contributor(self):
        book = {"contributions": [_c("Ed One", "Editor"), _c("Ed Two", "Editor")]}
        assert author_names(book) == ["Ed One"]

    def test_empty_cached_contributors_is_empty(self):
        assert author_names({"cached_contributors": []}) == []

    def test_no_contributors(self):
        assert author_names({}) == []


class TestContributors:
    def test_lists_every_contributor_with_role(self):
        book = {"contributions": [_c("Tara Westover", "Author"), _c("Julia Whelan", "Narrator")]}
        assert contributors(book) == [
            {"name": "Tara Westover", "role": "Author"},
            {"name": "Julia Whelan", "role": "Narrator"},
        ]

    def test_empty_role_reported_as_author(self):
        assert contributors({"cached_contributors": [_c("A", None)]}) == [
            {"name": "A", "role": "Author"}
        ]

    def test_skips_entries_without_a_name(self):
        assert contributors({"contributions": [{"author": None}, {}]}) == []


class TestHandleGetBookContributors:
    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_authors_and_contributors(self, mock_execute):
        book = {"id": 1, "title": "Educated"}
        book["contributions"] = [_c("Tara Westover", "Author"), _c("Julia Whelan", "Narrator")]
        mock_execute.return_value = {"data": {"books": [book]}}

        data = json.loads((await handle_get_book({"id": 1}))[0].text)

        assert data["authors"] == ["Tara Westover"]
        assert data["contributors"] == [
            {"name": "Tara Westover", "role": "Author"},
            {"name": "Julia Whelan", "role": "Narrator"},
        ]
        assert "contributions" not in data


def _editions() -> dict:
    return {
        "data": {
            "editions": [
                {
                    "id": 7,
                    "title": "T",
                    "edition_format": "Hardcover",
                    "pages": 400,
                    "isbn_13": "9780000000000",
                    "users_count": 50,
                    "language": {"language": "English"},
                    "publisher": {"name": "Pub"},
                    "reading_format": {"format": "Read"},
                },
                {"id": 8, "language": None, "publisher": None, "reading_format": None},
            ]
        }
    }


class TestHandleGetBookIncludeEditions:
    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_omits_editions_by_default(self, mock_execute):
        mock_execute.return_value = _book()

        data = json.loads((await handle_get_book({"id": 123}))[0].text)

        assert "editions" not in data
        assert mock_execute.call_count == 1

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_includes_flattened_editions(self, mock_execute):
        mock_execute.side_effect = [_book(), _editions()]

        data = json.loads((await handle_get_book({"id": 123, "include_editions": True}))[0].text)

        first, second = data["editions"]
        assert first["language"] == "English"
        assert first["publisher"]["name"] == "Pub"
        assert first["reading_format"] == "Read"
        assert second["language"] is None
        assert mock_execute.call_args_list[1][0][1] == {"book_id": 123, "limit": 10}

    @patch("hardcover_mcp.tools.books.execute", new_callable=AsyncMock)
    async def test_editions_limit_is_capped(self, mock_execute):
        mock_execute.side_effect = [_book(), {"data": {"editions": []}}]

        await handle_get_book({"id": 123, "include_editions": True, "editions_limit": 500})

        assert mock_execute.call_args_list[1][0][1]["limit"] == 50

    async def test_rejects_non_integer_editions_limit(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_book({"id": 123, "editions_limit": "lots"})

        assert "must be an integer" in str(exc.value)


class TestHandleGetBookEditionKeys:
    @patch("hardcover_mcp.tools.books.handle_get_edition", new_callable=AsyncMock)
    async def test_isbn_returns_the_edition(self, mock_edition):
        mock_edition.return_value = ["edition result"]

        result = await handle_get_book({"isbn_13": "9780593135204"})

        assert result == ["edition result"]
        mock_edition.assert_awaited_once_with({"isbn_13": "9780593135204"})

    @patch("hardcover_mcp.tools.books.handle_get_edition", new_callable=AsyncMock)
    async def test_edition_id_maps_to_edition_lookup_id(self, mock_edition):
        await handle_get_book({"edition_id": 30405492})

        mock_edition.assert_awaited_once_with({"id": 30405492})

    @patch("hardcover_mcp.tools.books.handle_get_edition", new_callable=AsyncMock)
    async def test_asin_returns_the_edition(self, mock_edition):
        await handle_get_book({"asin": "B08FHBV4ZX"})

        mock_edition.assert_awaited_once_with({"asin": "B08FHBV4ZX"})

    async def test_rejects_book_and_edition_keys_together(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_book({"id": 1, "isbn_13": "9780593135204"})

        assert "provide one of 'id' or 'slug'" in str(exc.value)

    async def test_rejects_two_edition_keys(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_book({"isbn_13": "9780593135204", "asin": "B08FHBV4ZX"})

        assert "exactly one of 'isbn_13'" in str(exc.value)

    async def test_rejects_include_flags_with_edition_key(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_book({"isbn_13": "9780593135204", "include_editions": True})

        assert "need a book key" in str(exc.value)

    async def test_requires_some_key(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_book({})

        assert "provide one of 'id' or 'slug'" in str(exc.value)
