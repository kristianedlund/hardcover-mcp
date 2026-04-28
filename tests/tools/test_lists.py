"""Tests for tools/lists.py — formatting helpers and input building."""

import pytest

from hardcover_mcp.tools.lists import (
    _build_list_input,
    _format_list_book,
    _format_list_summary,
)


class TestFormatListSummary:
    def test_maps_privacy_setting_id(self):
        lst = {
            "id": 1,
            "name": "My List",
            "slug": "my-list",
            "description": None,
            "books_count": 5,
            "privacy_setting_id": 1,
            "updated_at": "2025-01-01",
        }
        result = _format_list_summary(lst)

        assert result["privacy"] == "public"
        assert result["books_count"] == 5

    def test_unknown_privacy_id(self):
        lst = {
            "id": 1,
            "name": "X",
            "slug": "x",
            "books_count": 0,
            "privacy_setting_id": 99,
        }
        result = _format_list_summary(lst)

        assert result["privacy"] == "unknown"


class TestFormatListBook:
    def test_flattens_book_and_authors(self):
        lb = {
            "position": 1,
            "book": {
                "id": 42,
                "title": "Test",
                "slug": "test",
                "contributions": [{"author": {"name": "A"}}],
            },
        }
        result = _format_list_book(lb)

        assert result["position"] == 1
        assert result["book_id"] == 42
        assert result["authors"] == ["A"]


class TestBuildListInput:
    def test_builds_from_name_and_privacy(self):
        result = _build_list_input({"name": "New", "privacy": "private"})

        assert result["name"] == "New"
        assert result["privacy_setting_id"] == 3

    def test_accepts_numeric_privacy(self):
        result = _build_list_input({"name": "X", "privacy": "2"})

        assert result["privacy_setting_id"] == 2

    def test_raises_on_invalid_privacy(self):
        with pytest.raises(ValueError, match="Unknown privacy"):
            _build_list_input({"privacy": "secret"})

    def test_returns_empty_when_no_fields(self):
        assert _build_list_input({}) == {}
