"""Tools: get_user_library, get_user_book, set_user_book, reading log, delete_user_book."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools.user import get_current_user

STATUS_MAP: dict[int, str] = {
    1: "Want to Read",
    2: "Currently Reading",
    3: "Read",
    4: "Paused",
    5: "Did Not Finish",
    6: "Ignored",
}

STATUS_NAME_TO_ID: dict[str, int] = {v.lower(): k for k, v in STATUS_MAP.items()}

# ── Shared field fragments ──

_USER_BOOK_FIELDS = """
    id
    book_id
    status_id
    rating
    updated_at
    book {
        title
        slug
        contributions {
            author {
                name
            }
        }
    }
"""

_USER_BOOK_DETAIL_FIELDS = """
    id
    book_id
    status_id
    rating
    updated_at
    user_book_reads(order_by: {id: desc}) {
        id
        started_at
        finished_at
        progress_pages
    }
    book {
        title
        slug
        pages
        contributions {
            author {
                name
            }
        }
    }
"""


# ── Read: get_user_library (single query, optional status filter) ──

def _build_library_query(with_status: bool) -> str:
    status_filter = ", status_id: {_eq: $status_id}" if with_status else ""
    status_var = ", $status_id: Int!" if with_status else ""
    return f"""
query GetUserLibrary($user_id: Int!, $limit: Int!, $offset: Int!{status_var}) {{
    user_books(
        where: {{user_id: {{_eq: $user_id}}{status_filter}}},
        limit: $limit,
        offset: $offset,
        order_by: {{updated_at: desc}}
    ) {{
        {_USER_BOOK_FIELDS}
    }}
    user_books_aggregate(
        where: {{user_id: {{_eq: $user_id}}{status_filter}}}
    ) {{
        aggregate {{ count }}
    }}
}}
"""


GET_USER_LIBRARY_QUERY = _build_library_query(with_status=True)
GET_USER_LIBRARY_ALL_QUERY = _build_library_query(with_status=False)


# ── Read: get_user_book ──

GET_USER_BOOK_QUERY = f"""
query GetUserBook($user_id: Int!, $book_id: Int!) {{
    user_books(
        where: {{user_id: {{_eq: $user_id}}, book_id: {{_eq: $book_id}}}},
        limit: 1,
        order_by: {{updated_at: desc}}
    ) {{
        {_USER_BOOK_DETAIL_FIELDS}
    }}
}}
"""

GET_BOOK_ID_BY_SLUG_QUERY = """
query GetBookIdBySlug($slug: String!) {
    books(where: {slug: {_eq: $slug}}, limit: 1) {
        id
    }
}
"""


def _format_user_book(ub: dict[str, Any]) -> dict[str, Any]:
    book = ub.get("book", {})
    authors = [c["author"]["name"] for c in book.get("contributions", [])]
    return {
        "user_book_id": ub["id"],
        "book_id": ub["book_id"],
        "title": book.get("title"),
        "slug": book.get("slug"),
        "authors": authors,
        "status": STATUS_MAP.get(ub["status_id"], f"Unknown ({ub['status_id']})"),
        "rating": ub.get("rating"),
        "updated_at": ub.get("updated_at"),
    }


def _format_user_book_detail(ub: dict[str, Any]) -> dict[str, Any]:
    book = ub.get("book", {})
    authors = [c["author"]["name"] for c in book.get("contributions", [])]
    return {
        "user_book_id": ub["id"],
        "book_id": ub["book_id"],
        "title": book.get("title"),
        "slug": book.get("slug"),
        "pages": book.get("pages"),
        "authors": authors,
        "status": STATUS_MAP.get(ub["status_id"], f"Unknown ({ub['status_id']})"),
        "rating": ub.get("rating"),
        "updated_at": ub.get("updated_at"),
        "reads": ub.get("user_book_reads", []),
    }


async def handle_get_user_library(arguments: dict[str, Any]) -> list[TextContent]:
    user = await get_current_user()
    user_id = user["id"]

    limit = min(arguments.get("limit", 25), 100)
    offset = arguments.get("offset", 0)
    status = arguments.get("status")

    status_id = _resolve_status_id(status)
    if status is not None and status_id is None:
        valid = ", ".join(STATUS_MAP.values())
        return [TextContent(type="text", text=f"Error: unknown status '{status}'. Valid: {valid}")]

    if status_id is not None:
        result = await execute(GET_USER_LIBRARY_QUERY, {
            "user_id": user_id, "limit": limit, "offset": offset, "status_id": status_id,
        })
    else:
        result = await execute(GET_USER_LIBRARY_ALL_QUERY, {
            "user_id": user_id, "limit": limit, "offset": offset,
        })

    total = result["data"]["user_books_aggregate"]["aggregate"]["count"]
    user_books = result["data"]["user_books"]
    formatted = [_format_user_book(ub) for ub in user_books]

    output = {"total": total, "returned": len(formatted), "offset": offset, "books": formatted}
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def handle_get_user_book(arguments: dict[str, Any]) -> list[TextContent]:
    book_id = arguments.get("book_id")
    slug = arguments.get("slug")

    if not book_id and not slug:
        return [TextContent(type="text", text="Error: provide 'book_id' or 'slug'.")]

    # Resolve slug to book_id if needed
    if not book_id:
        slug_result = await execute(GET_BOOK_ID_BY_SLUG_QUERY, {"slug": slug})
        books = slug_result["data"]["books"]
        if not books:
            return [TextContent(type="text", text=f"No book found with slug '{slug}'.")]
        book_id = books[0]["id"]

    user = await get_current_user()
    result = await execute(GET_USER_BOOK_QUERY, {
        "user_id": user["id"], "book_id": int(book_id),
    })
    user_books = result["data"]["user_books"]
    if not user_books:
        return [TextContent(type="text", text="Book not in your library.")]

    output = _format_user_book_detail(user_books[0])
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Write: set_user_book ──

FIND_USER_BOOK_QUERY = """
query FindUserBook($user_id: Int!, $book_id: Int!) {
    user_books(
        where: {user_id: {_eq: $user_id}, book_id: {_eq: $book_id}},
        limit: 1,
        order_by: {updated_at: desc}
    ) {
        id
        status_id
        rating
    }
}
"""

INSERT_USER_BOOK_MUTATION = """
mutation InsertUserBook($object: UserBookCreateInput!) {
    insert_user_book(object: $object) {
        error
        id
        user_book {
            id
            book_id
            status_id
            rating
        }
    }
}
"""

UPDATE_USER_BOOK_MUTATION = """
mutation UpdateUserBook($id: Int!, $object: UserBookUpdateInput!) {
    update_user_book(id: $id, object: $object) {
        error
        id
        user_book {
            id
            book_id
            status_id
            rating
        }
    }
}
"""


def _resolve_status_id(status: str | int | None) -> int | None:
    if status is None:
        return None
    if isinstance(status, int):
        return status
    if isinstance(status, str) and status.isdigit():
        return int(status)
    return STATUS_NAME_TO_ID.get(str(status).lower())


async def handle_set_user_book(arguments: dict[str, Any]) -> list[TextContent]:
    book_id = arguments.get("book_id")
    if not book_id:
        return [TextContent(type="text", text="Error: 'book_id' is required.")]

    user = await get_current_user()
    user_id = user["id"]

    status = arguments.get("status")
    status_id = _resolve_status_id(status)
    if status is not None and status_id is None:
        valid = ", ".join(STATUS_MAP.values())
        return [TextContent(type="text", text=f"Error: unknown status '{status}'. Valid: {valid}")]

    rating = arguments.get("rating")

    # Check if user_book already exists
    existing = await execute(FIND_USER_BOOK_QUERY, {
        "user_id": user_id, "book_id": int(book_id),
    })
    existing_books = existing["data"]["user_books"]

    if existing_books:
        # Merge: preserve existing fields the caller didn't specify
        current = existing_books[0]
        obj: dict[str, Any] = {}
        obj["status_id"] = status_id if status_id is not None else current["status_id"]
        if rating is not None:
            obj["rating"] = float(rating)
        elif current.get("rating") is not None:
            obj["rating"] = current["rating"]

        ub_id = current["id"]
        result = await execute(UPDATE_USER_BOOK_MUTATION, {"id": ub_id, "object": obj})
        mutation_result = result["data"]["update_user_book"]
    else:
        obj = {}
        obj["book_id"] = int(book_id)
        if status_id is not None:
            obj["status_id"] = status_id
        if rating is not None:
            obj["rating"] = float(rating)
        result = await execute(INSERT_USER_BOOK_MUTATION, {"object": obj})
        mutation_result = result["data"]["insert_user_book"]

    if mutation_result.get("error"):
        return [TextContent(type="text", text=f"Error: {mutation_result['error']}")]

    ub = mutation_result.get("user_book", {})
    output = {
        "user_book_id": ub.get("id"),
        "book_id": ub.get("book_id"),
        "status": STATUS_MAP.get(ub.get("status_id"), str(ub.get("status_id"))),
        "rating": ub.get("rating"),
    }
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Write: user_book_reads ──

INSERT_USER_BOOK_READ_MUTATION = """
mutation InsertUserBookRead($userBookId: Int!, $userBookRead: DatesReadInput!) {
    insert_user_book_read(user_book_id: $userBookId, user_book_read: $userBookRead) {
        error
        id
        user_book_read {
            id
            user_book_id
            started_at
            finished_at
            progress_pages
        }
    }
}
"""

UPDATE_USER_BOOK_READ_MUTATION = """
mutation UpdateUserBookRead($id: Int!, $object: DatesReadInput!) {
    update_user_book_read(id: $id, object: $object) {
        error
        id
        user_book_read {
            id
            user_book_id
            started_at
            finished_at
            progress_pages
        }
    }
}
"""

FIND_ACTIVE_READ_QUERY = """
query FindActiveRead($user_book_id: Int!) {
    user_book_reads(
        where: {user_book_id: {_eq: $user_book_id}, finished_at: {_is_null: true}},
        order_by: {id: desc},
        limit: 1
    ) {
        id
        started_at
        finished_at
        progress_pages
    }
}
"""

GET_USER_BOOK_READ_QUERY = """
query GetUserBookRead($id: Int!) {
    user_book_reads(where: {id: {_eq: $id}}, limit: 1) {
        id
        started_at
        finished_at
        progress_pages
    }
}
"""


def _merge_read_input(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Merge updates onto existing read fields so unchanged values aren't nulled out."""
    merged: dict[str, Any] = {}
    for field in ("started_at", "finished_at", "progress_pages"):
        if field in updates:
            merged[field] = updates[field]
        elif existing.get(field) is not None:
            merged[field] = existing[field]
    return merged


def _build_read_input(arguments: dict[str, Any]) -> dict[str, Any]:
    """Extract read fields from tool arguments."""
    read_input: dict[str, Any] = {}
    if arguments.get("started_at"):
        read_input["started_at"] = arguments["started_at"]
    if arguments.get("finished_at"):
        read_input["finished_at"] = arguments["finished_at"]
    if arguments.get("progress_pages") is not None:
        read_input["progress_pages"] = int(arguments["progress_pages"])
    return read_input


async def _resolve_user_book_id(arguments: dict[str, Any]) -> int | str:
    """Resolve user_book_id from arguments. Returns int on success, str error message on failure."""
    user_book_id = arguments.get("user_book_id")
    if user_book_id:
        return int(user_book_id)

    book_id = arguments.get("book_id")
    if not book_id:
        return "Error: provide 'book_id' or 'user_book_id'."

    user = await get_current_user()
    existing = await execute(FIND_USER_BOOK_QUERY, {
        "user_id": user["id"], "book_id": int(book_id),
    })
    ubs = existing["data"]["user_books"]
    if not ubs:
        return "Error: book not in your library. Use set_user_book first."
    return ubs[0]["id"]


async def handle_add_user_book_read(arguments: dict[str, Any]) -> list[TextContent]:
    resolved = await _resolve_user_book_id(arguments)
    if isinstance(resolved, str):
        return [TextContent(type="text", text=resolved)]
    user_book_id = resolved

    read_input = _build_read_input(arguments)
    if not read_input:
        return [TextContent(type="text", text="Error: provide at least one of 'started_at', 'finished_at', 'progress_pages'.")]

    # Check for an active (unfinished) read entry — update it instead of creating a duplicate
    active = await execute(FIND_ACTIVE_READ_QUERY, {"user_book_id": user_book_id})
    active_reads = active["data"]["user_book_reads"]

    if active_reads:
        existing_read = active_reads[0]
        merged = _merge_read_input(existing_read, read_input)
        result = await execute(UPDATE_USER_BOOK_READ_MUTATION, {
            "id": existing_read["id"], "object": merged,
        })
        mutation_result = result["data"]["update_user_book_read"]
    else:
        result = await execute(INSERT_USER_BOOK_READ_MUTATION, {
            "userBookId": user_book_id, "userBookRead": read_input,
        })
        mutation_result = result["data"]["insert_user_book_read"]

    if mutation_result.get("error"):
        return [TextContent(type="text", text=f"Error: {mutation_result['error']}")]

    return [TextContent(type="text", text=json.dumps(mutation_result.get("user_book_read", {}), indent=2))]


async def handle_update_user_book_read(arguments: dict[str, Any]) -> list[TextContent]:
    read_id = arguments.get("id")
    if not read_id:
        return [TextContent(type="text", text="Error: 'id' (user_book_read id) is required.")]

    read_input = _build_read_input(arguments)
    if not read_input:
        return [TextContent(type="text", text="Error: provide at least one of 'started_at', 'finished_at', 'progress_pages'.")]

    # Fetch current values and merge so unchanged fields aren't nulled out
    current = await execute(GET_USER_BOOK_READ_QUERY, {"id": int(read_id)})
    current_reads = current["data"]["user_book_reads"]
    if not current_reads:
        return [TextContent(type="text", text="Error: no read entry found with that ID.")]
    merged = _merge_read_input(current_reads[0], read_input)

    result = await execute(UPDATE_USER_BOOK_READ_MUTATION, {
        "id": int(read_id), "object": merged,
    })
    mutation_result = result["data"]["update_user_book_read"]

    if mutation_result.get("error"):
        return [TextContent(type="text", text=f"Error: {mutation_result['error']}")]

    return [TextContent(type="text", text=json.dumps(mutation_result.get("user_book_read", {}), indent=2))]


# ── Write: delete ──

DELETE_USER_BOOK_READ_MUTATION = """
mutation DeleteUserBookRead($id: Int!) {
    delete_user_book_read(id: $id) {
        __typename
    }
}
"""

DELETE_USER_BOOK_MUTATION = """
mutation DeleteUserBook($id: Int!) {
    delete_user_book(id: $id) {
        __typename
    }
}
"""


async def handle_delete_user_book_read(arguments: dict[str, Any]) -> list[TextContent]:
    read_id = arguments.get("id")
    if not read_id:
        return [TextContent(type="text", text="Error: 'id' (user_book_read id) is required.")]

    await execute(DELETE_USER_BOOK_READ_MUTATION, {"id": int(read_id)})
    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": int(read_id)}))]


async def handle_delete_user_book(arguments: dict[str, Any]) -> list[TextContent]:
    resolved = await _resolve_user_book_id(arguments)
    if isinstance(resolved, str):
        return [TextContent(type="text", text=resolved)]

    await execute(DELETE_USER_BOOK_MUTATION, {"id": resolved})
    return [TextContent(type="text", text=json.dumps({"deleted": True, "user_book_id": resolved}))]
