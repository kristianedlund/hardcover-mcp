"""Tests for tools/library.py — status resolution, formatting, input building."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools.library import (
    _build_read_input,
    _format_owned_book,
    _format_user_book,
    _format_user_book_detail,
    _format_user_review,
    _merge_read_input,
    _resolve_privacy_id,
    _resolve_status_id,
    _text_to_slate,
    handle_get_owned_books,
    handle_get_user_reviews,
    handle_set_edition_owned,
    handle_set_user_book,
    handle_get_user_library,
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
        assert result["edition"] == edition

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


class TestHandleGetUserReviews:
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
            result = await handle_get_user_reviews({})

        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["returned"] == 1
        assert data["offset"] == 0
        assert len(data["reviews"]) == 1
        review = data["reviews"][0]
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
            await handle_get_user_reviews({})

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
            await handle_get_user_reviews({"limit": 10, "offset": 20})

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
            await handle_get_user_reviews({"limit": 500})

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
            result = await handle_get_user_reviews({})

        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["returned"] == 0
        assert data["reviews"] == []


class TestResolvePrivacyId:
    def test_returns_none_for_none(self):
        assert _resolve_privacy_id(None) is None

    def test_resolves_int_directly(self):
        assert _resolve_privacy_id(1) == 1
        assert _resolve_privacy_id(3) == 3

    def test_resolves_numeric_string(self):
        assert _resolve_privacy_id("2") == 2

    def test_resolves_name_case_insensitive(self):
        assert _resolve_privacy_id("public") == 1
        assert _resolve_privacy_id("Public") == 1
        assert _resolve_privacy_id("followers") == 2
        assert _resolve_privacy_id("Followers") == 2
        assert _resolve_privacy_id("private") == 3
        assert _resolve_privacy_id("Private") == 3

    def test_returns_none_for_unknown_name(self):
        assert _resolve_privacy_id("secret") is None


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
        assert result["privacy"] == "Public"

    def test_privacy_followers(self):
        ub = self._make_ub(privacy_setting_id=2)
        result = _format_user_book_detail(ub)
        assert result["privacy"] == "Followers"

    def test_privacy_private(self):
        ub = self._make_ub(privacy_setting_id=3)
        result = _format_user_book_detail(ub)
        assert result["privacy"] == "Private"

    def test_privacy_unknown_id(self):
        ub = self._make_ub(privacy_setting_id=99)
        result = _format_user_book_detail(ub)
        assert "Unknown" in result["privacy"]


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
        assert output["privacy"] == "Private"

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
        assert output["privacy"] == "Followers"

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

        with patch(
            "hardcover_mcp.tools.library.get_current_user",
            new=AsyncMock(return_value=mock_user),
        ):
            result = await handle_set_user_book({"book_id": 42, "privacy": "secret"})

        assert "Error" in result[0].text
        assert "secret" in result[0].text


class TestFormatOwnedBook:
    """Verify that _format_owned_book produces the correct shape."""

    def _make_lb(self, **extra: object) -> dict:
        base: dict = {
            "id": 7,
            "book_id": 55,
            "edition_id": 200,
            "date_added": "2025-03-01T00:00:00+00:00",
            "edition": None,
            "book": {
                "title": "Owned Book",
                "slug": "owned-book",
                "contributions": [{"author": {"name": "Jane Doe"}}],
            },
        }
        base.update(extra)
        return base

    def test_output_shape(self):
        result = _format_owned_book(self._make_lb())
        assert result["book_id"] == 55
        assert result["edition_id"] == 200
        assert result["title"] == "Owned Book"
        assert result["slug"] == "owned-book"
        assert result["authors"] == ["Jane Doe"]
        assert result["edition"] is None
        assert result["date_added"] == "2025-03-01T00:00:00+00:00"

    def test_multiple_authors(self):
        lb = self._make_lb(
            book={
                "title": "Co-written",
                "slug": "co-written",
                "contributions": [
                    {"author": {"name": "Alice"}},
                    {"author": {"name": "Bob"}},
                ],
            }
        )
        result = _format_owned_book(lb)
        assert result["authors"] == ["Alice", "Bob"]

    def test_edition_present(self):
        edition = {
            "id": 200,
            "title": "Paperback",
            "isbn_13": "9781234567890",
            "asin": None,
            "pages": 300,
            "audio_seconds": None,
            "edition_format": "Paperback",
            "release_date": "2020-01-01",
            "language": {"language": "English"},
        }
        lb = self._make_lb(edition=edition)
        result = _format_owned_book(lb)
        assert result["edition"] == edition


class TestHandleGetOwnedBooks:
    """Verify the handle_get_owned_books handler."""

    def _mock_api_response(self, books: list[dict], total: int = 1) -> dict:
        return {
            "data": {
                "lists": [
                    {
                        "id": 100,
                        "list_books": books,
                        "list_books_aggregate": {"aggregate": {"count": total}},
                    }
                ]
            }
        }

    def _mock_empty_response(self) -> dict:
        return {"data": {"lists": []}}

    def _make_owned_record(self) -> dict:
        return {
            "id": 7,
            "book_id": 55,
            "edition_id": 200,
            "date_added": "2025-03-01T00:00:00+00:00",
            "edition": None,
            "book": {
                "title": "Owned Book",
                "slug": "owned-book",
                "contributions": [{"author": {"name": "Jane Doe"}}],
            },
        }

    async def test_returns_expected_output_structure(self):
        mock_user = {"id": 1}
        mock_result = self._mock_api_response([self._make_owned_record()], total=1)

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
            result = await handle_get_owned_books({})

        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["returned"] == 1
        assert data["offset"] == 0
        book = data["books"][0]
        assert book["book_id"] == 55
        assert book["edition_id"] == 200
        assert book["authors"] == ["Jane Doe"]

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
            await handle_get_owned_books({})

        call_vars = mock_exec.call_args[0][1]
        assert call_vars["limit"] == 20
        assert call_vars["offset"] == 0

    async def test_custom_page_and_per_page(self):
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
            await handle_get_owned_books({"page": 3, "per_page": 10})

        call_vars = mock_exec.call_args[0][1]
        assert call_vars["limit"] == 10
        assert call_vars["offset"] == 20  # (3-1) * 10

    async def test_per_page_capped_at_100(self):
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
            await handle_get_owned_books({"per_page": 500})

        call_vars = mock_exec.call_args[0][1]
        assert call_vars["limit"] == 100

    async def test_empty_books_list(self):
        mock_user = {"id": 1}
        mock_result = self._mock_empty_response()

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
            result = await handle_get_owned_books({})

        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["books"] == []


class TestHandleSetEditionOwned:
    """Verify handle_set_edition_owned checks state and toggles correctly."""

    def _mock_check_result(self, owned: bool) -> dict:
        """Mock the CHECK_EDITION_OWNED_QUERY response."""
        if owned:
            return {"data": {"lists": [{"list_books": [{"id": 10}]}]}}
        return {"data": {"lists": [{"list_books": []}]}}

    def _mock_toggle_result(self) -> dict:
        return {"data": {"edition_owned": {"id": 1, "list_book": {"id": 99}}}}

    async def test_marks_owned_when_not_currently_owned(self):
        mock_user = {"id": 1}

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(
                    side_effect=[self._mock_check_result(False), self._mock_toggle_result()]
                ),
            ) as mock_exec,
        ):
            result = await handle_set_edition_owned({"edition_id": 500, "owned": True})

        output = json.loads(result[0].text)
        assert output["edition_id"] == 500
        assert output["owned"] is True
        assert output["toggled"] is True
        # Should have called execute twice: check + toggle
        assert mock_exec.call_count == 2

    async def test_no_toggle_when_already_owned(self):
        mock_user = {"id": 1}

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=self._mock_check_result(True)),
            ) as mock_exec,
        ):
            result = await handle_set_edition_owned({"edition_id": 500, "owned": True})

        output = json.loads(result[0].text)
        assert output["owned"] is True
        assert output["toggled"] is False
        # Should have called execute only once (check), no toggle
        assert mock_exec.call_count == 1

    async def test_un_owns_when_currently_owned(self):
        mock_user = {"id": 1}

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(
                    side_effect=[self._mock_check_result(True), self._mock_toggle_result()]
                ),
            ) as mock_exec,
        ):
            result = await handle_set_edition_owned({"edition_id": 500, "owned": False})

        output = json.loads(result[0].text)
        assert output["owned"] is False
        assert output["toggled"] is True
        assert mock_exec.call_count == 2

    async def test_no_toggle_when_already_not_owned(self):
        mock_user = {"id": 1}

        with (
            patch(
                "hardcover_mcp.tools.library.get_current_user",
                new=AsyncMock(return_value=mock_user),
            ),
            patch(
                "hardcover_mcp.tools.library.execute",
                new=AsyncMock(return_value=self._mock_check_result(False)),
            ) as mock_exec,
        ):
            result = await handle_set_edition_owned({"edition_id": 500, "owned": False})

        output = json.loads(result[0].text)
        assert output["owned"] is False
        assert output["toggled"] is False
        assert mock_exec.call_count == 1

    async def test_missing_edition_id_returns_error(self):
        result = await handle_set_edition_owned({"owned": True})
        assert "Error" in result[0].text
        assert "edition_id" in result[0].text

    async def test_missing_owned_returns_error(self):
        result = await handle_set_edition_owned({"edition_id": 500})
        assert "Error" in result[0].text
        assert "owned" in result[0].text

    async def test_invalid_edition_id_returns_error(self):
        result = await handle_set_edition_owned({"edition_id": "abc", "owned": True})
        assert "Error" in result[0].text
        assert "edition_id" in result[0].text


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

    async def test_invalid_sort_returns_error(self):
        result = await handle_get_user_library({"sort": "banana"})
        assert "Error" in result[0].text
        assert "sort" in result[0].text

    async def test_invalid_order_returns_error(self):
        result = await handle_get_user_library({"order": "sideways"})
        assert "Error" in result[0].text
        assert "order" in result[0].text


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
        call_vars = mock_exec.call_args[0][1]
        assert call_vars["start_date"] == "2025-05-01"
        assert call_vars["end_date"] == "2025-05-31"

    async def test_start_date_without_end_date_returns_error(self):
        result = await handle_get_user_library({"start_date": "2025-01-01"})
        assert "Error" in result[0].text
        assert "end_date" in result[0].text

    async def test_end_date_without_start_date_returns_error(self):
        result = await handle_get_user_library({"end_date": "2025-12-31"})
        assert "Error" in result[0].text
        assert "start_date" in result[0].text

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
