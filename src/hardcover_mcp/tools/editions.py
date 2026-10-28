"""Edition lookup by Hardcover ID, ISBN-13, or ASIN — used by get_book's edition keys."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int

# ── The edition shape every tool returns ──

# Fields behind ``format_edition``. Tools that return editions select these (plus their
# own extras), so an edition has the same keys whichever tool it comes from.
EDITION_FIELDS = """
        id
        title
        edition_format
        physical_format
        pages
        audio_seconds
        release_date
        isbn_13
        asin
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
"""


def format_edition(e: dict[str, Any]) -> dict[str, Any]:
    """The shared edition shape, from a record selected with ``EDITION_FIELDS``.

    ``language`` and ``reading_format`` are flattened to strings; ``publisher`` is
    ``{id, name, slug}`` or None.
    """
    publisher = e.get("publisher")
    return {
        "id": e.get("id"),
        "title": e.get("title"),
        "edition_format": e.get("edition_format"),
        "physical_format": e.get("physical_format"),
        "reading_format": (e.get("reading_format") or {}).get("format"),
        "pages": e.get("pages"),
        "audio_seconds": e.get("audio_seconds"),
        "release_date": e.get("release_date"),
        "isbn_13": e.get("isbn_13"),
        "asin": e.get("asin"),
        "language": (e.get("language") or {}).get("language"),
        "publisher": (
            {key: publisher.get(key) for key in ("id", "name", "slug")} if publisher else None
        ),
    }


# Edition lookup (get_book with an edition key) adds a few fields and the book.
_EDITION_FIELDS = (
    EDITION_FIELDS
    + """
        subtitle
        isbn_10
        book {
            id
            slug
            title
            rating
        }
"""
)

# One query for every edition key: get_book passes ``{id|isbn_13|asin: {_eq: value}}``.
EDITION_LOOKUP_QUERY = (
    """
query GetEdition($where: editions_bool_exp!) {
    editions(where: $where, limit: 1) {"""
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
        The shared edition shape (``format_edition``) plus ``subtitle``, ``isbn_10``,
        and ``book``.
    """
    book = e.get("book") or {}

    return {
        **format_edition(e),
        "subtitle": e.get("subtitle"),
        "isbn_10": e.get("isbn_10"),
        "book": {
            "id": book.get("id"),
            "slug": book.get("slug"),
            "title": book.get("title"),
            "rating": book.get("rating"),
        }
        if book
        else None,
    }


async def fetch_edition(key: str, value: Any) -> list[TextContent]:
    """The edition whose ``key`` (``edition_id``, ``isbn_13``, or ``asin``) is ``value``.

    ``get_book`` checks that exactly one edition key was given before calling this.

    Returns
    -------
    list[TextContent]
        JSON with edition metadata including publisher, language, reading format, and the
        associated book; or "No edition found." when nothing matches.
    """
    if key == "edition_id":
        where = {"id": {"_eq": _require_int(value, "edition_id")}}
    else:
        where = {key: {"_eq": str(value)}}
    editions = (await execute(EDITION_LOOKUP_QUERY, {"where": where}))["data"]["editions"]
    if not editions:
        return [TextContent(type="text", text="No edition found.")]
    return [TextContent(type="text", text=json.dumps(_format_edition(editions[0]), indent=2))]
