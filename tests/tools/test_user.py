"""Unit tests for tools.user."""

from hardcover_mcp.tools.user import _format_user, _render_user_query


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
        assert result["privacy"] == "Public"
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

        assert result["privacy"] == "Followers"
        assert result["image_url"] is None
        assert len(result["library"]) == 1
        entry = result["library"][0]
        assert entry["book_id"] == 100
        assert entry["title"] == "Dune"
        assert entry["your_rating"] == 4.5
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
