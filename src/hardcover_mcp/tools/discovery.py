"""Tools: get_trending_books and get_vibes (discovery)."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.books import fetch_books_by_ids

# ── Trending ──

_TRENDING_DURATIONS = frozenset({"all", "week", "month", "three_month", "one_year"})
_DEFAULT_TRENDING_LIMIT = 25
_MAX_TRENDING_LIMIT = 100

BOOKS_TRENDING_QUERY = """
query BooksTrending($duration: TrendingDuration, $limit: Int!, $offset: Int!) {
    books_trending(duration: $duration, limit: $limit, offset: $offset) {
        ids
        error
    }
}
"""


async def handle_get_trending_books(arguments: dict[str, Any]) -> list[TextContent]:
    """Return currently trending books, most popular first.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``duration`` (one of 'all', 'week', 'month', 'three_month',
        'one_year'; default 'week'), ``limit`` (default 25, max 100),
        ``offset`` (default 0).

    Returns
    -------
    list[TextContent]
        JSON array of book summaries (id, title, authors, rating, release year).
    """
    duration = arguments.get("duration", "week")
    if duration not in _TRENDING_DURATIONS:
        valid = ", ".join(sorted(_TRENDING_DURATIONS))
        return [
            TextContent(
                type="text", text=f"Error: invalid duration '{duration}'. Must be one of: {valid}."
            )
        ]

    try:
        limit = min(
            _require_int(arguments.get("limit", _DEFAULT_TRENDING_LIMIT), "limit"),
            _MAX_TRENDING_LIMIT,
        )
        offset = _require_int(arguments.get("offset", 0), "offset")
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    result = await execute(
        BOOKS_TRENDING_QUERY, {"duration": duration, "limit": limit, "offset": offset}
    )
    trending = result["data"]["books_trending"]
    if trending.get("error"):
        return [TextContent(type="text", text=f"Error: {trending['error']}")]

    books = await fetch_books_by_ids(trending.get("ids") or [])
    return [TextContent(type="text", text=json.dumps(books, indent=2))]


# ── Vibes (curated recommendation collections) ──

_DEFAULT_VIBES_LIMIT = 10
_MAX_VIBES_LIMIT = 50
_DEFAULT_BOOKS_PER_VIBE = 10
_MAX_BOOKS_PER_VIBE = 50


def _render_vibes_query(featured_only: bool) -> str:
    """Render a vibes query, optionally filtered to featured vibes only."""
    where = "where: {featured: {_eq: true}}, " if featured_only else ""
    return f"""
query GetVibes($limit: Int!, $offset: Int!) {{
    vibes(
        {where}order_by: {{likes_count: desc}},
        limit: $limit,
        offset: $offset
    ) {{
        id
        slug
        title
        description
        featured
        likes_count
        cached_book_ids
    }}
}}
"""


async def handle_get_vibes(arguments: dict[str, Any]) -> list[TextContent]:
    """List Hardcover vibes — curated, themed book recommendation collections.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``featured`` (bool, default true) to return only featured
        vibes; ``limit`` (default 10, max 50) and ``offset`` for vibe
        pagination; ``books_per_vibe`` (int, default 10, max 50) — how many
        books to hydrate per vibe from its ``cached_book_ids``.

    Returns
    -------
    list[TextContent]
        JSON array of vibes, each with metadata and a ``books`` array.
    """
    featured = arguments.get("featured", True)
    try:
        limit = min(
            _require_int(arguments.get("limit", _DEFAULT_VIBES_LIMIT), "limit"), _MAX_VIBES_LIMIT
        )
        offset = _require_int(arguments.get("offset", 0), "offset")
        requested_bpv = arguments.get("books_per_vibe", _DEFAULT_BOOKS_PER_VIBE)
        books_per_vibe = min(
            _require_int(requested_bpv, "books_per_vibe"),
            _MAX_BOOKS_PER_VIBE,
        )
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    result = await execute(_render_vibes_query(bool(featured)), {"limit": limit, "offset": offset})
    vibes = result["data"]["vibes"]

    # Hydrate every vibe's books in one query, then slot them back per vibe (avoids N+1).
    per_vibe_ids = [(v.get("cached_book_ids") or [])[:books_per_vibe] for v in vibes]
    all_ids = list({i for ids in per_vibe_ids for i in ids})
    by_id = {b["book_id"]: b for b in await fetch_books_by_ids(all_ids)}

    output = [
        {
            "id": v.get("id"),
            "slug": v.get("slug"),
            "title": v.get("title"),
            "description": v.get("description"),
            "featured": v.get("featured"),
            "likes_count": v.get("likes_count"),
            "books": [by_id[i] for i in ids if i in by_id],
        }
        for v, ids in zip(vibes, per_vibe_ids, strict=True)
    ]
    return [TextContent(type="text", text=json.dumps(output, indent=2))]
