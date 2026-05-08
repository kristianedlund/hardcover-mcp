"""Tools: get_prompts and answer_prompt — community book prompt browsing and answering."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int

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
mutation InsertPromptAnswer($object: PromptAnswerInput!) {
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


async def handle_answer_prompt(arguments: dict[str, Any]) -> list[TextContent]:
    """Submit a book as an answer to a community prompt.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``prompt_id`` (int), ``book_id`` (int).

    Returns
    -------
    list[TextContent]
        JSON confirmation with the created prompt_answer ``id``,
        ``prompt_id``, and ``book_id``.
    """
    prompt_id = arguments.get("prompt_id")
    book_id = arguments.get("book_id")

    if prompt_id is None or book_id is None:
        return [TextContent(type="text", text="Error: 'prompt_id' and 'book_id' are required.")]

    try:
        obj: dict[str, Any] = {
            "prompt_id": _require_int(prompt_id, "prompt_id"),
            "book_id": _require_int(book_id, "book_id"),
        }
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    result = await execute(ANSWER_PROMPT_MUTATION, {"object": obj})
    mutation_result = result["data"]["insert_prompt_answer"]

    answer = mutation_result.get("prompt_answer", {})
    return [TextContent(type="text", text=json.dumps(answer, indent=2))]
