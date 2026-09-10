"""Unit tests for tools.follow (validation, no live API calls)."""

from hardcover_mcp.tools.follow import handle_follow_user, handle_unfollow_user


class TestFollowValidation:
    async def test_rejects_missing_user(self):
        result = await handle_follow_user({})
        assert "provide either" in result[0].text

    async def test_rejects_non_int_user_id(self):
        result = await handle_follow_user({"user_id": "abc"})
        assert "Error" in result[0].text


class TestUnfollowValidation:
    async def test_rejects_missing_user(self):
        result = await handle_unfollow_user({})
        assert "provide either" in result[0].text
