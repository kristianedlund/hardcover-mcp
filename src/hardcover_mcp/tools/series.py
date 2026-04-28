"""Tools: get_series."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int

# ── Read: get_series by id or slug ──

GET_SERIES_BY_ID_QUERY = """
query GetSeriesById($id: Int!) {
    series(where: {id: {_eq: $id}}, limit: 1) {
        id
        name
        slug
        description
        books_count
        primary_books_count
        is_completed
        author {
            name
            slug
        }
        book_series(
            distinct_on: position
            order_by: [{position: asc}, {book: {users_count: desc}}]
            where: {
                book: {canonical_id: {_is_null: true}, is_partial_book: {_eq: false}},
                compilation: {_eq: false}
            }
        ) {
            position
            book {
                id
                slug
                title
                release_year
                rating
                users_count
            }
        }
    }
}
"""

GET_SERIES_BY_SLUG_QUERY = GET_SERIES_BY_ID_QUERY.replace(
    "GetSeriesById($id: Int!)", "GetSeriesBySlug($slug: String!)"
).replace("{id: {_eq: $id}}", "{slug: {_eq: $slug}}")

# Name lookup may return multiple results — pick the best candidate.
GET_SERIES_BY_NAME_QUERY = """
query GetSeriesByName($name: String!) {
    series(
        where: {
            name: {_eq: $name},
            books_count: {_gt: 0},
            canonical_id: {_is_null: true}
        },
        order_by: [{primary_books_count: desc_nulls_last}, {books_count: desc}],
        limit: 5
    ) {
        id
        name
        slug
        description
        books_count
        primary_books_count
        is_completed
        author {
            name
            slug
        }
        book_series(
            distinct_on: position
            order_by: [{position: asc}, {book: {users_count: desc}}]
            where: {
                book: {canonical_id: {_is_null: true}, is_partial_book: {_eq: false}},
                compilation: {_eq: false}
            }
        ) {
            position
            book {
                id
                slug
                title
                release_year
                rating
                users_count
            }
        }
    }
}
"""


def _format_series(s: dict[str, Any]) -> dict[str, Any]:
    """Format a raw series record into a structured response dict."""
    author = s.get("author") or {}
    books = [
        {
            "position": bs.get("position"),
            "book_id": bs["book"]["id"],
            "slug": bs["book"]["slug"],
            "title": bs["book"]["title"],
            "release_year": bs["book"].get("release_year"),
            "rating": bs["book"].get("rating"),
        }
        for bs in s.get("book_series", [])
    ]
    return {
        "id": s["id"],
        "name": s["name"],
        "slug": s["slug"],
        "description": s.get("description"),
        "books_count": s["books_count"],
        "primary_books_count": s.get("primary_books_count"),
        "is_completed": s.get("is_completed"),
        "author": author.get("name"),
        "author_slug": author.get("slug"),
        "books": books,
    }


async def handle_get_series(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch a series by id, slug, or exact name, including books in order.

    Parameters
    ----------
    arguments : dict[str, Any]
        Provide one of: ``id`` (int), ``slug`` (str), or ``name`` (str).

    Returns
    -------
    list[TextContent]
        JSON with series metadata and a ``books`` array in position order.
    """
    series_id = arguments.get("id")
    slug = arguments.get("slug")
    name = arguments.get("name")

    if not series_id and not slug and not name:
        return [TextContent(type="text", text="Error: provide 'id', 'slug', or 'name'.")]

    if series_id:
        try:
            result = await execute(GET_SERIES_BY_ID_QUERY, {"id": _require_int(series_id, "id")})
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
        series_list = result["data"]["series"]
    elif slug:
        result = await execute(GET_SERIES_BY_SLUG_QUERY, {"slug": slug})
        series_list = result["data"]["series"]
    else:
        result = await execute(GET_SERIES_BY_NAME_QUERY, {"name": name})
        series_list = result["data"]["series"]

    if not series_list:
        return [TextContent(type="text", text="No series found.")]

    # Name lookups return multiple candidates; take the top-ranked one.
    output = _format_series(series_list[0])
    return [TextContent(type="text", text=json.dumps(output, indent=2))]
