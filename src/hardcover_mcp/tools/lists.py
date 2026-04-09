"""Tools: get_my_lists, get_list."""

import json

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools.user import get_current_user

PRIVACY_MAP = {
    1: "public",
    2: "followers_only",
    3: "private",
}

GET_MY_LISTS_QUERY = """
query GetMyLists($user_id: Int!) {
    lists(
        where: {user_id: {_eq: $user_id}},
        order_by: {updated_at: desc}
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


def _format_list_summary(lst: dict) -> dict:
    return {
        "id": lst["id"],
        "name": lst["name"],
        "slug": lst["slug"],
        "description": lst.get("description"),
        "books_count": lst["books_count"],
        "privacy": PRIVACY_MAP.get(lst.get("privacy_setting_id"), "unknown"),
        "updated_at": lst.get("updated_at"),
    }


def _format_list_book(lb: dict) -> dict:
    book = lb.get("book", {})
    authors = [c["author"]["name"] for c in book.get("contributions", [])]
    return {
        "position": lb.get("position"),
        "book_id": book.get("id"),
        "title": book.get("title"),
        "slug": book.get("slug"),
        "authors": authors,
    }


async def handle_get_my_lists(arguments: dict) -> list[TextContent]:
    user = await get_current_user()
    user_id = user["id"]

    result = await execute(GET_MY_LISTS_QUERY, {"user_id": user_id})
    lists = result["data"]["lists"]
    formatted = [_format_list_summary(lst) for lst in lists]

    return [TextContent(type="text", text=json.dumps(formatted, indent=2))]


async def handle_get_list(arguments: dict) -> list[TextContent]:
    list_id = arguments.get("id")
    if not list_id:
        return [TextContent(type="text", text="Error: 'id' is required.")]

    book_limit = min(arguments.get("book_limit", 25), 100)
    book_offset = arguments.get("book_offset", 0)

    result = await execute(GET_LIST_BY_ID_QUERY, {
        "id": int(list_id),
        "book_limit": book_limit,
        "book_offset": book_offset,
    })

    lists = result["data"]["lists"]
    if not lists:
        return [TextContent(type="text", text="No list found with that ID.")]

    lst = lists[0]
    output = _format_list_summary(lst)
    output["books"] = [_format_list_book(lb) for lb in lst.get("list_books", [])]

    return [TextContent(type="text", text=json.dumps(output, indent=2))]
