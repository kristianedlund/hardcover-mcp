"""Tools: get_user_library, set_user_book, reading log."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools.user import get_current_user

STATUS_MAP = {
    1: "Want to Read",
    2: "Currently Reading",
    3: "Read",
    4: "Paused",
    5: "Did Not Finish",
    6: "Ignored",
}

STATUS_NAME_TO_ID = {v.lower(): k for k, v in STATUS_MAP.items()}

GET_USER_LIBRARY_QUERY = """
query GetUserLibrary($user_id: Int!, $limit: Int!, $offset: Int!, $status_id: Int) {
    user_books(
        where: {
            user_id: {_eq: $user_id},
            status_id: {_eq: $status_id}
        },
        limit: $limit,
        offset: $offset,
        order_by: {updated_at: desc}
    ) {
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
    }
}
"""

GET_USER_LIBRARY_ALL_QUERY = """
query GetUserLibraryAll($user_id: Int!, $limit: Int!, $offset: Int!) {
    user_books(
        where: {
            user_id: {_eq: $user_id}
        },
        limit: $limit,
        offset: $offset,
        order_by: {updated_at: desc}
    ) {
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
    }
}
"""

COUNT_BY_STATUS_QUERY = """
query CountByStatus($user_id: Int!, $status_id: Int!) {
    user_books_aggregate(
        where: {user_id: {_eq: $user_id}, status_id: {_eq: $status_id}}
    ) {
        aggregate { count }
    }
}
"""

COUNT_ALL_QUERY = """
query CountAll($user_id: Int!) {
    user_books_aggregate(
        where: {user_id: {_eq: $user_id}}
    ) {
        aggregate { count }
    }
}
"""


def _format_user_book(ub: dict) -> dict:
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


async def handle_get_user_library(arguments: dict) -> list[TextContent]:
    user = await get_current_user()
    user_id = user["id"]

    limit = min(arguments.get("limit", 25), 100)
    offset = arguments.get("offset", 0)
    status = arguments.get("status")

    # Resolve status name to ID if provided as string
    status_id = None
    if status is not None:
        if isinstance(status, int):
            status_id = status
        elif isinstance(status, str) and status.isdigit():
            status_id = int(status)
        else:
            status_id = STATUS_NAME_TO_ID.get(str(status).lower())
            if status_id is None:
                valid = ", ".join(STATUS_MAP.values())
                return [TextContent(type="text", text=f"Error: unknown status '{status}'. Valid: {valid}")]

    if status_id is not None:
        result = await execute(GET_USER_LIBRARY_QUERY, {
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
            "status_id": status_id,
        })
        count_result = await execute(COUNT_BY_STATUS_QUERY, {
            "user_id": user_id,
            "status_id": status_id,
        })
    else:
        result = await execute(GET_USER_LIBRARY_ALL_QUERY, {
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
        })
        count_result = await execute(COUNT_ALL_QUERY, {
            "user_id": user_id,
        })

    total = count_result["data"]["user_books_aggregate"]["aggregate"]["count"]
    user_books = result["data"]["user_books"]
    formatted = [_format_user_book(ub) for ub in user_books]

    output = {"total": total, "returned": len(formatted), "offset": offset, "books": formatted}
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


async def handle_set_user_book(arguments: dict) -> list[TextContent]:
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

    # Build the update fields
    obj: dict[str, Any] = {}
    if status_id is not None:
        obj["status_id"] = status_id
    if rating is not None:
        obj["rating"] = float(rating)

    if not obj:
        return [TextContent(type="text", text="Error: provide at least 'status' or 'rating'.")]

    # Check if user_book already exists
    existing = await execute(FIND_USER_BOOK_QUERY, {
        "user_id": user_id,
        "book_id": int(book_id),
    })
    existing_books = existing["data"]["user_books"]

    if existing_books:
        # Update
        ub_id = existing_books[0]["id"]
        result = await execute(UPDATE_USER_BOOK_MUTATION, {"id": ub_id, "object": obj})
        mutation_result = result["data"]["update_user_book"]
    else:
        # Insert
        obj["book_id"] = int(book_id)
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


async def handle_add_user_book_read(arguments: dict) -> list[TextContent]:
    book_id = arguments.get("book_id")
    user_book_id = arguments.get("user_book_id")

    if not book_id and not user_book_id:
        return [TextContent(type="text", text="Error: provide 'book_id' or 'user_book_id'.")]

    # Resolve user_book_id from book_id if needed
    if not user_book_id:
        user = await get_current_user()
        existing = await execute(FIND_USER_BOOK_QUERY, {
            "user_id": user["id"],
            "book_id": int(book_id),
        })
        ubs = existing["data"]["user_books"]
        if not ubs:
            return [TextContent(type="text", text="Error: book not in your library. Use set_user_book first.")]
        user_book_id = ubs[0]["id"]

    read_input: dict[str, Any] = {}
    if arguments.get("started_at"):
        read_input["started_at"] = arguments["started_at"]
    if arguments.get("finished_at"):
        read_input["finished_at"] = arguments["finished_at"]
    if arguments.get("progress_pages") is not None:
        read_input["progress_pages"] = int(arguments["progress_pages"])

    if not read_input:
        return [TextContent(type="text", text="Error: provide at least one of 'started_at', 'finished_at', 'progress_pages'.")]

    result = await execute(INSERT_USER_BOOK_READ_MUTATION, {
        "userBookId": int(user_book_id),
        "userBookRead": read_input,
    })
    mutation_result = result["data"]["insert_user_book_read"]

    if mutation_result.get("error"):
        return [TextContent(type="text", text=f"Error: {mutation_result['error']}")]

    return [TextContent(type="text", text=json.dumps(mutation_result.get("user_book_read", {}), indent=2))]


async def handle_update_user_book_read(arguments: dict) -> list[TextContent]:
    read_id = arguments.get("id")
    if not read_id:
        return [TextContent(type="text", text="Error: 'id' (user_book_read id) is required.")]

    read_input: dict[str, Any] = {}
    if arguments.get("started_at"):
        read_input["started_at"] = arguments["started_at"]
    if arguments.get("finished_at"):
        read_input["finished_at"] = arguments["finished_at"]
    if arguments.get("progress_pages") is not None:
        read_input["progress_pages"] = int(arguments["progress_pages"])

    if not read_input:
        return [TextContent(type="text", text="Error: provide at least one of 'started_at', 'finished_at', 'progress_pages'.")]

    result = await execute(UPDATE_USER_BOOK_READ_MUTATION, {
        "id": int(read_id),
        "object": read_input,
    })
    mutation_result = result["data"]["update_user_book_read"]

    if mutation_result.get("error"):
        return [TextContent(type="text", text=f"Error: {mutation_result['error']}")]

    return [TextContent(type="text", text=json.dumps(mutation_result.get("user_book_read", {}), indent=2))]


DELETE_USER_BOOK_READ_MUTATION = """
mutation DeleteUserBookRead($id: Int!) {
    delete_user_book_read(id: $id) {
        __typename
    }
}
"""


async def handle_delete_user_book_read(arguments: dict) -> list[TextContent]:
    read_id = arguments.get("id")
    if not read_id:
        return [TextContent(type="text", text="Error: 'id' (user_book_read id) is required.")]

    await execute(DELETE_USER_BOOK_READ_MUTATION, {"id": int(read_id)})
    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": int(read_id)}))]
