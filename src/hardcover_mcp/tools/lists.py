"""Tools: list CRUD and list-book management."""

import json
from typing import Any

from mcp.types import TextContent, Tool

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import CREATE, DELETE, READ, UPDATE, ToolSpec
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.books import author_names
from hardcover_mcp.tools.user import get_current_user

PRIVACY_MAP = {
    1: "public",
    2: "followers_only",
    3: "private",
}

GET_MY_LISTS_QUERY = """
query GetMyLists($user_id: Int!, $limit: Int!, $offset: Int!) {
    lists(
        where: {user_id: {_eq: $user_id}},
        order_by: {updated_at: desc},
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
}
"""

GET_LIST_BY_ID_QUERY = """
query GetListById($id: Int!, $book_limit: Int!, $book_offset: Int!) {
    lists(where: {id: {_eq: $id}}, limit: 1) {
        id
        name
        slug
        description
        books_count
        privacy_setting_id
        updated_at
        list_books(order_by: {position: asc}, limit: $book_limit, offset: $book_offset) {
            position
            book {
                id
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
        "privacy": PRIVACY_MAP.get(lst.get("privacy_setting_id"), "unknown"),
        "updated_at": lst.get("updated_at"),
    }


def _format_list_book(lb: dict[str, Any]) -> dict[str, Any]:
    """Format a list_book entry into a flat dict with position and book info."""
    book = lb.get("book", {})
    authors = author_names(book)
    return {
        "position": lb.get("position"),
        "book_id": book.get("id"),
        "title": book.get("title"),
        "slug": book.get("slug"),
        "authors": authors,
    }


async def handle_get_my_lists(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch the authenticated user's Hardcover lists.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``limit`` (int, default 50, max 200), ``offset`` (int, default 0).

    Returns
    -------
    list[TextContent]
        JSON array of list summaries.
    """
    user = await get_current_user()
    user_id = user["id"]

    limit = min(arguments.get("limit", 50), 200)
    offset = arguments.get("offset", 0)

    result = await execute(
        GET_MY_LISTS_QUERY, {"user_id": user_id, "limit": limit, "offset": offset}
    )
    lists = result["data"]["lists"]
    formatted = [_format_list_summary(lst) for lst in lists]

    return [TextContent(type="text", text=json.dumps(formatted, indent=2))]


async def handle_get_list(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch a single Hardcover list with its books.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``id`` (int).
        Optional: ``book_limit`` (int, default 25, max 100),
        ``book_offset`` (int, default 0).

    Returns
    -------
    list[TextContent]
        JSON with list summary and nested ``books`` array.
    """
    list_id = arguments.get("id")
    if not list_id:
        return [TextContent(type="text", text="Error: 'id' is required.")]

    book_limit = min(arguments.get("book_limit", 25), 100)
    book_offset = arguments.get("book_offset", 0)

    try:
        result = await execute(
            GET_LIST_BY_ID_QUERY,
            {
                "id": _require_int(list_id, "id"),
                "book_limit": book_limit,
                "book_offset": book_offset,
            },
        )
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    lists = result["data"]["lists"]
    if not lists:
        return [TextContent(type="text", text="No list found with that ID.")]

    lst = lists[0]
    output = _format_list_summary(lst)
    output["books"] = [_format_list_book(lb) for lb in lst.get("list_books", [])]

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Write: list CRUD ──

PRIVACY_NAME_TO_ID = {v: k for k, v in PRIVACY_MAP.items()}

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
    ValueError
        If an unrecognised privacy value is provided.
    """
    obj: dict[str, Any] = {}
    if arguments.get("name"):
        obj["name"] = arguments["name"]
    if arguments.get("description") is not None:
        obj["description"] = arguments["description"]
    privacy = arguments.get("privacy")
    if privacy is not None:
        if isinstance(privacy, int) or (isinstance(privacy, str) and privacy.isdigit()):
            obj["privacy_setting_id"] = int(privacy)
        else:
            pid = PRIVACY_NAME_TO_ID.get(str(privacy).lower())
            if pid is None:
                raise ValueError(
                    f"Unknown privacy '{privacy}'. Valid: {', '.join(PRIVACY_MAP.values())}"
                )
            obj["privacy_setting_id"] = pid
    return obj


async def handle_create_list(arguments: dict[str, Any]) -> list[TextContent]:
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
        return [TextContent(type="text", text="Error: 'name' is required.")]

    try:
        obj = _build_list_input(arguments)
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    result = await execute(CREATE_LIST_MUTATION, {"object": obj})
    mutation_result = result["data"]["insert_list"]

    lst = mutation_result.get("list", {})
    output = {
        "id": lst.get("id"),
        "name": lst.get("name"),
        "slug": lst.get("slug"),
        "description": lst.get("description"),
        "privacy": PRIVACY_MAP.get(lst.get("privacy_setting_id"), "unknown"),
    }
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def handle_update_list(arguments: dict[str, Any]) -> list[TextContent]:
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
        return [TextContent(type="text", text="Error: 'id' is required.")]

    try:
        obj = _build_list_input(arguments)
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    if not obj:
        return [
            TextContent(
                type="text",
                text="Error: provide at least one of 'name', 'description', 'privacy'.",
            )
        ]

    try:
        result = await execute(
            UPDATE_LIST_MUTATION, {"id": _require_int(list_id, "id"), "object": obj}
        )
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    mutation_result = result["data"]["update_list"]

    lst = mutation_result.get("list", {})
    output = {
        "id": lst.get("id"),
        "name": lst.get("name"),
        "slug": lst.get("slug"),
        "description": lst.get("description"),
        "privacy": PRIVACY_MAP.get(lst.get("privacy_setting_id"), "unknown"),
    }
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


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
        return [TextContent(type="text", text="Error: 'id' is required.")]

    try:
        list_id_int = _require_int(list_id, "id")
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

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


async def handle_add_book_to_list(arguments: dict[str, Any]) -> list[TextContent]:
    """Add a book to a Hardcover list.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``list_id`` (int), ``book_id`` (int).
        Optional: ``position`` (int).

    Returns
    -------
    list[TextContent]
        JSON with the created list_book entry.
    """
    list_id = arguments.get("list_id")
    book_id = arguments.get("book_id")
    if not list_id or not book_id:
        return [TextContent(type="text", text="Error: 'list_id' and 'book_id' are required.")]

    try:
        obj: dict[str, Any] = {
            "list_id": _require_int(list_id, "list_id"),
            "book_id": _require_int(book_id, "book_id"),
        }
        if arguments.get("position") is not None:
            obj["position"] = _require_int(arguments["position"], "position")
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    result = await execute(INSERT_LIST_BOOK_MUTATION, {"object": obj})
    mutation_result = result["data"]["insert_list_book"]

    lb = mutation_result.get("list_book", {})
    return [TextContent(type="text", text=json.dumps(lb, indent=2))]


async def handle_remove_book_from_list(arguments: dict[str, Any]) -> list[TextContent]:
    """Remove a book from a list.

    Parameters
    ----------
    arguments : dict[str, Any]
        Provide ``id`` (list_book ID) directly, or both ``list_id`` and
        ``book_id`` for an automatic lookup.

    Returns
    -------
    list[TextContent]
        JSON confirmation with ``deleted: true`` and the list_book ID.
    """
    list_book_id = arguments.get("id")
    list_id = arguments.get("list_id")
    book_id = arguments.get("book_id")

    # If no direct list_book id given, look it up by list_id + book_id
    if not list_book_id:
        if not list_id or not book_id:
            return [
                TextContent(
                    type="text",
                    text="Error: provide 'id' (list_book id) or both 'list_id' and 'book_id'.",
                )
            ]
        try:
            result = await execute(
                FIND_LIST_BOOK_QUERY,
                {
                    "list_id": _require_int(list_id, "list_id"),
                    "book_id": _require_int(book_id, "book_id"),
                },
            )
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
        lbs = result["data"]["list_books"]
        if not lbs:
            return [TextContent(type="text", text="Error: book not found in that list.")]
        list_book_id = lbs[0]["id"]

    try:
        list_book_id_int = _require_int(list_book_id, "id")
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    result = await execute(DELETE_LIST_BOOK_MUTATION, {"id": list_book_id_int})

    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": list_book_id_int}))]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="get_my_lists",
            description=(
                "List the lists you own, most recently updated first, paginated with "
                "limit/offset. Read-only. Returns id, name, slug, description, books count, and "
                "privacy, but not the books themselves; use get_list with an id for those. "
                "Returns an empty array if you have no lists."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max lists to return (default 50, max 200).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Offset for pagination (default 0).",
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_my_lists,
        toolset="lists",
    ),
    ToolSpec(
        Tool(
            name="get_list",
            description=(
                "Get one list (yours or another user's) by id, with its books in list order. "
                "Read-only. Returns the list's name, description, privacy, and books count, plus "
                "a 'books' array (position, book_id, title, slug, authors) paginated with "
                "book_limit/book_offset. Find ids with get_my_lists or "
                "search_books(query_type='List')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover list ID (use get_my_lists to find IDs).",
                    },
                    "book_limit": {
                        "type": "integer",
                        "description": "Max books to return (default 25, max 100).",
                    },
                    "book_offset": {
                        "type": "integer",
                        "description": "Offset for book pagination (default 0).",
                    },
                },
                "required": ["id"],
            },
            annotations=READ,
        ),
        handle_get_list,
        toolset="lists",
    ),
    ToolSpec(
        Tool(
            name="create_list",
            description=(
                "Create a new, empty custom list owned by you. Each call creates a separate "
                "list, so check get_my_lists first to avoid duplicates. Returns the new list's "
                "id, name, slug, description, and privacy. To rename or change an existing list "
                "use update_list; to add books use add_book_to_list with the returned id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the new list.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description.",
                    },
                    "privacy": {
                        "type": "string",
                        "description": "public/followers_only/private. Default: public.",
                    },
                },
                "required": ["name"],
            },
            annotations=CREATE,
        ),
        handle_create_list,
        toolset="lists",
    ),
    ToolSpec(
        Tool(
            name="update_list",
            description=(
                "Change the name, description, or privacy of a list you own (pass at least one). "
                "Only the fields you pass are overwritten. Returns the updated list. Does not "
                "change the list's books: use add_book_to_list/remove_book_from_list for that, "
                "and create_list to make a new list."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover list ID.",
                    },
                    "name": {
                        "type": "string",
                        "description": "New name.",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description.",
                    },
                    "privacy": {
                        "type": "string",
                        "description": "Privacy: 'public', 'followers_only', 'private'.",
                    },
                },
                "required": ["id"],
            },
            annotations=UPDATE,
        ),
        handle_update_list,
        toolset="lists",
    ),
    ToolSpec(
        Tool(
            name="delete_list",
            description=(
                "Permanently delete a list you own by id. The books themselves stay in your "
                "library; only the list and its entries are removed. Cannot be undone. Returns "
                "{deleted: true, id}. To remove a single book use remove_book_from_list."
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
    ),
    ToolSpec(
        Tool(
            name="add_book_to_list",
            description=(
                "Add a book to one of your custom lists, optionally at a given position. Does "
                "not add the book to your library or change its reading status (use "
                "set_user_book for that). Not idempotent: check get_list first if the book may "
                "already be on the list. Returns the new list entry (id, list_id, book_id, "
                "position). Find list ids with get_my_lists and book ids with search_books."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "list_id": {
                        "type": "integer",
                        "description": "Hardcover list ID.",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID to add.",
                    },
                    "position": {
                        "type": "integer",
                        "description": "Position in the list (optional).",
                    },
                },
                "required": ["list_id", "book_id"],
            },
            annotations=CREATE,
        ),
        handle_add_book_to_list,
        toolset="lists",
    ),
    ToolSpec(
        Tool(
            name="remove_book_from_list",
            description=(
                "Remove a book from one of your custom lists, identified by the list entry id "
                "or by list_id + book_id. The book stays in your library with its status and "
                "rating. Errors if the book isn't on that list. Returns {deleted: true, id}. To "
                "remove the book from your library entirely use delete_user_book."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "list_book ID. If unknown, use list_id + book_id.",
                    },
                    "list_id": {
                        "type": "integer",
                        "description": "List ID (use with book_id to find list_book).",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Book ID (use with list_id to find list_book).",
                    },
                },
            },
            annotations=DELETE,
        ),
        handle_remove_book_from_list,
        toolset="lists",
    ),
]
