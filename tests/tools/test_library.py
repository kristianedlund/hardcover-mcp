"""Tests for tools/library.py — status resolution, formatting, input building."""

from hardcover_mcp.tools.library import (
    STATUS_MAP,
    _build_read_input,
    _format_user_book,
    _merge_read_input,
    _resolve_status_id,
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
        existing = {"started_at": "2025-01-01", "finished_at": None, "progress_pages": 50}
        updates = {"finished_at": "2025-02-01"}

        merged = _merge_read_input(existing, updates)

        assert merged["started_at"] == "2025-01-01"
        assert merged["finished_at"] == "2025-02-01"
        assert merged["progress_pages"] == 50

    def test_skips_none_existing_fields(self):
        existing = {"started_at": None, "finished_at": None, "progress_pages": None}
        updates = {"started_at": "2025-03-01"}

        merged = _merge_read_input(existing, updates)

        assert merged == {"started_at": "2025-03-01"}


class TestBuildReadInput:
    def test_extracts_read_fields(self):
        args = {"started_at": "2025-01-01", "book_id": 42, "extra": "ignored"}
        result = _build_read_input(args)

        assert result == {"started_at": "2025-01-01"}
        assert "book_id" not in result

    def test_returns_empty_when_no_read_fields(self):
        assert _build_read_input({"book_id": 42}) == {}
