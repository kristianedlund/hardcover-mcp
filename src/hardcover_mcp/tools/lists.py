"""Tools: list CRUD and list-book management."""

import json
from typing import Any

from mcp.types import TextContent, Tool, ToolAnnotations

from hardcover_mcp.client import HardcoverAPIError, execute
from hardcover_mcp.tools._registry import DELETE, READ, UPDATE, ToolSpec
from hardcover_mcp.tools._results import list_result, mutation_payload, returned_object
from hardcover_mcp.tools._validation import (
    PRIVACY_DESCRIPTION,
    ToolError,
    _require_count,
    _require_int,
    _require_privacy,
    privacy_label,
)
from hardcover_mcp.tools.books import author_names
from hardcover_mcp.tools.user import get_current_user

GET_MY_LISTS_QUERY = """
query GetMyLists($user_id: Int!, $limit: Int!, $offset: Int!) {
    lists(
        where: {user_id: {_eq: $user_id}},
        order_by: [{updated_at: desc}, {id: desc}],
        limit: $limit,
        offset: $offset
    ) {
        id
        name
        slug
        description
        books_count
        privacy_setting_id
        updated_at
    }
    lists_aggregate(where: {user_id: {_eq: $user_id}}) {
        aggregate { count }
    }
}
"""

GET_LIST_BY_ID_QUERY = """
query GetListById($id: Int!, $books_limit: Int!, $books_offset: Int!) {
    lists(where: {id: {_eq: $id}}, limit: 1) {
        id
        name
        slug
        description
        books_count
        privacy_setting_id
        updated_at
        list_books(
            order_by: [{position: asc}, {id: asc}],
            limit: $books_limit,
            offset: $books_offset
        ) {
            position
            book {
                id
                title
                slug
                cached_contributors
            }
        }
    }
}
"""


def _format_list_summary(lst: dict[str, Any]) -> dict[str, Any]:
    """Format a raw list record into a flat summary dict."""
    return {
        "id": lst["id"],
        "name": lst["name"],
        "slug": lst["slug"],
        "description": lst.get("description"),
        "books_count": lst["books_count"],
        "privacy": privacy_label(lst.get("privacy_setting_id")),
        "updated_at": lst.get("updated_at"),
    }


def _format_list_book(lb: dict[str, Any]) -> dict[str, Any]:
    """Format a list_book entry into a flat dict with position and book info."""
    book = lb.get("book") or {}
    authors = author_names(book)
    return {
        "position": lb.get("position"),
        "book_id": book.get("id"),
        "title": book.get("title"),
        "slug": book.get("slug"),
        "authors": authors,
    }


async def _get_my_lists(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch the authenticated user's Hardcover lists.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``limit`` (int, default 50, max 200), ``offset`` (int, default 0).

    Returns
    -------
    list[TextContent]
        JSON ``{total, returned, offset, lists}`` of list summaries.
    """
    user = await get_current_user()
    user_id = user["id"]

    limit = _require_count(arguments.get("limit"), "limit", default=50, minimum=1, maximum=200)
    offset = _require_count(arguments.get("offset"), "offset", default=0)

    result = await execute(
        GET_MY_LISTS_QUERY, {"user_id": user_id, "limit": limit, "offset": offset}
    )
    lists = [_format_list_summary(lst) for lst in result["data"]["lists"]]
    total = result["data"]["lists_aggregate"]["aggregate"]["count"]
    return list_result("lists", lists, offset=offset, total=total)


async def handle_get_list(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch a single Hardcover list with its books, or your own lists when no id is given.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``id`` (int). Without it, delegates to ``_get_my_lists``
        (``limit``, ``offset``).
        With it: ``books_limit`` (int, default 25, max 100),
        ``books_offset`` (int, default 0).

    Returns
    -------
    list[TextContent]
        JSON with list summary and nested ``books`` array, or
        ``{total, returned, offset, lists}`` when no id is given.
    """
    list_id = arguments.get("id")
    if list_id is None:
        return await _get_my_lists(arguments)

    books_limit = _require_count(
        arguments.get("books_limit"), "books_limit", default=25, minimum=1, maximum=100
    )
    books_offset = _require_count(arguments.get("books_offset"), "books_offset", default=0)

    result = await execute(
        GET_LIST_BY_ID_QUERY,
        {
            "id": _require_int(list_id, "id"),
            "books_limit": books_limit,
            "books_offset": books_offset,
        },
    )

    lists = result["data"]["lists"]
    if not lists:
        return [TextContent(type="text", text="No list found with that ID.")]

    lst = lists[0]
    output = _format_list_summary(lst)
    output["books"] = [_format_list_book(lb) for lb in lst.get("list_books", [])]

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Write: list CRUD ──

CREATE_LIST_MUTATION = """
mutation CreateList($object: ListInput!) {
    insert_list(object: $object) {
        id
        list {
            id
            name
            slug
            description
            privacy_setting_id
        }
    }
}
"""

UPDATE_LIST_MUTATION = """
mutation UpdateList($id: Int!, $object: ListInput!) {
    update_list(id: $id, object: $object) {
        id
        list {
            id
            name
            slug
            description
            privacy_setting_id
        }
    }
}
"""

DELETE_LIST_MUTATION = """
mutation DeleteList($id: Int!) {
    delete_list(id: $id) {
        __typename
    }
}
"""


def _build_list_input(arguments: dict[str, Any]) -> dict[str, Any]:
    """Build a ListInput object from tool arguments.

    Raises
    ------
    ToolError
        If an unrecognised privacy value is provided.
    """
    obj: dict[str, Any] = {}
    if arguments.get("name"):
        obj["name"] = arguments["name"]
    if arguments.get("description") is not None:
        obj["description"] = arguments["description"]
    privacy = arguments.get("privacy")
    if privacy is not None:
        obj["privacy_setting_id"] = _require_privacy(privacy)
    return obj


async def _create_list(arguments: dict[str, Any]) -> list[TextContent]:
    """Create a new Hardcover list.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``name`` (str).
        Optional: ``description`` (str), ``privacy`` (str, default public).

    Returns
    -------
    list[TextContent]
        JSON with the created list's id, name, slug, and privacy.
    """
    name = arguments.get("name")
    if not name:
        raise ToolError("'name' is required.")

    obj = _build_list_input(arguments)

    result = await execute(CREATE_LIST_MUTATION, {"object": obj})
    mutation_result = mutation_payload(result, "insert_list")

    lst = returned_object(mutation_result, "list", "list")
    output = {
        "id": lst.get("id"),
        "name": lst.get("name"),
        "slug": lst.get("slug"),
        "description": lst.get("description"),
        "privacy": privacy_label(lst.get("privacy_setting_id")),
    }
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def _update_list(arguments: dict[str, Any]) -> list[TextContent]:
    """Update an existing Hardcover list's name, description, or privacy.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``id`` (int).
        Optional: ``name``, ``description``, ``privacy``.

    Returns
    -------
    list[TextContent]
        JSON with the updated list details.
    """
    list_id = arguments.get("id")
    if not list_id:
        raise ToolError("'id' is required.")

    obj = _build_list_input(arguments)
    if not obj:
        raise ToolError("provide at least one of 'name', 'description', 'privacy'.")

    result = await execute(
        UPDATE_LIST_MUTATION, {"id": _require_int(list_id, "id"), "object": obj}
    )
    mutation_result = mutation_payload(result, "update_list")

    lst = returned_object(mutation_result, "list", "list")
    output = {
        "id": lst.get("id"),
        "name": lst.get("name"),
        "slug": lst.get("slug"),
        "description": lst.get("description"),
        "privacy": privacy_label(lst.get("privacy_setting_id")),
    }
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def handle_set_list(arguments: dict[str, Any]) -> list[TextContent]:
    """Create a list (no ``id``) or update an existing one (``id`` given)."""
    if arguments.get("id") is None:
        return await _create_list(arguments)
    return await _update_list(arguments)


async def handle_delete_list(arguments: dict[str, Any]) -> list[TextContent]:
    """Delete a Hardcover list by ID.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``id`` (int).

    Returns
    -------
    list[TextContent]
        JSON confirmation with ``deleted: true`` and the list ID.
    """
    list_id = arguments.get("id")
    if not list_id:
        raise ToolError("'id' is required.")

    list_id_int = _require_int(list_id, "id")

    await execute(DELETE_LIST_MUTATION, {"id": list_id_int})

    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": list_id_int}))]


# ── Write: list books ──

INSERT_LIST_BOOK_MUTATION = """
mutation InsertListBook($object: ListBookInput!) {
    insert_list_book(object: $object) {
        id
        list_book {
            id
            list_id
            book_id
            position
        }
    }
}
"""

DELETE_LIST_BOOK_MUTATION = """
mutation DeleteListBook($id: Int!) {
    delete_list_book(id: $id) {
        __typename
    }
}
"""

FIND_LIST_BOOK_QUERY = """
query FindListBook($list_id: Int!, $book_id: Int!) {
    list_books(
        where: {list_id: {_eq: $list_id}, book_id: {_eq: $book_id}},
        limit: 1
    ) {
        id
    }
}
"""


# For list_ids: which of the lists are yours, and the book's entries on them, in one request.
FIND_OWN_LIST_BOOKS_QUERY = """
query FindOwnListBooks($list_ids: [Int!], $book_id: Int!, $user_id: Int!) {
    lists(where: {id: {_in: $list_ids}, user_id: {_eq: $user_id}}) {
        id
    }
    list_books(where: {list_id: {_in: $list_ids}, book_id: {_eq: $book_id}}) {
        id
        list_id
    }
}
"""

# Keeps a many-list call well inside the per-minute rate limit.
_MAX_LIST_IDS = 20


async def handle_set_list_book(arguments: dict[str, Any]) -> list[TextContent]:
    """Put a book on one or more lists or take it off, so membership matches ``on_list``.

    Checks current membership first, so repeating a call is a no-op.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``book_id`` (int), ``on_list`` (bool), and either ``list_id`` (int) or
        ``list_ids`` (list of int, up to 20). Optional: ``position`` (int), used only when
        adding to a single ``list_id``.

    Returns
    -------
    list[TextContent]
        With ``list_id``: JSON with ``list_id``, ``book_id``, ``on_list``, ``changed``, and
        ``list_book_id`` (null once removed). With ``list_ids``: ``book_id``, ``on_list``,
        and ``results`` with one entry per list (see ``_set_on_lists``).
    """
    on_list = arguments.get("on_list")
    if not isinstance(on_list, bool):
        raise ToolError("'on_list' (true/false) is required.")
    if not arguments.get("book_id"):
        raise ToolError("'book_id' is required.")
    has_one = arguments.get("list_id") is not None
    has_many = arguments.get("list_ids") is not None
    if has_one == has_many:
        raise ToolError("provide either 'list_id' or 'list_ids'.")

    book_id = _require_int(arguments["book_id"], "book_id")
    if has_many:
        if arguments.get("position") is not None:
            raise ToolError("'position' only works with a single 'list_id'.")
        return await _set_on_lists(arguments["list_ids"], book_id, on_list)

    list_id = _require_int(arguments["list_id"], "list_id")
    position = (
        _require_int(arguments["position"], "position")
        if arguments.get("position") is not None
        else None
    )

    found = await execute(FIND_LIST_BOOK_QUERY, {"list_id": list_id, "book_id": book_id})
    existing = found["data"]["list_books"]
    existing_id = existing[0]["id"] if existing else None

    output: dict[str, Any] = {"list_id": list_id, "book_id": book_id, "on_list": on_list}

    if on_list and existing_id is None:
        obj: dict[str, Any] = {"list_id": list_id, "book_id": book_id}
        if position is not None:
            obj["position"] = position
        result = await execute(INSERT_LIST_BOOK_MUTATION, {"object": obj})
        lb = mutation_payload(result, "insert_list_book").get("list_book") or {}
        output.update(changed=True, list_book_id=lb.get("id"), position=lb.get("position"))
    elif not on_list and existing_id is not None:
        await execute(DELETE_LIST_BOOK_MUTATION, {"id": existing_id})
        output.update(changed=True, list_book_id=None)
    else:
        output.update(changed=False, list_book_id=existing_id)

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def _set_on_lists(raw_ids: Any, book_id: int, on_list: bool) -> list[TextContent]:
    """Apply ``on_list`` for one book on each of several lists.

    Each list is checked and changed on its own, so the call stays idempotent. A list that
    isn't yours, or whose change the API rejects, gets an ``error`` in its entry and the
    others still go ahead.

    Returns
    -------
    list[TextContent]
        JSON with ``book_id``, ``on_list``, and ``results``: per list, ``list_id`` and
        ``changed``, plus ``list_book_id`` on success or ``error`` on failure.
    """
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ToolError("'list_ids' must be a non-empty array of list ids.")
    list_ids = list(dict.fromkeys(_require_int(i, "list_ids") for i in raw_ids))
    if len(list_ids) > _MAX_LIST_IDS:
        raise ToolError(f"'list_ids' takes at most {_MAX_LIST_IDS} lists per call.")

    user = await get_current_user()
    found = await execute(
        FIND_OWN_LIST_BOOKS_QUERY,
        {"list_ids": list_ids, "book_id": book_id, "user_id": user["id"]},
    )
    own = {lst["id"] for lst in found["data"]["lists"]}
    existing: dict[int, int] = {}
    for lb in found["data"]["list_books"]:
        existing.setdefault(lb["list_id"], lb["id"])

    results: list[dict[str, Any]] = []
    for list_id in list_ids:
        entry: dict[str, Any] = {"list_id": list_id, "changed": False}
        if list_id not in own:
            entry["error"] = "not one of your lists."
        elif on_list == (list_id in existing):
            entry["list_book_id"] = existing.get(list_id)
        else:
            try:
                if on_list:
                    result = await execute(
                        INSERT_LIST_BOOK_MUTATION,
                        {"object": {"list_id": list_id, "book_id": book_id}},
                    )
                    lb = mutation_payload(result, "insert_list_book").get("list_book") or {}
                    entry.update(changed=True, list_book_id=lb.get("id"))
                else:
                    await execute(DELETE_LIST_BOOK_MUTATION, {"id": existing[list_id]})
                    entry.update(changed=True, list_book_id=None)
            except HardcoverAPIError as exc:
                entry["error"] = str(exc)
        results.append(entry)

    output = {"book_id": book_id, "on_list": on_list, "results": results}
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="get_list",
            description=(
                "Without id: list the lists you own, most recently updated first, as {total, "
                "returned, offset, lists} (id, name, slug, description, books count, privacy; no "
                "books), paginated with limit/offset. With id: get that list (yours or another "
                "user's) including a 'books' array in list order (position, book_id, title, slug, "
                "authors), paginated with books_limit/books_offset. Read-only. Find other users' "
                "lists with search_books(query_type='List')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "List ID. Omit to list your own lists.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Without id: max lists to return (default 50, max 200).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Without id: offset for pagination (default 0).",
                    },
                    "books_limit": {
                        "type": "integer",
                        "description": "With id: max books to return (default 25, max 100).",
                    },
                    "books_offset": {
                        "type": "integer",
                        "description": "With id: offset for book pagination (default 0).",
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_list,
        toolset="lists",
        scopes=("read:lists", "read:me"),
    ),
    ToolSpec(
        Tool(
            name="set_list",
            description=(
                "Create a list (omit id; name required) or change the name, description, or "
                "privacy of a list you own (pass id plus at least one field; only the fields "
                "you pass are overwritten). Creating twice makes two lists, so check get_list "
                "first. Returns the list's id, name, slug, description, and privacy. Does not "
                "change which books are on it: use set_list_book for that."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "List ID to update. Omit to create a new list.",
                    },
                    "name": {
                        "type": "string",
                        "description": "List name (required when creating).",
                    },
                    "description": {
                        "type": "string",
                        "description": "List description.",
                    },
                    "privacy": {
                        "type": "string",
                        "description": PRIVACY_DESCRIPTION + " Default when creating: public.",
                    },
                },
            },
            # Updates overwrite fields; creates are not idempotent.
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=False,
                open_world_hint=True,
            ),
        ),
        handle_set_list,
        toolset="lists",
        scopes=("write:lists",),
    ),
    ToolSpec(
        Tool(
            name="delete_list",
            description=(
                "Permanently delete a list you own by id. The books themselves stay in your "
                "library; only the list and its entries are removed. Cannot be undone. Returns "
                "{deleted: true, id}. To take a single book off use set_list_book with "
                "on_list=false."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover list ID to delete.",
                    },
                },
                "required": ["id"],
            },
            annotations=DELETE,
        ),
        handle_delete_list,
        toolset="lists",
        scopes=("write:lists",),
    ),
    ToolSpec(
        Tool(
            name="set_list_book",
            description=(
                "Put a book on your lists (on_list=true) or take it off (on_list=false): one "
                "list with list_id (optionally at a position), or up to 20 at once with "
                "list_ids. Idempotent: lists already in the requested state don't change, and "
                "an existing entry's position is not moved. Does not touch your library or "
                "reading status (use set_user_book). With list_id returns list_id, book_id, "
                "on_list, 'changed', and list_book_id; with list_ids returns one result per "
                "list, and a list that isn't yours or fails gets an 'error' while the others "
                "still change. Find list ids with get_list (or a book's current lists with "
                "get_user_book) and book ids with search_books."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "list_id": {
                        "type": "integer",
                        "description": "Hardcover list ID. Use this or list_ids.",
                    },
                    "list_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Several list IDs (up to 20). Use this or list_id.",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID.",
                    },
                    "on_list": {
                        "type": "boolean",
                        "description": "true to add the book, false to remove it.",
                    },
                    "position": {
                        "type": "integer",
                        "description": (
                            "Position when adding to a single list_id (optional; ignored when "
                            "removing)."
                        ),
                    },
                },
                "required": ["book_id", "on_list"],
            },
            annotations=UPDATE,
        ),
        handle_set_list_book,
        toolset="lists",
        scopes=("read:lists", "read:me", "write:lists"),
    ),
]
