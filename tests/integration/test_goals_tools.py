"""Integration tests for reading goal tools."""

import json
from datetime import date

import pytest

from tests.integration._eventually import eventually

pytestmark = pytest.mark.integration


class TestReadingGoalsLifecycle:
    """Create a goal → verify it appears → archive → restore → edit → delete."""

    async def test_goal_lifecycle(self):
        from hardcover_mcp.tools.goals import (
            handle_delete_reading_goal,
            handle_get_reading_goal,
            handle_set_reading_goal,
        )

        current_year = date.today().year
        start_date = f"{current_year}-06-01"
        end_date = f"{current_year}-06-30"

        async def active_goal_ids() -> set[int]:
            result = await handle_get_reading_goal({"limit": 100})
            return {goal["id"] for goal in json.loads(result[0].text)["goals"]}

        async def is_active(active: bool) -> bool:
            return await eventually(lambda: _matches(active))

        async def _matches(active: bool) -> bool:
            return (goal_id in await active_goal_ids()) == active

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

            # 2. It appears in active goals
            assert await is_active(True)

            # 3. Archive by id: hidden from active goals, target unchanged
            archived = json.loads(
                (await handle_set_reading_goal({"id": goal_id, "archived": True}))[0].text
            )
            assert archived["archived"] is True
            assert archived["goal"] == 99
            assert await is_active(False)

            # 4. Restore and edit the target in one call
            restored = json.loads(
                (await handle_set_reading_goal({"id": goal_id, "archived": False, "goal": 98}))[
                    0
                ].text
            )
            assert restored["archived"] is False
            assert restored["goal"] == 98
            assert await is_active(True)

            # 5. Delete
            deleted = json.loads((await handle_delete_reading_goal({"id": goal_id}))[0].text)
            assert deleted == {"deleted": True, "id": goal_id}
            goal_id = None
        finally:
            # Always clean up the test goal, even if a step above failed.
            if goal_id is not None:
                await handle_delete_reading_goal({"id": goal_id})
