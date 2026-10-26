"""Integration tests that hit the real Hardcover API.

Requires HARDCOVER_API_TOKEN in the environment (loaded from .env by conftest.py).
Skipped automatically when the token is absent.

Run locally:
    uv run python -m pytest tests/integration/ -v
"""

import json

import pytest

from hardcover_mcp.tools._validation import ToolError

pytestmark = pytest.mark.integration


# ── Read tools ──


class TestGetUserSelf:
    async def test_no_args_returns_authenticated_user(self):
        from hardcover_mcp.tools.user import handle_get_user

        result = await handle_get_user({})

        data = json.loads(result[0].text)
        assert "id" in data
        assert "username" in data
        assert isinstance(data["id"], int)


class TestSearchBooks:
    async def test_search_returns_results(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Project Hail Mary"})

        data = json.loads(result[0].text)
        assert data["total"] > 0
        assert len(data["books"]) > 0
        assert data["books"][0]["title"] is not None

    async def test_search_respects_per_page(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Sanderson", "per_page": 2})

        data = json.loads(result[0].text)
        assert len(data["books"]) <= 2


class TestGetBook:
    async def test_get_book_by_slug(self):
        from hardcover_mcp.tools.books import handle_get_book

        result = await handle_get_book({"slug": "project-hail-mary"})

        data = json.loads(result[0].text)
        assert data["title"] == "Project Hail Mary"
        assert data["id"] is not None

    async def test_get_book_by_id(self):
        from hardcover_mcp.tools.books import handle_get_book

        result = await handle_get_book({"slug": "project-hail-mary"})
        book_id = json.loads(result[0].text)["id"]

        result = await handle_get_book({"id": book_id})
        data = json.loads(result[0].text)
        assert data["title"] == "Project Hail Mary"

    async def test_authors_leave_out_narrator(self):
        from hardcover_mcp.tools.books import handle_get_book, handle_search_books

        # Educated (44186) lists narrator Julia Whelan alongside Tara Westover.
        book = json.loads((await handle_get_book({"id": 44186}))[0].text)
        assert book["authors"] == ["Tara Westover"]
        assert {"name": "Julia Whelan", "role": "Narrator"} in book["contributors"]

        search = json.loads((await handle_search_books({"query": "Educated: A Memoir"}))[0].text)
        hit = next(b for b in search["books"] if str(b["id"]) == "44186")
        assert hit["authors"] == ["Tara Westover"]

    async def test_edition_key_returns_that_edition(self):
        from hardcover_mcp.tools.books import handle_get_book

        book = json.loads((await handle_get_book({"slug": "project-hail-mary"}))[0].text)
        editions = json.loads(
            (await handle_get_book({"id": book["id"], "include_editions": True}))[0].text
        )["editions"]
        with_isbn = next(e for e in editions if e["isbn_13"])

        by_id = json.loads((await handle_get_book({"edition_id": with_isbn["id"]}))[0].text)
        by_isbn = json.loads((await handle_get_book({"isbn_13": with_isbn["isbn_13"]}))[0].text)

        assert by_id["id"] == by_isbn["id"] == with_isbn["id"]
        assert by_id["book"]["id"] == book["id"]

    async def test_include_characters(self):
        from hardcover_mcp.tools.books import handle_get_book

        result = await handle_get_book({"slug": "project-hail-mary", "include_characters": True})

        data = json.loads(result[0].text)
        assert isinstance(data["characters"], list)
        for character in data["characters"]:
            expected = {"id", "name", "slug", "biography", "spoiler", "only_mentioned"}
            assert expected <= character.keys()


class TestGetUserLibrary:
    async def test_date_range_and_owned_filters_run(self):
        # Both build their own queries; the date range was broken against the live API
        # (unsortable finished_at) without any test noticing.
        from hardcover_mcp.tools.library import handle_get_user_library

        for args in (
            {"start_date": "2000-01-01", "end_date": "2100-12-31", "limit": 5},
            {"owned": True, "limit": 5},
            {"owned": True, "start_date": "2000-01-01", "end_date": "2100-12-31", "limit": 5},
        ):
            data = json.loads((await handle_get_user_library(args))[0].text)
            assert isinstance(data["books"], list), args
            assert data["total"] >= data["returned"], args

    async def test_returns_library_entries(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({})

        data = json.loads(result[0].text)
        assert "books" in data
        assert "total" in data
        assert isinstance(data["books"], list)

    async def test_filter_by_status(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({"status": "Want to Read"})

        data = json.loads(result[0].text)
        assert "books" in data
        assert isinstance(data["books"], list)

    async def test_pagination(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({"limit": 2, "offset": 0})

        data = json.loads(result[0].text)
        assert data["returned"] <= 2

    async def test_rating_pages_do_not_overlap(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        args = {"sort": "rating", "order": "desc", "limit": 20}
        page1 = json.loads((await handle_get_user_library({**args, "offset": 0}))[0].text)
        page2 = json.loads((await handle_get_user_library({**args, "offset": 20}))[0].text)

        ids1 = {b["user_book_id"] for b in page1["books"]}
        ids2 = {b["user_book_id"] for b in page2["books"]}
        assert not ids1 & ids2

    async def test_rating_desc_puts_unrated_last(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({"sort": "rating", "order": "desc", "limit": 50})

        ratings = [b["rating"] for b in json.loads(result[0].text)["books"]]
        rated = [r is not None for r in ratings]
        assert rated == sorted(rated, reverse=True)


class TestGetAuthor:
    async def test_get_author_by_slug(self):
        from hardcover_mcp.tools.authors import handle_get_author

        result = await handle_get_author({"slug": "brandon-sanderson"})

        data = json.loads(result[0].text)
        assert data["name"] == "Brandon Sanderson"
        assert data["slug"] == "brandon-sanderson"
        assert isinstance(data["books"], list)
        assert len(data["books"]) > 0

    async def test_get_author_by_name(self):
        from hardcover_mcp.tools.authors import handle_get_author

        result = await handle_get_author({"name": "Andy Weir"})

        data = json.loads(result[0].text)
        assert data["name"] == "Andy Weir"
        assert isinstance(data["books"], list)

    async def test_get_author_respects_books_limit(self):
        from hardcover_mcp.tools.authors import handle_get_author

        result = await handle_get_author({"slug": "brandon-sanderson", "books_limit": 3})

        data = json.loads(result[0].text)
        assert len(data["books"]) <= 3

    async def test_unknown_author_returns_not_found(self):
        from hardcover_mcp.tools.authors import handle_get_author

        result = await handle_get_author({"slug": "zzz-does-not-exist-zzz"})

        assert "No author found" in result[0].text


class TestGetListOwn:
    async def test_returns_lists(self):
        from hardcover_mcp.tools.lists import handle_get_list

        result = await handle_get_list({})

        data = json.loads(result[0].text)
        assert isinstance(data["lists"], list)
        assert data["total"] >= data["returned"] == len(data["lists"])

    async def test_list_has_expected_fields(self):
        from hardcover_mcp.tools.lists import handle_get_list

        result = await handle_get_list({"limit": 1})

        data = json.loads(result[0].text)["lists"]
        if data:
            lst = data[0]
            assert "id" in lst
            assert "name" in lst


class TestGetUserBookLists:
    async def test_shows_a_list_the_book_is_on(self):
        from hardcover_mcp.tools.library import handle_get_user_book
        from hardcover_mcp.tools.lists import handle_get_list

        lists = json.loads((await handle_get_list({"limit": 50}))[0].text)["lists"]
        for summary in lists:
            if summary["slug"] == "owned" or not summary["books_count"]:
                continue
            detail = json.loads((await handle_get_list({"id": summary["id"]}))[0].text)
            for book in detail["books"][:3]:
                result = await handle_get_user_book({"book_id": book["book_id"]})
                if result[0].text == "Book not in your library.":
                    continue
                entry = json.loads(result[0].text)
                assert summary["id"] in [lst["id"] for lst in entry["lists"]]
                assert all(lst["name"] != "Owned" for lst in entry["lists"])
                return
        pytest.skip("no listed book from your library to check")


class TestGetSeries:
    async def test_get_series_by_slug(self):
        from hardcover_mcp.tools.series import handle_get_series

        result = await handle_get_series({"slug": "the-stormlight-archive"})

        data = json.loads(result[0].text)
        assert data["name"] == "The Stormlight Archive"
        assert data["slug"] == "the-stormlight-archive"
        assert len(data["books"]) > 0
        # Books are sorted by position; first position should be the lowest
        assert data["books"][0]["position"] is not None

    async def test_get_series_by_name(self):
        from hardcover_mcp.tools.series import handle_get_series

        result = await handle_get_series({"name": "Harry Potter"})

        data = json.loads(result[0].text)
        assert "Harry Potter" in data["name"]
        assert data["books_count"] > 0

    async def test_get_series_returns_error_without_args(self):
        from hardcover_mcp.tools.series import handle_get_series

        with pytest.raises(ToolError):
            await handle_get_series({})


class TestGetEdition:
    async def test_get_edition_by_isbn13(self):
        from hardcover_mcp.tools.editions import handle_get_edition

        result = await handle_get_edition({"isbn_13": "9780547928227"})

        data = json.loads(result[0].text)
        assert "id" in data
        assert data["isbn_13"] == "9780547928227"
        assert isinstance(data["book"], dict)
        assert data["book"]["id"] is not None
        assert "slug" in data["book"]
        assert "title" in data["book"]

    async def test_get_edition_returns_not_found_for_unknown_isbn(self):
        from hardcover_mcp.tools.editions import handle_get_edition

        result = await handle_get_edition({"isbn_13": "9799999999999"})

        assert "No edition found" in result[0].text

    async def test_get_edition_error_on_no_args(self):
        from hardcover_mcp.tools.editions import handle_get_edition

        with pytest.raises(ToolError):
            await handle_get_edition({})

    async def test_get_edition_error_on_multiple_args(self):
        from hardcover_mcp.tools.editions import handle_get_edition

        with pytest.raises(ToolError):
            await handle_get_edition({"isbn_13": "9780547928227", "asin": "B007978NPG"})


class TestSearchEntities:
    async def test_search_author_returns_results(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Brandon Sanderson", "query_type": "Author"})

        data = json.loads(result[0].text)
        assert data["total"] > 0
        assert len(data["authors"]) > 0
        assert data["authors"][0]["name"] is not None

    async def test_search_author_result_has_expected_fields(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Andy Weir", "query_type": "Author"})

        data = json.loads(result[0].text)
        assert data["total"] > 0
        author = data["authors"][0]
        assert "id" in author
        assert "name" in author
        assert "slug" in author

    async def test_search_series_returns_results(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Stormlight", "query_type": "Series"})

        data = json.loads(result[0].text)
        assert data["total"] > 0
        assert len(data["series"]) > 0
        assert data["series"][0]["name"] is not None

    async def test_search_series_result_has_expected_fields(self):
        from hardcover_mcp.tools.books import handle_search_books

        result = await handle_search_books({"query": "Mistborn", "query_type": "Series"})

        data = json.loads(result[0].text)
        assert data["total"] > 0
        series = data["series"][0]
        assert "id" in series
        assert "name" in series
        assert "slug" in series


class TestGetPublisher:
    async def test_lookup_by_name(self):
        from hardcover_mcp.tools.publishers import handle_get_publisher

        result = await handle_get_publisher({"name": "Tor Books"})

        data = json.loads(result[0].text)
        assert data["id"] == 185
        assert data["name"] == "Tor Books"
        assert data["editions_count"] > 0
        assert data["state"] == "active"

    async def test_lookup_by_slug(self):
        from hardcover_mcp.tools.publishers import handle_get_publisher

        result = await handle_get_publisher({"slug": "tor-books"})

        data = json.loads(result[0].text)
        assert data["name"] == "Tor Books"

    async def test_lookup_by_id(self):
        from hardcover_mcp.tools.publishers import handle_get_publisher

        result = await handle_get_publisher({"id": 185})

        data = json.loads(result[0].text)
        assert data["name"] == "Tor Books"
        assert len(data["editions"]) > 0

    async def test_editions_pagination(self):
        from hardcover_mcp.tools.publishers import handle_get_publisher

        result = await handle_get_publisher({"id": 185, "editions_limit": 5})

        data = json.loads(result[0].text)
        assert len(data["editions"]) <= 5

    async def test_not_found(self):
        from hardcover_mcp.tools.publishers import handle_get_publisher

        result = await handle_get_publisher({"name": "zzz_nonexistent_publisher_xyz"})

        assert "No publisher found" in result[0].text


class TestGetUserIncludeStats:
    async def test_returns_required_fields(self):
        from hardcover_mcp.tools.user import handle_get_user

        result = await handle_get_user({"include_stats": True})

        data = json.loads(result[0].text)["stats"]
        assert "total_books" in data
        assert "by_status" in data
        assert "average_rating" in data
        assert "books_read_this_year" in data
        assert "year" in data

    async def test_by_status_has_all_statuses(self):
        from hardcover_mcp.tools.user import handle_get_user

        result = await handle_get_user({"include_stats": True})

        data = json.loads(result[0].text)["stats"]
        by_status = data["by_status"]
        assert "want_to_read" in by_status
        assert "currently_reading" in by_status
        assert "read" in by_status
        assert "did_not_finish" in by_status
        assert "paused" in by_status
        assert "ignored" in by_status

    async def test_total_books_is_non_negative(self):
        from hardcover_mcp.tools.user import handle_get_user

        result = await handle_get_user({"include_stats": True})

        data = json.loads(result[0].text)["stats"]
        assert isinstance(data["total_books"], int)
        assert data["total_books"] >= 0

    async def test_year_filter_changes_books_read_count(self):
        from hardcover_mcp.tools.user import handle_get_user

        result_past = await handle_get_user({"include_stats": True, "stats_year": 1900})

        data = json.loads(result_past[0].text)["stats"]
        # No books were read in 1900 — count should be 0
        assert data["books_read_this_year"] == 0
        assert data["year"] == 1900


class TestGetUserFollowLists:
    async def test_following_and_followers_have_people(self):
        from hardcover_mcp.tools.user import handle_get_user

        result = await handle_get_user(
            {"include_following": True, "include_followers": True, "follow_limit": 5}
        )

        data = json.loads(result[0].text)
        for key in ("following", "followers"):
            assert isinstance(data[key], list)
            assert len(data[key]) <= 5
            for person in data[key]:
                assert {"id", "username", "name", "since"} <= person.keys()


class TestGetUserLibraryHasReview:
    async def test_returns_reviews_structure(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({"has_review": True})

        data = json.loads(result[0].text)
        assert "total" in data
        assert "returned" in data
        assert "offset" in data
        assert "books" in data
        assert isinstance(data["books"], list)
        assert data["offset"] == 0

    async def test_each_review_has_expected_fields(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({"has_review": True})

        data = json.loads(result[0].text)
        for review in data["books"]:
            assert "user_book_id" in review
            assert "book_id" in review
            assert "title" in review
            assert "slug" in review
            assert "authors" in review
            assert "rating" in review
            assert "review_raw" in review
            assert "review_has_spoilers" in review
            assert "reviewed_at" in review

    async def test_pagination(self):
        from hardcover_mcp.tools.library import handle_get_user_library

        result = await handle_get_user_library({"has_review": True, "limit": 1, "offset": 0})

        data = json.loads(result[0].text)
        assert data["returned"] <= 1


class TestGetReadingJournal:
    async def test_returns_list(self):
        from hardcover_mcp.tools.journal import handle_get_reading_journal

        result = await handle_get_reading_journal({})

        data = json.loads(result[0].text)
        assert isinstance(data["entries"], list)

    async def test_each_entry_has_expected_fields(self):
        from hardcover_mcp.tools.journal import handle_get_reading_journal

        result = await handle_get_reading_journal({"limit": 5})

        data = json.loads(result[0].text)["entries"]
        for entry in data:
            assert "id" in entry
            assert "event" in entry
            assert "action_at" in entry
            assert "book_id" in entry
            assert "book" in entry
            assert "title" in entry["book"]
            assert "authors" in entry["book"]

    async def test_limit_is_respected(self):
        from hardcover_mcp.tools.journal import handle_get_reading_journal

        result = await handle_get_reading_journal({"limit": 2})

        data = json.loads(result[0].text)["entries"]
        assert len(data) <= 2

    async def test_filter_by_event_type(self):
        from hardcover_mcp.tools.journal import handle_get_reading_journal

        result = await handle_get_reading_journal({"event": "status_read", "limit": 10})

        data = json.loads(result[0].text)["entries"]
        assert isinstance(data, list)
        for entry in data:
            assert entry["event"] == "status_read"
