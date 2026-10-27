"""Tests for tools/library.py — status resolution, formatting, input building."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.library import (
    LIBRARY_SORT_FIELDS,
    STATUS_MAP,
    STATUS_NAMES,
    _build_read_input,
    _format_user_book,
    _format_user_book_detail,
    _format_user_review,
    _merge_read_input,
    _resolve_status_id,
    _set_edition_owned,
    _text_to_slate,
    handle_get_user_book,
    handle_get_user_library,
    handle_set_user_book,
    handle_set_user_book_read,
    status_label,
)


class TestResolveStatusId:
    def test_returns_none_for_none(self):
        assert _resolve_status_id(None) is None

    def test_resolves_int_directly(self):
        assert _resolve_status_id(3) == 3

    def test_resolves_numeric_string(self):
        assert _resolve_status_id("3") == 3

    def test_resolves_name_case_insensitive(self):
        assert _resolve_status_id("currently reading") == 2
        assert _resolve_status_id("Currently Reading") == 2

    def test_resolves_every_status(self):
        for status_id, name in STATUS_MAP.items():
            assert _resolve_status_id(name.upper()) == status_id
            assert _resolve_status_id(status_id) == status_id

    @pytest.mark.parametrize("value", ["nonexistent", "", 0, 7, 99, "99", True, 3.0, ["Read"]])
    def test_rejects_anything_else(self, value):
        with pytest.raises(ToolError, match="unknown status") as exc:
            _resolve_status_id(value)
        assert "Did Not Finish" in str(exc.value)  # lists the valid names

    def test_error_names_the_argument(self):
        with pytest.raises(ToolError, match="unknown library_status"):
            _resolve_status_id("x", "library_status")


class TestStatusLabel:
    def test_labels(self):
        assert status_label(5) == "Did Not Finish"
        assert status_label(None) is None
        assert status_label(99) == "unknown (99)"

    def test_status_schemas_list_every_name(self):
        from hardcover_mcp import server

        schemas = {
            spec.tool.name: spec.tool.input_schema["properties"] for spec in server.TOOL_REGISTRY
        }
        assert schemas["set_user_book"]["status"]["enum"] == STATUS_NAMES
        assert schemas["get_user_library"]["status"]["enum"] == STATUS_NAMES
        assert schemas["get_user"]["library_status"]["enum"] == STATUS_NAMES


class TestFormatUserBook:
    def test_flattens_contributions_to_authors(self):
        ub = {
            "id": 1,
            "book_id": 42,
            "status_id": 3,
            "rating": 4.5,
            "updated_at": "2025-01-01",
            "book": {
                "title": "Test Book",
                "slug": "test-book",
                "contributions": [{"author": {"name": "Author One"}}],
            },
        }
        result = _format_user_book(ub)

        assert result["authors"] == ["Author One"]
        assert result["status"] == "Read"
        assert result["user_book_id"] == 1

    def test_handles_unknown_status_id(self):
        ub = {
            "id": 1,
            "book_id": 42,
            "status_id": 99,
            "rating": None,
            "updated_at": None,
            "book": {"title": "X", "slug": "x", "contributions": []},
        }
        result = _format_user_book(ub)

        assert result["status"] == "unknown (99)"


class TestMergeReadInput:
    def test_updates_override_existing(self):
        existing = {
            "started_at": "2025-01-01",
            "finished_at": None,
            "progress_pages": 50,
            "progress_seconds": None,
        }
        updates = {"finished_at": "2025-02-01"}

        merged = _merge_read_input(existing, updates)

        assert merged["started_at"] == "2025-01-01"
        assert merged["finished_at"] == "2025-02-01"
        assert merged["progress_pages"] == 50

    def test_skips_none_existing_fields(self):
        existing = {
            "started_at": None,
            "finished_at": None,
            "progress_pages": None,
            "progress_seconds": None,
        }
        updates = {"started_at": "2025-03-01"}

        merged = _merge_read_input(existing, updates)

        assert merged == {"started_at": "2025-03-01"}

    def test_preserves_progress_seconds(self):
        existing = {
            "started_at": "2025-01-01",
            "finished_at": None,
            "progress_pages": None,
            "progress_seconds": 3600,
        }
        updates = {"progress_seconds": 7200}

        merged = _merge_read_input(existing, updates)

        assert merged["progress_seconds"] == 7200
        assert merged["started_at"] == "2025-01-01"


class TestBuildReadInput:
    def test_extracts_read_fields(self):
        args = {"started_at": "2025-01-01", "book_id": 42, "extra": "ignored"}
        result = _build_read_input(args)

        assert result == {"started_at": "2025-01-01"}
        assert "book_id" not in result

    def test_returns_empty_when_no_read_fields(self):
        assert _build_read_input({"book_id": 42}) == {}

    def test_raises_on_non_numeric_progress_pages(self):
        with pytest.raises(ToolError, match="'progress_pages' must be an integer"):
            _build_read_input({"progress_pages": "abc"})

    def test_extracts_progress_seconds(self):
        args = {"progress_seconds": 3600, "book_id": 42}
        result = _build_read_input(args)

        assert result == {"progress_seconds": 3600}

    def test_raises_on_non_numeric_progress_seconds(self):
        with pytest.raises(ToolError, match="'progress_seconds' must be an integer"):
            _build_read_input({"progress_seconds": "abc"})

    def test_extracts_all_fields(self):
        args = {
            "started_at": "2025-01-01",
            "finished_at": "2025-02-01",
            "progress_pages": 100,
            "progress_seconds": 7200,
        }
        result = _build_read_input(args)

        assert result == {
            "started_at": "2025-01-01",
            "finished_at": "2025-02-01",
            "progress_pages": 100,
            "progress_seconds": 7200,
        }


class TestTextToSlate:
    def test_single_paragraph(self):
        result = _text_to_slate("Hello world")
        assert result == [{"type": "p", "children": [{"text": "Hello world"}]}]

    def test_multiple_paragraphs(self):
        result = _text_to_slate("First paragraph\n\nSecond paragraph")
        assert result == [
            {"type": "p", "children": [{"text": "First paragraph"}]},
            {"type": "p", "children": [{"text": "Second paragraph"}]},
        ]

    def test_three_paragraphs(self):
        result = _text_to_slate("One\n\nTwo\n\nThree")
        assert len(result) == 3
        assert result[0]["children"][0]["text"] == "One"
        assert result[1]["children"][0]["text"] == "Two"
        assert result[2]["children"][0]["text"] == "Three"

    def test_empty_paragraphs_skipped(self):
        # Trailing double-newline should not produce an empty node
        result = _text_to_slate("Only one\n\n")
        assert result == [{"type": "p", "children": [{"text": "Only one"}]}]

    def test_single_newline_preserved_within_paragraph(self):
        # A single newline is NOT a paragraph break — kept as-is
        result = _text_to_slate("Line one\nLine two")
        assert result == [{"type": "p", "children": [{"text": "Line one\nLine two"}]}]


class TestHandleSetUserBookReview:
    """Verify that handle_set_user_book converts review_raw to review_slate in the mutation."""

    async def test_review_raw_converted_to_slate_on_insert(self):
        mock_user = {"id": 1}
        mock_existing = {"data": {"user_books": []}}
        mock_mutation = {
            "data": {
                "insert_user_book": {
                    "error": None,
                    "id": 99,
                    "user_book": {"id": 99, "book_id": 42, "status_id": 3, "rating": None},
                }
            }
        }

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(side_effect=[mock_existing, mock_mutation]),
            ) as mock_exec,
        ):
            await handle_set_user_book(
                {"book_id": 42, "status": "Read", "review_raw": "Great book!"}
            )

        # Second call is the insert mutation; check its object arg
        insert_call_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert insert_call_obj["review_slate"] == [
            {"type": "p", "children": [{"text": "Great book!"}]}
        ]
        assert "review_raw" not in insert_call_obj

    async def test_review_raw_converted_to_slate_on_update(self):
        mock_user = {"id": 1}
        mock_existing = {
            "data": {
                "user_books": [
                    {
                        "id": 10,
                        "status_id": 3,
                        "rating": 4.0,
                        "review_slate": None,
                        "review_has_spoilers": None,
                        "reviewed_at": None,
                        "private_notes": None,
                    }
                ]
            }
        }
        mock_mutation = {
            "data": {
                "update_user_book": {
                    "error": None,
                    "id": 10,
                    "user_book": {"id": 10, "book_id": 42, "status_id": 3, "rating": 4.0},
                }
            }
        }

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(side_effect=[mock_existing, mock_mutation]),
            ) as mock_exec,
        ):
            await handle_set_user_book(
                {"book_id": 42, "review_raw": "Two paragraphs\n\nSecond one"}
            )

        update_call_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert update_call_obj["review_slate"] == [
            {"type": "p", "children": [{"text": "Two paragraphs"}]},
            {"type": "p", "children": [{"text": "Second one"}]},
        ]

    async def test_status_only_update_sends_no_review_fields(self):
        # Sending any review field needs the write:reviews scope, so a status/rating change
        # must not echo the existing review back.
        mock_existing = {
            "data": {
                "user_books": [
                    {
                        "id": 10,
                        "status_id": 1,
                        "rating": None,
                        "review_slate": [{"type": "p", "children": [{"text": "Kept"}]}],
                        "review_has_spoilers": False,
                        "reviewed_at": "2025-06-01",
                        "private_notes": "mine",
                    }
                ]
            }
        }
        mock_mutation = {
            "data": {"update_user_book": {"error": None, "id": 10, "user_book": {"id": 10}}}
        }

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(side_effect=[mock_existing, mock_mutation]),
            ) as mock_exec,
        ):
            await handle_set_user_book({"book_id": 42, "status": "Read", "rating": 4.0})

        update_call_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert update_call_obj["status_id"] == 3
        assert update_call_obj["rating"] == 4.0
        assert update_call_obj["private_notes"] == "mine"
        for field in ("review_slate", "review_has_spoilers", "reviewed_at"):
            assert field not in update_call_obj


class TestFormatUserBookDetailReview:
    """Verify that _format_user_book_detail surfaces review fields."""

    def _make_ub(self, **extra: object) -> dict:
        base: dict = {
            "id": 1,
            "book_id": 42,
            "status_id": 3,
            "rating": 4.0,
            "updated_at": "2025-01-01",
            "review_raw": None,
            "review_has_spoilers": False,
            "reviewed_at": None,
            "private_notes": None,
            "user_book_reads": [],
            "book": {"title": "T", "slug": "t", "pages": 300, "contributions": []},
        }
        base.update(extra)
        return base

    def test_includes_review_raw(self):
        ub = self._make_ub(review_raw="A great book.")
        result = _format_user_book_detail(ub)
        assert result["review_raw"] == "A great book."

    def test_includes_review_has_spoilers(self):
        ub = self._make_ub(review_has_spoilers=True)
        result = _format_user_book_detail(ub)
        assert result["review_has_spoilers"] is True

    def test_includes_reviewed_at(self):
        ub = self._make_ub(reviewed_at="2025-06-15")
        result = _format_user_book_detail(ub)
        assert result["reviewed_at"] == "2025-06-15"

    def test_includes_private_notes(self):
        ub = self._make_ub(private_notes="Chapter 12 has the best quote.")
        result = _format_user_book_detail(ub)
        assert result["private_notes"] == "Chapter 12 has the best quote."

    def test_none_fields_present_when_absent(self):
        ub = self._make_ub()
        result = _format_user_book_detail(ub)
        assert "review_raw" in result
        assert result["review_raw"] is None


class TestFormatUserReview:
    def _make_ub(self, **extra: object) -> dict:
        base: dict = {
            "id": 5,
            "book_id": 99,
            "status_id": 3,
            "rating": 4.0,
            "review_raw": "A great read.",
            "review_has_spoilers": False,
            "reviewed_at": "2025-03-10",
            "book": {
                "title": "Test Book",
                "slug": "test-book",
                "contributions": [{"author": {"name": "Author One"}}],
            },
        }
        base.update(extra)
        return base

    def test_output_shape(self):
        result = _format_user_review(self._make_ub())
        assert result["user_book_id"] == 5
        assert result["book_id"] == 99
        assert result["title"] == "Test Book"
        assert result["slug"] == "test-book"
        assert result["authors"] == ["Author One"]
        assert result["rating"] == 4.0
        assert result["review_raw"] == "A great read."
        assert result["review_has_spoilers"] is False
        assert result["reviewed_at"] == "2025-03-10"

    def test_multiple_authors(self):
        ub = self._make_ub(
            book={
                "title": "Co-authored",
                "slug": "co-authored",
                "contributions": [
                    {"author": {"name": "Alice"}},
                    {"author": {"name": "Bob"}},
                ],
            }
        )
        result = _format_user_review(ub)
        assert result["authors"] == ["Alice", "Bob"]

    def test_none_rating(self):
        result = _format_user_review(self._make_ub(rating=None))
        assert result["rating"] is None

    def test_spoiler_flag_true(self):
        result = _format_user_review(self._make_ub(review_has_spoilers=True))
        assert result["review_has_spoilers"] is True


class TestFormatUserBookDetailEdition:
    """Verify that _format_user_book_detail surfaces edition info."""

    def _make_ub(self, **extra: object) -> dict:
        base: dict = {
            "id": 1,
            "book_id": 42,
            "status_id": 3,
            "rating": 4.0,
            "updated_at": "2025-01-01",
            "review_raw": None,
            "review_has_spoilers": False,
            "reviewed_at": None,
            "private_notes": None,
            "user_book_reads": [],
            "book": {"title": "T", "slug": "t", "pages": 300, "contributions": []},
        }
        base.update(extra)
        return base

    def test_includes_edition_when_present(self):
        edition = {
            "id": 100,
            "title": "Kindle Edition",
            "isbn_13": None,
            "asin": "B001234567",
            "pages": 412,
            "audio_seconds": None,
            "edition_format": "Digital",
            "release_date": "2010-01-01",
            "language": {"language": "English"},
        }
        ub = self._make_ub(edition=edition)
        result = _format_user_book_detail(ub)
        assert result["edition"]["id"] == 100
        assert result["edition"]["asin"] == "B001234567"
        assert result["edition"]["language"] == "English"  # flattened, not nested

    def test_edition_none_when_absent(self):
        ub = self._make_ub()
        result = _format_user_book_detail(ub)
        assert result["edition"] is None


class TestHandleSetUserBookEdition:
    """Verify that handle_set_user_book handles edition_id correctly."""

    async def test_edition_id_passed_on_insert(self):
        mock_user = {"id": 1}
        mock_existing = {"data": {"user_books": []}}
        mock_mutation = {
            "data": {
                "insert_user_book": {
                    "error": None,
                    "id": 99,
                    "user_book": {
                        "id": 99,
                        "book_id": 42,
                        "status_id": 3,
                        "rating": None,
                        "edition_id": 777,
                    },
                }
            }
        }

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(side_effect=[mock_existing, mock_mutation]),
            ) as mock_exec,
        ):
            result = await handle_set_user_book(
                {"book_id": 42, "status": "Read", "edition_id": 777}
            )

        insert_call_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert insert_call_obj["edition_id"] == 777
        output = json.loads(result[0].text)
        assert output["edition_id"] == 777

    async def test_edition_id_preserved_on_update(self):
        mock_user = {"id": 1}
        mock_existing = {
            "data": {
                "user_books": [
                    {
                        "id": 10,
                        "status_id": 3,
                        "rating": 4.0,
                        "review_slate": None,
                        "review_has_spoilers": None,
                        "reviewed_at": None,
                        "private_notes": None,
                        "edition_id": 555,
                    }
                ]
            }
        }
        mock_mutation = {
            "data": {
                "update_user_book": {
                    "error": None,
                    "id": 10,
                    "user_book": {
                        "id": 10,
                        "book_id": 42,
                        "status_id": 3,
                        "rating": 5.0,
                        "edition_id": 555,
                    },
                }
            }
        }

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(side_effect=[mock_existing, mock_mutation]),
            ) as mock_exec,
        ):
            await handle_set_user_book({"book_id": 42, "rating": 5.0})

        update_call_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert update_call_obj["edition_id"] == 555

    async def test_edition_id_updated(self):
        mock_user = {"id": 1}
        mock_existing = {
            "data": {
                "user_books": [
                    {
                        "id": 10,
                        "status_id": 3,
                        "rating": 4.0,
                        "review_slate": None,
                        "review_has_spoilers": None,
                        "reviewed_at": None,
                        "private_notes": None,
                        "edition_id": 555,
                    }
                ]
            }
        }
        mock_mutation = {
            "data": {
                "update_user_book": {
                    "error": None,
                    "id": 10,
                    "user_book": {
                        "id": 10,
                        "book_id": 42,
                        "status_id": 3,
                        "rating": 4.0,
                        "edition_id": 888,
                    },
                }
            }
        }

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(side_effect=[mock_existing, mock_mutation]),
            ) as mock_exec,
        ):
            await handle_set_user_book({"book_id": 42, "edition_id": 888})

        update_call_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert update_call_obj["edition_id"] == 888


class TestHandleGetUserLibraryHasReview:
    def _mock_api_response(self, reviews: list[dict], total: int = 1) -> dict:
        return {
            "data": {
                "user_books": reviews,
                "user_books_aggregate": {"aggregate": {"count": total}},
            }
        }

    def _make_review_record(self, book_id: int = 42) -> dict:
        return {
            "id": 10,
            "book_id": book_id,
            "status_id": 3,
            "rating": 5.0,
            "review_raw": "Fantastic.",
            "review_has_spoilers": False,
            "reviewed_at": "2025-06-01",
            "book": {
                "title": "Some Book",
                "slug": "some-book",
                "contributions": [{"author": {"name": "Some Author"}}],
            },
        }

    async def test_returns_expected_output_structure(self):
        mock_user = {"id": 1}
        mock_result = self._mock_api_response([self._make_review_record()], total=1)

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=mock_result),
            ),
        ):
            result = await handle_get_user_library({"has_review": True})

        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["returned"] == 1
        assert data["offset"] == 0
        assert len(data["books"]) == 1
        review = data["books"][0]
        assert review["user_book_id"] == 10
        assert review["review_raw"] == "Fantastic."
        assert review["review_has_spoilers"] is False
        assert review["reviewed_at"] == "2025-06-01"
        assert review["title"] == "Some Book"
        assert review["authors"] == ["Some Author"]

    async def test_default_pagination_params(self):
        mock_user = {"id": 1}
        mock_result = self._mock_api_response([])

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=mock_result),
            ) as mock_exec,
        ):
            await handle_get_user_library({"has_review": True})

        call_vars = mock_exec.call_args[0][1]
        assert call_vars["limit"] == 25
        assert call_vars["offset"] == 0

    async def test_custom_pagination_params(self):
        mock_user = {"id": 1}
        mock_result = self._mock_api_response([])

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=mock_result),
            ) as mock_exec,
        ):
            await handle_get_user_library({"has_review": True, "limit": 10, "offset": 20})

        call_vars = mock_exec.call_args[0][1]
        assert call_vars["limit"] == 10
        assert call_vars["offset"] == 20

    async def test_limit_capped_at_100(self):
        mock_user = {"id": 1}
        mock_result = self._mock_api_response([])

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=mock_result),
            ) as mock_exec,
        ):
            await handle_get_user_library({"has_review": True, "limit": 500})

        call_vars = mock_exec.call_args[0][1]
        assert call_vars["limit"] == 100

    async def test_empty_reviews_list(self):
        mock_user = {"id": 1}
        mock_result = self._mock_api_response([], total=0)

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=mock_result),
            ),
        ):
            result = await handle_get_user_library({"has_review": True})

        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["returned"] == 0
        assert data["books"] == []


_LIBRARY_ENTRY = {"id": 1, "book_id": 42, "status_id": 3, "book": {"title": "T"}}


class TestHandleGetUserBookLists:
    async def _run(self, list_books: list[dict]) -> tuple[dict, AsyncMock]:
        mock_exec = AsyncMock(
            return_value={"data": {"user_books": [_LIBRARY_ENTRY], "list_books": list_books}}
        )
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value={"id": 7}),
            ),
            patch("hardcover_mcp.tools.library.execute", new=mock_exec),
        ):
            result = await handle_get_user_book({"book_id": 42})
        return json.loads(result[0].text), mock_exec

    async def test_lists_the_book_is_on(self):
        data, _ = await self._run(
            [
                {"position": 4, "list": {"id": 123, "name": "Biography and Business"}},
                {"position": None, "list": {"id": 9, "name": "Favourites"}},
            ]
        )

        assert data["lists"] == [
            {"id": 123, "name": "Biography and Business", "position": 4},
            {"id": 9, "name": "Favourites", "position": None},
        ]

    async def test_one_entry_per_list_when_several_editions_are_on_it(self):
        data, _ = await self._run(
            [
                {"position": 2, "list": {"id": 5, "name": "Sci-fi"}},
                {"position": 8, "list": {"id": 5, "name": "Sci-fi"}},
            ]
        )

        assert data["lists"] == [{"id": 5, "name": "Sci-fi", "position": 2}]

    async def test_on_no_lists_is_empty(self):
        data, _ = await self._run([])

        assert data["lists"] == []

    async def test_query_is_one_request_scoped_to_your_lists_without_owned(self):
        _, mock_exec = await self._run([])

        mock_exec.assert_awaited_once()
        query, variables = mock_exec.call_args[0]
        assert "list_books(" in query
        assert 'slug: {_neq: "owned"}' in query
        assert variables == {"user_id": 7, "book_id": 42}


class TestFormatUserBookDetailPrivacy:
    """Verify that _format_user_book_detail surfaces the privacy field."""

    def _make_ub(self, **extra: object) -> dict:
        base: dict = {
            "id": 1,
            "book_id": 42,
            "status_id": 3,
            "privacy_setting_id": None,
            "rating": 4.0,
            "updated_at": "2025-01-01",
            "review_raw": None,
            "review_has_spoilers": False,
            "reviewed_at": None,
            "private_notes": None,
            "user_book_reads": [],
            "book": {"title": "T", "slug": "t", "pages": 300, "contributions": []},
        }
        base.update(extra)
        return base

    def test_privacy_none_when_absent(self):
        ub = self._make_ub()
        result = _format_user_book_detail(ub)
        assert "privacy" in result
        assert result["privacy"] is None

    def test_privacy_public(self):
        ub = self._make_ub(privacy_setting_id=1)
        result = _format_user_book_detail(ub)
        assert result["privacy"] == "public"

    def test_privacy_followers(self):
        ub = self._make_ub(privacy_setting_id=2)
        result = _format_user_book_detail(ub)
        assert result["privacy"] == "followers"

    def test_privacy_private(self):
        ub = self._make_ub(privacy_setting_id=3)
        result = _format_user_book_detail(ub)
        assert result["privacy"] == "private"

    def test_privacy_unknown_id(self):
        ub = self._make_ub(privacy_setting_id=99)
        result = _format_user_book_detail(ub)
        assert result["privacy"] == "unknown (99)"


class TestHandleSetUserBookPrivacy:
    """Verify that handle_set_user_book handles privacy correctly."""

    def _make_existing(self, privacy_setting_id: int | None = None) -> dict:
        return {
            "data": {
                "user_books": [
                    {
                        "id": 10,
                        "status_id": 3,
                        "privacy_setting_id": privacy_setting_id,
                        "rating": 4.0,
                        "review_slate": None,
                        "review_has_spoilers": None,
                        "reviewed_at": None,
                        "private_notes": None,
                        "edition_id": None,
                    }
                ]
            }
        }

    def _make_mutation_result(self, privacy_setting_id: int | None = None) -> dict:
        return {
            "data": {
                "update_user_book": {
                    "error": None,
                    "id": 10,
                    "user_book": {
                        "id": 10,
                        "book_id": 42,
                        "status_id": 3,
                        "privacy_setting_id": privacy_setting_id,
                        "rating": 4.0,
                        "edition_id": None,
                    },
                }
            }
        }

    async def test_privacy_passed_on_insert(self):
        mock_user = {"id": 1}
        mock_existing = {"data": {"user_books": []}}
        mock_mutation = {
            "data": {
                "insert_user_book": {
                    "error": None,
                    "id": 99,
                    "user_book": {
                        "id": 99,
                        "book_id": 42,
                        "status_id": 3,
                        "privacy_setting_id": 3,
                        "rating": None,
                        "edition_id": None,
                    },
                }
            }
        }

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(side_effect=[mock_existing, mock_mutation]),
            ) as mock_exec,
        ):
            result = await handle_set_user_book({"book_id": 42, "privacy": "Private"})

        insert_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert insert_obj["privacy_setting_id"] == 3
        output = json.loads(result[0].text)
        assert output["privacy"] == "private"

    async def test_privacy_passed_on_update(self):
        mock_user = {"id": 1}

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(side_effect=[self._make_existing(), self._make_mutation_result(2)]),
            ) as mock_exec,
        ):
            result = await handle_set_user_book({"book_id": 42, "privacy": "Followers"})

        update_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert update_obj["privacy_setting_id"] == 2
        output = json.loads(result[0].text)
        assert output["privacy"] == "followers"

    async def test_privacy_preserved_on_update_when_not_specified(self):
        mock_user = {"id": 1}

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(
                    side_effect=[
                        self._make_existing(privacy_setting_id=1),
                        self._make_mutation_result(1),
                    ]
                ),
            ) as mock_exec,
        ):
            await handle_set_user_book({"book_id": 42, "rating": 5.0})

        update_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert update_obj["privacy_setting_id"] == 1

    async def test_privacy_numeric_string_accepted(self):
        mock_user = {"id": 1}
        mock_existing = {"data": {"user_books": []}}
        mock_mutation = {
            "data": {
                "insert_user_book": {
                    "error": None,
                    "id": 5,
                    "user_book": {
                        "id": 5,
                        "book_id": 42,
                        "status_id": 3,
                        "privacy_setting_id": 1,
                        "rating": None,
                        "edition_id": None,
                    },
                }
            }
        }

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(side_effect=[mock_existing, mock_mutation]),
            ) as mock_exec,
        ):
            await handle_set_user_book({"book_id": 42, "privacy": "1"})

        insert_obj = mock_exec.call_args_list[1][0][1]["object"]
        assert insert_obj["privacy_setting_id"] == 1

    async def test_invalid_privacy_returns_error(self):
        mock_user = {"id": 1}

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            pytest.raises(ToolError) as exc,
        ):
            await handle_set_user_book({"book_id": 42, "privacy": "secret"})

        assert "secret" in str(exc.value)


class TestSetEditionOwnedHelper:
    """_set_edition_owned checks the Owned list before toggling, so it's idempotent."""

    @staticmethod
    def _check(owned: bool) -> dict:
        return {"data": {"lists": [{"list_books": [{"id": 10}] if owned else []}]}}

    @staticmethod
    def _toggle() -> dict:
        return {"data": {"edition_owned": {"id": 1, "list_book": {"id": 99}}}}

    async def _run(self, owned: bool, *responses: dict) -> tuple[bool, AsyncMock]:
        mock_exec = AsyncMock(side_effect=list(responses))
        self.mock_exec = mock_exec
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch("hardcover_mcp.tools.library.execute", new=mock_exec),
        ):
            changed = await _set_edition_owned(500, owned)
        return changed, mock_exec

    async def test_marks_owned_when_not_owned(self):
        changed, mock_exec = await self._run(True, self._check(False), self._toggle())
        assert changed is True
        assert mock_exec.call_args_list[1][0][1] == {"id": 500}

    async def test_no_toggle_when_already_owned(self):
        changed, mock_exec = await self._run(True, self._check(True))
        assert changed is False
        assert mock_exec.call_count == 1

    async def test_un_owns_when_owned(self):
        changed, _ = await self._run(False, self._check(True), self._toggle())
        assert changed is True

    async def test_no_toggle_when_already_not_owned(self):
        changed, mock_exec = await self._run(False, self._check(False))
        assert changed is False
        assert mock_exec.call_count == 1


def _existing_entry(edition_id: int | None) -> dict:
    return {
        "data": {
            "user_books": [{"id": 10, "status_id": 3, "rating": None, "edition_id": edition_id}]
        }
    }


_UPDATED = {
    "data": {
        "update_user_book": {
            "error": None,
            "user_book": {"id": 10, "book_id": 42, "status_id": 3, "edition_id": 500},
        }
    }
}


class TestHandleSetUserBookOwned:
    async def _run(self, arguments: dict, *responses: dict) -> tuple[str, AsyncMock]:
        mock_exec = AsyncMock(side_effect=list(responses))
        self.mock_exec = mock_exec
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch("hardcover_mcp.tools.library.execute", new=mock_exec),
        ):
            result = await handle_set_user_book(arguments)
        return result[0].text, mock_exec

    async def test_owned_with_edition_id_sets_ownership_after_upsert(self):
        text, mock_exec = await self._run(
            {"book_id": 42, "edition_id": 500, "owned": True},
            _existing_entry(None),
            _UPDATED,
            TestSetEditionOwnedHelper._check(False),
            TestSetEditionOwnedHelper._toggle(),
        )
        data = json.loads(text)
        assert data["owned"] is True
        assert data["owned_changed"] is True
        assert mock_exec.call_args_list[1][0][1]["object"]["edition_id"] == 500
        assert mock_exec.call_args_list[3][0][1] == {"id": 500}

    async def test_owned_without_edition_id_uses_current_edition(self):
        text, mock_exec = await self._run(
            {"book_id": 42, "owned": False},
            _existing_entry(777),
            _UPDATED,
            TestSetEditionOwnedHelper._check(False),
        )
        data = json.loads(text)
        assert data["owned"] is False
        assert data["owned_changed"] is False
        assert mock_exec.call_args_list[2][0][1]["edition_id"] == 777

    async def test_owned_without_any_edition_errors_before_writing(self):
        with pytest.raises(ToolError) as exc:
            await self._run({"book_id": 42, "owned": True}, _existing_entry(None))
        assert "'owned' needs an edition" in str(exc.value)
        assert self.mock_exec.call_count == 1  # only the lookup; nothing written

    async def test_owned_on_new_book_without_edition_errors(self):
        with pytest.raises(ToolError) as exc:
            await self._run({"book_id": 42, "owned": True}, {"data": {"user_books": []}})
        assert "'owned' needs an edition" in str(exc.value)
        assert self.mock_exec.call_count == 1

    async def test_non_bool_owned_is_rejected(self):
        with pytest.raises(ToolError) as exc:
            await self._run({"book_id": 42, "owned": "yes"})
        assert "'owned' must be true or false" in str(exc.value)
        self.mock_exec.assert_not_awaited()

    async def test_without_owned_no_ownership_fields(self):
        text, mock_exec = await self._run(
            {"book_id": 42, "status": "Read"}, _existing_entry(5), _UPDATED
        )
        data = json.loads(text)
        assert "owned" not in data
        assert mock_exec.call_count == 2


class TestGetUserLibrarySort:
    """Tests for sort/order parameters in handle_get_user_library."""

    def _mock_result(self, books=None):
        return {
            "data": {
                "user_books": books or [],
                "user_books_aggregate": {"aggregate": {"count": 0}},
            }
        }

    async def test_default_sort_calls_execute(self):
        mock_user = {"id": 1}
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=self._mock_result()),
            ) as mock_exec,
        ):
            result = await handle_get_user_library({})

        assert len(result) == 1
        query = mock_exec.call_args[0][0]
        assert "updated_at" in query
        assert "desc" in query

    async def test_sort_by_rating_desc(self):
        mock_user = {"id": 1}
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=self._mock_result()),
            ) as mock_exec,
        ):
            result = await handle_get_user_library({"sort": "rating", "order": "desc"})

        assert len(result) == 1
        query = mock_exec.call_args[0][0]
        assert "rating" in query
        assert "desc" in query

    async def test_sort_by_date_added_asc(self):
        mock_user = {"id": 1}
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=self._mock_result()),
            ) as mock_exec,
        ):
            result = await handle_get_user_library({"sort": "date_added", "order": "asc"})

        assert len(result) == 1
        query = mock_exec.call_args[0][0]
        assert "date_added" in query
        assert "asc" in query

    @pytest.mark.parametrize("sort", sorted(LIBRARY_SORT_FIELDS))
    @pytest.mark.parametrize("order", ["asc", "desc"])
    async def test_sort_puts_nulls_last_with_id_tiebreaker(self, sort, order):
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=self._mock_result()),
            ) as mock_exec,
        ):
            await handle_get_user_library({"sort": sort, "order": order})

        field = LIBRARY_SORT_FIELDS[sort]
        expected = f"order_by: [{{{field}: {order}_nulls_last}}, {{id: desc}}]"
        assert expected in mock_exec.call_args[0][0]

    async def test_invalid_sort_returns_error(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_user_library({"sort": "banana"})
        assert "sort" in str(exc.value)

    async def test_invalid_order_returns_error(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_user_library({"order": "sideways"})
        assert "order" in str(exc.value)


class TestGetUserLibraryDateRange:
    """Tests for start_date/end_date filtering in handle_get_user_library."""

    def _mock_result(self, books=None):
        return {
            "data": {
                "user_books": books or [],
                "user_books_aggregate": {"aggregate": {"count": 0}},
            }
        }

    async def test_date_range_uses_date_range_query(self):
        mock_user = {"id": 1}
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=self._mock_result()),
            ) as mock_exec,
        ):
            result = await handle_get_user_library(
                {"start_date": "2025-05-01", "end_date": "2025-05-31"}
            )

        assert len(result) == 1
        assert (
            "order_by: [{last_read_date: desc_nulls_last}, {id: desc}]"
            in mock_exec.call_args[0][0]
        )
        call_vars = mock_exec.call_args[0][1]
        assert call_vars["start_date"] == "2025-05-01"
        assert call_vars["end_date"] == "2025-05-31"

    async def test_start_date_without_end_date_returns_error(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_user_library({"start_date": "2025-01-01"})
        assert "end_date" in str(exc.value)

    async def test_end_date_without_start_date_returns_error(self):
        with pytest.raises(ToolError) as exc:
            await handle_get_user_library({"end_date": "2025-12-31"})
        assert "start_date" in str(exc.value)

    async def test_date_range_result_includes_finished_at(self):
        mock_user = {"id": 1}
        book = {
            "id": 10,
            "book_id": 99,
            "status_id": 3,
            "rating": 4.5,
            "updated_at": "2025-05-15",
            "book": {
                "title": "Test Book",
                "slug": "test-book",
                "contributions": [{"author": {"name": "Author A"}}],
            },
            "user_book_reads": [{"finished_at": "2025-05-15", "started_at": "2025-05-01"}],
        }
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(
                    return_value={
                        "data": {
                            "user_books": [book],
                            "user_books_aggregate": {"aggregate": {"count": 1}},
                        }
                    }
                ),
            ),
        ):
            result = await handle_get_user_library(
                {"start_date": "2025-05-01", "end_date": "2025-05-31"}
            )

        output = json.loads(result[0].text)
        assert output["total"] == 1
        assert output["books"][0]["finished_at"] == "2025-05-15"
        assert output["books"][0]["started_at"] == "2025-05-01"


class TestHandleGetUserLibraryHasReviewQuery:
    async def _run(self, arguments: dict) -> tuple[list, AsyncMock]:
        empty = {"data": {"user_books": [], "user_books_aggregate": {"aggregate": {"count": 0}}}}
        mock_exec = AsyncMock(return_value=empty)
        self.mock_exec = mock_exec
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch("hardcover_mcp.tools.library.execute", new=mock_exec),
        ):
            result = await handle_get_user_library(arguments)
        return result, mock_exec

    async def test_filters_and_sorts_by_review_date(self):
        _, mock_exec = await self._run({"has_review": True})
        query = mock_exec.call_args[0][0]
        assert "has_review: {_eq: true}" in query
        assert "order_by: [{reviewed_at: desc_nulls_last}, {id: desc}]" in query
        assert "review_raw" in query

    async def test_explicit_sort_overrides_review_default(self):
        _, mock_exec = await self._run({"has_review": True, "sort": "rating"})
        assert "order_by: [{rating: desc_nulls_last}, {id: desc}]" in mock_exec.call_args[0][0]

    async def test_without_has_review_no_review_filter(self):
        _, mock_exec = await self._run({})
        query = mock_exec.call_args[0][0]
        assert "has_review" not in query
        assert "review_raw" not in query

    async def test_rejects_date_range(self):
        with pytest.raises(ToolError) as exc:
            await self._run(
                {"has_review": True, "start_date": "2025-01-01", "end_date": "2025-12-31"}
            )
        assert "can't be combined" in str(exc.value)
        self.mock_exec.assert_not_called()


class TestHandleSetUserBookRead:
    async def test_with_id_edits_that_read(self):
        current = {"data": {"user_book_reads": [{"id": 3, "started_at": "2025-01-01"}]}}
        updated = {"data": {"update_user_book_read": {"user_book_read": {"id": 3}}}}
        mock_exec = AsyncMock(side_effect=[current, updated])
        with patch("hardcover_mcp.tools.library.execute", new=mock_exec):
            result = await handle_set_user_book_read({"id": 3, "finished_at": "2025-02-01"})

        assert json.loads(result[0].text) == {"id": 3}
        assert mock_exec.call_args_list[1][0][1]["id"] == 3
        merged = mock_exec.call_args_list[1][0][1]["object"]
        assert merged["started_at"] == "2025-01-01"
        assert merged["finished_at"] == "2025-02-01"

    async def test_without_id_needs_a_book(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_user_book_read({"finished_at": "2025-02-01"})
        assert "provide 'book_id' or 'user_book_id'" in str(exc.value)

    async def test_without_id_inserts_when_no_active_read(self):
        no_active = {"data": {"user_book_reads": []}}
        inserted = {"data": {"insert_user_book_read": {"user_book_read": {"id": 8}}}}
        mock_exec = AsyncMock(side_effect=[no_active, inserted])
        with patch("hardcover_mcp.tools.library.execute", new=mock_exec):
            result = await handle_set_user_book_read(
                {"user_book_id": 5, "started_at": "2025-03-01"}
            )

        assert json.loads(result[0].text) == {"id": 8}
        assert mock_exec.call_args_list[1][0][1]["userBookId"] == 5


_READ_UPDATED = {"data": {"update_user_book_read": {"user_book_read": {"id": 3}}}}
_READ_INSERTED = {"data": {"insert_user_book_read": {"user_book_read": {"id": 8}}}}


class TestSetUserBookReadContinuesOrInserts:
    """Without an id: update the unfinished read only when the call continues it."""

    async def _run(self, active: dict, arguments: dict) -> AsyncMock:
        found = {"data": {"user_book_reads": [active]}}
        mock_exec = AsyncMock(side_effect=[found, _READ_UPDATED, _READ_INSERTED])
        with patch("hardcover_mcp.tools.library.execute", new=mock_exec):
            await handle_set_user_book_read({"user_book_id": 5, **arguments})
        return mock_exec

    @pytest.mark.parametrize(
        "arguments",
        [
            {"progress_pages": 120},
            {"finished_at": "2026-10-20"},
            {"started_at": "2026-10-01", "finished_at": "2026-10-20"},
        ],
        ids=["progress", "finish-only", "same-start"],
    )
    async def test_continuing_calls_update_the_unfinished_read(self, arguments):
        mock_exec = await self._run({"id": 3, "started_at": "2026-10-01"}, arguments)

        assert mock_exec.call_count == 2
        assert mock_exec.call_args_list[1][0][1]["id"] == 3

    async def test_a_start_date_fills_an_unfinished_read_without_one(self):
        mock_exec = await self._run({"id": 3, "started_at": None}, {"started_at": "2026-10-01"})

        assert mock_exec.call_args_list[1][0][1]["object"]["started_at"] == "2026-10-01"

    async def test_a_different_start_date_logs_another_read(self):
        # Reading it again since 2026-10-01; logging the 2019 read must not rewrite that.
        found = {"data": {"user_book_reads": [{"id": 3, "started_at": "2026-10-01"}]}}
        mock_exec = AsyncMock(side_effect=[found, _READ_INSERTED])
        with patch("hardcover_mcp.tools.library.execute", new=mock_exec):
            result = await handle_set_user_book_read(
                {"user_book_id": 5, "started_at": "2019-01-01", "finished_at": "2019-02-01"}
            )

        assert json.loads(result[0].text) == {"id": 8}
        assert mock_exec.call_count == 2
        inserted = mock_exec.call_args_list[1][0][1]
        assert inserted["userBookId"] == 5
        assert inserted["userBookRead"] == {
            "started_at": "2019-01-01",
            "finished_at": "2019-02-01",
        }


class TestHandleGetUserLibraryOwned:
    async def _query(self, arguments: dict) -> str:
        empty = {"data": {"user_books": [], "user_books_aggregate": {"aggregate": {"count": 0}}}}
        mock_exec = AsyncMock(return_value=empty)
        self.mock_exec = mock_exec
        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch("hardcover_mcp.tools.library.execute", new=mock_exec),
        ):
            await handle_get_user_library(arguments)
        return mock_exec.call_args[0][0]

    async def test_owned_filters_through_owned_list(self):
        query = await self._query({"owned": True})
        assert 'list: {slug: {_eq: "owned"}, user_id: {_eq: $user_id}}' in query

    async def test_owned_combines_with_status(self):
        query = await self._query({"owned": True, "status": "Want to Read"})
        assert "status_id: {_eq: $status_id}" in query
        assert 'slug: {_eq: "owned"}' in query

    async def test_owned_combines_with_date_range(self):
        query = await self._query(
            {"owned": True, "start_date": "2025-01-01", "end_date": "2025-12-31"}
        )
        assert "finished_at: {_gte: $start_date" in query
        assert 'slug: {_eq: "owned"}' in query

    async def test_without_owned_no_owned_filter(self):
        assert "owned" not in await self._query({})
