"""Tools: get_edition."""

import json
from typing import Any

from mcp.types import TextContent, Tool

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import READ, ToolSpec
from hardcover_mcp.tools._validation import _require_int

# ── Edition field fragment, shared across lookup queries ──

_EDITION_FIELDS = """
        id
        title
        subtitle
        isbn_13
        isbn_10
        asin
        pages
        audio_seconds
        release_date
        edition_format
        physical_format
        publisher {
            id
            name
            slug
        }
        language {
            language
        }
        reading_format {
            format
        }
        book {
            id
            slug
            title
            rating
        }
"""

EDITION_BY_ID_QUERY = (
    """
query GetEditionById($id: Int!) {
    editions(where: {id: {_eq: $id}}, limit: 1) {"""
    + _EDITION_FIELDS
    + """    }
}
"""
)

EDITION_BY_ISBN13_QUERY = (
    """
query GetEditionByIsbn13($isbn_13: String!) {
    editions(where: {isbn_13: {_eq: $isbn_13}}, limit: 1) {"""
    + _EDITION_FIELDS
    + """    }
}
"""
)

EDITION_BY_ASIN_QUERY = (
    """
query GetEditionByAsin($asin: String!) {
    editions(where: {asin: {_eq: $asin}}, limit: 1) {"""
    + _EDITION_FIELDS
    + """    }
}
"""
)


def _format_edition(e: dict[str, Any]) -> dict[str, Any]:
    """Format a raw edition record into a structured response dict.

    Parameters
    ----------
    e : dict[str, Any]
        A single record from the ``editions`` GraphQL response. Expected keys:
        ``id``, ``title``, ``subtitle``, ``isbn_13``, ``isbn_10``, ``asin``,
        ``pages``, ``audio_seconds``, ``release_date``, ``edition_format``,
        ``physical_format``, ``publisher``, ``language``, ``reading_format``,
        and ``book``.

    Returns
    -------
    dict[str, Any]
        Flattened edition dict with nested objects inlined for readability.
    """
    publisher = e.get("publisher") or {}
    language = e.get("language") or {}
    reading_format = e.get("reading_format") or {}
    book = e.get("book") or {}

    return {
        "id": e["id"],
        "title": e.get("title"),
        "subtitle": e.get("subtitle"),
        "isbn_13": e.get("isbn_13"),
        "isbn_10": e.get("isbn_10"),
        "asin": e.get("asin"),
        "pages": e.get("pages"),
        "audio_seconds": e.get("audio_seconds"),
        "release_date": e.get("release_date"),
        "edition_format": e.get("edition_format"),
        "physical_format": e.get("physical_format"),
        "publisher": {
            "id": publisher.get("id"),
            "name": publisher.get("name"),
            "slug": publisher.get("slug"),
        }
        if publisher
        else None,
        "language": language.get("language"),
        "reading_format": reading_format.get("format"),
        "book": {
            "id": book.get("id"),
            "slug": book.get("slug"),
            "title": book.get("title"),
            "rating": book.get("rating"),
        }
        if book
        else None,
    }


async def handle_get_edition(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch a specific edition by Hardcover ID, ISBN-13, or ASIN.

    Parameters
    ----------
    arguments : dict[str, Any]
        Provide exactly one of: ``id`` (int), ``isbn_13`` (str), or ``asin`` (str).

    Returns
    -------
    list[TextContent]
        JSON with edition metadata including publisher, language, reading format,
        and the associated book.

    Raises
    ------
    ValueError
        If ``id`` is provided but cannot be coerced to an integer.
    """
    edition_id = arguments.get("id")
    isbn_13 = arguments.get("isbn_13")
    asin = arguments.get("asin")

    # Exactly one selector must be supplied
    provided = [x for x in (edition_id, isbn_13, asin) if x is not None]
    if len(provided) == 0:
        return [
            TextContent(
                type="text",
                text="Error: provide exactly one of 'id', 'isbn_13', or 'asin'.",
            )
        ]
    if len(provided) > 1:
        return [
            TextContent(
                type="text",
                text="Error: provide exactly one of 'id', 'isbn_13', or 'asin' — not multiple.",
            )
        ]

    if edition_id is not None:
        try:
            result = await execute(EDITION_BY_ID_QUERY, {"id": _require_int(edition_id, "id")})
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
    elif isbn_13 is not None:
        result = await execute(EDITION_BY_ISBN13_QUERY, {"isbn_13": str(isbn_13)})
    else:
        result = await execute(EDITION_BY_ASIN_QUERY, {"asin": str(asin)})

    editions = result["data"]["editions"]
    if not editions:
        return [TextContent(type="text", text="No edition found.")]

    output = _format_edition(editions[0])
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="get_edition",
            description=(
                "Get one specific edition (a particular printing, ebook, or audiobook of a "
                "book) by exactly one of Hardcover id, ISBN-13, or ASIN. Read-only. Returns "
                "format, pages, audio length, release date, language, publisher, and the "
                "parent book. Use this to get the edition_id needed by set_edition_owned, "
                "set_user_book, or audiobook progress; for the work as a whole use get_book."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover edition ID.",
                    },
                    "isbn_13": {
                        "type": "string",
                        "description": "ISBN-13 of the edition (e.g. '9780547928227').",
                    },
                    "asin": {
                        "type": "string",
                        "description": "Amazon ASIN of the edition.",
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_edition,
        toolset="catalog",
    ),
]
