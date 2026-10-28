"""Unit tests for tools.activity."""

import json
from unittest.mock import AsyncMock, patch

from hardcover_mcp.tools.activity import _format_activity, handle_get_activity_feed

_EVENT = {
    "id": 100,
    "event": "UserBookActivity",
    "created_at": "2026-09-10T09:06:38+00:00",
    "likes_count": 0,
    "book": None,
    "user": {"id": 1, "username": "adam", "name": "Adam"},
}


class TestFormatActivity:
    def test_formats_book_event(self):
        raw = {
            "id": 100,
            "event": "UserBookActivity",
            "created_at": "2026-09-10T09:06:38+00:00",
            "likes_count": 3,
            "book": {"id": 374481, "slug": "lord-of-the-flies", "title": "Lord of the Flies"},
            "user": {"id": 1, "username": "adam", "name": "Adam"},
            "data": {"huge": "blob", "dropped": True},
        }

        result = _format_activity(raw)

        assert result["id"] == 100
        assert result["event"] == "UserBookActivity"
        assert result["likes_count"] == 3
        assert result["book"]["title"] == "Lord of the Flies"
        assert result["user"]["username"] == "adam"
        assert "data" not in result

    def test_handles_null_book(self):
        raw = {
            "id": 101,
            "event": "ListActivity",
            "created_at": "2026-09-10T02:55:14+00:00",
            "likes_count": 0,
            "book": None,
            "user": {"id": 1, "username": "adam", "name": "Adam"},
        }

        result = _format_activity(raw)

        assert result["book"] is None
        assert result["event"] == "ListActivity"


class TestHandleGetActivityFeed:
    async def test_one_users_activity_is_a_page(self):
        mock = AsyncMock(return_value={"data": {"activities": [_EVENT]}})
        with patch("hardcover_mcp.tools.activity.execute", new=mock):
            result = await handle_get_activity_feed({"user_id": 1, "offset": 20})

        data = json.loads(result[0].text)
        assert {k: data[k] for k in ("returned", "offset")} == {"returned": 1, "offset": 20}
        assert data["activities"][0]["user"]["username"] == "adam"

    async def test_following_nobody_is_an_empty_page(self):
        mock = AsyncMock(return_value={"data": {"me": [{"followed_users": []}]}})
        with patch("hardcover_mcp.tools.activity.execute", new=mock):
            result = await handle_get_activity_feed({})

        assert json.loads(result[0].text) == {"returned": 0, "offset": 0, "activities": []}
        mock.assert_awaited_once()  # no feed query when there's nobody to show

    async def test_unknown_username_is_an_empty_page(self):
        mock = AsyncMock(return_value={"data": {"users": []}})
        with patch("hardcover_mcp.tools.activity.execute", new=mock):
            result = await handle_get_activity_feed({"username": "ghost"})

        assert json.loads(result[0].text) == {"returned": 0, "offset": 0, "activities": []}
        mock.assert_awaited_once()  # only the user lookup
