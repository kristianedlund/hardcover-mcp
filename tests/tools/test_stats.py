"""Tests for tools/stats.py — _format_reading_stats and fetch_reading_stats."""

from unittest.mock import AsyncMock, patch

from hardcover_mcp.tools.stats import _format_reading_stats, fetch_reading_stats

# ── Fixture helpers ──

_AGGREGATE_RESPONSE = {
    "total": {"aggregate": {"count": 142}},
    "want_to_read": {"aggregate": {"count": 35}},
    "currently_reading": {"aggregate": {"count": 3}},
    "read": {"aggregate": {"count": 98}},
    "did_not_finish": {"aggregate": {"count": 6}},
    "paused": {"aggregate": {"count": 0}},
    "ignored": {"aggregate": {"count": 0}},
    "ratings": {"aggregate": {"avg": {"rating": 3.8333}}},
    "read_in_year": {"aggregate": {"count": 12}},
}


class TestFormatReadingStats:
    def test_maps_all_top_level_fields(self):
        result = _format_reading_stats(_AGGREGATE_RESPONSE, 2025)

        assert result["total_books"] == 142
        assert result["books_read_this_year"] == 12
        assert result["year"] == 2025

    def test_by_status_contains_all_statuses(self):
        result = _format_reading_stats(_AGGREGATE_RESPONSE, 2025)

        by_status = result["by_status"]
        assert by_status["want_to_read"] == 35
        assert by_status["currently_reading"] == 3
        assert by_status["read"] == 98
        assert by_status["did_not_finish"] == 6
        assert by_status["paused"] == 0
        assert by_status["ignored"] == 0

    def test_rounds_average_rating_to_two_decimal_places(self):
        result = _format_reading_stats(_AGGREGATE_RESPONSE, 2025)

        assert result["average_rating"] == 3.83

    def test_average_rating_is_none_when_no_ratings(self):
        data = {
            **_AGGREGATE_RESPONSE,
            "ratings": {"aggregate": {"avg": {"rating": None}}},
        }
        result = _format_reading_stats(data, 2025)

        assert result["average_rating"] is None

    def test_zero_counts_are_preserved(self):
        data = {
            **_AGGREGATE_RESPONSE,
            "total": {"aggregate": {"count": 0}},
            "read_in_year": {"aggregate": {"count": 0}},
        }
        result = _format_reading_stats(data, 2025)

        assert result["total_books"] == 0
        assert result["books_read_this_year"] == 0

    def test_year_is_passed_through(self):
        result_2023 = _format_reading_stats(_AGGREGATE_RESPONSE, 2023)
        result_2024 = _format_reading_stats(_AGGREGATE_RESPONSE, 2024)

        assert result_2023["year"] == 2023
        assert result_2024["year"] == 2024


class TestFetchReadingStats:
    @patch("hardcover_mcp.tools.stats.execute", new_callable=AsyncMock)
    async def test_returns_formatted_stats(self, mock_execute):
        mock_execute.return_value = {"data": _AGGREGATE_RESPONSE}

        data = await fetch_reading_stats(1)

        assert data["total_books"] == 142
        assert data["by_status"]["read"] == 98
        assert data["average_rating"] == 3.83
        assert data["books_read_this_year"] == 12

    @patch("hardcover_mcp.tools.stats.execute", new_callable=AsyncMock)
    async def test_passes_user_and_year_variables(self, mock_execute):
        mock_execute.return_value = {"data": _AGGREGATE_RESPONSE}

        await fetch_reading_stats(7, 2023)

        assert mock_execute.call_args_list[0][0][1] == {"user_id": 7}
        call_vars = mock_execute.call_args[0][1]
        assert call_vars["year_start"] == "2023-01-01"
        assert call_vars["year_end"] == "2023-12-31"

    @patch("hardcover_mcp.tools.stats.execute", new_callable=AsyncMock)
    async def test_defaults_to_current_year(self, mock_execute):
        from datetime import date

        mock_execute.return_value = {"data": _AGGREGATE_RESPONSE}

        await fetch_reading_stats(1)

        current_year = date.today().year
        assert mock_execute.call_args[0][1]["year_start"] == f"{current_year}-01-01"
