"""Integration tests for write tools — create, modify, then clean up.

Each test class follows a lifecycle pattern: create → verify → delete.
Tests are ordered within each class so the account is left in its original state.

Requires HARDCOVER_API_TOKEN in the environment (loaded from .env by conftest.py).
Skipped automatically when the token is absent.
"""

import json
import uuid
from collections.abc import Callable

import pytest

from tests.integration._eventually import eventually

pytestmark = pytest.mark.integration

# Candidate books for the user-book lifecycle test. The test picks the first
# one that is NOT already in the user's library, so we never add/remove a
# book the user actually tracks.
_CANDIDATE_BOOK_SLUGS = [
    "surely-youre-joking-mr-feynman",
    "the-code-book",
    "a-short-history-of-nearly-everything-1",
]


async def _get_book_id(slug: str) -> int:
    from hardcover_mcp.tools.books import handle_get_book

    result = await handle_get_book({"slug": slug})
    return json.loads(result[0].text)["id"]


async def _find_book_not_in_library() -> int:
    """Return the book_id of the first candidate that is NOT in the user's library."""
    from hardcover_mcp.tools.library import handle_get_user_book

    for slug in _CANDIDATE_BOOK_SLUGS:
        book_id = await _get_book_id(slug)
        result = await handle_get_user_book({"book_id": book_id})
        if "not in your library" in result[0].text.lower():
            return book_id
    pytest.skip("All candidate books already in library — cannot test without side effects")


async def _library_entry(book_id: int, check: Callable[[dict], bool] = bool) -> dict | None:
    """``get_user_book`` for ``book_id`` once it passes ``check``, or None if it never does.

    Waits because reads lag writes, and ``set_user_book`` merges with what it reads: a
    follow-up write before the previous one is readable would write the old values back.
    """
    from hardcover_mcp.tools.library import handle_get_user_book

    async def read() -> dict | None:
        result = await handle_get_user_book({"book_id": book_id})
        if "not in your library" in result[0].text.lower():
            return None
        detail = json.loads(result[0].text)
        return detail if check(detail) else None

    return await eventually(read)


class TestListLifecycle:
    """Create a list → update → add book (twice) → remove book (twice) → delete list."""

    async def test_full_lifecycle(self):
        from hardcover_mcp.tools.lists import (
            handle_delete_list,
            handle_get_list,
            handle_set_list,
            handle_set_list_book,
        )

        unique = uuid.uuid4().hex[:8]
        list_name = f"_test_integration_{unique}"

        # 1. Create (no id)
        result = await handle_set_list(
            {
                "name": list_name,
                "description": "Temporary test list",
                "privacy": "private",
            }
        )
        created = json.loads(result[0].text)
        list_id = created["id"]
        assert created["name"] == list_name
        assert created["privacy"] == "private"

        try:
            # 2. Update (with id)
            updated_name = f"_test_integration_{unique}_updated"
            result = await handle_set_list({"id": list_id, "name": updated_name})
            updated = json.loads(result[0].text)
            assert updated["name"] == updated_name

            # 3. Add book, then repeat: second call is a no-op
            book_id = await _find_book_not_in_library()
            entry = {"list_id": list_id, "book_id": book_id}

            async def books_on_list() -> list[int]:
                listed = json.loads((await handle_get_list({"id": list_id}))[0].text)
                return [b["book_id"] for b in listed["books"]]

            async def listed_is(expected: list[int]) -> bool:
                return await books_on_list() == expected

            added = json.loads((await handle_set_list_book({**entry, "on_list": True}))[0].text)
            assert added["changed"] is True
            assert added["list_book_id"] is not None
            # Repeat only once the add is readable, or a stale lookup inserts it twice.
            assert await eventually(lambda: listed_is([book_id]))
            again = json.loads((await handle_set_list_book({**entry, "on_list": True}))[0].text)
            assert again["changed"] is False
            assert again["list_book_id"] == added["list_book_id"]

            # 4. Remove book, then repeat: second call is a no-op
            removed = json.loads((await handle_set_list_book({**entry, "on_list": False}))[0].text)
            assert removed["changed"] is True
            assert await eventually(lambda: listed_is([]))
            again = json.loads((await handle_set_list_book({**entry, "on_list": False}))[0].text)
            assert again["changed"] is False

        finally:
            # 5. Delete list (cleanup always runs)
            result = await handle_delete_list({"id": list_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True


class TestListBookOnSeveralLists:
    """Create two lists → add a book to both in one call (twice) → remove from both → delete."""

    async def test_add_and_remove_on_two_lists(self):
        from hardcover_mcp.tools.lists import (
            handle_delete_list,
            handle_get_list,
            handle_set_list,
            handle_set_list_book,
        )

        async def on_every_list(book_id: int, expected: bool) -> bool:
            for list_id in list_ids:
                listed = json.loads((await handle_get_list({"id": list_id}))[0].text)
                if (book_id in [b["book_id"] for b in listed["books"]]) != expected:
                    return False
            return True

        unique = uuid.uuid4().hex[:8]
        list_ids = []
        try:
            for n in (1, 2):
                result = await handle_set_list(
                    {"name": f"_test_integration_{unique}_{n}", "privacy": "private"}
                )
                list_ids.append(json.loads(result[0].text)["id"])

            book_id = await _find_book_not_in_library()
            call = {"list_ids": list_ids, "book_id": book_id}

            added = json.loads((await handle_set_list_book({**call, "on_list": True}))[0].text)
            assert [r["list_id"] for r in added["results"]] == list_ids
            assert all(r["changed"] and r["list_book_id"] for r in added["results"])

            assert await eventually(lambda: on_every_list(book_id, True))
            again = json.loads((await handle_set_list_book({**call, "on_list": True}))[0].text)
            assert not any(r["changed"] for r in again["results"])

            removed = json.loads((await handle_set_list_book({**call, "on_list": False}))[0].text)
            assert all(r["changed"] for r in removed["results"])
        finally:
            for list_id in list_ids:
                await handle_delete_list({"id": list_id})


class TestUserBookLifecycle:
    """Add a book to library → verify → delete."""

    async def test_full_lifecycle(self):
        from hardcover_mcp.tools.library import (
            handle_delete_user_book,
            handle_set_user_book,
        )

        book_id = await _find_book_not_in_library()

        # 1. Add to library
        result = await handle_set_user_book(
            {
                "book_id": book_id,
                "status": "Want to Read",
            }
        )
        created = json.loads(result[0].text)
        user_book_id = created["user_book_id"]
        assert created["status"] == "Want to Read"

        try:
            assert await _library_entry(book_id)

            # 2. Update status to Read and set rating
            result = await handle_set_user_book(
                {
                    "book_id": book_id,
                    "status": "Read",
                    "rating": 4.0,
                }
            )
            updated = json.loads(result[0].text)
            assert updated["user_rating"] == 4.0
            assert updated["status"] == "Read"

            # 3. Verify via get
            detail = await _library_entry(book_id, lambda d: d["user_rating"] == 4.0)
            assert detail is not None
            assert detail["book_id"] == book_id

        finally:
            # 4. Delete (cleanup always runs)
            result = await handle_delete_user_book({"user_book_id": user_book_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True


class TestUserBookReviewLifecycle:
    """Add a book with a review and notes → verify → status-only update keeps them → delete."""

    async def test_review_and_notes(self):
        from hardcover_mcp.tools.library import (
            handle_delete_user_book,
            handle_set_user_book,
        )

        book_id = await _find_book_not_in_library()

        # 1. Add to library with a review and private note
        result = await handle_set_user_book(
            {
                "book_id": book_id,
                "status": "Read",
                "rating": 4.5,
                "review_raw": "A fantastic read.\n\nHighly recommended.",
                "review_has_spoilers": False,
                "reviewed_at": "2025-06-01",
                "private_notes": "The quote in chapter 12 is memorable.",
            }
        )
        created = json.loads(result[0].text)
        user_book_id = created["user_book_id"]
        assert created["status"] == "Read"

        try:
            # 2. Read back and verify review fields
            detail = await _library_entry(book_id, lambda d: d["private_notes"] is not None)
            assert detail is not None
            assert detail["review_has_spoilers"] is False
            assert detail["reviewed_at"].startswith("2025-06-01")
            assert detail["private_notes"] == "The quote in chapter 12 is memorable."
            # review_raw is the plain text stored by the API
            assert detail["review_raw"] is not None
            original_review = detail["review_raw"]

            # 3. A status/rating-only update omits review fields (so it needs no
            #    write:reviews scope); the API must leave the review untouched.
            result = await handle_set_user_book(
                {"book_id": book_id, "status": "Currently Reading", "rating": 3.5}
            )
            assert json.loads(result[0].text)["status"] == "Currently Reading"
            detail = await _library_entry(book_id, lambda d: d["status"] == "Currently Reading")
            assert detail is not None
            assert detail["review_raw"] == original_review
            assert detail["review_has_spoilers"] is False
            assert detail["reviewed_at"].startswith("2025-06-01")
            assert detail["private_notes"] == "The quote in chapter 12 is memorable."

        finally:
            # 4. Delete (cleanup always runs)
            result = await handle_delete_user_book({"user_book_id": user_book_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True


async def _find_edition_for_book_not_in_library() -> tuple[int, int]:
    """Return (book_id, edition_id) for a well-known book not in the test user's library."""
    from hardcover_mcp.tools.books import handle_get_book
    from hardcover_mcp.tools.library import handle_get_user_book

    # Candidate ISBNs for common books — use the first whose book is not in library
    candidate_isbns = [
        "9780393316049",  # Surely You're Joking, Mr. Feynman! (W. W. Norton paperback)
        "9780385495325",  # The Code Book (Simon Singh)
        "9780385333481",  # A Short History of Nearly Everything (Anchor paperback)
    ]
    for isbn_13 in candidate_isbns:
        edition_result = await handle_get_book({"isbn_13": isbn_13})
        edition_data = json.loads(edition_result[0].text)
        if "id" not in edition_data or not edition_data.get("book"):
            continue
        edition_id = edition_data["id"]
        book_id = edition_data["book"]["id"]
        library_result = await handle_get_user_book({"book_id": book_id})
        if "not in your library" in library_result[0].text.lower():
            return book_id, edition_id

    pytest.skip("No suitable book+edition found for edition selection test")


class TestEditionSelection:
    """Set an edition on a library entry → verify → delete."""

    async def test_set_and_read_edition_id(self):
        from hardcover_mcp.tools.library import (
            handle_delete_user_book,
            handle_set_user_book,
        )

        book_id, edition_id = await _find_edition_for_book_not_in_library()

        # 1. Add book to library with a specific edition
        result = await handle_set_user_book(
            {
                "book_id": book_id,
                "status": "Want to Read",
                "edition_id": edition_id,
            }
        )
        created = json.loads(result[0].text)
        user_book_id = created["user_book_id"]
        assert created["edition_id"] == edition_id

        try:
            # 2. Verify edition info is returned by get_user_book
            detail = await _library_entry(
                book_id, lambda d: (d["edition"] or {}).get("id") == edition_id
            )
            assert detail is not None

        finally:
            # 3. Clean up
            result = await handle_delete_user_book({"user_book_id": user_book_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True


class TestReadingProgress:
    """Add a book → log reading progress → update progress → clean up."""

    async def test_progress_tracking(self):
        from hardcover_mcp.tools.library import (
            handle_delete_user_book,
            handle_delete_user_book_read,
            handle_get_user_book,
            handle_set_user_book,
            handle_set_user_book_read,
        )

        book_id = await _find_book_not_in_library()

        async def read_started(read_id: int, started_at: str) -> bool:
            detail = json.loads((await handle_get_user_book({"book_id": book_id}))[0].text)
            return any(
                r["id"] == read_id and r["started_at"] == started_at for r in detail["reads"]
            )

        # 1. Add to library as currently reading
        result = await handle_set_user_book(
            {
                "book_id": book_id,
                "status": "Currently Reading",
            }
        )
        created = json.loads(result[0].text)
        user_book_id = created["user_book_id"]
        assert created["status"] == "Currently Reading"

        try:
            # 2. Log initial progress (page count)
            result = await handle_set_user_book_read(
                {
                    "user_book_id": user_book_id,
                    "started_at": "2025-01-01",
                    "progress_pages": 50,
                }
            )
            read_entry = json.loads(result[0].text)
            read_id = read_entry["id"]
            assert read_entry["progress_pages"] == 50
            assert read_entry["started_at"] == "2025-01-01"
            # The update merges with the stored read, so it must see the new start date.
            assert await eventually(lambda: read_started(read_id, "2025-01-01"))

            # 3. Update progress further
            result = await handle_set_user_book_read(
                {
                    "id": read_id,
                    "progress_pages": 150,
                }
            )
            updated = json.loads(result[0].text)
            assert updated["progress_pages"] == 150
            # started_at must be preserved after update
            assert updated["started_at"] == "2025-01-01"

            # 4. Test audiobook progress_seconds (requires edition_id)
            result = await handle_set_user_book_read(
                {
                    "id": read_id,
                    "progress_seconds": 3600,
                    "edition_id": read_entry.get("edition_id"),
                }
            )
            updated = json.loads(result[0].text)
            # progress_seconds only persists when edition_id points to an audiobook;
            # for non-audiobook editions the API may return None — just verify no error
            assert "Error" not in result[0].text

            # 4. Clean up the read entry
            result = await handle_delete_user_book_read({"id": read_id})
            deleted_read = json.loads(result[0].text)
            assert deleted_read["deleted"] is True

        finally:
            # 5. Remove book from library (cleanup always runs)
            result = await handle_delete_user_book({"user_book_id": user_book_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True


class TestPrivacyControls:
    """Add a book → set privacy → verify via get_user_book → delete."""

    async def test_set_and_read_privacy(self):
        from hardcover_mcp.tools.library import (
            handle_delete_user_book,
            handle_set_user_book,
        )

        book_id = await _find_book_not_in_library()

        # 1. Add to library as Private
        result = await handle_set_user_book(
            {
                "book_id": book_id,
                "status": "Want to Read",
                "privacy": "Private",
            }
        )
        created = json.loads(result[0].text)
        user_book_id = created["user_book_id"]
        assert created["privacy"] == "private"

        try:
            # 2. Verify privacy is returned by get_user_book
            assert await _library_entry(book_id, lambda d: d["privacy"] == "private")

            # 3. Update to Public — the privacy must change
            result = await handle_set_user_book(
                {
                    "book_id": book_id,
                    "privacy": "Public",
                }
            )
            updated = json.loads(result[0].text)
            assert updated["privacy"] == "public"
            assert await _library_entry(book_id, lambda d: d["privacy"] == "public")

            # 4. Update without specifying privacy — should be preserved
            result = await handle_set_user_book(
                {
                    "book_id": book_id,
                    "status": "Want to Read",
                }
            )
            preserved = json.loads(result[0].text)
            assert preserved["privacy"] == "public"

        finally:
            # 5. Clean up
            result = await handle_delete_user_book({"user_book_id": user_book_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True


class TestOwnedBooksLifecycle:
    """set_user_book(owned=true) → verify get_user_library(owned=true) → no-op repeat → restore."""

    async def test_full_lifecycle(self):
        from hardcover_mcp.tools.library import (
            handle_get_user_book,
            handle_get_user_library,
            handle_set_user_book,
        )

        lib_result = await handle_get_user_library({"status": "Read", "limit": 1})
        lib_data = json.loads(lib_result[0].text)
        assert lib_data["returned"] >= 1, "Need at least one 'Read' book for this test"

        book_id = lib_data["books"][0]["book_id"]

        # Get user_book detail to find the edition_id
        detail_result = await handle_get_user_book({"book_id": book_id})
        detail = json.loads(detail_result[0].text)
        edition = detail.get("edition")
        if edition is None:
            pytest.skip("Test book has no edition set — cannot test edition_owned")
        edition_id = edition["id"]

        # Remember initial owned state so we can restore it
        async def owned_book_ids() -> set[int]:
            result = await handle_get_user_library({"owned": True, "limit": 100})
            return {b["book_id"] for b in json.loads(result[0].text)["books"]}

        initially_owned = book_id in await owned_book_ids()

        try:
            # 1. Mark as owned
            result = await handle_set_user_book(
                {"book_id": book_id, "edition_id": edition_id, "owned": True}
            )
            output = json.loads(result[0].text)
            assert output["edition_id"] == edition_id
            assert output["owned"] is True

            # 2. Verify get_user_library(owned=true) returns it (before repeating the call)
            async def owned_now() -> bool:
                return book_id in await owned_book_ids()

            assert await eventually(owned_now)

            # 3. Calling again with owned=True should be a no-op
            result2 = await handle_set_user_book({"book_id": book_id, "owned": True})
            output2 = json.loads(result2[0].text)
            assert output2["owned_changed"] is False

            # 4. owned=False really removes ownership (it deletes the Owned-list row)
            if not initially_owned:
                result3 = await handle_set_user_book(
                    {"book_id": book_id, "edition_id": edition_id, "owned": False}
                )
                assert json.loads(result3[0].text)["owned_changed"] is True

                async def not_owned() -> bool:
                    return book_id not in await owned_book_ids()

                assert await eventually(not_owned)

        finally:
            # Restore original state
            if not initially_owned:
                await handle_set_user_book(
                    {"book_id": book_id, "edition_id": edition_id, "owned": False}
                )
