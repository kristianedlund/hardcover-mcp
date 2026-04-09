"""Tools: get_my_lists, get_list, create_list, update_list, delete_list, add_book_to_list, remove_book_from_list."""

import json
from typing import Any

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


def _build_list_input(arguments: dict) -> dict[str, Any]:
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
                return {"__error": f"Unknown privacy '{privacy}'. Valid: {', '.join(PRIVACY_MAP.values())}"}
            obj["privacy_setting_id"] = pid
    return obj


async def handle_create_list(arguments: dict) -> list[TextContent]:
    name = arguments.get("name")
    if not name:
        return [TextContent(type="text", text="Error: 'name' is required.")]

    obj = _build_list_input(arguments)
    if "__error" in obj:
        return [TextContent(type="text", text=f"Error: {obj['__error']}")]

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


async def handle_update_list(arguments: dict) -> list[TextContent]:
    list_id = arguments.get("id")
    if not list_id:
        return [TextContent(type="text", text="Error: 'id' is required.")]

    obj = _build_list_input(arguments)
    if "__error" in obj:
        return [TextContent(type="text", text=f"Error: {obj['__error']}")]
    if not obj:
        return [TextContent(type="text", text="Error: provide at least one of 'name', 'description', 'privacy'.")]

    result = await execute(UPDATE_LIST_MUTATION, {"id": int(list_id), "object": obj})
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


async def handle_delete_list(arguments: dict) -> list[TextContent]:
    list_id = arguments.get("id")
    if not list_id:
        return [TextContent(type="text", text="Error: 'id' is required.")]

    result = await execute(DELETE_LIST_MUTATION, {"id": int(list_id)})

    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": int(list_id)}))]


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


async def handle_add_book_to_list(arguments: dict) -> list[TextContent]:
    list_id = arguments.get("list_id")
    book_id = arguments.get("book_id")
    if not list_id or not book_id:
        return [TextContent(type="text", text="Error: 'list_id' and 'book_id' are required.")]

    obj: dict[str, Any] = {
        "list_id": int(list_id),
        "book_id": int(book_id),
    }
    if arguments.get("position") is not None:
        obj["position"] = int(arguments["position"])

    result = await execute(INSERT_LIST_BOOK_MUTATION, {"object": obj})
    mutation_result = result["data"]["insert_list_book"]

    lb = mutation_result.get("list_book", {})
    return [TextContent(type="text", text=json.dumps(lb, indent=2))]


async def handle_remove_book_from_list(arguments: dict) -> list[TextContent]:
    list_book_id = arguments.get("id")
    list_id = arguments.get("list_id")
    book_id = arguments.get("book_id")

    # If no direct list_book id given, look it up by list_id + book_id
    if not list_book_id:
        if not list_id or not book_id:
            return [TextContent(type="text", text="Error: provide 'id' (list_book id) or both 'list_id' and 'book_id'.")]
        result = await execute(FIND_LIST_BOOK_QUERY, {
            "list_id": int(list_id),
            "book_id": int(book_id),
        })
        lbs = result["data"]["list_books"]
        if not lbs:
            return [TextContent(type="text", text="Error: book not found in that list.")]
        list_book_id = lbs[0]["id"]

    result = await execute(DELETE_LIST_BOOK_MUTATION, {"id": int(list_book_id)})

    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": int(list_book_id)}))]
