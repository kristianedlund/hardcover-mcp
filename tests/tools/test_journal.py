"""Tests for tools/journal.py — formatting, reading, and writing journal entries."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.journal import (
    _format_journal_entry,
    handle_delete_journal_entry,
    handle_get_reading_journal,
    handle_set_journal_entry,
)

# ── Fixture helpers ──

_RAW_ENTRY = {
    "id": 101,
    "book_id": 42,
    "edition_id": 7,
    "event": "note",
    "entry": "Really liked the ending.",
    "action_at": "2025-03-15T10:00:00+00:00",
    "metadata": None,
    "privacy_setting_id": 1,
    "book": {
        "title": "Project Hail Mary",
        "slug": "project-hail-mary",
        "contributions": [{"author": {"name": "Andy Weir"}}],
    },
}

_MOCK_RESPONSE = {"data": {"reading_journals": [_RAW_ENTRY]}}
_EMPTY_RESPONSE = {"data": {"reading_journals": []}}
_INSERT_RESPONSE = {"data": {"insert_reading_journal": {"reading_journal": _RAW_ENTRY}}}


class TestFormatJournalEntry:
    def test_flattens_contributions_to_authors(self):
        result = _format_journal_entry(_RAW_ENTRY)

        assert result["book"]["authors"] == ["Andy Weir"]

    def test_preserves_top_level_fields(self):
        result = _format_journal_entry(_RAW_ENTRY)

        assert result["id"] == 101
        assert result["book_id"] == 42
        assert result["edition_id"] == 7
        assert result["event"] == "note"
        assert result["entry"] == "Really liked the ending."
        assert result["action_at"] == "2025-03-15T10:00:00+00:00"
        assert result["metadata"] is None
        assert result["privacy"] == "public"
        assert "privacy_setting_id" not in result

    def test_includes_book_title_and_slug(self):
        result = _format_journal_entry(_RAW_ENTRY)

        assert result["book"]["title"] == "Project Hail Mary"
        assert result["book"]["slug"] == "project-hail-mary"

    def test_handles_missing_book(self):
        raw = {**_RAW_ENTRY, "book": None}
        result = _format_journal_entry(raw)

        assert result["book"]["title"] is None
        assert result["book"]["slug"] is None
        assert result["book"]["authors"] == []

    def test_handles_empty_contributions(self):
        raw = {
            **_RAW_ENTRY,
            "book": {**_RAW_ENTRY["book"], "contributions": []},
        }
        result = _format_journal_entry(raw)

        assert result["book"]["authors"] == []

    def test_handles_multiple_authors(self):
        raw = {
            **_RAW_ENTRY,
            "book": {
                **_RAW_ENTRY["book"],
                "contributions": [
                    {"author": {"name": "Author A"}},
                    {"author": {"name": "Author B"}},
                ],
            },
        }
        result = _format_journal_entry(raw)

        assert result["book"]["authors"] == ["Author A", "Author B"]

    def test_handles_none_entry_and_metadata(self):
        raw = {**_RAW_ENTRY, "entry": None, "metadata": {"page": 150}}
        result = _format_journal_entry(raw)

        assert result["entry"] is None
        assert result["metadata"] == {"page": 150}

    def test_handles_none_edition_id(self):
        raw = {**_RAW_ENTRY, "edition_id": None}
        result = _format_journal_entry(raw)

        assert result["edition_id"] is None


class TestHandleGetReadingJournal:
    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_returns_formatted_entries(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _MOCK_RESPONSE

        result = await handle_get_reading_journal({"offset": 5})
        data = json.loads(result[0].text)

        assert data["returned"] == 1
        assert data["offset"] == 5
        assert "total" not in data
        assert data["entries"][0]["event"] == "note"
        assert data["entries"][0]["book"]["authors"] == ["Andy Weir"]

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_returns_empty_list_when_no_entries(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _EMPTY_RESPONSE

        result = await handle_get_reading_journal({})
        data = json.loads(result[0].text)

        assert data == {"returned": 0, "offset": 0, "entries": []}

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_default_limit_and_offset(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal({})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["limit"] == 25
        assert call_vars["offset"] == 0

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_custom_limit_and_offset(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal({"limit": 10, "offset": 5})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["limit"] == 10
        assert call_vars["offset"] == 5

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_limit_capped_at_100(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal({"limit": 999})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["limit"] == 100

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_where_includes_user_id(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 99}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal({})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["where"]["user_id"] == {"_eq": 99}

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_book_id_filter_added_to_where(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal({"book_id": 42})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["where"]["book_id"] == {"_eq": 42}

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_no_book_id_filter_when_not_provided(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal({})

        call_vars = mock_execute.call_args[0][1]
        assert "book_id" not in call_vars["where"]

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_event_filter_added_to_where(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal({"event": "note"})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["where"]["event"] == {"_eq": "note"}

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_no_event_filter_when_not_provided(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal({})

        call_vars = mock_execute.call_args[0][1]
        assert "event" not in call_vars["where"]

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_all_filters_combined(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 5}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal(
            {"book_id": 42, "event": "quote", "limit": 5, "offset": 2}
        )

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["where"]["user_id"] == {"_eq": 5}
        assert call_vars["where"]["book_id"] == {"_eq": 42}
        assert call_vars["where"]["event"] == {"_eq": "quote"}
        assert call_vars["limit"] == 5
        assert call_vars["offset"] == 2

    async def test_non_numeric_book_id_raises_value_error(self):
        with pytest.raises(ToolError, match="'book_id' must be an integer"):
            await handle_get_reading_journal({"book_id": "not-a-number"})

    async def test_non_numeric_limit_raises_value_error(self):
        with pytest.raises(ToolError, match="'limit' must be an integer"):
            await handle_get_reading_journal({"limit": "bad"})

    async def test_non_numeric_offset_raises_value_error(self):
        with pytest.raises(ToolError, match="'offset' must be an integer"):
            await handle_get_reading_journal({"offset": "bad"})

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_string_book_id_is_coerced_to_int(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _EMPTY_RESPONSE

        await handle_get_reading_journal({"book_id": "42"})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["where"]["book_id"] == {"_eq": 42}


class TestHandleSetJournalEntryCreate:
    @pytest.mark.parametrize(
        ("privacy", "expected"), [("followers", 2), ("Private", 3), (None, 1)]
    )
    async def test_privacy_reaches_the_mutation(self, privacy, expected):
        mock_exec = AsyncMock(return_value=_INSERT_RESPONSE)
        arguments = {"book_id": 42, "entry": "x", "event": "note"}
        if privacy is not None:
            arguments["privacy"] = privacy
        with (
            patch(
                "hardcover_mcp.tools.journal.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch("hardcover_mcp.tools.journal.execute", new=mock_exec),
        ):
            await handle_set_journal_entry(arguments)

        assert mock_exec.call_args[0][1]["object"]["privacy_setting_id"] == expected

    async def test_invalid_privacy_errors_before_api_calls(self):
        mock_exec = AsyncMock()
        with (
            patch("hardcover_mcp.tools.journal.execute", new=mock_exec),
            pytest.raises(ToolError, match="'privacy' must be"),
        ):
            await handle_set_journal_entry(
                {"book_id": 42, "entry": "x", "event": "note", "privacy": "friends"}
            )
        mock_exec.assert_not_awaited()

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_returns_created_entry(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = _INSERT_RESPONSE

        result = await handle_set_journal_entry(
            {
                "book_id": "42",
                "entry": "Important note",
                "event": "NOTE",
                "edition_id": "7",
                "privacy": "3",
            }
        )
        data = json.loads(result[0].text)

        assert data["id"] == 101
        assert data["book_id"] == 42
        assert data["edition_id"] == 7
        assert data["event"] == "note"
        assert data["entry"] == "Really liked the ending."
        assert data["privacy"] == "public"

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["object"] == {
            "book_id": 42,
            "entry": "Important note",
            "event": "note",
            "edition_id": 7,
            "privacy_setting_id": 3,
            "tags": [],
        }

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_missing_book_id_returns_error_before_api_calls(self, mock_execute, mock_user):
        with pytest.raises(ToolError) as exc:
            await handle_set_journal_entry({"entry": "x", "event": "note"})

        assert str(exc.value) == "'book_id' is required when creating."
        mock_user.assert_not_awaited()
        mock_execute.assert_not_awaited()

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_invalid_event_returns_error_before_api_calls(self, mock_execute, mock_user):
        with pytest.raises(ToolError) as exc:
            await handle_set_journal_entry({"book_id": 1, "entry": "x", "event": "rating"})

        assert str(exc.value) == "'event' must be one of: note, quote."
        mock_user.assert_not_awaited()
        mock_execute.assert_not_awaited()

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_invalid_book_id_returns_error_before_api_calls(self, mock_execute, mock_user):
        with pytest.raises(ToolError) as exc:
            await handle_set_journal_entry({"book_id": "bad", "entry": "x", "event": "note"})

        assert "'book_id' must be an integer" in str(exc.value)
        mock_user.assert_not_awaited()
        mock_execute.assert_not_awaited()


def _own_entry(event: str = "note") -> dict:
    return {
        "data": {
            "reading_journals": [
                {
                    "id": 101,
                    "book_id": 42,
                    "edition_id": None,
                    "event": event,
                    "entry": "Old text",
                    "privacy_setting_id": 3,
                }
            ]
        }
    }


class TestHandleSetJournalEntryEdit:
    async def _run(self, arguments: dict, *responses: dict) -> tuple[str, AsyncMock]:
        mock_exec = AsyncMock(side_effect=list(responses))
        self.mock_exec = mock_exec
        with (
            patch(
                "hardcover_mcp.tools.journal.get_current_user",
                new=AsyncMock(return_value={"id": 1}),
            ),
            patch("hardcover_mcp.tools.journal.execute", new=mock_exec),
        ):
            result = await handle_set_journal_entry(arguments)
        return result[0].text, mock_exec

    async def test_edits_text_and_preserves_other_fields(self):
        updated = {
            "data": {
                "update_reading_journal": {
                    "errors": None,
                    "reading_journal": {"id": 101, "entry": "New text", "event": "note"},
                }
            }
        }
        text, mock_exec = await self._run(
            {"id": 101, "entry": " New text "}, _own_entry(), updated
        )

        assert json.loads(text)["entry"] == "New text"
        assert mock_exec.call_args_list[0][0][1] == {"id": 101, "user_id": 1}
        assert mock_exec.call_args_list[1][0][1] == {
            "id": 101,
            "object": {"entry": "New text", "event": "note", "privacy_setting_id": 3},
        }

    async def test_privacy_alone_is_a_change(self):
        updated = {"data": {"update_reading_journal": {"errors": None, "reading_journal": {}}}}
        _, mock_exec = await self._run({"id": 101, "privacy": "public"}, _own_entry(), updated)

        assert mock_exec.call_args_list[1][0][1]["object"]["privacy_setting_id"] == 1

    async def test_requires_a_field_to_change(self):
        with pytest.raises(ToolError) as exc:
            await self._run({"id": 101})

        assert "at least one" in str(exc.value)
        self.mock_exec.assert_not_awaited()

    async def test_rejects_entries_that_are_not_yours(self):
        with pytest.raises(ToolError) as exc:
            await self._run({"id": 101, "entry": "x"}, {"data": {"reading_journals": []}})

        assert "no journal entry of yours" in str(exc.value)

    async def test_rejects_non_note_events(self):
        with pytest.raises(ToolError) as exc:
            await self._run({"id": 101, "entry": "x"}, _own_entry(event="status_read"))

        assert "only note and quote" in str(exc.value)
        assert self.mock_exec.call_count == 1

    async def test_reports_api_errors(self):
        failed = {
            "data": {"update_reading_journal": {"errors": ["nope"], "reading_journal": None}}
        }
        with pytest.raises(ToolError) as exc:
            await self._run({"id": 101, "privacy": "public"}, _own_entry(), failed)

        assert str(exc.value) == "nope"


class TestHandleDeleteJournalEntry:
    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_deletes_entry(self, mock_execute, mock_user):
        mock_user.return_value = {"id": 1}
        mock_execute.side_effect = [
            {"data": {"reading_journals": [{"id": 123}]}},
            {"data": {"delete_reading_journal": {"__typename": "Mutation"}}},
        ]

        result = await handle_delete_journal_entry({"id": "123"})
        data = json.loads(result[0].text)

        assert data == {"deleted": True, "id": 123}
        assert mock_execute.call_args_list[0][0][1] == {"id": 123, "user_id": 1}
        assert mock_execute.call_args_list[1][0][1] == {"id": 123}

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_entry_that_isnt_yours_is_an_error_and_not_deleted(
        self, mock_execute, mock_user
    ):
        mock_user.return_value = {"id": 1}
        mock_execute.return_value = {"data": {"reading_journals": []}}

        with pytest.raises(ToolError, match="no journal entry of yours"):
            await handle_delete_journal_entry({"id": 123})
        assert mock_execute.call_count == 1

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_missing_id_returns_error_before_api_calls(self, mock_execute, mock_user):
        with pytest.raises(ToolError) as exc:
            await handle_delete_journal_entry({})

        assert str(exc.value) == "'id' is required."
        mock_user.assert_not_awaited()
        mock_execute.assert_not_awaited()

    @patch("hardcover_mcp.tools.journal.get_current_user", new_callable=AsyncMock)
    @patch("hardcover_mcp.tools.journal.execute", new_callable=AsyncMock)
    async def test_invalid_id_returns_error_before_api_calls(self, mock_execute, mock_user):
        with pytest.raises(ToolError) as exc:
            await handle_delete_journal_entry({"id": "bad"})

        assert "'id' must be an integer" in str(exc.value)
        mock_user.assert_not_awaited()
        mock_execute.assert_not_awaited()
