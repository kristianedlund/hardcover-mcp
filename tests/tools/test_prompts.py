"""Unit tests for tools/prompts.py — formatting helpers and handler functions."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from hardcover_mcp.tools.prompts import (
    _format_prompt,
    handle_answer_prompt,
    handle_get_prompts,
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
        assert len(data) == 1
        assert data[0]["question"] == "Best sci-fi?"
        assert data[0]["featured"] is True

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


class TestHandleAnswerPrompt:
    @pytest.mark.asyncio
    async def test_returns_error_when_prompt_id_missing(self):
        result = await handle_answer_prompt({"book_id": 42})

        assert "Error" in result[0].text
        assert "prompt_id" in result[0].text

    @pytest.mark.asyncio
    async def test_returns_error_when_book_id_missing(self):
        result = await handle_answer_prompt({"prompt_id": 7})

        assert "Error" in result[0].text
        assert "book_id" in result[0].text

    @pytest.mark.asyncio
    async def test_returns_error_for_non_integer_ids(self):
        result = await handle_answer_prompt({"prompt_id": "abc", "book_id": 42})

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    async def test_returns_error_for_non_integer_book_id(self):
        result = await handle_answer_prompt({"prompt_id": 7, "book_id": "xyz"})

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    async def test_submits_answer_and_returns_prompt_answer(self):
        mock_answer = {"id": 99, "prompt_id": 7, "book_id": 42}
        mock_result = {"data": {"insert_prompt_answer": {"id": 1, "prompt_answer": mock_answer}}}

        with patch(
            "hardcover_mcp.tools.prompts.execute",
            new=AsyncMock(return_value=mock_result),
        ) as mock_exec:
            result = await handle_answer_prompt({"prompt_id": 7, "book_id": 42})

        data = json.loads(result[0].text)
        assert data["prompt_id"] == 7
        assert data["book_id"] == 42

        _, called_vars = mock_exec.call_args[0]
        assert called_vars["object"]["prompt_id"] == 7
        assert called_vars["object"]["book_id"] == 42
