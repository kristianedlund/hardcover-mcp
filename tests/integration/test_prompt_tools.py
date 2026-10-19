"""Integration tests for set_prompt_answer against the real Hardcover API.

Requires HARDCOVER_API_TOKEN in the environment (loaded from .env by conftest.py).
Skipped automatically when the token is absent.
"""

import asyncio
import json

import pytest

pytestmark = pytest.mark.integration


class TestSetPromptAnswer:
    async def test_answer_and_withdraw_restores_state(self):
        from hardcover_mcp.client import execute
        from hardcover_mcp.tools.books import handle_get_book
        from hardcover_mcp.tools.prompts import (
            FIND_PROMPT_ANSWER_QUERY,
            handle_get_prompts,
            handle_set_prompt_answer,
        )
        from hardcover_mcp.tools.user import get_current_user

        prompts = json.loads((await handle_get_prompts({"limit": 1}))[0].text)
        assert prompts, "expected at least one community prompt"
        prompt_id = prompts[0]["id"]
        book = json.loads((await handle_get_book({"slug": "the-code-book"}))[0].text)

        async def set_answered(answered: bool) -> dict:
            result = await handle_set_prompt_answer(
                {"prompt_id": prompt_id, "book_id": book["id"], "answered": answered}
            )
            return json.loads(result[0].text)

        async def wait_until(visible: bool) -> None:
            # Reads of prompt answers lag a few seconds behind writes in both directions;
            # repeating before they catch up would insert a duplicate or re-delete a
            # withdrawn answer rather than test idempotency.
            user = await get_current_user()
            for _ in range(15):
                found = await execute(
                    FIND_PROMPT_ANSWER_QUERY,
                    {"user_id": user["id"], "prompt_id": prompt_id, "book_id": book["id"]},
                )
                if bool(found["data"]["prompt_answers"]) == visible:
                    return
                await asyncio.sleep(1)
            pytest.fail(f"prompt answer lookup never showed visible={visible}")

        # Probe with a no-op-safe call, then restore whatever the account had before.
        probe = await set_answered(False)
        originally_answered = probe["changed"]
        try:
            added = await set_answered(True)
            assert added["changed"] is True
            assert added["answer_id"] is not None
            await wait_until(visible=True)
            again = await set_answered(True)
            assert again["changed"] is False
            assert again["answer_id"] == added["answer_id"]

            withdrawn = await set_answered(False)
            assert withdrawn["changed"] is True
            await wait_until(visible=False)
            assert (await set_answered(False))["changed"] is False
        finally:
            # Always restore. Not parsed: if reads still lag, a withdraw of an
            # already-withdrawn answer returns an error message rather than JSON.
            await handle_set_prompt_answer(
                {"prompt_id": prompt_id, "book_id": book["id"], "answered": originally_answered}
            )
