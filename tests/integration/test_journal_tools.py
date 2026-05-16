"""Integration tests for journal write tools."""

import json
import uuid

import pytest

pytestmark = pytest.mark.integration


async def _get_book_id(slug: str) -> int:
    from hardcover_mcp.tools.books import handle_get_book

    result = await handle_get_book({"slug": slug})
    return json.loads(result[0].text)["id"]


class TestJournalEntryLifecycle:
    """Create a journal entry → verify in list → delete → verify removed."""

    async def test_add_verify_delete_journal_entry(self):
        from hardcover_mcp.tools.journal import (
            handle_add_journal_entry,
            handle_delete_journal_entry,
            handle_get_reading_journal,
        )

        book_id = await _get_book_id("project-hail-mary")
        unique_note = f"_test_journal_{uuid.uuid4().hex[:8]}"
        entry_id: int | None = None

        try:
            add_result = await handle_add_journal_entry(
                {
                    "book_id": book_id,
                    "entry": unique_note,
                    "event": "note",
                }
            )
            created = json.loads(add_result[0].text)
            entry_id = created["id"]
            assert created["book_id"] == book_id
            assert created["event"] == "note"
            assert created["entry"] == unique_note

            read_result = await handle_get_reading_journal(
                {
                    "book_id": book_id,
                    "event": "note",
                    "limit": 100,
                }
            )
            entries = json.loads(read_result[0].text)
            assert any(entry["id"] == entry_id for entry in entries)

            # Delete and verify removal in the same block so cleanup is
            # guaranteed by the finally even if verification fails.
            await handle_delete_journal_entry({"id": entry_id})
            deleted_id = entry_id
            entry_id = None  # Prevent double-delete in finally

            verify_result = await handle_get_reading_journal(
                {
                    "book_id": book_id,
                    "event": "note",
                    "limit": 100,
                }
            )
            entries_after = json.loads(verify_result[0].text)
            assert all(e["id"] != deleted_id for e in entries_after)

        finally:
            if entry_id is not None:
                await handle_delete_journal_entry({"id": entry_id})
