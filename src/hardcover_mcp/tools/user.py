"""Tool: get_user (your profile or another user's), plus the cached current-user lookup."""

import json
import time
from typing import Any

from mcp.types import TextContent, Tool

from hardcover_mcp.client import NEW_API_KEY_URL, HardcoverAPIError, execute
from hardcover_mcp.tools._registry import READ, ToolSpec
from hardcover_mcp.tools._validation import ToolError, _require_int, privacy_label
from hardcover_mcp.tools.books import resolve_id_by_name
from hardcover_mcp.tools.stats import fetch_reading_stats

# Cached after first call — used by other tools that need user_id.
# TTL ensures long-running processes eventually refresh.
_cached_user: dict[str, Any] | None = None
_cached_at: float = 0.0
_CACHE_TTL = 3600.0  # 1 hour

ME_QUERY = """
query {
  me {
    id
    username
    name
    books_count
    followers_count
  }
}
"""


async def get_current_user() -> dict[str, Any]:
    """Return the authenticated user, using a 1-hour cache.

    Returns
    -------
    dict[str, Any]
        User dict with keys: ``id``, ``username``, ``name``, ``books_count``,
        ``followers_count``.

    Raises
    ------
    HardcoverAPIError
        If the API returns no user (invalid or expired token).
    """
    global _cached_user, _cached_at
    if _cached_user is None or (time.monotonic() - _cached_at) > _CACHE_TTL:
        result = await execute(ME_QUERY)
        users = result["data"]["me"]
        if not users:
            raise HardcoverAPIError(
                "Hardcover returned no user for this API token; it may be invalid or "
                f"expired. Create a new key at {NEW_API_KEY_URL}"
            )
        _cached_user = users[0]
        _cached_at = time.monotonic()
    return _cached_user


# ── Read: get_user (public profile by id, username, or name) ──

_USER_FIELDS = """
        id
        username
        name
        bio
        books_count
        followers_count
        followed_users_count
        flair
        pro
        account_privacy_setting_id
        cached_image
        created_at
"""

_DEFAULT_LIBRARY_LIMIT = 10
_MAX_LIBRARY_LIMIT = 50
_DEFAULT_FOLLOW_LIMIT = 25
_MAX_FOLLOW_LIMIT = 100


def _render_user_query(
    by: str,
    with_library: bool,
    with_status: bool,
    with_following: bool = False,
    with_followers: bool = False,
) -> str:
    """Render a users query keyed on ``id`` or ``username``, with optional sections.

    Parameters
    ----------
    by : str
        Either ``"id"`` (Int) or ``"username"`` (String) — the lookup key.
    with_library : bool
        Include a ``user_books`` block (recent entries, newest first).
    with_status : bool
        Filter the library block to a single ``status_id``.
    with_following, with_followers : bool
        Include who the user follows / who follows them (newest first).
    """
    key_type = "Int!" if by == "id" else "citext!"
    status_var = ", $status_id: Int!" if with_status else ""
    status_filter = "status_id: {_eq: $status_id}" if with_status else ""
    library_block = (
        f"""
        user_books(
            where: {{{status_filter}}},
            order_by: {{updated_at: desc}},
            limit: $library_limit
        ) {{
            rating
            status_id
            book {{ id slug title rating release_year }}
        }}"""
        if with_library
        else ""
    )
    library_var = ", $library_limit: Int!" if with_library else ""
    follow_block = ""
    if with_following:
        follow_block += """
        followed_users(order_by: {created_at: desc}, limit: $follow_limit) {
            created_at
            followed_user { id username name }
        }"""
    if with_followers:
        follow_block += """
        followed_by_users(order_by: {created_at: desc}, limit: $follow_limit) {
            created_at
            user { id username name }
        }"""
    follow_var = ", $follow_limit: Int!" if (with_following or with_followers) else ""
    return f"""
query GetUser(${by}: {key_type}{library_var}{status_var}{follow_var}) {{
    users(where: {{{by}: {{_eq: ${by}}}}}, limit: 1) {{{_USER_FIELDS}{library_block}{follow_block}
    }}
}}
"""


def _format_user(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten a users record into a clean profile dict.

    Includes a ``library`` list only if the raw record carried ``user_books``
    (i.e. the caller requested it). Library entries respect the API's own
    privacy enforcement — a private user returns an empty list to non-followers.
    """
    from hardcover_mcp.tools.library import STATUS_MAP

    image = raw.get("cached_image") or {}
    privacy_id = raw.get("account_privacy_setting_id")
    profile: dict[str, Any] = {
        "id": raw.get("id"),
        "username": raw.get("username"),
        "name": raw.get("name"),
        "bio": raw.get("bio"),
        "books_count": raw.get("books_count"),
        "followers_count": raw.get("followers_count"),
        "following_count": raw.get("followed_users_count"),
        "flair": raw.get("flair"),
        "pro": raw.get("pro"),
        "privacy": privacy_label(privacy_id),
        "image_url": image.get("url"),
        "created_at": raw.get("created_at"),
    }
    if "user_books" in raw:
        profile["library"] = [
            {
                "book_id": ub["book"]["id"],
                "slug": ub["book"].get("slug"),
                "title": ub["book"].get("title"),
                "release_year": ub["book"].get("release_year"),
                "rating": ub["book"].get("rating"),
                "your_rating": ub.get("rating"),
                "status": STATUS_MAP.get(ub["status_id"], f"Unknown ({ub['status_id']})"),
            }
            for ub in raw["user_books"]
            if ub.get("book")
        ]
    for key, rel, person in (
        ("following", "followed_users", "followed_user"),
        ("followers", "followed_by_users", "user"),
    ):
        if rel in raw:
            profile[key] = [
                {
                    "id": (row.get(person) or {}).get("id"),
                    "username": (row.get(person) or {}).get("username"),
                    "name": (row.get(person) or {}).get("name"),
                    "since": row.get("created_at"),
                }
                for row in raw[rel]
            ]
    return profile


async def handle_get_user(arguments: dict[str, Any]) -> list[TextContent]:
    """Look up a Hardcover user profile by id, username, or name (default: you).

    Parameters
    ----------
    arguments : dict[str, Any]
        Provide one of: ``id`` (int), ``username`` (str), or ``name`` (str);
        with none of them, the authenticated user's profile is returned.
        Optional: ``include_library`` (bool, default false) to include recent
        library entries; ``library_status`` (str, e.g. 'Read') to filter them;
        ``library_limit`` (int, default 10, max 50); ``include_following`` /
        ``include_followers`` (bool) with ``follow_limit`` (int, default 25, max 100);
        ``include_stats`` (bool, your own profile only) with ``stats_year`` (int).

    Returns
    -------
    list[TextContent]
        JSON with profile metadata and, if requested, ``library``, ``following``,
        ``followers``, and ``stats``.
        Library visibility is enforced by the Hardcover API based on the
        target user's privacy setting.
    """
    user_id = arguments.get("id")
    username = arguments.get("username")
    name = arguments.get("name")

    if not user_id and not username and not name:
        user_id = (await get_current_user())["id"]

    from hardcover_mcp.tools.library import STATUS_MAP, _resolve_status_id

    include_library = bool(arguments.get("include_library"))
    library_status = arguments.get("library_status")
    status_id = _resolve_status_id(library_status)
    if library_status is not None and status_id is None:
        valid = ", ".join(STATUS_MAP.values())
        raise ToolError(f"unknown status '{library_status}'. Valid: {valid}")

    include_following = bool(arguments.get("include_following"))
    include_followers = bool(arguments.get("include_followers"))
    include_stats = bool(arguments.get("include_stats"))

    variables: dict[str, Any] = {}
    if include_following or include_followers:
        requested = arguments.get("follow_limit", _DEFAULT_FOLLOW_LIMIT)
        variables["follow_limit"] = min(_require_int(requested, "follow_limit"), _MAX_FOLLOW_LIMIT)
    stats_year = (
        _require_int(arguments["stats_year"], "stats_year")
        if arguments.get("stats_year") is not None
        else None
    )

    if include_library:
        requested = arguments.get("library_limit", _DEFAULT_LIBRARY_LIMIT)
        variables["library_limit"] = min(
            _require_int(requested, "library_limit"),
            _MAX_LIBRARY_LIMIT,
        )
        if status_id is not None:
            variables["status_id"] = status_id

    # Resolve name → id via search; then always look up by a concrete key.
    if not user_id and not username:
        user_id = await resolve_id_by_name(name, "User")
        if not user_id:
            return [TextContent(type="text", text="No user found.")]

    if user_id:
        variables["id"] = _require_int(user_id, "id")
        by = "id"
    else:
        variables["username"] = username
        by = "username"

    query = _render_user_query(
        by,
        include_library,
        include_library and status_id is not None,
        include_following,
        include_followers,
    )
    result = await execute(query, variables)
    users = result["data"]["users"]
    if not users:
        return [TextContent(type="text", text="No user found.")]

    output = _format_user(users[0])
    if include_stats:
        # Stats aggregate a library; Hardcover only lets you aggregate your own.
        if output["id"] != (await get_current_user())["id"]:
            raise ToolError("include_stats is only available for your own profile.")
        output["stats"] = await fetch_reading_stats(output["id"], stats_year)
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="get_user",
            description=(
                "Get a Hardcover user's profile. With no arguments, returns your own profile "
                "(the owner of the API token) including your user id; otherwise look someone "
                "up by id, username, or name (name resolves to the top search match). "
                "Read-only. Returns bio, book/follower counts, and privacy. Optional sections: "
                "include_library (recent library entries; a private user's comes back empty "
                "unless you follow them), include_following / include_followers (who they "
                "follow / who follows them, newest first), and include_stats (your own profile "
                "only: totals per status, average rating, books read in stats_year, default "
                "this year). For activity use get_activity_feed; to follow someone use "
                "set_following. Fails if the token is missing or invalid."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover user ID.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Hardcover username (e.g. 'adam').",
                    },
                    "name": {
                        "type": "string",
                        "description": "Display name to search for (resolves to the top match).",
                    },
                    "include_library": {
                        "type": "boolean",
                        "description": "If true, include recent library entries (default false).",
                    },
                    "library_status": {
                        "type": "string",
                        "description": (
                            "Filter library entries by status (e.g. 'Read', 'Currently Reading')."
                        ),
                    },
                    "library_limit": {
                        "type": "integer",
                        "description": "Max library entries to return (default 10, max 50).",
                    },
                    "include_following": {
                        "type": "boolean",
                        "description": "Include who the user follows (default false).",
                    },
                    "include_followers": {
                        "type": "boolean",
                        "description": "Include who follows the user (default false).",
                    },
                    "follow_limit": {
                        "type": "integer",
                        "description": "Max people per follow list (default 25, max 100).",
                    },
                    "include_stats": {
                        "type": "boolean",
                        "description": (
                            "Your own profile only: include reading statistics (default false)."
                        ),
                    },
                    "stats_year": {
                        "type": "integer",
                        "description": "Year for books_read_this_year (default: current year).",
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_user,
        toolset="core",
        scopes=("read:catalog", "read:library", "read:me", "read:social", "read:users"),
    ),
]
