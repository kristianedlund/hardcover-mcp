"""Tests for tools/goals.py."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.goals import (
    _format_reading_goal,
    handle_delete_reading_goal,
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
            "privacy": "public",
            "privacy_setting_id": 1,
            "archived": False,
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
        with pytest.raises(ToolError) as exc:
            await handle_get_reading_goal({"limit": 0})
        assert str(exc.value) == "'limit' must be greater than 0."


class TestHandleSetReadingGoal:
    async def test_missing_required_field_returns_error(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_reading_goal(
                {
                    "goal": 52,
                    "metric": "books",
                    "start_date": "2026-01-01",
                }
            )
        assert str(exc.value) == "'end_date' is required."

    async def test_invalid_metric_returns_error(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_reading_goal(
                {
                    "goal": 52,
                    "metric": "hours",
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                }
            )
        assert str(exc.value) == "'metric' must be either 'book' or 'page'"

    async def test_invalid_date_returns_error(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_reading_goal(
                {
                    "goal": 52,
                    "metric": "book",
                    "start_date": "2026-13-01",
                    "end_date": "2026-12-31",
                }
            )
        assert "'start_date' must be an ISO 8601 date" in str(exc.value)

    async def test_end_date_before_start_date_returns_error(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_reading_goal(
                {
                    "goal": 52,
                    "metric": "book",
                    "start_date": "2026-12-31",
                    "end_date": "2026-01-01",
                }
            )
        assert str(exc.value) == "'end_date' must be on or after 'start_date'"

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
                "privacy": "followers",
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


def _own_goal(**overrides) -> dict:
    goal = {
        "id": 7,
        "goal": 52,
        "metric": "book",
        "progress": 12,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "description": "52 books",
        "state": "active",
        "privacy_setting_id": 1,
        "archived": False,
    }
    return {"data": {"goals": [{**goal, **overrides}]}}


class TestGoalEditAndDelete:
    async def _run(self, handler, arguments: dict, *responses: dict) -> tuple[str, AsyncMock]:
        mock_exec = AsyncMock(side_effect=list(responses))
        self.mock_exec = mock_exec
        with (
            patch(
                "hardcover_mcp.tools.goals.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch("hardcover_mcp.tools.goals.execute", new=mock_exec),
        ):
            result = await handler(arguments)
        return result[0].text, mock_exec

    async def test_archive_by_id_keeps_other_fields(self):
        updated = {"data": {"update_goal": {"errors": None, "goal": None}}}
        text, mock_exec = await self._run(
            handle_set_reading_goal, {"id": 7, "archived": True}, _own_goal(), updated
        )

        assert json.loads(text)["archived"] is True
        assert mock_exec.call_args_list[0][0][1] == {"id": 7, "user_id": 1}
        sent = mock_exec.call_args_list[1][0][1]
        assert sent["id"] == 7
        assert sent["object"]["archived"] is True
        assert sent["object"]["goal"] == 52
        assert sent["object"]["description"] == "52 books"

    async def test_edit_by_id_changes_only_passed_fields(self):
        updated = {"data": {"update_goal": {"errors": None, "goal": None}}}
        _, mock_exec = await self._run(
            handle_set_reading_goal, {"id": 7, "goal": 60}, _own_goal(), updated
        )

        sent = mock_exec.call_args_list[1][0][1]["object"]
        assert sent["goal"] == 60
        assert sent["metric"] == "book"
        assert sent["archived"] is False

    async def test_edit_privacy(self):
        updated = {"data": {"update_goal": {"errors": None, "goal": None}}}
        text, mock_exec = await self._run(
            handle_set_reading_goal, {"id": 7, "privacy": "followers"}, _own_goal(), updated
        )

        assert mock_exec.call_args_list[1][0][1]["object"]["privacy_setting_id"] == 2
        assert json.loads(text)["privacy"] == "followers"

    async def test_removed_privacy_setting_id_errors_before_api_calls(self):
        with pytest.raises(ToolError, match="'privacy_setting_id' was removed"):
            await self._run(handle_set_reading_goal, {"id": 7, "privacy_setting_id": 3})
        self.mock_exec.assert_not_awaited()

    async def test_edit_keeps_privacy_when_not_passed(self):
        updated = {"data": {"update_goal": {"errors": None, "goal": None}}}
        _, mock_exec = await self._run(
            handle_set_reading_goal,
            {"id": 7, "goal": 60},
            _own_goal(privacy_setting_id=3),
            updated,
        )

        assert mock_exec.call_args_list[1][0][1]["object"]["privacy_setting_id"] == 3

    async def test_create_with_privacy(self):
        inserted = {"data": {"insert_goal": {"id": 55, "errors": None, "goal": None}}}
        _, mock_exec = await self._run(
            handle_set_reading_goal,
            {
                "goal": 52,
                "metric": "book",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "privacy": "private",
            },
            {"data": {"goals": []}},
            inserted,
        )

        assert mock_exec.call_args_list[1][0][1]["object"]["privacy_setting_id"] == 3

    async def test_edit_requires_a_field(self):
        with pytest.raises(ToolError) as exc:
            await self._run(handle_set_reading_goal, {"id": 7})

        assert "at least one of" in str(exc.value)
        self.mock_exec.assert_not_awaited()

    async def test_edit_someone_elses_goal_is_not_found(self):
        with pytest.raises(ToolError) as exc:
            await self._run(
                handle_set_reading_goal, {"id": 7, "archived": True}, {"data": {"goals": []}}
            )

        assert "no reading goal of yours" in str(exc.value)

    async def test_archived_without_id_is_an_error(self):
        with pytest.raises(ToolError) as exc:
            await self._run(
                handle_set_reading_goal,
                {
                    "goal": 5,
                    "metric": "book",
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "archived": True,
                },
            )

        assert "'archived' needs the goal's id" in str(exc.value)
        self.mock_exec.assert_not_awaited()

    async def test_delete_own_goal(self):
        text, mock_exec = await self._run(
            handle_delete_reading_goal,
            {"id": 7},
            _own_goal(),
            {"data": {"delete_goal": {"id": 7, "errors": None}}},
        )

        assert json.loads(text) == {"deleted": True, "id": 7}
        assert mock_exec.call_args_list[1][0][1] == {"id": 7}

    async def test_delete_someone_elses_goal_is_not_found(self):
        with pytest.raises(ToolError) as exc:
            await self._run(handle_delete_reading_goal, {"id": 7}, {"data": {"goals": []}})

        assert "no reading goal of yours" in str(exc.value)
        assert self.mock_exec.call_count == 1
