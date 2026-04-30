"""Tests for tools/library.py — status resolution, formatting, input building."""

from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools.library import (
    _build_read_input,
    _format_user_book,
    _format_user_book_detail,
    _merge_read_input,
    _resolve_status_id,
    _text_to_slate,
    handle_set_user_book,
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

    def test_returns_none_for_unknown_name(self):
        assert _resolve_status_id("nonexistent") is None


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

        assert "Unknown" in result["status"]


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
        with pytest.raises(ValueError, match="'progress_pages' must be an integer"):
            _build_read_input({"progress_pages": "abc"})

    def test_extracts_progress_seconds(self):
        args = {"progress_seconds": 3600, "book_id": 42}
        result = _build_read_input(args)

        assert result == {"progress_seconds": 3600}

    def test_raises_on_non_numeric_progress_seconds(self):
        with pytest.raises(ValueError, match="'progress_seconds' must be an integer"):
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


class TestFormatUserBookDetailReview:
    """Verify that _format_user_book_detail surfaces review fields."""

    def _make_ub(self, **extra: object) -> dict:
        base: dict = {
            "id": 1,
            "book_id": 42,
            "status_id": 3,
            "rating": 4.0,
            "updated_at": "2025-01-01",
            "review_html": None,
            "review_has_spoilers": False,
            "reviewed_at": None,
            "private_notes": None,
            "user_book_reads": [],
            "book": {"title": "T", "slug": "t", "pages": 300, "contributions": []},
        }
        base.update(extra)
        return base

    def test_includes_review_html(self):
        ub = self._make_ub(review_html="<p>Great</p>")
        result = _format_user_book_detail(ub)
        assert result["review_html"] == "<p>Great</p>"

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
        assert "review_html" in result
        assert result["review_html"] is None
