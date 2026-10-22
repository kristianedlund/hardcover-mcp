"""Integration tests for journal write tools."""

import json
import uuid

import pytest

from tests.integration._eventually import eventually

pytestmark = pytest.mark.integration


async def _get_book_id(slug: str) -> int:
    from hardcover_mcp.tools.books import handle_get_book

    result = await handle_get_book({"slug": slug})
    return json.loads(result[0].text)["id"]


class TestJournalEntryLifecycle:
    """Create a journal entry → verify in list → edit → delete → verify removed."""

    async def test_create_edit_delete_journal_entry(self):
        from hardcover_mcp.tools.journal import (
            handle_delete_journal_entry,
            handle_get_reading_journal,
            handle_set_journal_entry,
        )

        book_id = await _get_book_id("project-hail-mary")
        unique_note = f"_test_journal_{uuid.uuid4().hex[:8]}"
        entry_id: int | None = None

        try:
            add_result = await handle_set_journal_entry(
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

            async def notes() -> list[dict]:
                read_result = await handle_get_reading_journal(
                    {"book_id": book_id, "event": "note", "limit": 100}
                )
                return json.loads(read_result[0].text)

            async def find(target: int) -> list[dict]:
                return [e for e in await notes() if e["id"] == target]

            # Wait until it's readable: the edit below looks the entry up first.
            matching = await eventually(lambda: find(entry_id))
            assert len(matching) == 1
            assert matching[0]["entry"] == unique_note

            # Edit: change the text and privacy; the event must be preserved.
            edited_note = f"{unique_note}_edited"
            edit_result = await handle_set_journal_entry(
                {"id": entry_id, "entry": edited_note, "privacy": "private"}
            )
            edited = json.loads(edit_result[0].text)
            assert edited["id"] == entry_id
            assert edited["entry"] == edited_note
            assert edited["event"] == "note"
            assert edited["privacy_setting_id"] == 3

            # Delete and verify removal in the same block so cleanup is
            # guaranteed by the finally even if verification fails.
            await handle_delete_journal_entry({"id": entry_id})
            deleted_id = entry_id
            entry_id = None  # Prevent double-delete in finally

            async def gone() -> bool:
                return not await find(deleted_id)

            assert await eventually(gone)

        finally:
            if entry_id is not None:
                await handle_delete_journal_entry({"id": entry_id})
