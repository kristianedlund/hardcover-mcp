"""Tools: get_publisher."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.books import SEARCH_QUERY

_DEFAULT_EDITIONS_LIMIT = 20
_MAX_EDITIONS_LIMIT = 100

_PUBLISHER_FIELDS = """
        id
        name
        slug
        editions_count
        state
        parent_publisher {
            name
            slug
        }
        editions(
            limit: $editions_limit,
            offset: $editions_offset,
            order_by: {book: {users_count: desc_nulls_last}}
        ) {
            id
            title
            isbn_13
            edition_format
            book {
                id
                title
                slug
                rating
                release_year
            }
        }
"""

GET_PUBLISHER_BY_ID_QUERY = (
    """
query GetPublisherById($id: bigint!, $editions_limit: Int!, $editions_offset: Int!) {
    publishers(where: {id: {_eq: $id}}, limit: 1) {"""
    + _PUBLISHER_FIELDS
    + """    }
}
"""
)

GET_PUBLISHER_BY_SLUG_QUERY = (
    """
query GetPublisherBySlug($slug: String!, $editions_limit: Int!, $editions_offset: Int!) {
    publishers(where: {slug: {_eq: $slug}}, limit: 1) {"""
    + _PUBLISHER_FIELDS
    + """    }
}
"""
)


def _format_publisher(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten a publisher record into a clean response dict."""
    parent = raw.get("parent_publisher")
    editions = raw.get("editions") or []

    formatted_editions = []
    for e in editions:
        book = e.get("book") or {}
        formatted_editions.append(
            {
                "edition_id": e.get("id"),
                "title": e.get("title"),
                "isbn_13": e.get("isbn_13"),
                "format": e.get("edition_format"),
                "book_id": book.get("id"),
                "book_title": book.get("title"),
                "book_slug": book.get("slug"),
                "rating": book.get("rating"),
                "release_year": book.get("release_year"),
            }
        )

    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "slug": raw.get("slug"),
        "editions_count": raw.get("editions_count"),
        "state": raw.get("state"),
        "parent_publisher": (
            {"name": parent.get("name"), "slug": parent.get("slug")} if parent else None
        ),
        "editions": formatted_editions,
    }


async def handle_get_publisher(arguments: dict[str, Any]) -> list[TextContent]:
    """Look up a publisher by ID, slug, or name."""
    publisher_id = arguments.get("id")
    slug = arguments.get("slug")
    name = arguments.get("name")

    if not publisher_id and not slug and not name:
        return [TextContent(type="text", text="Error: provide 'id', 'slug', or 'name'.")]

    try:
        editions_limit = min(
            _require_int(
                arguments.get("editions_limit", _DEFAULT_EDITIONS_LIMIT), "editions_limit"
            ),
            _MAX_EDITIONS_LIMIT,
        )
        editions_offset = _require_int(arguments.get("editions_offset", 0), "editions_offset")
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    variables: dict[str, Any] = {
        "editions_limit": editions_limit,
        "editions_offset": editions_offset,
    }

    if publisher_id:
        try:
            variables["id"] = _require_int(publisher_id, "id")
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
        result = await execute(GET_PUBLISHER_BY_ID_QUERY, variables)
    elif slug:
        variables["slug"] = slug
        result = await execute(GET_PUBLISHER_BY_SLUG_QUERY, variables)
    else:
        search_result = await execute(
            SEARCH_QUERY,
            {
                "query": name,
                "query_type": "Publisher",
                "per_page": 1,
                "page": 1,
            },
        )
        hits = search_result["data"]["search"]["results"].get("hits", [])
        if not hits:
            return [TextContent(type="text", text="No publisher found.")]
        found_id = hits[0].get("document", {}).get("id")
        if not found_id:
            return [TextContent(type="text", text="No publisher found.")]
        variables["id"] = found_id
        result = await execute(GET_PUBLISHER_BY_ID_QUERY, variables)

    publishers = result["data"]["publishers"]
    if not publishers:
        return [TextContent(type="text", text="No publisher found.")]

    output = _format_publisher(publishers[0])
    return [TextContent(type="text", text=json.dumps(output, indent=2))]
