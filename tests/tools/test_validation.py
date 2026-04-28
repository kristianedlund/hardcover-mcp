"""Tests for tools/_validation.py — _require_int and _require_float."""

import pytest

from hardcover_mcp.tools._validation import _require_float, _require_int


class TestRequireInt:
    def test_converts_int(self):
        assert _require_int(42, "x") == 42

    def test_converts_numeric_string(self):
        assert _require_int("42", "x") == 42

    def test_raises_on_non_numeric_string(self):
        with pytest.raises(ValueError, match="'book_id' must be an integer"):
            _require_int("abc", "book_id")

    def test_raises_on_none(self):
        with pytest.raises(ValueError, match="must be an integer"):
            _require_int(None, "id")

    def test_raises_on_float_string(self):
        with pytest.raises(ValueError, match="must be an integer"):
            _require_int("3.5", "id")


class TestRequireFloat:
    def test_converts_float(self):
        assert _require_float(4.5, "x") == 4.5

    def test_converts_int_to_float(self):
        assert _require_float(4, "x") == 4.0

    def test_converts_numeric_string(self):
        assert _require_float("3.5", "x") == 3.5

    def test_raises_on_non_numeric_string(self):
        with pytest.raises(ValueError, match="'rating' must be a number"):
            _require_float("abc", "rating")

    def test_raises_on_none(self):
        with pytest.raises(ValueError, match="must be a number"):
            _require_float(None, "rating")
