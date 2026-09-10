"""Unit tests for tools.activity."""

from hardcover_mcp.tools.activity import _format_activity


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
