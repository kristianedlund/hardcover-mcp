"""Tools: get_activity_feed (recent reading activity)."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int

_DEFAULT_LIMIT = 25
_MAX_LIMIT = 100

_ACTIVITY_FIELDS = """
        id
        event
        created_at
        likes_count
        book { id slug title }
        user { id username name }
"""

# Followed-user ids for the authenticated account.
FOLLOWED_IDS_QUERY = """
query {
    me {
        followed_users {
            followed_user_id
        }
    }
}
"""

GET_USER_ID_BY_USERNAME_QUERY = """
query GetUserId($username: citext!) {
    users(where: {username: {_eq: $username}}, limit: 1) {
        id
    }
}
"""

FEED_QUERY = (
    """
query ActivityFeed($ids: [Int!], $limit: Int!, $offset: Int!) {
    activities(
        where: {user_id: {_in: $ids}},
        order_by: {created_at: desc},
        limit: $limit,
        offset: $offset
    ) {"""
    + _ACTIVITY_FIELDS
    + """    }
}
"""
)

USER_ACTIVITY_QUERY = (
    """
query UserActivity($user_id: Int!, $limit: Int!, $offset: Int!) {
    activities(
        where: {user_id: {_eq: $user_id}},
        order_by: {created_at: desc},
        limit: $limit,
        offset: $offset
    ) {"""
    + _ACTIVITY_FIELDS
    + """    }
}
"""
)


def _format_activity(a: dict[str, Any]) -> dict[str, Any]:
    """Flatten an activity record into a compact event dict.

    Drops the large raw ``data`` blob; keeps event type, book, user, and timing.
    ``book`` is null for non-book events (e.g. ``ListActivity``).
    """
    book = a.get("book")
    user = a.get("user") or {}
    return {
        "id": a.get("id"),
        "event": a.get("event"),
        "created_at": a.get("created_at"),
        "likes_count": a.get("likes_count"),
        "book": (
            {"id": book["id"], "slug": book.get("slug"), "title": book.get("title")}
            if book
            else None
        ),
        "user": {
            "id": user.get("id"),
            "username": user.get("username"),
            "name": user.get("name"),
        },
    }


async def handle_get_activity_feed(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch recent reading activity, newest first.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``user_id`` (int) or ``username`` (str) to fetch a single
        user's activity. If neither is given, returns the feed of users you
        follow. Pagination: ``limit`` (default 25, max 100), ``offset`` (default 0).

    Returns
    -------
    list[TextContent]
        JSON array of activity events (event type, book, user, timestamp).
    """
    try:
        limit = min(_require_int(arguments.get("limit", _DEFAULT_LIMIT), "limit"), _MAX_LIMIT)
        offset = _require_int(arguments.get("offset", 0), "offset")
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    user_id = arguments.get("user_id")
    username = arguments.get("username")

    if username and not user_id:
        found = await execute(GET_USER_ID_BY_USERNAME_QUERY, {"username": username})
        users = found["data"]["users"]
        if not users:
            return [TextContent(type="text", text=f"No user found for username '{username}'.")]
        user_id = users[0]["id"]

    if user_id:
        try:
            uid = _require_int(user_id, "user_id")
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
        result = await execute(
            USER_ACTIVITY_QUERY, {"user_id": uid, "limit": limit, "offset": offset}
        )
    else:
        followed = await execute(FOLLOWED_IDS_QUERY)
        me = followed["data"]["me"]
        ids = [f["followed_user_id"] for f in (me[0]["followed_users"] if me else [])]
        if not ids:
            return [
                TextContent(
                    type="text",
                    text="You don't follow anyone yet, so your activity feed is empty.",
                )
            ]
        result = await execute(FEED_QUERY, {"ids": ids, "limit": limit, "offset": offset})

    activities = [_format_activity(a) for a in result["data"]["activities"]]
    return [TextContent(type="text", text=json.dumps(activities, indent=2))]
