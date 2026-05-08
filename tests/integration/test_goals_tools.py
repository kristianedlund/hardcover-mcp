"""Integration tests for reading goal tools."""

import json
from datetime import date

import pytest

pytestmark = pytest.mark.integration


class TestReadingGoalsLifecycle:
    """Create or update a goal, then verify it appears in active goals."""

    async def test_set_then_get_reading_goal(self):
        from hardcover_mcp.tools.goals import handle_get_reading_goal, handle_set_reading_goal

        current_year = date.today().year
        start_date = f"{current_year}-01-01"
        end_date = f"{current_year}-12-31"

        # 1. Create or update the active yearly books goal
        result = await handle_set_reading_goal(
            {
                "goal": 52,
                "metric": "books",
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        saved = json.loads(result[0].text)
        assert saved["goal"] == 52
        assert saved["metric"] == "books"

        # 2. Verify the goal appears in active goals
        result = await handle_get_reading_goal({"limit": 25})
        data = json.loads(result[0].text)
        goals = data["goals"]

        assert any(
            goal["metric"] == "books"
            and goal["start_date"] == start_date
            and goal["end_date"] == end_date
            and goal["goal"] == 52
            for goal in goals
        )
