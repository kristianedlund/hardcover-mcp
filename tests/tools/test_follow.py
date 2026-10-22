"""Unit tests for tools.follow (validation and state handling, no live API calls)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.follow import handle_set_following


def _followed(*ids: int) -> dict:
    return {"data": {"me": [{"followed_users": [{"followed_user_id": i} for i in ids]}]}}


class TestSetFollowingValidation:
    async def test_rejects_missing_following(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_following({"user_id": 1})
        assert "'following'" in str(exc.value)

    async def test_rejects_non_bool_following(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_following({"user_id": 1, "following": "yes"})
        assert "'following'" in str(exc.value)

    async def test_rejects_missing_user(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_following({"following": True})
        assert "provide either" in str(exc.value)

    async def test_rejects_non_int_user_id(self):
        with pytest.raises(ToolError):
            await handle_set_following({"user_id": "abc", "following": True})


class TestSetFollowingState:
    async def test_follow_when_not_following_runs_mutation(self):
        mock = AsyncMock(
            side_effect=[
                _followed(),
                {"data": {"insert_followed_user": {"followed_user_id": 7, "error": None}}},
            ]
        )
        with patch("hardcover_mcp.tools.follow.execute", new=mock):
            result = await handle_set_following({"user_id": 7, "following": True})

        assert json.loads(result[0].text) == {"user_id": 7, "following": True, "changed": True}
        assert "insert_followed_user" in mock.call_args_list[1][0][0]

    async def test_follow_when_already_following_is_noop(self):
        mock = AsyncMock(return_value=_followed(7))
        with patch("hardcover_mcp.tools.follow.execute", new=mock):
            result = await handle_set_following({"user_id": 7, "following": True})

        assert json.loads(result[0].text)["changed"] is False
        assert mock.call_count == 1

    async def test_unfollow_when_following_runs_mutation(self):
        mock = AsyncMock(
            side_effect=[
                _followed(7),
                {"data": {"delete_followed_user": {"followed_user_id": 7, "error": None}}},
            ]
        )
        with patch("hardcover_mcp.tools.follow.execute", new=mock):
            result = await handle_set_following({"user_id": 7, "following": False})

        assert json.loads(result[0].text)["changed"] is True
        assert "delete_followed_user" in mock.call_args_list[1][0][0]

    async def test_unfollow_when_not_following_is_noop(self):
        mock = AsyncMock(return_value=_followed())
        with patch("hardcover_mcp.tools.follow.execute", new=mock):
            result = await handle_set_following({"user_id": 7, "following": False})

        assert json.loads(result[0].text)["changed"] is False

    async def test_api_error_is_reported(self):
        mock = AsyncMock(
            side_effect=[
                _followed(),
                {"data": {"insert_followed_user": {"followed_user_id": None, "error": "nope"}}},
            ]
        )
        with (
            patch("hardcover_mcp.tools.follow.execute", new=mock),
            pytest.raises(ToolError) as exc,
        ):
            await handle_set_following({"user_id": 7, "following": True})

        assert str(exc.value) == "nope"
