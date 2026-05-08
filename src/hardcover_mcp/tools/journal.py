"""Tools for reading journal entries."""

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

INSERT_READING_JOURNAL_MUTATION = """
mutation InsertReadingJournal($object: ReadingJournalInput!) {
    insert_reading_journal(object: $object) {
        reading_journal {
            id
            book_id
            edition_id
            event
            entry
            action_at
            metadata
            privacy_setting_id
        }
    }
}
"""

DELETE_READING_JOURNAL_MUTATION = """
mutation DeleteReadingJournal($id: Int!) {
    delete_reading_journal(id: $id) {
        __typename
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
            "limit": limit,
            "offset": offset,
            "where": where,
        },
    )

    # --- 5. Format and return
    entries = result["data"]["reading_journals"]
    formatted = [_format_journal_entry(e) for e in entries]
    return [TextContent(type="text", text=json.dumps(formatted, indent=2))]


async def handle_add_journal_entry(arguments: dict[str, Any]) -> list[TextContent]:
    """Create a reading journal entry for a book.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``book_id`` (int), ``entry`` (str), ``event`` (``"note"`` or ``"quote"``).
        Optional: ``edition_id`` (int), ``privacy_setting_id`` (int).

    Returns
    -------
    list[TextContent]
        Single-element list with JSON for the created journal entry.
    """
    book_id = arguments.get("book_id")
    if book_id is None:
        return [TextContent(type="text", text="Error: 'book_id' is required.")]

    entry = arguments.get("entry")
    if not isinstance(entry, str) or not entry.strip():
        return [TextContent(type="text", text="Error: 'entry' must be a non-empty string.")]

    event = arguments.get("event")
    if not isinstance(event, str):
        return [TextContent(type="text", text="Error: 'event' is required.")]
    event_value = event.strip().lower()
    if event_value not in {"note", "quote"}:
        return [TextContent(type="text", text="Error: 'event' must be one of: note, quote.")]

    try:
        obj: dict[str, Any] = {
            "book_id": _require_int(book_id, "book_id"),
            "entry": entry.strip(),
            "event": event_value,
        }
        if arguments.get("edition_id") is not None:
            obj["edition_id"] = _require_int(arguments["edition_id"], "edition_id")
        if arguments.get("privacy_setting_id") is not None:
            obj["privacy_setting_id"] = _require_int(
                arguments["privacy_setting_id"], "privacy_setting_id"
            )
    except ValueError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]

    await get_current_user()
    result = await execute(INSERT_READING_JOURNAL_MUTATION, {"object": obj})
    created = result["data"]["insert_reading_journal"]["reading_journal"]
    output = {
        "id": created.get("id"),
        "book_id": created.get("book_id"),
        "edition_id": created.get("edition_id"),
        "event": created.get("event"),
        "entry": created.get("entry"),
        "action_at": created.get("action_at"),
        "metadata": created.get("metadata"),
        "privacy_setting_id": created.get("privacy_setting_id"),
    }
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def handle_delete_journal_entry(arguments: dict[str, Any]) -> list[TextContent]:
    """Delete a reading journal entry by ID.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``id`` (int).

    Returns
    -------
    list[TextContent]
        Single-element list with JSON confirmation for the deleted entry.
    """
    entry_id = arguments.get("id")
    if entry_id is None:
        return [TextContent(type="text", text="Error: 'id' is required.")]

    try:
        entry_id_int = _require_int(entry_id, "id")
    except ValueError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]

    await get_current_user()
    await execute(DELETE_READING_JOURNAL_MUTATION, {"id": entry_id_int})
    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": entry_id_int}))]
