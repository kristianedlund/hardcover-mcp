"""Unit tests for tools/prompts.py — formatting helpers and handler functions."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools._validation import ToolError
from hardcover_mcp.tools.prompts import (
    _format_prompt,
    handle_get_prompts,
    handle_set_prompt_answer,
)


class TestFormatPrompt:
    def test_formats_full_prompt(self):
        raw = {
            "id": 1,
            "slug": "best-sci-fi-2025",
            "question": "Best sci-fi of 2025?",
            "description": "Share your favourite sci-fi reads from 2025.",
            "featured": True,
            "answers_count": 42,
            "books_count": 15,
        }
        result = _format_prompt(raw)

        assert result["id"] == 1
        assert result["slug"] == "best-sci-fi-2025"
        assert result["question"] == "Best sci-fi of 2025?"
        assert result["description"] == "Share your favourite sci-fi reads from 2025."
        assert result["featured"] is True
        assert result["answers_count"] == 42
        assert result["books_count"] == 15

    def test_defaults_featured_to_false(self):
        raw = {
            "id": 2,
            "slug": "cozy-reads",
            "question": "Favourite cozy reads?",
            "answers_count": 10,
            "books_count": 5,
        }
        result = _format_prompt(raw)

        assert result["featured"] is False

    def test_defaults_counts_to_zero(self):
        raw = {
            "id": 3,
            "slug": "new-prompt",
            "question": "New prompt?",
        }
        result = _format_prompt(raw)

        assert result["answers_count"] == 0
        assert result["books_count"] == 0

    def test_description_can_be_none(self):
        raw = {
            "id": 4,
            "slug": "no-desc",
            "question": "No description prompt?",
            "description": None,
            "answers_count": 0,
            "books_count": 0,
        }
        result = _format_prompt(raw)

        assert result["description"] is None


class TestHandleGetPrompts:
    def _mock_api_response(self, prompts: list) -> dict:
        return {"data": {"prompts": prompts}}

    @pytest.mark.asyncio
    async def test_returns_formatted_prompts(self):
        mock_prompts = [
            {
                "id": 1,
                "slug": "best-sci-fi",
                "question": "Best sci-fi?",
                "description": "Sci-fi picks",
                "featured": True,
                "answers_count": 10,
                "books_count": 5,
            }
        ]
        with patch(
            "hardcover_mcp.tools.prompts.execute",
            new=AsyncMock(return_value=self._mock_api_response(mock_prompts)),
        ):
            result = await handle_get_prompts({})

        data = json.loads(result[0].text)
        assert data["returned"] == 1
        assert data["prompts"][0]["question"] == "Best sci-fi?"
        assert data["prompts"][0]["featured"] is True

    @pytest.mark.asyncio
    async def test_featured_filter_sends_where_clause(self):
        with patch(
            "hardcover_mcp.tools.prompts.execute",
            new=AsyncMock(return_value=self._mock_api_response([])),
        ) as mock_exec:
            await handle_get_prompts({"featured": True})

        _, kwargs_vars = mock_exec.call_args[0]
        assert kwargs_vars["where"] == {"featured": {"_eq": True}}

    @pytest.mark.asyncio
    async def test_no_filter_sends_none_where(self):
        with patch(
            "hardcover_mcp.tools.prompts.execute",
            new=AsyncMock(return_value=self._mock_api_response([])),
        ) as mock_exec:
            await handle_get_prompts({})

        _, kwargs_vars = mock_exec.call_args[0]
        assert kwargs_vars["where"] is None

    @pytest.mark.asyncio
    async def test_respects_limit_and_offset(self):
        with patch(
            "hardcover_mcp.tools.prompts.execute",
            new=AsyncMock(return_value=self._mock_api_response([])),
        ) as mock_exec:
            await handle_get_prompts({"limit": 10, "offset": 5})

        _, kwargs_vars = mock_exec.call_args[0]
        assert kwargs_vars["limit"] == 10
        assert kwargs_vars["offset"] == 5

    @pytest.mark.asyncio
    async def test_caps_limit_at_100(self):
        with patch(
            "hardcover_mcp.tools.prompts.execute",
            new=AsyncMock(return_value=self._mock_api_response([])),
        ) as mock_exec:
            await handle_get_prompts({"limit": 999})

        _, kwargs_vars = mock_exec.call_args[0]
        assert kwargs_vars["limit"] == 100


def _existing(*ids: int) -> dict:
    return {"data": {"prompt_answers": [{"id": i} for i in ids]}}


class TestHandleSetPromptAnswer:
    async def test_returns_error_when_answered_missing(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_prompt_answer({"prompt_id": 7, "book_id": 42})

        assert "'answered'" in str(exc.value)

    async def test_returns_error_when_prompt_id_missing(self):
        with pytest.raises(ToolError) as exc:
            await handle_set_prompt_answer({"book_id": 42, "answered": True})

        assert "prompt_id" in str(exc.value)

    async def test_returns_error_for_non_integer_ids(self):
        with pytest.raises(ToolError):
            await handle_set_prompt_answer({"prompt_id": "abc", "book_id": 42, "answered": True})

    async def _run(self, arguments: dict, *responses: dict) -> tuple[dict, AsyncMock]:
        mock_exec = AsyncMock(side_effect=list(responses))
        with (
            patch(
                "hardcover_mcp.tools.prompts.get_current_user",
                new=AsyncMock(return_value={"id": 5}),
            ),
            patch("hardcover_mcp.tools.prompts.execute", new=mock_exec),
        ):
            result = await handle_set_prompt_answer(arguments)
        return json.loads(result[0].text), mock_exec

    async def test_adds_answer_with_description(self):
        data, mock_exec = await self._run(
            {"prompt_id": 7, "book_id": 42, "answered": True, "description": "Fits."},
            _existing(),
            {"data": {"insert_prompt_answer": {"id": 99, "prompt_id": 7, "book_id": 42}}},
        )

        assert data == {
            "prompt_id": 7,
            "book_id": 42,
            "answered": True,
            "changed": True,
            "answer_id": 99,
        }
        assert mock_exec.call_args_list[0][0][1] == {"user_id": 5, "prompt_id": 7, "book_id": 42}
        assert mock_exec.call_args_list[1][0][1] == {
            "object": {"prompt_id": 7, "book_id": 42, "description": "Fits."}
        }

    async def test_add_when_already_answered_is_noop(self):
        data, mock_exec = await self._run(
            {"prompt_id": 7, "book_id": 42, "answered": True}, _existing(99)
        )

        assert data["changed"] is False
        assert data["answer_id"] == 99
        assert mock_exec.call_count == 1

    async def test_withdraws_existing_answer(self):
        data, mock_exec = await self._run(
            {"prompt_id": 7, "book_id": 42, "answered": False},
            _existing(99),
            {"data": {"delete_prompt_answer": {"id": 99}}},
        )

        assert data["changed"] is True
        assert data["answer_id"] is None
        assert mock_exec.call_args_list[1][0][1] == {"id": 99}

    async def test_withdraw_when_not_answered_is_noop(self):
        data, mock_exec = await self._run(
            {"prompt_id": 7, "book_id": 42, "answered": False}, _existing()
        )

        assert data["changed"] is False
        assert mock_exec.call_count == 1

    async def test_failed_withdraw_returns_clear_error(self):
        mock_exec = AsyncMock(
            side_effect=[_existing(99), RuntimeError("GraphQL error: not a valid json response")]
        )
        with (
            patch(
                "hardcover_mcp.tools.prompts.get_current_user",
                new=AsyncMock(return_value={"id": 5}),
            ),
            patch("hardcover_mcp.tools.prompts.execute", new=mock_exec),
            pytest.raises(ToolError) as exc,
        ):
            await handle_set_prompt_answer({"prompt_id": 7, "book_id": 42, "answered": False})

        assert "could not withdraw" in str(exc.value)
        assert "few seconds" in str(exc.value)


async def test_featured_false_as_a_string_lists_all_prompts():
    mock = AsyncMock(return_value={"data": {"prompts": []}})
    with patch("hardcover_mcp.tools.prompts.execute", new=mock):
        await handle_get_prompts({"featured": "false"})

    assert mock.call_args[0][1]["where"] is None


async def test_withdraw_keeps_other_errors_own_message():
    from hardcover_mcp.client import HardcoverAPIError

    mock_exec = AsyncMock(
        side_effect=[_existing(99), HardcoverAPIError("Hardcover's daily API limit … is used up.")]
    )
    with (
        patch(
            "hardcover_mcp.tools.prompts.get_current_user", new=AsyncMock(return_value={"id": 5})
        ),
        patch("hardcover_mcp.tools.prompts.execute", new=mock_exec),
        pytest.raises(HardcoverAPIError, match="daily API limit"),
    ):
        await handle_set_prompt_answer({"prompt_id": 1, "book_id": 2, "answered": False})
