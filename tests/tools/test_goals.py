"""Tests for tools/goals.py."""

import json
from unittest.mock import AsyncMock, patch

from hardcover_mcp.tools.goals import (
    _format_reading_goal,
    handle_get_reading_goal,
    handle_set_reading_goal,
)


class TestFormatReadingGoal:
    def test_maps_expected_fields(self):
        result = _format_reading_goal(
            {
                "id": 7,
                "goal": 52,
                "metric": "book",
                "progress": 12,
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "state": "active",
                "privacy_setting_id": 1,
            }
        )

        assert result == {
            "id": 7,
            "goal": 52,
            "metric": "book",
            "progress": 12,
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "state": "active",
            "privacy_setting_id": 1,
        }


class TestHandleGetReadingGoal:
    @patch("hardcover_mcp.tools.goals.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.goals.execute", new_callable=AsyncMock)
    async def test_returns_active_goals(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = {
            "data": {
                "goals": [
                    {
                        "id": 10,
                        "goal": 52,
                        "metric": "book",
                        "progress": 11,
                        "start_date": "2026-01-01",
                        "end_date": "2026-12-31",
                        "state": "active",
                        "privacy_setting_id": 1,
                    }
                ]
            }
        }

        result = await handle_get_reading_goal({})
        data = json.loads(result[0].text)

        assert data["returned"] == 1
        assert data["goals"][0]["goal"] == 52
        assert data["goals"][0]["metric"] == "book"

        query_vars = mock_execute.call_args[0][1]
        assert query_vars["limit"] == 10
        assert query_vars["user_id"] == 1

    async def test_invalid_limit_returns_error(self):
        result = await handle_get_reading_goal({"limit": 0})
        assert result[0].text == "Error: 'limit' must be greater than 0."


class TestHandleSetReadingGoal:
    async def test_missing_required_field_returns_error(self):
        result = await handle_set_reading_goal(
            {
                "goal": 52,
                "metric": "books",
                "start_date": "2026-01-01",
            }
        )
        assert result[0].text == "Error: 'end_date' is required."

    async def test_invalid_metric_returns_error(self):
        result = await handle_set_reading_goal(
            {
                "goal": 52,
                "metric": "hours",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            }
        )
        assert result[0].text == "Error: 'metric' must be either 'book' or 'page'"

    async def test_invalid_date_returns_error(self):
        result = await handle_set_reading_goal(
            {
                "goal": 52,
                "metric": "book",
                "start_date": "2026-13-01",
                "end_date": "2026-12-31",
            }
        )
        assert "'start_date' must be an ISO 8601 date" in result[0].text

    async def test_end_date_before_start_date_returns_error(self):
        result = await handle_set_reading_goal(
            {
                "goal": 52,
                "metric": "book",
                "start_date": "2026-12-31",
                "end_date": "2026-01-01",
            }
        )
        assert result[0].text == "Error: 'end_date' must be on or after 'start_date'"

    @patch("hardcover_mcp.tools.goals.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.goals.execute", new_callable=AsyncMock)
    async def test_creates_goal_when_no_match_exists(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.side_effect = [
            {"data": {"goals": []}},
            {
                "data": {
                    "insert_goal": {
                        "id": 55,
                        "errors": None,
                        "goal": {
                            "id": 55,
                            "goal": 52,
                            "metric": "book",
                            "progress": 0,
                            "start_date": "2026-01-01",
                            "end_date": "2026-12-31",
                            "state": "active",
                            "privacy_setting_id": 2,
                        },
                    }
                }
            },
        ]

        result = await handle_set_reading_goal(
            {
                "goal": 52,
                "metric": "book",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "description": "Read one per week",
                "privacy_setting_id": 2,
            }
        )
        data = json.loads(result[0].text)

        assert data["id"] == 55
        assert data["goal"] == 52
        assert data["metric"] == "book"

        insert_vars = mock_execute.call_args_list[1][0][1]["object"]
        assert insert_vars["description"] == "Read one per week"
        assert insert_vars["privacy_setting_id"] == 2

    @patch("hardcover_mcp.tools.goals.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.goals.execute", new_callable=AsyncMock)
    async def test_updates_goal_when_match_exists(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.side_effect = [
            {"data": {"goals": [{"id": 12}]}},
            {
                "data": {
                    "update_goal": {
                        "id": 12,
                        "errors": None,
                        "goal": {
                            "id": 12,
                            "goal": 60,
                            "metric": "book",
                            "progress": 14,
                            "start_date": "2026-01-01",
                            "end_date": "2026-12-31",
                            "state": "active",
                            "privacy_setting_id": 1,
                        },
                    }
                }
            },
        ]

        result = await handle_set_reading_goal(
            {
                "goal": 60,
                "metric": "book",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            }
        )
        data = json.loads(result[0].text)

        assert data["id"] == 12
        assert data["goal"] == 60
        assert data["metric"] == "book"

        update_vars = mock_execute.call_args_list[1][0][1]
        assert update_vars["id"] == 12
        assert update_vars["object"]["goal"] == 60
