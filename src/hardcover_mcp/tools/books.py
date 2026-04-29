"""Tools: search_books, get_book."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int

SEARCH_QUERY = """
query Search($query: String!, $query_type: String!, $per_page: Int!, $page: Int!) {
    search(query: $query, query_type: $query_type, per_page: $per_page, page: $page) {
        results
    }
}
"""

# All entity types supported by the Hardcover search endpoint
VALID_QUERY_TYPES: frozenset[str] = frozenset(
    {"Book", "Author", "Series", "List", "User", "Publisher", "Character", "Prompt"}
)

# Map each query_type to the output list key in the response JSON
_RESULT_KEY: dict[str, str] = {
    "Book": "books",
    "Author": "authors",
    "Series": "series",
    "List": "lists",
    "User": "users",
    "Publisher": "publishers",
    "Character": "characters",
    "Prompt": "prompts",
}

GET_BOOK_BY_ID_QUERY = """
query GetBookById($id: Int!) {
    books(where: {id: {_eq: $id}}, limit: 1) {
        id
        title
        slug
        subtitle
        description
        release_year
        pages
        rating
        ratings_count
        contributions {
            author {
                name
                slug
            }
        }
    }
}
"""

GET_BOOK_BY_SLUG_QUERY = GET_BOOK_BY_ID_QUERY.replace(
    "GetBookById($id: Int!)", "GetBookBySlug($slug: String!)"
).replace("{id: {_eq: $id}}", "{slug: {_eq: $slug}}")


def _format_book_hit(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from a Book search hit document."""
    return {
        "id": doc.get("id"),
        "title": doc.get("title"),
        "slug": doc.get("slug"),
        "authors": doc.get("author_names", []),
        "release_year": doc.get("release_year"),
        "rating": doc.get("rating"),
        "pages": doc.get("pages"),
        "series": doc.get("featured_series"),
    }


def _format_author_hit(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from an Author search hit document."""
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "slug": doc.get("slug"),
        "books_count": doc.get("books_count"),
        "image": doc.get("image"),
    }


def _format_series_hit(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from a Series search hit document."""
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "slug": doc.get("slug"),
        "books_count": doc.get("books_count"),
    }


def _format_list_hit(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from a List search hit document."""
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "slug": doc.get("slug"),
        "books_count": doc.get("books_count"),
        "user": doc.get("user_username"),
    }


def _format_user_hit(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from a User search hit document."""
    return {
        "id": doc.get("id"),
        "username": doc.get("username"),
        "name": doc.get("name"),
    }


def _format_publisher_hit(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from a Publisher search hit document."""
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "slug": doc.get("slug"),
    }


def _format_character_hit(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from a Character search hit document."""
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "slug": doc.get("slug"),
    }


def _format_prompt_hit(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from a Prompt search hit document."""
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
    }


_HIT_FORMATTERS = {
    "Book": _format_book_hit,
    "Author": _format_author_hit,
    "Series": _format_series_hit,
    "List": _format_list_hit,
    "User": _format_user_hit,
    "Publisher": _format_publisher_hit,
    "Character": _format_character_hit,
    "Prompt": _format_prompt_hit,
}


def _format_search_hit(hit: dict[str, Any], query_type: str = "Book") -> dict[str, Any]:
    """Dispatch a search hit to the appropriate per-type formatter.

    Parameters
    ----------
    hit : dict[str, Any]
        Raw search hit containing a ``document`` field from Typesense.
    query_type : str, optional
        Entity type to format for. Must be one of ``VALID_QUERY_TYPES``.
        Defaults to ``"Book"``.

    Returns
    -------
    dict[str, Any]
        Flattened dict of relevant fields for the given entity type.
    """
    doc = hit.get("document", {})
    formatter = _HIT_FORMATTERS.get(query_type, _format_book_hit)
    return formatter(doc)


async def handle_search_books(arguments: dict[str, Any]) -> list[TextContent]:
    """Search Hardcover for entities matching a query string.

    Parameters
    ----------
    arguments : dict[str, Any]
        Tool arguments. Required: ``query`` (str).
        Optional: ``per_page`` (int, default 10, max 25), ``page`` (int, default 1),
        ``query_type`` (str, default ``"Book"``). Must be one of ``VALID_QUERY_TYPES``.

    Returns
    -------
    list[TextContent]
        JSON with ``found`` count, ``page`` number, and a type-keyed results list
        (e.g. ``"books"`` for ``Book``, ``"authors"`` for ``Author``).
    """
    query = arguments.get("query", "").strip()
    if not query:
        return [TextContent(type="text", text="Error: 'query' is required.")]

    query_type = arguments.get("query_type", "Book")
    if query_type not in VALID_QUERY_TYPES:
        valid = ", ".join(sorted(VALID_QUERY_TYPES))
        return [
            TextContent(
                type="text",
                text=f"Error: invalid query_type '{query_type}'. Must be one of: {valid}.",
            )
        ]

    per_page = min(arguments.get("per_page", 10), 25)
    page = arguments.get("page", 1)

    result = await execute(
        SEARCH_QUERY,
        {
            "query": query,
            "query_type": query_type,
            "per_page": per_page,
            "page": page,
        },
    )

    raw_results = result["data"]["search"]["results"]
    hits = raw_results.get("hits", [])
    found = raw_results.get("found", 0)

    result_key = _RESULT_KEY.get(query_type, "results")
    items = [_format_search_hit(h, query_type) for h in hits]
    output = {"found": found, "page": page, result_key: items}
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def handle_get_book(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch detailed info for a single book by Hardcover ID or slug.

    Parameters
    ----------
    arguments : dict[str, Any]
        Tool arguments. Provide ``id`` (int) or ``slug`` (str).

    Returns
    -------
    list[TextContent]
        JSON with book details including title, authors, pages, and rating.
    """
    book_id = arguments.get("id")
    slug = arguments.get("slug")

    if not book_id and not slug:
        return [TextContent(type="text", text="Error: provide either 'id' or 'slug'.")]

    try:
        if book_id:
            result = await execute(GET_BOOK_BY_ID_QUERY, {"id": _require_int(book_id, "id")})
        else:
            result = await execute(GET_BOOK_BY_SLUG_QUERY, {"slug": slug})
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    books = result["data"]["books"]
    if not books:
        return [TextContent(type="text", text="No book found.")]

    book = books[0]
    # Flatten authors for readability
    book["authors"] = [c["author"]["name"] for c in book.get("contributions", [])]
    del book["contributions"]

    return [TextContent(type="text", text=json.dumps(book, indent=2))]
