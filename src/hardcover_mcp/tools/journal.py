"""Tools: get_reading_journal — fetch reading journal entries."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.user import get_current_user

# Fetch reading journal entries for the authenticated user.
# Filters on user_id are mandatory; book_id and event are optional.
# Results are ordered newest-first by action_at.
GET_READING_JOURNAL_QUERY = """
query GetReadingJournal(
    $user_id: Int!,
    $limit: Int!,
    $offset: Int!,
    $where: reading_journals_bool_exp!
) {
    reading_journals(
        where: $where,
        order_by: {action_at: desc},
        limit: $limit,
        offset: $offset
    ) {
        id
        book_id
        edition_id
        event
        entry
        action_at
        metadata
        privacy_setting_id
        book {
            title
            slug
            contributions {
                author {
                    name
                }
            }
        }
    }
}
"""


def _format_journal_entry(raw: dict[str, Any]) -> dict[str, Any]:
    """Format a single reading_journals row into a clean response dict.

    Parameters
    ----------
    raw : dict[str, Any]
        A single row from the ``reading_journals`` GraphQL response.
        Expected keys: ``id``, ``book_id``, ``edition_id``, ``event``,
        ``entry``, ``action_at``, ``metadata``, ``privacy_setting_id``,
        ``book`` (with ``title``, ``slug``, ``contributions``).

    Returns
    -------
    dict[str, Any]
        Flattened dict with ``id``, ``event``, ``entry``, ``action_at``,
        ``book_id``, ``edition_id``, ``metadata``, ``privacy_setting_id``,
        and ``book`` (with ``title``, ``slug``, ``authors``).
    """
    book_raw = raw.get("book") or {}
    contributions = book_raw.get("contributions") or []
    authors = [c["author"]["name"] for c in contributions if c.get("author")]

    return {
        "id": raw.get("id"),
        "event": raw.get("event"),
        "entry": raw.get("entry"),
        "action_at": raw.get("action_at"),
        "book_id": raw.get("book_id"),
        "edition_id": raw.get("edition_id"),
        "metadata": raw.get("metadata"),
        "privacy_setting_id": raw.get("privacy_setting_id"),
        "book": {
            "title": book_raw.get("title"),
            "slug": book_raw.get("slug"),
            "authors": authors,
        },
    }


async def handle_get_reading_journal(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch reading journal entries for the authenticated user.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional filters:

        - ``book_id`` (int) — restrict to entries for a specific book.
        - ``event`` (str) — restrict to a specific event type, e.g.
          ``"note"``, ``"quote"``, ``"status_currently_reading"``,
          ``"status_read"``, ``"rated"``, ``"reviewed"``,
          ``"progress_updated"``.
        - ``limit`` (int, default 25, max 100) — number of entries to return.
        - ``offset`` (int, default 0) — pagination offset.

    Returns
    -------
    list[TextContent]
        Single-element list with a JSON array of formatted journal entries.
        Each entry contains ``id``, ``event``, ``entry``, ``action_at``,
        ``book_id``, ``edition_id``, ``metadata``, ``privacy_setting_id``,
        and ``book`` (``title``, ``slug``, ``authors``).

    Raises
    ------
    ValueError
        If ``book_id``, ``limit``, or ``offset`` cannot be coerced to int.
    """
    # --- 1. Validate and resolve optional parameters
    book_id_raw = arguments.get("book_id")
    book_id = _require_int(book_id_raw, "book_id") if book_id_raw is not None else None

    event = arguments.get("event")

    limit_raw = arguments.get("limit", 25)
    limit = _require_int(limit_raw, "limit")
    limit = min(limit, 100)

    offset_raw = arguments.get("offset", 0)
    offset = _require_int(offset_raw, "offset")

    # --- 2. Fetch authenticated user
    user = await get_current_user()
    user_id = user["id"]

    # --- 3. Build where clause — always filter by user_id; book_id and
    #        event are only added when provided to keep the query minimal.
    where: dict[str, Any] = {"user_id": {"_eq": user_id}}
    if book_id is not None:
        where["book_id"] = {"_eq": book_id}
    if event is not None:
        where["event"] = {"_eq": event}

    # --- 4. Execute query
    result = await execute(
        GET_READING_JOURNAL_QUERY,
        {
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
            "where": where,
        },
    )

    # --- 5. Format and return
    entries = result["data"]["reading_journals"]
    formatted = [_format_journal_entry(e) for e in entries]
    return [TextContent(type="text", text=json.dumps(formatted, indent=2))]
