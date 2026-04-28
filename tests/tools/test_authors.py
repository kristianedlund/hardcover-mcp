"""Unit tests for tools.authors."""

from hardcover_mcp.tools.authors import _format_author


class TestFormatAuthor:
    def test_formats_full_author(self):
        raw = {
            "id": 1,
            "slug": "brandon-sanderson",
            "name": "Brandon Sanderson",
            "bio": "American fantasy author.",
            "books_count": 50,
            "users_count": 200000,
            "born_year": 1975,
            "death_year": None,
            "contributions": [
                {
                    "book": {
                        "id": 100,
                        "slug": "the-way-of-kings",
                        "title": "The Way of Kings",
                        "release_year": 2010,
                        "rating": 4.65,
                    }
                },
                {
                    "book": {
                        "id": 101,
                        "slug": "mistborn",
                        "title": "Mistborn",
                        "release_year": 2006,
                        "rating": 4.45,
                    }
                },
            ],
        }

        result = _format_author(raw)

        assert result["id"] == 1
        assert result["slug"] == "brandon-sanderson"
        assert result["name"] == "Brandon Sanderson"
        assert result["bio"] == "American fantasy author."
        assert result["books_count"] == 50
        assert result["users_count"] == 200000
        assert result["born_year"] == 1975
        assert result["death_year"] is None
        assert len(result["books"]) == 2
        assert result["books"][0]["title"] == "The Way of Kings"
        assert result["books"][0]["book_id"] == 100
        assert result["books"][1]["title"] == "Mistborn"

    def test_handles_no_contributions(self):
        raw = {
            "id": 2,
            "slug": "unknown-author",
            "name": "Unknown Author",
            "bio": None,
            "books_count": 0,
            "users_count": 0,
            "born_year": None,
            "death_year": None,
            "contributions": [],
        }

        result = _format_author(raw)

        assert result["books"] == []
        assert result["bio"] is None
        assert result["born_year"] is None

    def test_skips_contributions_with_null_book(self):
        raw = {
            "id": 3,
            "slug": "some-author",
            "name": "Some Author",
            "bio": None,
            "books_count": 1,
            "users_count": 10,
            "born_year": None,
            "death_year": None,
            "contributions": [
                {"book": None},
                {
                    "book": {
                        "id": 10,
                        "slug": "a-book",
                        "title": "A Book",
                        "release_year": 2020,
                        "rating": 3.5,
                    }
                },
            ],
        }

        result = _format_author(raw)

        assert len(result["books"]) == 1
        assert result["books"][0]["title"] == "A Book"

    def test_book_fields_do_not_include_users_count(self):
        raw = {
            "id": 4,
            "slug": "author",
            "name": "Author",
            "bio": None,
            "books_count": 1,
            "users_count": 5,
            "born_year": None,
            "death_year": None,
            "contributions": [
                {
                    "book": {
                        "id": 20,
                        "slug": "book",
                        "title": "Book",
                        "release_year": 2021,
                        "rating": 4.0,
                    }
                }
            ],
        }

        result = _format_author(raw)

        assert "users_count" not in result["books"][0]
