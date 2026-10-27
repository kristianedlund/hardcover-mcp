"""Tools: get_trending_books and get_vibes (discovery)."""

from typing import Any

from mcp.types import TextContent, Tool

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import READ, ToolSpec
from hardcover_mcp.tools._results import list_result
from hardcover_mcp.tools._validation import ToolError, _require_bool, _require_count
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
        JSON ``{returned, offset, books}`` of book summaries (id, title, authors,
        rating, release year).
    """
    duration = arguments.get("duration", "week")
    if duration not in _TRENDING_DURATIONS:
        valid = ", ".join(sorted(_TRENDING_DURATIONS))
        raise ToolError(f"invalid duration '{duration}'. Must be one of: {valid}.")

    limit = _require_count(
        arguments.get("limit"),
        "limit",
        default=_DEFAULT_TRENDING_LIMIT,
        minimum=1,
        maximum=_MAX_TRENDING_LIMIT,
    )
    offset = _require_count(arguments.get("offset"), "offset", default=0)

    result = await execute(
        BOOKS_TRENDING_QUERY, {"duration": duration, "limit": limit, "offset": offset}
    )
    trending = result["data"]["books_trending"]
    if trending.get("error"):
        raise ToolError(str(trending["error"]))

    books = await fetch_books_by_ids(trending.get("ids") or [])
    return list_result("books", books, offset=offset)


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
        {where}order_by: [{{likes_count: desc}}, {{id: desc}}],
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
        JSON ``{returned, offset, vibes}``, each vibe with metadata and a ``books`` array.
    """
    featured = _require_bool(arguments.get("featured"), "featured", default=True)
    limit = _require_count(
        arguments.get("limit"),
        "limit",
        default=_DEFAULT_VIBES_LIMIT,
        minimum=1,
        maximum=_MAX_VIBES_LIMIT,
    )
    offset = _require_count(arguments.get("offset"), "offset", default=0)
    books_per_vibe = _require_count(
        arguments.get("books_per_vibe"),
        "books_per_vibe",
        default=_DEFAULT_BOOKS_PER_VIBE,
        maximum=_MAX_BOOKS_PER_VIBE,
    )

    result = await execute(_render_vibes_query(featured), {"limit": limit, "offset": offset})
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
    return list_result("vibes", output, offset=offset)


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="get_trending_books",
            description=(
                "Get the books trending on Hardcover in a time window ('duration', default "
                "'week'), ranked most popular first and paginated with limit/offset. Read-only. "
                "Returns {returned, offset, books} with book_id, slug, title, authors, rating, "
                "and release year. For curated "
                "themed collections use get_vibes; for a custom query use search_books with "
                "sort='users_count:desc'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "duration": {
                        "type": "string",
                        "description": "Time window (default 'week').",
                        "enum": ["all", "week", "month", "three_month", "one_year"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max books to return (default 25, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_trending_books,
        toolset="catalog",
        scopes=("read:catalog",),
    ),
    ToolSpec(
        Tool(
            name="get_vibes",
            description=(
                "List Hardcover 'vibes': curated, themed book recommendation collections (e.g. "
                "'Hidden Gem Fantasy'). Read-only. Only featured vibes are returned unless "
                "featured=false; paginate with limit/offset. Returns {returned, offset, vibes}; "
                "each vibe includes title, description, likes, and up to books_per_vibe books. "
                "For popularity rankings use get_trending_books; for user-made lists use get_list."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "featured": {
                        "type": "boolean",
                        "description": "If true (default), return only featured vibes.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max vibes to return (default 10, max 50).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                    "books_per_vibe": {
                        "type": "integer",
                        "description": "Books to include per vibe (default 10, max 50).",
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_vibes,
        toolset="catalog",
        scopes=("read:catalog", "read:vibes"),
    ),
]
