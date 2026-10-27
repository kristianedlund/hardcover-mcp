"""Tests for tools/_validation.py — numeric and privacy validators."""

import pytest

from hardcover_mcp.tools._validation import (
    ToolError,
    _privacy_argument,
    _require_bool,
    _require_count,
    _require_float,
    _require_int,
    _require_privacy,
    _require_str,
    privacy_label,
)


class TestRequireInt:
    def test_converts_int(self):
        assert _require_int(42, "x") == 42

    def test_converts_numeric_string(self):
        assert _require_int("42", "x") == 42

    def test_raises_on_non_numeric_string(self):
        with pytest.raises(ToolError, match="'book_id' must be an integer"):
            _require_int("abc", "book_id")

    def test_raises_on_none(self):
        with pytest.raises(ToolError, match="must be an integer"):
            _require_int(None, "id")

    def test_raises_on_float_string(self):
        with pytest.raises(ToolError, match="must be an integer"):
            _require_int("3.5", "id")


class TestRequireFloat:
    def test_converts_float(self):
        assert _require_float(4.5, "x") == 4.5

    def test_converts_int_to_float(self):
        assert _require_float(4, "x") == 4.0

    def test_converts_numeric_string(self):
        assert _require_float("3.5", "x") == 3.5

    def test_raises_on_non_numeric_string(self):
        with pytest.raises(ToolError, match="'rating' must be a number"):
            _require_float("abc", "rating")

    def test_raises_on_none(self):
        with pytest.raises(ToolError, match="must be a number"):
            _require_float(None, "rating")


class TestRequirePrivacy:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("public", 1),
            ("Public", 1),
            ("followers", 2),
            ("FOLLOWERS", 2),
            ("followers_only", 2),
            ("Followers_Only", 2),
            ("private", 3),
            (" Private ", 3),
            (1, 1),
            (2, 2),
            (3, 3),
            ("3", 3),
        ],
    )
    def test_accepts_labels_aliases_and_ids(self, value, expected):
        assert _require_privacy(value) == expected

    @pytest.mark.parametrize("value", ["secret", "", 0, 4, "4", True, None, 1.0])
    def test_rejects_everything_else(self, value):
        with pytest.raises(
            ToolError, match="'privacy' must be 'public', 'followers', or 'private'"
        ):
            _require_privacy(value)

    def test_error_names_the_argument(self):
        with pytest.raises(ToolError, match="'privacy_setting_id' must be"):
            _require_privacy("nope", "privacy_setting_id")


class TestPrivacyArgument:
    def test_neither_is_none(self):
        assert _privacy_argument({}) is None

    def test_privacy(self):
        assert _privacy_argument({"privacy": "followers"}) == 2

    @pytest.mark.parametrize(
        "arguments", [{"privacy_setting_id": 3}, {"privacy": "private", "privacy_setting_id": 3}]
    )
    def test_removed_privacy_setting_id_is_rejected(self, arguments):
        with pytest.raises(ToolError, match="'privacy_setting_id' was removed; use 'privacy'"):
            _privacy_argument(arguments)


class TestPrivacyLabel:
    def test_labels(self):
        assert [privacy_label(i) for i in (1, 2, 3)] == ["public", "followers", "private"]

    def test_none(self):
        assert privacy_label(None) is None

    def test_unknown(self):
        assert privacy_label(7) == "unknown (7)"


class TestRequireCount:
    def test_default_when_not_given(self):
        assert _require_count(None, "limit", default=25) == 25

    def test_converts_and_caps(self):
        assert _require_count("10", "limit", default=25, minimum=1, maximum=100) == 10
        assert _require_count(500, "limit", default=25, minimum=1, maximum=100) == 100

    @pytest.mark.parametrize(
        ("value", "message"),
        [(0, "at least 1"), (-5, "at least 1"), (True, "must be an integer"), ("x", "integer")],
    )
    def test_rejects(self, value, message):
        with pytest.raises(ToolError, match=message):
            _require_count(value, "limit", default=25, minimum=1)

    def test_offset_allows_zero_but_not_negative(self):
        assert _require_count(0, "offset", default=0) == 0
        with pytest.raises(ToolError, match="'offset' must be at least 0"):
            _require_count(-1, "offset", default=0)


class TestRequireBool:
    @pytest.mark.parametrize(
        ("value", "expected"), [(True, True), (False, False), ("false", False), (" TRUE ", True)]
    )
    def test_accepts(self, value, expected):
        assert _require_bool(value, "featured") is expected

    def test_default(self):
        assert _require_bool(None, "featured", default=True) is True

    @pytest.mark.parametrize("value", [1, "yes", [], "0"])
    def test_rejects(self, value):
        with pytest.raises(ToolError, match="'featured' must be true or false"):
            _require_bool(value, "featured")


class TestRequireStr:
    def test_accepts_none_and_strings(self):
        assert _require_str(None, "sort") is None
        assert _require_str("rating", "sort") == "rating"

    def test_rejects_other_types(self):
        with pytest.raises(ToolError, match="'sort' must be a string"):
            _require_str(["rating"], "sort")
