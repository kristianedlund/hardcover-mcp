"""Integration tests for set_following against the real Hardcover API.

Requires HARDCOVER_API_TOKEN in the environment (loaded from .env by conftest.py).
Skipped automatically when the token is absent.
"""

import json

import pytest

from tests.integration._eventually import eventually

pytestmark = pytest.mark.integration


class TestSetFollowing:
    async def test_toggle_and_restore_by_username(self):
        from hardcover_mcp.tools.follow import _is_following, handle_set_following

        async def set_following(following: bool) -> dict:
            result = await handle_set_following({"username": "adam", "following": following})
            return json.loads(result[0].text)

        async def readable(user_id: int, following: bool) -> bool:
            # Repeat a call only once the previous one is readable, or it changes again.
            async def matches() -> bool:
                return await _is_following(user_id) == following

            return await eventually(matches)

        # 'adam' (Hardcover founder) is a stable public account. Flip the follow state,
        # check idempotency, then restore whatever the account had before.
        probe = await set_following(True)
        originally_following = not probe["changed"]
        assert await readable(probe["user_id"], True)
        try:
            unfollowed = await set_following(False)
            assert unfollowed["changed"] is True
            assert await readable(unfollowed["user_id"], False)
            assert (await set_following(False))["changed"] is False

            followed = await set_following(True)
            assert followed["changed"] is True
            assert await readable(followed["user_id"], True)
            assert (await set_following(True))["changed"] is False
        finally:
            await set_following(originally_following)

    async def test_unknown_username_reports_not_found(self):
        from hardcover_mcp.tools.follow import handle_set_following

        result = await handle_set_following(
            {"username": "definitely-not-a-real-user-xyz-9999", "following": True}
        )

        assert "No user found" in result[0].text
