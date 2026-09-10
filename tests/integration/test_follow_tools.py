"""Integration tests for follow_user / unfollow_user against the real Hardcover API.

Requires HARDCOVER_API_TOKEN in the environment (loaded from .env by conftest.py).
Skipped automatically when the token is absent.
"""

import json

import pytest

pytestmark = pytest.mark.integration


class TestFollowUnfollow:
    async def test_follow_then_unfollow_by_username(self):
        from hardcover_mcp.tools.follow import handle_follow_user, handle_unfollow_user

        # 'adam' (Hardcover founder) is a stable public account to follow/unfollow.
        followed = json.loads((await handle_follow_user({"username": "adam"}))[0].text)
        assert followed["followed"] is True

        unfollowed = json.loads((await handle_unfollow_user({"username": "adam"}))[0].text)
        assert unfollowed["unfollowed"] is True

    async def test_unknown_username_reports_not_found(self):
        from hardcover_mcp.tools.follow import handle_follow_user

        result = await handle_follow_user({"username": "definitely-not-a-real-user-xyz-9999"})

        assert "No user found" in result[0].text
