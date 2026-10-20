"""Tools: get_prompts and set_prompt_answer — browse community prompts and answer them."""

import json
from typing import Any

from mcp.types import TextContent, Tool

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import READ, UPDATE, ToolSpec
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.user import get_current_user

GET_PROMPTS_QUERY = """
query GetPrompts($limit: Int!, $offset: Int!, $where: prompts_bool_exp) {
    prompts(
        where: $where,
        order_by: {answers_count: desc},
        limit: $limit,
        offset: $offset
    ) {
        id
        slug
        question
        description
        featured
        answers_count
        books_count
    }
}
"""

ANSWER_PROMPT_MUTATION = """
mutation InsertPromptAnswer($object: PromptAnswerCreateInput!) {
    insert_prompt_answer(object: $object) {
        id
        prompt_answer {
            id
            prompt_id
            book_id
        }
    }
}
"""


FIND_PROMPT_ANSWER_QUERY = """
query FindPromptAnswer($user_id: Int!, $prompt_id: Int!, $book_id: Int!) {
    prompt_answers(
        where: {
            user_id: {_eq: $user_id},
            prompt_id: {_eq: $prompt_id},
            book_id: {_eq: $book_id}
        },
        limit: 1
    ) {
        id
    }
}
"""

DELETE_PROMPT_ANSWER_MUTATION = """
mutation DeletePromptAnswer($id: Int!) {
    delete_prompt_answer(id: $id) {
        id
    }
}
"""


def _format_prompt(prompt: dict[str, Any]) -> dict[str, Any]:
    """Format a raw prompt record into a flat summary dict.

    Parameters
    ----------
    prompt : dict[str, Any]
        Raw prompt record from the Hardcover API.

    Returns
    -------
    dict[str, Any]
        Flat dict with ``id``, ``slug``, ``question``, ``description``,
        ``featured``, ``answers_count``, and ``books_count``.
    """
    return {
        "id": prompt["id"],
        "slug": prompt["slug"],
        "question": prompt["question"],
        "description": prompt.get("description"),
        "featured": prompt.get("featured", False),
        "answers_count": prompt.get("answers_count", 0),
        "books_count": prompt.get("books_count", 0),
    }


async def handle_get_prompts(arguments: dict[str, Any]) -> list[TextContent]:
    """List community book prompts, optionally filtered to featured only.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``featured`` (bool, default False — return all prompts),
        ``limit`` (int, default 25, max 100), ``offset`` (int, default 0).

    Returns
    -------
    list[TextContent]
        JSON array of prompt summaries with ``question``, ``description``,
        ``answers_count``, and ``books_count``.
    """
    limit = min(arguments.get("limit", 25), 100)
    offset = arguments.get("offset", 0)
    featured_only = arguments.get("featured", False)

    # Build optional where clause — omit entirely when not filtering by featured
    where: dict[str, Any] | None = {"featured": {"_eq": True}} if featured_only else None

    result = await execute(
        GET_PROMPTS_QUERY,
        {"limit": limit, "offset": offset, "where": where},
    )
    prompts = result["data"]["prompts"]
    formatted = [_format_prompt(p) for p in prompts]

    return [TextContent(type="text", text=json.dumps(formatted, indent=2))]


async def handle_set_prompt_answer(arguments: dict[str, Any]) -> list[TextContent]:
    """Answer a community prompt with a book, or withdraw that answer.

    Checks for your existing answer first, so repeating a call is a no-op.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``prompt_id`` (int), ``book_id`` (int), ``answered`` (bool).
        Optional: ``description`` (str), why the book fits — used only when adding.

    Returns
    -------
    list[TextContent]
        JSON with ``prompt_id``, ``book_id``, ``answered``, ``changed``, and
        ``answer_id`` (null once withdrawn).
    """
    answered = arguments.get("answered")
    if not isinstance(answered, bool):
        return [TextContent(type="text", text="Error: 'answered' (true/false) is required.")]
    if arguments.get("prompt_id") is None or arguments.get("book_id") is None:
        return [TextContent(type="text", text="Error: 'prompt_id' and 'book_id' are required.")]

    try:
        prompt_id = _require_int(arguments["prompt_id"], "prompt_id")
        book_id = _require_int(arguments["book_id"], "book_id")
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    user = await get_current_user()
    found = await execute(
        FIND_PROMPT_ANSWER_QUERY,
        {"user_id": user["id"], "prompt_id": prompt_id, "book_id": book_id},
    )
    existing = found["data"]["prompt_answers"]
    existing_id = existing[0]["id"] if existing else None

    output: dict[str, Any] = {"prompt_id": prompt_id, "book_id": book_id, "answered": answered}

    if answered and existing_id is None:
        obj: dict[str, Any] = {"prompt_id": prompt_id, "book_id": book_id}
        if arguments.get("description"):
            obj["description"] = arguments["description"]
        result = await execute(ANSWER_PROMPT_MUTATION, {"object": obj})
        created = result["data"]["insert_prompt_answer"]
        output.update(changed=True, answer_id=created.get("id"))
    elif not answered and existing_id is not None:
        try:
            await execute(DELETE_PROMPT_ANSWER_MUTATION, {"id": existing_id})
        except RuntimeError:
            # Reads of prompt answers lag a few seconds behind writes, so the lookup can
            # return an answer that was just withdrawn; deleting it again fails on
            # Hardcover's side with an opaque webhook error.
            return [
                TextContent(
                    type="text",
                    text=(
                        "Error: Hardcover could not withdraw that answer. It may already have "
                        "been withdrawn moments ago; changes to prompt answers can take a few "
                        "seconds to show."
                    ),
                )
            ]
        output.update(changed=True, answer_id=None)
    else:
        output.update(changed=False, answer_id=existing_id)

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="get_prompts",
            description=(
                "List community book prompts (questions like 'best sci-fi of 2025'), most "
                "answered first, paginated with limit/offset. Read-only. Set featured=true for "
                "featured prompts only. Returns id, question, description, answers_count, and "
                "books_count. Use it to browse; to find a prompt by words in its question use "
                "search_books(query_type='Prompt'). Pass a prompt id to set_prompt_answer to "
                "submit a book."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "featured": {
                        "type": "boolean",
                        "description": "If true, return only featured prompts (default false).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max prompts to return (default 25, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_prompts,
        toolset="social",
        scopes=("read:prompts",),
    ),
    ToolSpec(
        Tool(
            name="set_prompt_answer",
            description=(
                "Answer a community prompt with a book (answered=true, optionally with a "
                "description of why it fits) or withdraw that answer (answered=false). "
                "Idempotent: if you already answered the prompt with that book, nothing "
                "changes and the existing description is kept. Changes take a few seconds to "
                "show, so don't repeat a call immediately. You can answer one prompt with "
                "several different books. Returns prompt_id, book_id, answered, 'changed', and "
                "answer_id. Find prompt ids with get_prompts and book ids with search_books."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt_id": {
                        "type": "integer",
                        "description": "Hardcover prompt ID (use get_prompts to find IDs).",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID.",
                    },
                    "answered": {
                        "type": "boolean",
                        "description": "true to submit the book, false to withdraw it.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Why this book fits the prompt (optional; when adding).",
                    },
                },
                "required": ["prompt_id", "book_id", "answered"],
            },
            annotations=UPDATE,
        ),
        handle_set_prompt_answer,
        toolset="social",
        scopes=("read:me", "read:prompts", "write:prompts"),
    ),
]
