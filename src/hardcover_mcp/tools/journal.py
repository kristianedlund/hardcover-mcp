"""Tools for reading journal entries."""

import json
from typing import Any

from mcp.types import TextContent, Tool, ToolAnnotations

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import DELETE, READ, ToolSpec
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.books import author_names
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
        order_by: [{action_at: desc}, {id: desc}],
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
                contribution
                author {
                    name
                }
            }
        }
    }
}
"""

INSERT_READING_JOURNAL_MUTATION = """
mutation InsertReadingJournal($object: ReadingJournalCreateType!) {
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

GET_OWN_JOURNAL_ENTRY_QUERY = """
query GetOwnJournalEntry($id: bigint!, $user_id: Int!) {
    reading_journals(where: {id: {_eq: $id}, user_id: {_eq: $user_id}}, limit: 1) {
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
"""

UPDATE_READING_JOURNAL_MUTATION = """
mutation UpdateReadingJournal($id: Int!, $object: ReadingJournalUpdateType!) {
    update_reading_journal(id: $id, object: $object) {
        errors
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
    authors = author_names(book_raw)

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


_EDITABLE_EVENTS = {"note", "quote"}


def _format_written_entry(raw: dict[str, Any]) -> dict[str, Any]:
    """Format the reading_journal returned by an insert/update mutation."""
    return {
        "id": raw.get("id"),
        "book_id": raw.get("book_id"),
        "edition_id": raw.get("edition_id"),
        "event": raw.get("event"),
        "entry": raw.get("entry"),
        "action_at": raw.get("action_at"),
        "metadata": raw.get("metadata"),
        "privacy_setting_id": raw.get("privacy_setting_id"),
    }


def _parse_event(value: Any) -> str:
    """Validate a note/quote event value.

    Raises
    ------
    ValueError
        If the value is not ``"note"`` or ``"quote"``.
    """
    if not isinstance(value, str) or value.strip().lower() not in _EDITABLE_EVENTS:
        raise ValueError("'event' must be one of: note, quote.")
    return value.strip().lower()


async def _create_journal_entry(arguments: dict[str, Any]) -> list[TextContent]:
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
        return [TextContent(type="text", text="Error: 'book_id' is required when creating.")]

    entry = arguments.get("entry")
    if not isinstance(entry, str) or not entry.strip():
        return [TextContent(type="text", text="Error: 'entry' must be a non-empty string.")]

    if arguments.get("event") is None:
        return [TextContent(type="text", text="Error: 'event' is required when creating.")]

    try:
        obj: dict[str, Any] = {
            "book_id": _require_int(book_id, "book_id"),
            "entry": entry.strip(),
            "event": _parse_event(arguments["event"]),
        }
        if arguments.get("edition_id") is not None:
            obj["edition_id"] = _require_int(arguments["edition_id"], "edition_id")
        # Required by the API; valid values are 1 (public), 2 (followers),
        # 3 (private). A 0 is silently rejected (returns a null entry).
        obj["privacy_setting_id"] = (
            _require_int(arguments["privacy_setting_id"], "privacy_setting_id")
            if arguments.get("privacy_setting_id") is not None
            else 1
        )
        obj["tags"] = arguments.get("tags", [])
    except ValueError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]

    # Auth gate — the API scopes the mutation to the authenticated user via token.
    await get_current_user()
    result = await execute(INSERT_READING_JOURNAL_MUTATION, {"object": obj})
    created = result["data"]["insert_reading_journal"]["reading_journal"]
    if created is None:
        return [
            TextContent(
                type="text",
                text="Error: journal entry not created (privacy_setting_id must be 1, 2, or 3).",
            )
        ]
    return [TextContent(type="text", text=json.dumps(_format_written_entry(created), indent=2))]


async def _update_journal_entry(arguments: dict[str, Any]) -> list[TextContent]:
    """Edit one of your note/quote journal entries, preserving fields not passed.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``id`` (int). Optional: ``entry`` (str), ``event`` (note/quote),
        ``edition_id`` (int), ``privacy_setting_id`` (int). ``book_id`` is ignored.

    Returns
    -------
    list[TextContent]
        Single-element list with JSON for the updated journal entry.
    """
    try:
        entry_id = _require_int(arguments["id"], "id")
        updates: dict[str, Any] = {}
        if arguments.get("entry") is not None:
            entry = arguments["entry"]
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("'entry' must be a non-empty string.")
            updates["entry"] = entry.strip()
        if arguments.get("event") is not None:
            updates["event"] = _parse_event(arguments["event"])
        for key in ("edition_id", "privacy_setting_id"):
            if arguments.get(key) is not None:
                updates[key] = _require_int(arguments[key], key)
    except ValueError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]
    if not updates:
        return [
            TextContent(
                type="text",
                text=(
                    "Error: provide at least one of 'entry', 'event', 'edition_id', "
                    "'privacy_setting_id'."
                ),
            )
        ]

    # Only your own entries; scoping by user_id also gives a clear "not found".
    user = await get_current_user()
    found = await execute(GET_OWN_JOURNAL_ENTRY_QUERY, {"id": entry_id, "user_id": user["id"]})
    rows = found["data"]["reading_journals"]
    if not rows:
        return [TextContent(type="text", text="Error: no journal entry of yours with that id.")]
    current = rows[0]
    if current.get("event") not in _EDITABLE_EVENTS:
        return [
            TextContent(
                type="text",
                text=(
                    f"Error: only note and quote entries can be edited (this one is "
                    f"'{current.get('event')}')."
                ),
            )
        ]

    # Send the full editable set so unspecified fields keep their current values.
    obj = {
        key: current.get(key)
        for key in ("entry", "event", "edition_id", "privacy_setting_id")
        if current.get(key) is not None
    }
    obj.update(updates)

    result = await execute(UPDATE_READING_JOURNAL_MUTATION, {"id": entry_id, "object": obj})
    payload = result["data"]["update_reading_journal"]
    if payload.get("errors"):
        return [TextContent(type="text", text=f"Error: {'; '.join(payload['errors'])}")]
    updated = payload.get("reading_journal") or {**current, **obj, "id": entry_id}
    return [TextContent(type="text", text=json.dumps(_format_written_entry(updated), indent=2))]


async def handle_set_journal_entry(arguments: dict[str, Any]) -> list[TextContent]:
    """Create a note/quote journal entry (no ``id``) or edit an existing one (``id`` given)."""
    if arguments.get("id") is not None:
        return await _update_journal_entry(arguments)
    return await _create_journal_entry(arguments)


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

    # Auth gate — the API scopes the mutation to the authenticated user via token.
    await get_current_user()
    await execute(DELETE_READING_JOURNAL_MUTATION, {"id": entry_id_int})
    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": entry_id_int}))]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="get_reading_journal",
            description=(
                "Get your own reading journal, newest first: notes, quotes, status changes, "
                "ratings, reviews, and progress updates. Read-only. Filter by book_id and/or "
                "event type; paginate with limit/offset. Returns each entry's id, event, text, "
                "timestamp, and book. This is your personal log; for what people you follow are "
                "doing use get_activity_feed; for review texts use "
                "get_user_library(has_review=true)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Filter entries to a specific book by Hardcover book ID.",
                    },
                    "event": {
                        "type": "string",
                        "description": (
                            "Filter by event type. Examples: 'note', 'quote', "
                            "'status_currently_reading', 'status_read', 'rated', "
                            "'reviewed', 'progress_updated'."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries to return (default 25, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_reading_journal,
        toolset="journal",
        scopes=("read:journal", "read:me"),
    ),
    ToolSpec(
        Tool(
            name="set_journal_entry",
            description=(
                "Add a note or quote to your reading journal (omit id; book_id, entry, and "
                "event required) or edit one of your existing notes/quotes (pass its id from "
                "get_reading_journal; only the fields you pass change, the book can't). New "
                "entries are public unless privacy_setting_id says otherwise. Each create makes "
                "a separate entry. Status, rating, and progress entries can't be created or "
                "edited here; they come from set_user_book and set_user_book_read. Returns the "
                "entry with its id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Journal entry ID to edit. Omit to create a new entry.",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID (required when creating).",
                    },
                    "entry": {
                        "type": "string",
                        "description": "Journal entry text (required when creating).",
                    },
                    "event": {
                        "type": "string",
                        "enum": ["note", "quote"],
                        "description": "Entry type (required when creating).",
                    },
                    "edition_id": {
                        "type": "integer",
                        "description": "Optional Hardcover edition ID.",
                    },
                    "privacy_setting_id": {
                        "type": "integer",
                        "description": (
                            "1 public (default when creating), 2 followers, 3 private."
                        ),
                    },
                },
            },
            # Edits overwrite text; creates are not idempotent.
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=False,
                open_world_hint=True,
            ),
        ),
        handle_set_journal_entry,
        toolset="journal",
        scopes=("read:journal", "read:me", "write:library"),
    ),
    ToolSpec(
        Tool(
            name="delete_journal_entry",
            description=(
                "Permanently delete one of your reading journal entries by id (from "
                "get_reading_journal). Only that entry is removed; the book, its status, and "
                "other entries are unaffected. Cannot be undone. Returns {deleted: true, id}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Reading journal entry ID.",
                    },
                },
                "required": ["id"],
            },
            annotations=DELETE,
        ),
        handle_delete_journal_entry,
        toolset="journal",
        scopes=("read:me", "write:library"),
    ),
]
