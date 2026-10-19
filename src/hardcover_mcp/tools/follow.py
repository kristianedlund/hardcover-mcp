"""Tool: set_following — follow or unfollow a Hardcover user."""

import json
from typing import Any

from mcp.types import TextContent, Tool

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import UPDATE, ToolSpec
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.activity import FOLLOWED_IDS_QUERY, GET_USER_ID_BY_USERNAME_QUERY

FOLLOW_USER_MUTATION = """
mutation FollowUser($id: Int!) {
    insert_followed_user(user_id: $id) {
        followed_user_id
        error
    }
}
"""

UNFOLLOW_USER_MUTATION = """
mutation UnfollowUser($id: Int!) {
    delete_followed_user(user_id: $id) {
        followed_user_id
        error
    }
}
"""


async def _resolve_user_id(arguments: dict[str, Any]) -> int | str:
    """Resolve user_id from arguments, looking up username if needed.

    Returns the resolved int id, or an error string.
    """
    user_id = arguments.get("user_id")
    username = arguments.get("username")

    if not user_id and not username:
        return "Error: provide either user_id or username."

    if username and not user_id:
        found = await execute(GET_USER_ID_BY_USERNAME_QUERY, {"username": username})
        users = found["data"]["users"]
        if not users:
            return f"No user found for username '{username}'."
        user_id = users[0]["id"]

    try:
        return _require_int(user_id, "user_id")
    except ValueError as e:
        return f"Error: {e}"


async def _is_following(user_id: int) -> bool:
    """Whether the authenticated user currently follows ``user_id``."""
    result = await execute(FOLLOWED_IDS_QUERY)
    me = result["data"]["me"]
    followed = me[0]["followed_users"] if me else []
    return any(f["followed_user_id"] == user_id for f in followed)


async def handle_set_following(arguments: dict[str, Any]) -> list[TextContent]:
    """Follow or unfollow a Hardcover user so that the follow state matches ``following``.

    Checks the current state first, so repeating a call is a no-op.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``following`` (bool) and one of ``user_id`` (int) or ``username`` (str).

    Returns
    -------
    list[TextContent]
        JSON with ``user_id``, ``following``, and ``changed`` (whether a mutation ran).
    """
    following = arguments.get("following")
    if not isinstance(following, bool):
        return [TextContent(type="text", text="Error: 'following' (true/false) is required.")]

    resolved = await _resolve_user_id(arguments)
    if isinstance(resolved, str):
        return [TextContent(type="text", text=resolved)]

    if await _is_following(resolved) == following:
        output = {"user_id": resolved, "following": following, "changed": False}
        return [TextContent(type="text", text=json.dumps(output, indent=2))]

    if following:
        result = await execute(FOLLOW_USER_MUTATION, {"id": resolved})
        payload = result["data"]["insert_followed_user"]
    else:
        result = await execute(UNFOLLOW_USER_MUTATION, {"id": resolved})
        payload = result["data"]["delete_followed_user"]
    if payload.get("error"):
        return [TextContent(type="text", text=f"Error: {payload['error']}")]

    output = {"user_id": resolved, "following": following, "changed": True}
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="set_following",
            description=(
                "Follow (following=true) or unfollow (following=false) another Hardcover user, "
                "identified by user_id or username (provide one; user_id wins if both are "
                "given). Idempotent: if you already are in the requested state nothing changes. "
                "Followed users' activity appears in get_activity_feed. Returns user_id, "
                "following, and 'changed' (whether anything was done), or an error message if "
                "the user isn't found."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "Hardcover user ID.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Username (resolved to an ID).",
                    },
                    "following": {
                        "type": "boolean",
                        "description": "true to follow, false to unfollow.",
                    },
                },
                "required": ["following"],
            },
            annotations=UPDATE,
        ),
        handle_set_following,
        toolset="social",
        scopes=("read:me", "read:social", "read:users", "write:social"),
    ),
]
