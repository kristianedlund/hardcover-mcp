"""Tools: get_user_library, set_user_book, reading log."""

import json

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
    else:
        result = await execute(GET_USER_LIBRARY_ALL_QUERY, {
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
        })

    user_books = result["data"]["user_books"]
    formatted = [_format_user_book(ub) for ub in user_books]

    output = {"count": len(formatted), "offset": offset, "books": formatted}
    return [TextContent(type="text", text=json.dumps(output, indent=2))]
