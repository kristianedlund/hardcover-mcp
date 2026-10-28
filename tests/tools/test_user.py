"""Unit tests for tools.user."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.user import _format_user, _render_user_query, handle_get_user


class TestFormatUser:
    def test_formats_profile_without_library(self):
        raw = {
            "id": 1,
            "username": "adam",
            "name": "Adam",
            "bio": "Founder.",
            "books_count": 1264,
            "followers_count": 10053,
            "followed_users_count": 1010,
            "flair": "Supporter",
            "pro": True,
            "account_privacy_setting_id": 1,
            "cached_image": {"url": "https://example.com/a.jpg"},
            "created_at": "2021-10-02T21:11:34+00:00",
        }

        result = _format_user(raw)

        assert result["id"] == 1
        assert result["username"] == "adam"
        assert result["following_count"] == 1010
        assert result["privacy"] == "public"
        assert result["image_url"] == "https://example.com/a.jpg"
        assert "library" not in result

    def test_includes_library_when_present(self):
        raw = {
            "id": 1,
            "account_privacy_setting_id": 2,
            "cached_image": None,
            "user_books": [
                {
                    "rating": 4.5,
                    "status_id": 3,
                    "book": {
                        "id": 100,
                        "slug": "dune",
                        "title": "Dune",
                        "release_year": 1965,
                        "rating": 4.2,
                    },
                },
                {"rating": None, "status_id": 3, "book": None},  # dropped
            ],
        }

        result = _format_user(raw)

        assert result["privacy"] == "followers"
        assert result["image_url"] is None
        assert len(result["library"]) == 1
        entry = result["library"][0]
        assert entry["book_id"] == 100
        assert entry["title"] == "Dune"
        assert entry["user_rating"] == 4.5
        assert "your_rating" not in entry
        assert entry["status"] == "Read"


class TestRenderUserQuery:
    def test_id_key_uses_int_type(self):
        q = _render_user_query("id", with_library=False, with_status=False)
        assert "$id: Int!" in q
        assert "user_books" not in q

    def test_username_key_uses_string_type(self):
        q = _render_user_query("username", with_library=False, with_status=False)
        assert "$username: citext!" in q

    def test_library_and_status_vars(self):
        q = _render_user_query("id", with_library=True, with_status=True)
        assert "$library_limit: Int!" in q
        assert "$status_id: Int!" in q
        assert "status_id: {_eq: $status_id}" in q
        assert "user_books(" in q


def _profile(user_id: int = 1, **extra) -> dict:
    return {"data": {"users": [{"id": user_id, "username": "me", **extra}]}}


class TestHandleGetUserSections:
    async def _run(self, arguments: dict, *responses: dict) -> tuple[str, AsyncMock]:
        mock_exec = AsyncMock(side_effect=list(responses))
        self.mock_exec = mock_exec
        with (
            patch(
                "hardcover_mcp.tools.user.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch("hardcover_mcp.tools.user.execute", new=mock_exec),
            patch(
                "hardcover_mcp.tools.user.fetch_reading_stats",
                new=AsyncMock(return_value={"total_books": 3}),
            ) as mock_stats,
        ):
            self.mock_stats = mock_stats
            result = await handle_get_user(arguments)
        return result[0].text, mock_exec

    async def test_include_stats_for_yourself(self):
        text, _ = await self._run({"include_stats": True, "stats_year": "2022"}, _profile(1))

        assert json.loads(text)["stats"] == {"total_books": 3}
        self.mock_stats.assert_awaited_once_with(1, 2022)

    async def test_include_stats_for_someone_else_is_an_error(self):
        with pytest.raises(ToolError) as exc:
            await self._run({"id": 99, "include_stats": True}, _profile(99))

        assert "only available for your own profile" in str(exc.value)
        self.mock_stats.assert_not_awaited()

    async def test_rejects_non_integer_stats_year(self):
        with pytest.raises(ToolError) as exc:
            await self._run({"include_stats": True, "stats_year": "soon"})

        assert "must be an integer" in str(exc.value)
        self.mock_exec.assert_not_awaited()

    async def test_follow_lists_are_flattened(self):
        raw = _profile(
            1,
            followed_users=[
                {"created_at": "2025-01-02", "followed_user": {"id": 5, "username": "a"}}
            ],
            followed_by_users=[{"created_at": "2025-03-04", "user": {"id": 6, "username": "b"}}],
        )
        text, mock_exec = await self._run(
            {"include_following": True, "include_followers": True, "follow_limit": 500}, raw
        )

        data = json.loads(text)
        assert data["following"] == [
            {"id": 5, "username": "a", "name": None, "created_at": "2025-01-02"}
        ]
        assert data["followers"][0]["username"] == "b"
        assert mock_exec.call_args[0][1]["follow_limit"] == 100
        query = mock_exec.call_args[0][0]
        assert "followed_users(" in query and "followed_by_users(" in query

    async def test_no_sections_by_default(self):
        text, mock_exec = await self._run({}, _profile(1))

        data = json.loads(text)
        assert not {"stats", "following", "followers", "library"} & data.keys()
        assert "followed_users(" not in mock_exec.call_args[0][0]


class TestWhoIsAsked:
    async def test_id_zero_is_looked_up_not_treated_as_me(self):
        me = AsyncMock(return_value={"id": 1})
        mock_exec = AsyncMock(return_value={"data": {"users": []}})
        with (
            patch("hardcover_mcp.tools.user.get_current_user", new=me),
            patch("hardcover_mcp.tools.user.execute", new=mock_exec),
        ):
            result = await handle_get_user({"id": 0})

        assert result[0].text == "No user found."
        me.assert_not_awaited()

    async def test_non_string_username_is_a_clear_error(self):
        with pytest.raises(ToolError, match="'username' must be a string"):
            await handle_get_user({"username": ["adam"]})


class TestCurrentUserCache:
    @pytest.fixture(autouse=True)
    def _empty_cache(self, monkeypatch):
        from hardcover_mcp.tools import user

        monkeypatch.setattr(user, "_cached_user", None)
        monkeypatch.setattr(user, "_cached_at", 0.0)

    async def test_second_call_uses_the_cache(self):
        from hardcover_mcp.tools.user import get_current_user

        mock = AsyncMock(return_value={"data": {"me": [{"id": 7}]}})
        with patch("hardcover_mcp.tools.user.execute", new=mock):
            assert (await get_current_user())["id"] == 7
            assert (await get_current_user())["id"] == 7
        mock.assert_awaited_once()

    async def test_expired_cache_asks_again(self, monkeypatch):
        from hardcover_mcp.tools import user

        mock = AsyncMock(
            side_effect=[{"data": {"me": [{"id": 7}]}}, {"data": {"me": [{"id": 8}]}}]
        )
        now = [1000.0]
        monkeypatch.setattr(user.time, "monotonic", lambda: now[0])
        with patch("hardcover_mcp.tools.user.execute", new=mock):
            assert (await user.get_current_user())["id"] == 7
            now[0] += user._CACHE_TTL + 1  # an hour later
            assert (await user.get_current_user())["id"] == 8
        assert mock.await_count == 2

    async def test_no_user_for_the_token_is_a_clear_error(self):
        from hardcover_mcp.client import HardcoverAPIError
        from hardcover_mcp.tools.user import get_current_user

        mock = AsyncMock(return_value={"data": {"me": []}})
        with (
            patch("hardcover_mcp.tools.user.execute", new=mock),
            pytest.raises(HardcoverAPIError, match="no user for this API token"),
        ):
            await get_current_user()
