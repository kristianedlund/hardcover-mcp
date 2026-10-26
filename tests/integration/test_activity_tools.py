"""Integration tests for get_activity_feed against the real Hardcover API.

Requires HARDCOVER_API_TOKEN in the environment (loaded from .env by conftest.py).
Skipped automatically when the token is absent.
"""

import json

import pytest

pytestmark = pytest.mark.integration


class TestActivityFeed:
    async def test_activity_by_username(self):
        from hardcover_mcp.tools.activity import handle_get_activity_feed

        # 'adam' (Hardcover founder) has a long, stable public activity history.
        result = await handle_get_activity_feed({"username": "adam", "limit": 3})

        events = json.loads(result[0].text)["activities"]
        assert isinstance(events, list)
        assert len(events) <= 3
        first = events[0]
        assert first["user"]["username"] == "adam"
        assert first["event"]
        assert first["created_at"]

    async def test_activity_by_user_id(self):
        from hardcover_mcp.tools.activity import handle_get_activity_feed

        result = await handle_get_activity_feed({"user_id": 1, "limit": 1})

        events = json.loads(result[0].text)["activities"]
        assert isinstance(events, list)
        assert events[0]["user"]["id"] == 1

    async def test_unknown_username_reports_not_found(self):
        from hardcover_mcp.tools.activity import handle_get_activity_feed

        result = await handle_get_activity_feed(
            {"username": "definitely-not-a-real-user-xyz-9999"}
        )

        assert "No user found" in result[0].text

    async def test_followed_feed_returns_a_page(self):
        from hardcover_mcp.tools.activity import handle_get_activity_feed

        # Feed depends on who the token's account follows; it may be empty.
        data = json.loads((await handle_get_activity_feed({"limit": 5}))[0].text)

        assert data["offset"] == 0
        assert data["returned"] == len(data["activities"]) <= 5
