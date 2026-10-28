"""Unit tests for tools.series."""

from hardcover_mcp.tools.series import _format_series


class TestFormatSeries:
    def test_formats_full_series(self):
        raw = {
            "id": 42,
            "name": "The Stormlight Archive",
            "slug": "the-stormlight-archive",
            "description": "Epic fantasy series",
            "books_count": 10,
            "primary_books_count": 4,
            "is_completed": False,
            "author": {"name": "Brandon Sanderson", "slug": "brandon-sanderson"},
            "book_series": [
                {
                    "position": 1,
                    "book": {
                        "id": 100,
                        "slug": "the-way-of-kings",
                        "title": "The Way of Kings",
                        "release_year": 2010,
                        "rating": 4.65,
                        "users_count": 50000,
                    },
                },
                {
                    "position": 2,
                    "book": {
                        "id": 101,
                        "slug": "words-of-radiance",
                        "title": "Words of Radiance",
                        "release_year": 2014,
                        "rating": 4.76,
                        "users_count": 40000,
                    },
                },
            ],
        }

        result = _format_series(raw)

        assert result["id"] == 42
        assert result["name"] == "The Stormlight Archive"
        assert result["slug"] == "the-stormlight-archive"
        assert result["authors"] == ["Brandon Sanderson"]
        assert "author" not in result
        assert result["is_completed"] is False
        assert result["primary_books_count"] == 4
        assert len(result["books"]) == 2
        assert result["books"][0]["position"] == 1
        assert result["books"][0]["title"] == "The Way of Kings"
        assert result["books"][1]["position"] == 2

    def test_handles_missing_author(self):
        raw = {
            "id": 1,
            "name": "Test Series",
            "slug": "test-series",
            "description": None,
            "books_count": 0,
            "primary_books_count": None,
            "is_completed": None,
            "author": None,
            "book_series": [],
        }

        result = _format_series(raw)

        assert result["authors"] == []
        assert result["books"] == []

    def test_excludes_users_count_from_output(self):
        raw = {
            "id": 1,
            "name": "S",
            "slug": "s",
            "books_count": 1,
            "author": None,
            "book_series": [
                {
                    "position": 1,
                    "book": {
                        "id": 10,
                        "slug": "b",
                        "title": "B",
                        "release_year": 2020,
                        "rating": 4.0,
                        "users_count": 999,
                    },
                },
            ],
        }

        result = _format_series(raw)

        assert "users_count" not in result["books"][0]


class TestSeriesPositions:
    def test_unnumbered_books_are_all_kept_and_positions_once(self):
        from hardcover_mcp.tools.series import _format_series

        def entry(position, book_id):
            return {"position": position, "book": {"id": book_id, "slug": "s", "title": "T"}}

        raw = {
            "id": 1,
            "name": "S",
            "slug": "s",
            "books_count": 5,
            "book_series": [
                entry(1, 10),
                entry(1, 11),
                entry(2, 12),
                entry(None, 13),
                entry(None, 14),
            ],
        }

        assert [b["book_id"] for b in _format_series(raw)["books"]] == [10, 12, 13, 14]
