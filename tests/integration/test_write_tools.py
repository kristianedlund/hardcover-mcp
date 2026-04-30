"""Integration tests for write tools — create, modify, then clean up.

Each test class follows a lifecycle pattern: create → verify → delete.
Tests are ordered within each class so the account is left in its original state.

Requires HARDCOVER_API_TOKEN in the environment (loaded from .env by conftest.py).
Skipped automatically when the token is absent.
"""

import json
import uuid

import pytest

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


class TestListLifecycle:
    """Create a list → update → add book → remove book → delete list."""

    async def test_full_lifecycle(self):
        from hardcover_mcp.tools.lists import (
            handle_add_book_to_list,
            handle_create_list,
            handle_delete_list,
            handle_remove_book_from_list,
            handle_update_list,
        )

        unique = uuid.uuid4().hex[:8]
        list_name = f"_test_integration_{unique}"

        # 1. Create
        result = await handle_create_list(
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
            # 2. Update
            updated_name = f"_test_integration_{unique}_updated"
            result = await handle_update_list(
                {
                    "id": list_id,
                    "name": updated_name,
                }
            )
            updated = json.loads(result[0].text)
            assert updated["name"] == updated_name

            # 3. Add book
            book_id = await _find_book_not_in_library()
            result = await handle_add_book_to_list(
                {
                    "list_id": list_id,
                    "book_id": book_id,
                }
            )
            list_book = json.loads(result[0].text)
            list_book_id = list_book["id"]
            assert list_book["book_id"] == book_id
            assert list_book["list_id"] == list_id

            # 4. Remove book
            result = await handle_remove_book_from_list(
                {
                    "id": list_book_id,
                }
            )
            removed = json.loads(result[0].text)
            assert removed["deleted"] is True

        finally:
            # 6. Delete list (cleanup always runs)
            result = await handle_delete_list({"id": list_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True


class TestUserBookLifecycle:
    """Add a book to library → verify → delete."""

    async def test_full_lifecycle(self):
        from hardcover_mcp.tools.library import (
            handle_delete_user_book,
            handle_get_user_book,
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
            # 2. Update rating
            result = await handle_set_user_book(
                {
                    "book_id": book_id,
                    "rating": 4.0,
                }
            )
            updated = json.loads(result[0].text)
            assert updated["rating"] == 4.0

            # 3. Verify via get
            result = await handle_get_user_book({"book_id": book_id})
            detail = json.loads(result[0].text)
            assert detail["book_id"] == book_id
            assert detail["rating"] == 4.0

        finally:
            # 4. Delete (cleanup always runs)
            result = await handle_delete_user_book({"user_book_id": user_book_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True


class TestUserBookReviewLifecycle:
    """Add a book with a review and private notes → verify → delete."""

    async def test_review_and_notes(self):
        from hardcover_mcp.tools.library import (
            handle_delete_user_book,
            handle_get_user_book,
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
            result = await handle_get_user_book({"book_id": book_id})
            detail = json.loads(result[0].text)
            assert detail["review_has_spoilers"] is False
            assert detail["reviewed_at"] == "2025-06-01"
            assert detail["private_notes"] == "The quote in chapter 12 is memorable."
            # review_html is rendered by the API from review_slate
            assert detail["review_html"] is not None

        finally:
            # 3. Delete (cleanup always runs)
            result = await handle_delete_user_book({"user_book_id": user_book_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True


class TestReadingProgress:
    """Add a book → log reading progress → update progress → clean up."""

    async def test_progress_tracking(self):
        from hardcover_mcp.tools.library import (
            handle_add_user_book_read,
            handle_delete_user_book,
            handle_delete_user_book_read,
            handle_set_user_book,
            handle_update_user_book_read,
        )

        book_id = await _find_book_not_in_library()

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
            result = await handle_add_user_book_read(
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

            # 3. Update progress further — also set progress_seconds for audiobook tracking
            result = await handle_update_user_book_read(
                {
                    "id": read_id,
                    "progress_pages": 150,
                    "progress_seconds": 3600,
                }
            )
            updated = json.loads(result[0].text)
            assert updated["progress_pages"] == 150
            assert updated["progress_seconds"] == 3600
            # started_at must be preserved after update
            assert updated["started_at"] == "2025-01-01"

            # 4. Clean up the read entry
            result = await handle_delete_user_book_read({"id": read_id})
            deleted_read = json.loads(result[0].text)
            assert deleted_read["deleted"] is True

        finally:
            # 5. Remove book from library (cleanup always runs)
            result = await handle_delete_user_book({"user_book_id": user_book_id})
            deleted = json.loads(result[0].text)
            assert deleted["deleted"] is True
