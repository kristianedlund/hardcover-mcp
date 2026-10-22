"""Tools: search_books, get_book."""

import json
from typing import Any

from mcp.types import TextContent, Tool

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import READ, ToolSpec
from hardcover_mcp.tools._validation import ToolError, _require_int
from hardcover_mcp.tools.editions import handle_get_edition

# Older records leave the role empty; on those the contributions relation says "Author".
_AUTHOR_ROLES = {None, "Author"}


def contributors(book: dict[str, Any]) -> list[dict[str, Any]]:
    """List a book's contributors as ``{name, role}``, in the API's order.

    Reads ``cached_contributors`` (a JSON field, so it adds no query depth) when the query
    selected it, otherwise the ``contributions { contribution author { name } }`` relation
    (search documents carry the same shape under ``contributions``). An empty role is
    reported as ``"Author"``.
    """
    entries = book.get("cached_contributors")
    if entries is None:
        entries = book.get("contributions") or []
    return [
        {"name": c["author"]["name"], "role": c.get("contribution") or "Author"}
        for c in entries
        if (c.get("author") or {}).get("name")
    ]


def author_names(book: dict[str, Any]) -> list[str]:
    """Names of a book's authors, leaving out narrators, translators, illustrators, etc.

    Falls back to the first contributor when none has an author role, so a book with
    contributors never comes back without a name.
    """
    everyone = contributors(book)
    authors = [c["name"] for c in everyone if c["role"] in _AUTHOR_ROLES]
    return authors or [c["name"] for c in everyone[:1]]


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
            contribution
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

GET_EDITIONS_QUERY = """
query GetBookEditions($book_id: Int!, $limit: Int!) {
    editions(where: {book_id: {_eq: $book_id}}, order_by: {users_count: desc}, limit: $limit) {
        id
        title
        edition_format
        physical_format
        pages
        audio_seconds
        release_date
        isbn_13
        asin
        users_count
        language {
            language
        }
        publisher {
            name
        }
        reading_format {
            format
        }
    }
}
"""

_DEFAULT_EDITIONS_LIMIT = 10
_MAX_EDITIONS_LIMIT = 50


def _format_edition_summary(edition: dict[str, Any]) -> dict[str, Any]:
    """Flatten an editions row (nested language/publisher/format names) for get_book."""
    return {
        "id": edition.get("id"),
        "title": edition.get("title"),
        "edition_format": edition.get("edition_format"),
        "physical_format": edition.get("physical_format"),
        "reading_format": (edition.get("reading_format") or {}).get("format"),
        "pages": edition.get("pages"),
        "audio_seconds": edition.get("audio_seconds"),
        "release_date": edition.get("release_date"),
        "isbn_13": edition.get("isbn_13"),
        "asin": edition.get("asin"),
        "language": (edition.get("language") or {}).get("language"),
        "publisher": (edition.get("publisher") or {}).get("name"),
        "users_count": edition.get("users_count"),
    }


GET_CHARACTERS_QUERY = """
query GetCharacters($book_id: bigint!) {
    book_characters(where: {book_id: {_eq: $book_id}}, order_by: {position: asc}) {
        spoiler
        only_mentioned
        character {
            id
            name
            slug
            biography
        }
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
    # ``author_names`` on the document lists every contributor; its contributions carry roles.
    if "authors" in out and doc.get("contributions"):
        out["authors"] = author_names(doc)
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
            contribution
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
        raise ToolError("'query' is required.")

    query_type = arguments.get("query_type", "Book")
    if query_type not in VALID_QUERY_TYPES:
        valid = ", ".join(sorted(VALID_QUERY_TYPES))
        raise ToolError(f"invalid query_type '{query_type}'. Must be one of: {valid}.")

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


_EDITION_KEYS = ("isbn_13", "asin", "edition_id")
_ONE_KEY_ERROR = (
    "provide one of 'id' or 'slug' (the book), or exactly one of 'isbn_13', "
    "'asin', or 'edition_id' (a specific edition)."
)


async def handle_get_book(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch a book by Hardcover ID or slug, or one specific edition by an edition key.

    Parameters
    ----------
    arguments : dict[str, Any]
        Tool arguments. Provide ``id`` (int) or ``slug`` (str) for the book (``id``
        wins if both are given), or exactly one edition key — ``isbn_13`` (str),
        ``asin`` (str), or ``edition_id`` (int) — for that edition (see
        ``handle_get_edition``). Edition keys can't be combined with book keys.
        Optional: ``include_characters`` (bool, default false),
        ``include_editions`` (bool, default false), ``editions_limit``
        (int, default 10, max 50).

    Returns
    -------
    list[TextContent]
        JSON with book details including title, authors, ``contributors`` (every
        contributor as ``{name, role}``, e.g. narrators), pages, and rating, plus
        ``characters`` and ``editions`` arrays when requested; or, for an edition
        key, the edition's details with a summary of its book.
    """
    book_id = arguments.get("id")
    slug = arguments.get("slug")
    edition_keys = {
        key: arguments[key]
        for key in _EDITION_KEYS
        if arguments.get(key) is not None and arguments.get(key) != ""
    }

    if edition_keys:
        if book_id or slug or len(edition_keys) > 1:
            raise ToolError(_ONE_KEY_ERROR)
        if arguments.get("include_characters") or arguments.get("include_editions"):
            raise ToolError(
                "include_characters and include_editions need a book key "
                "('id' or 'slug'); the edition's result includes its book id."
            )
        # The edition lookup calls its id key 'id'; here 'id' means the book.
        key, value = next(iter(edition_keys.items()))
        return await handle_get_edition({"id" if key == "edition_id" else key: value})

    if not book_id and not slug:
        raise ToolError(_ONE_KEY_ERROR)

    editions_limit = min(
        _require_int(arguments.get("editions_limit", _DEFAULT_EDITIONS_LIMIT), "editions_limit"),
        _MAX_EDITIONS_LIMIT,
    )
    if book_id:
        result = await execute(GET_BOOK_BY_ID_QUERY, {"id": _require_int(book_id, "id")})
    else:
        result = await execute(GET_BOOK_BY_SLUG_QUERY, {"slug": slug})

    books = result["data"]["books"]
    if not books:
        return [TextContent(type="text", text="No book found.")]

    book = books[0]
    # Flatten authors for readability
    book["authors"] = author_names(book)
    book["contributors"] = contributors(book)
    del book["contributions"]

    if arguments.get("include_characters"):
        chars = await execute(GET_CHARACTERS_QUERY, {"book_id": book["id"]})
        book["characters"] = [_format_character(bc) for bc in chars["data"]["book_characters"]]

    if arguments.get("include_editions"):
        editions = await execute(
            GET_EDITIONS_QUERY, {"book_id": book["id"], "limit": editions_limit}
        )
        book["editions"] = [_format_edition_summary(e) for e in editions["data"]["editions"]]

    return [TextContent(type="text", text=json.dumps(book, indent=2))]


def _format_character(book_character: dict[str, Any]) -> dict[str, Any]:
    """Flatten a book_characters row into a character dict.

    Parameters
    ----------
    book_character : dict[str, Any]
        Raw ``book_characters`` row from the Hardcover API, with a nested ``character``.

    Returns
    -------
    dict[str, Any]
        Flat dict with ``id``, ``name``, ``slug``, ``biography``, ``spoiler``,
        and ``only_mentioned``.
    """
    character = book_character.get("character") or {}
    return {
        "id": character.get("id"),
        "name": character.get("name"),
        "slug": character.get("slug"),
        "biography": character.get("biography"),
        "spoiler": book_character.get("spoiler"),
        "only_mentioned": book_character.get("only_mentioned"),
    }


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="search_books",
            description=(
                "Full-text search across Hardcover's catalog by title, author, ISBN, or keyword; "
                "set query_type to search authors, series, lists, users, publishers, characters, "
                "or prompts instead of books. Read-only. Returns a total 'found' count, the page "
                "number, and compact hits (id, slug, name/title, plus type-specific fields) "
                "ranked by relevance unless 'sort' is given. Use it to discover ids, then call "
                "get_book, get_author, get_series, etc. for full details. If you already have an "
                "id, slug, or ISBN, call the matching get_* tool directly."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (title, author name, ISBN, etc.).",
                    },
                    "query_type": {
                        "type": "string",
                        "description": "Entity type to search (default: 'Book').",
                        "enum": [
                            "Book",
                            "Author",
                            "Series",
                            "List",
                            "User",
                            "Publisher",
                            "Character",
                            "Prompt",
                        ],
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (default 10, max 25).",
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (default 1).",
                    },
                    "sort": {
                        "type": "string",
                        "description": (
                            "Typesense sort expression, e.g. 'rating:desc' or "
                            "'users_count:desc' for most popular first."
                        ),
                    },
                    "filter_by": {
                        "type": "string",
                        "description": (
                            "Typesense filter expression, e.g. 'release_year:>2020' or "
                            "'release_year:[2020..2024]'."
                        ),
                    },
                },
                "required": ["query"],
            },
            annotations=READ,
        ),
        handle_search_books,
        toolset="core",
        scopes=("read:catalog",),
    ),
    ToolSpec(
        Tool(
            name="get_book",
            description=(
                "Look up a book or one specific edition of it. Read-only. With id or slug: the "
                "book (the work, across all editions) — title, authors, pages, community rating. "
                "With exactly one of isbn_13, asin, or edition_id: that specific printing, ebook, "
                "or audiobook — format, pages, audio length, release date, language, publisher, "
                "and a summary of its book. For a book, include_characters=true adds a "
                "'characters' array in book order (id, name, slug, biography, plus 'spoiler' and "
                "'only_mentioned' flags; don't reveal spoiler characters unless asked), and "
                "include_editions=true adds an 'editions' array, most-read first, up to "
                "editions_limit. Edition ids work with set_user_book (edition_id, owned). Use "
                "search_books first if you only have a title; for your own status/rating of the "
                "book use get_user_book."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover book ID.",
                    },
                    "slug": {
                        "type": "string",
                        "description": "Hardcover book slug (e.g. 'project-hail-mary').",
                    },
                    "isbn_13": {
                        "type": "string",
                        "description": "ISBN-13 of a specific edition (e.g. '9780593135204').",
                    },
                    "asin": {
                        "type": "string",
                        "description": "Amazon ASIN of a specific edition.",
                    },
                    "edition_id": {
                        "type": "integer",
                        "description": "Hardcover edition ID (e.g. from include_editions).",
                    },
                    "include_characters": {
                        "type": "boolean",
                        "description": "With id/slug: also return its characters (default false).",
                    },
                    "include_editions": {
                        "type": "boolean",
                        "description": "With id/slug: also return its editions (default false).",
                    },
                    "editions_limit": {
                        "type": "integer",
                        "description": (
                            "With include_editions: max editions to return (default 10, max 50)."
                        ),
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_book,
        toolset="catalog",
        scopes=("read:catalog",),
    ),
]
