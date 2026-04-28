"""Tools: get_author."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int

# ── Read: get_author by id, slug, or name ──

_AUTHOR_FIELDS = """
        id
        slug
        name
        bio
        books_count
        users_count
        born_year
        death_year
        contributions(
            order_by: {book: {users_count: desc_nulls_last}},
            limit: $books_limit
        ) {
            book {
                id
                slug
                title
                rating
                release_year
            }
        }
"""

GET_AUTHOR_BY_ID_QUERY = (
    """
query GetAuthorById($id: Int!, $books_limit: Int!) {
    authors(where: {id: {_eq: $id}}, limit: 1) {"""
    + _AUTHOR_FIELDS
    + """    }
}
"""
)

GET_AUTHOR_BY_SLUG_QUERY = (
    """
query GetAuthorBySlug($slug: String!, $books_limit: Int!) {
    authors(where: {slug: {_eq: $slug}}, limit: 1) {"""
    + _AUTHOR_FIELDS
    + """    }
}
"""
)

# Name lookup may return multiple candidates — rank by books_count then users_count.
# Uses _eq (exact, case-sensitive) for name matching, consistent with series name lookup.
GET_AUTHOR_BY_NAME_QUERY = (
    """
query GetAuthorByName($name: String!, $books_limit: Int!) {
    authors(
        where: {
            name: {_eq: $name}
        },
        order_by: [
            {books_count: desc_nulls_last},
            {users_count: desc_nulls_last}
        ],
        limit: 5
    ) {"""
    + _AUTHOR_FIELDS
    + """    }
}
"""
)

_DEFAULT_BOOKS_LIMIT = 20
_MAX_BOOKS_LIMIT = 100


def _format_author(a: dict[str, Any]) -> dict[str, Any]:
    """Format a raw author record into a structured response dict.

    Parameters
    ----------
    a : dict[str, Any]
        A single record from the ``authors`` GraphQL response. Expected keys:
        ``id``, ``slug``, ``name``, ``bio``, ``books_count``, ``users_count``,
        ``born_year``, ``death_year``, ``contributions`` (list of
        ``{book: {id, slug, title, rating, release_year}}``).

    Returns
    -------
    dict[str, Any]
        Flattened author dict with a ``books`` list. Contributions with a null
        ``book`` are silently dropped. ``users_count`` is excluded from each
        book entry — it is used for ordering only and is not user-facing.
    """
    books = [
        {
            "book_id": c["book"]["id"],
            "slug": c["book"]["slug"],
            "title": c["book"]["title"],
            "release_year": c["book"].get("release_year"),
            "rating": c["book"].get("rating"),
        }
        for c in a.get("contributions", [])
        if c.get("book")
    ]
    return {
        "id": a["id"],
        "slug": a["slug"],
        "name": a["name"],
        "bio": a.get("bio"),
        "books_count": a.get("books_count"),
        "users_count": a.get("users_count"),
        "born_year": a.get("born_year"),
        "death_year": a.get("death_year"),
        "books": books,
    }


async def handle_get_author(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch an author by id, slug, or name, including their books by popularity.

    Parameters
    ----------
    arguments : dict[str, Any]
        Provide one of: ``id`` (int), ``slug`` (str), or ``name`` (str).
        Optional: ``books_limit`` (int, default 20, max 100).

    Returns
    -------
    list[TextContent]
        JSON with author metadata and a ``books`` array sorted by popularity.
    """
    author_id = arguments.get("id")
    slug = arguments.get("slug")
    name = arguments.get("name")

    if not author_id and not slug and not name:
        return [TextContent(type="text", text="Error: provide 'id', 'slug', or 'name'.")]

    try:
        books_limit = min(
            _require_int(arguments.get("books_limit", _DEFAULT_BOOKS_LIMIT), "books_limit"),
            _MAX_BOOKS_LIMIT,
        )
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    vars: dict[str, Any] = {"books_limit": books_limit}
    if author_id:
        try:
            vars["id"] = _require_int(author_id, "id")
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
        result = await execute(GET_AUTHOR_BY_ID_QUERY, vars)
    elif slug:
        vars["slug"] = slug
        result = await execute(GET_AUTHOR_BY_SLUG_QUERY, vars)
    else:
        vars["name"] = name
        result = await execute(GET_AUTHOR_BY_NAME_QUERY, vars)

    authors = result["data"]["authors"]
    if not authors:
        return [TextContent(type="text", text="No author found.")]

    # Name lookups return multiple ranked candidates; take the top result.
    output = _format_author(authors[0])
    return [TextContent(type="text", text=json.dumps(output, indent=2))]
