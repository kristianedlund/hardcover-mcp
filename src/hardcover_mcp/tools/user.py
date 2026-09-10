"""Tools: me (authenticated user info) and get_user (public profile lookup)."""

import json
import time
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.books import resolve_id_by_name

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
    RuntimeError
        If the API returns no user (invalid or expired token).
    """
    global _cached_user, _cached_at
    if _cached_user is None or (time.monotonic() - _cached_at) > _CACHE_TTL:
        result = await execute(ME_QUERY)
        users = result["data"]["me"]
        if not users:
            raise RuntimeError("No user returned — is your token valid?")
        _cached_user = users[0]
        _cached_at = time.monotonic()
    return _cached_user


async def handle_me() -> list[TextContent]:
    """Handle the 'me' tool call."""
    user = await get_current_user()
    return [TextContent(type="text", text=json.dumps(user, indent=2))]


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


def _render_user_query(by: str, with_library: bool, with_status: bool) -> str:
    """Render a users query keyed on ``id`` or ``username``, with optional library.

    Parameters
    ----------
    by : str
        Either ``"id"`` (Int) or ``"username"`` (String) — the lookup key.
    with_library : bool
        Include a ``user_books`` block (recent entries, newest first).
    with_status : bool
        Filter the library block to a single ``status_id``.
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
    return f"""
query GetUser(${by}: {key_type}{library_var}{status_var}) {{
    users(where: {{{by}: {{_eq: ${by}}}}}, limit: 1) {{{_USER_FIELDS}{library_block}
    }}
}}
"""


def _format_user(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten a users record into a clean profile dict.

    Includes a ``library`` list only if the raw record carried ``user_books``
    (i.e. the caller requested it). Library entries respect the API's own
    privacy enforcement — a private user returns an empty list to non-followers.
    """
    from hardcover_mcp.tools.library import PRIVACY_MAP, STATUS_MAP

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
        "privacy": (
            PRIVACY_MAP.get(privacy_id, f"Unknown ({privacy_id})")
            if privacy_id is not None
            else None
        ),
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
    return profile


async def handle_get_user(arguments: dict[str, Any]) -> list[TextContent]:
    """Look up a public Hardcover user profile by id, username, or name.

    Parameters
    ----------
    arguments : dict[str, Any]
        Provide one of: ``id`` (int), ``username`` (str), or ``name`` (str).
        Optional: ``include_library`` (bool, default false) to include recent
        library entries; ``library_status`` (str, e.g. 'Read') to filter them;
        ``library_limit`` (int, default 10, max 50).

    Returns
    -------
    list[TextContent]
        JSON with profile metadata and, if requested, a ``library`` array.
        Library visibility is enforced by the Hardcover API based on the
        target user's privacy setting.
    """
    user_id = arguments.get("id")
    username = arguments.get("username")
    name = arguments.get("name")

    if not user_id and not username and not name:
        return [TextContent(type="text", text="Error: provide 'id', 'username', or 'name'.")]

    from hardcover_mcp.tools.library import STATUS_MAP, _resolve_status_id

    include_library = bool(arguments.get("include_library"))
    library_status = arguments.get("library_status")
    status_id = _resolve_status_id(library_status)
    if library_status is not None and status_id is None:
        valid = ", ".join(STATUS_MAP.values())
        return [
            TextContent(
                type="text",
                text=f"Error: unknown status '{library_status}'. Valid: {valid}",
            )
        ]

    variables: dict[str, Any] = {}
    if include_library:
        try:
            requested = arguments.get("library_limit", _DEFAULT_LIBRARY_LIMIT)
            variables["library_limit"] = min(
                _require_int(requested, "library_limit"),
                _MAX_LIBRARY_LIMIT,
            )
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
        if status_id is not None:
            variables["status_id"] = status_id

    # Resolve name → id via search; then always look up by a concrete key.
    if not user_id and not username:
        user_id = await resolve_id_by_name(name, "User")
        if not user_id:
            return [TextContent(type="text", text="No user found.")]

    if user_id:
        try:
            variables["id"] = _require_int(user_id, "id")
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
        by = "id"
    else:
        variables["username"] = username
        by = "username"

    query = _render_user_query(by, include_library, status_id is not None)
    result = await execute(query, variables)
    users = result["data"]["users"]
    if not users:
        return [TextContent(type="text", text="No user found.")]

    output = _format_user(users[0])
    return [TextContent(type="text", text=json.dumps(output, indent=2))]
