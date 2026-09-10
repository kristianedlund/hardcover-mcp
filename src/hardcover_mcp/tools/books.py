"""Tools: search_books, get_book."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int


def author_names(book: dict[str, Any]) -> list[str]:
    """Flatten a book's contributions into a list of author names."""
    return [c["author"]["name"] for c in (book.get("contributions") or []) if c.get("author")]


SEARCH_QUERY = """
query Search(
    $query: String!, $query_type: String!, $per_page: Int!, $page: Int!,
    $sort: String, $filter_by: String
) {
    search(
        query: $query, query_type: $query_type, per_page: $per_page, page: $page,
        sort: $sort, filter_by: $filter_by
    ) {
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

GET_CHARACTERS_QUERY = """
query GetCharacters($book_id: Int!) {
    characters(where: {book_characters: {book_id: {_eq: $book_id}}}) {
        id
        name
        slug
        description
    }
}
"""


async def resolve_id_by_name(name: str, query_type: str) -> Any:
    """Resolve an entity name to its Hardcover id via the search endpoint.

    Hardcover's GraphQL API disables LIKE operators (403), so name lookups
    go through the Typesense ``search()`` endpoint; callers then fetch full
    details by id. Returns the top-ranked id, or ``None`` if no hit.
    """
    result = await execute(
        SEARCH_QUERY,
        {"query": name, "query_type": query_type, "per_page": 1, "page": 1},
    )
    hits = result["data"]["search"]["results"].get("hits", [])
    if not hits:
        return None
    return hits[0].get("document", {}).get("id")


# Per-type search-hit projection: output_key -> document_key.
_HIT_FIELDS: dict[str, dict[str, str]] = {
    "Book": {
        "id": "id",
        "title": "title",
        "slug": "slug",
        "authors": "author_names",
        "release_year": "release_year",
        "rating": "rating",
        "pages": "pages",
        "series": "featured_series",
    },
    "Author": {
        "id": "id",
        "name": "name",
        "slug": "slug",
        "books_count": "books_count",
        "image": "image",
    },
    "Series": {"id": "id", "name": "name", "slug": "slug", "books_count": "books_count"},
    "List": {
        "id": "id",
        "name": "name",
        "slug": "slug",
        "books_count": "books_count",
        "user": "user_username",
    },
    "User": {"id": "id", "username": "username", "name": "name"},
    "Publisher": {"id": "id", "name": "name", "slug": "slug"},
    "Character": {"id": "id", "name": "name", "slug": "slug"},
    "Prompt": {"id": "id", "name": "name"},
}


def _format_search_hit(hit: dict[str, Any], query_type: str = "Book") -> dict[str, Any]:
    """Project a search hit's document into the fields for its entity type.

    Parameters
    ----------
    hit : dict[str, Any]
        Raw search hit containing a ``document`` field from Typesense.
    query_type : str, optional
        Entity type to format for. Falls back to ``"Book"`` if unknown.

    Returns
    -------
    dict[str, Any]
        Flattened dict of relevant fields for the given entity type.
    """
    doc = hit.get("document", {})
    fields = _HIT_FIELDS.get(query_type, _HIT_FIELDS["Book"])
    out = {out_key: doc.get(doc_key) for out_key, doc_key in fields.items()}
    if out.get("authors") is None and "authors" in out:
        out["authors"] = []
    return out


BOOKS_BY_IDS_QUERY = """
query BooksByIds($ids: [Int!]) {
    books(where: {id: {_in: $ids}}) {
        id
        slug
        title
        rating
        release_year
        contributions {
            author {
                name
            }
        }
    }
}
"""


async def fetch_books_by_ids(ids: list[int]) -> list[dict[str, Any]]:
    """Fetch book summaries for a list of ids, preserving the input order.

    Used by discovery tools (trending, vibes) that receive an ordered list of
    book ids and need to hydrate them into title/authors/rating summaries.
    The ``_in`` query returns rows in arbitrary order, so results are re-sorted
    to match ``ids``. Ids with no matching book are dropped.
    """
    if not ids:
        return []
    result = await execute(BOOKS_BY_IDS_QUERY, {"ids": ids})
    by_id = {
        b["id"]: {
            "book_id": b["id"],
            "slug": b.get("slug"),
            "title": b.get("title"),
            "rating": b.get("rating"),
            "release_year": b.get("release_year"),
            "authors": author_names(b),
        }
        for b in result["data"]["books"]
    }
    return [by_id[i] for i in ids if i in by_id]


async def handle_search_books(arguments: dict[str, Any]) -> list[TextContent]:
    """Search Hardcover for entities matching a query string.

    Parameters
    ----------
    arguments : dict[str, Any]
        Tool arguments. Required: ``query`` (str).
        Optional: ``per_page`` (int, default 10, max 25), ``page`` (int, default 1),
        ``query_type`` (str, default ``"Book"``). Must be one of ``VALID_QUERY_TYPES``.
        ``sort`` (str, e.g. ``"rating:desc"``) and ``filter_by`` (str, e.g.
        ``"release_year:>2020"``) are passed through to the Typesense search engine.

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
            "sort": arguments.get("sort"),
            "filter_by": arguments.get("filter_by"),
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
    book["authors"] = author_names(book)
    del book["contributions"]

    return [TextContent(type="text", text=json.dumps(book, indent=2))]


def _format_character(character: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant fields from a character record.

    Parameters
    ----------
    character : dict[str, Any]
        Raw character object from the Hardcover API.

    Returns
    -------
    dict[str, Any]
        Flat dict with ``id``, ``name``, ``slug``, and ``description``.
    """
    return {
        "id": character.get("id"),
        "name": character.get("name"),
        "slug": character.get("slug"),
        "description": character.get("description"),
    }


async def handle_get_characters(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch characters associated with a book by its Hardcover ID.

    Parameters
    ----------
    arguments : dict[str, Any]
        Tool arguments. Required key: ``book_id`` (int).

    Returns
    -------
    list[TextContent]
        JSON list of characters with ``id``, ``name``, ``slug``, and ``description``.
    """
    book_id = arguments.get("book_id")
    if book_id is None:
        return [TextContent(type="text", text="Error: 'book_id' is required.")]

    try:
        result = await execute(
            GET_CHARACTERS_QUERY,
            {"book_id": _require_int(book_id, "book_id")},
        )
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    characters = result["data"]["characters"]
    if not characters:
        return [TextContent(type="text", text="No characters found for this book.")]

    output = [_format_character(c) for c in characters]
    return [TextContent(type="text", text=json.dumps(output, indent=2))]
