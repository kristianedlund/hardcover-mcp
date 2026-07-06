"""Integration tests for reading goal tools."""

import json
from datetime import date

import pytest

from hardcover_mcp.client import execute

pytestmark = pytest.mark.integration

DELETE_GOAL_MUTATION = """
mutation DeleteGoal($id: Int!) {
    delete_goal(id: $id) {
        __typename
    }
}
"""


class TestReadingGoalsLifecycle:
    """Create a goal → verify it appears → delete it."""

    async def test_set_then_get_reading_goal(self):
        from hardcover_mcp.tools.goals import handle_get_reading_goal, handle_set_reading_goal

        current_year = date.today().year
        start_date = f"{current_year}-06-01"
        end_date = f"{current_year}-06-30"

        goal_id = None
        try:
            # 1. Create a short-range test goal (won't collide with real yearly goals)
            result = await handle_set_reading_goal(
                {
                    "goal": 99,
                    "metric": "book",
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
            saved = json.loads(result[0].text)
            goal_id = saved["id"]
            assert saved["goal"] == 99
            assert saved["metric"] == "book"

            # 2. Verify the goal appears in active goals
            result = await handle_get_reading_goal({"limit": 25})
            data = json.loads(result[0].text)
            goals = data["goals"]

            assert any(
                goal["id"] == goal_id and goal["goal"] == 99 for goal in goals
            )
        finally:
            # 3. Always clean up the test goal
            if goal_id is not None:
                await execute(DELETE_GOAL_MUTATION, {"id": goal_id})
