"""Tools: follow_user and unfollow_user."""

import json
from typing import Any

from mcp.types import TextContent, Tool, ToolAnnotations

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import UPDATE, ToolSpec
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.activity import GET_USER_ID_BY_USERNAME_QUERY

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


async def handle_follow_user(arguments: dict[str, Any]) -> list[TextContent]:
    """Follow a Hardcover user by user_id or username."""
    resolved = await _resolve_user_id(arguments)
    if isinstance(resolved, str):
        return [TextContent(type="text", text=resolved)]

    result = await execute(FOLLOW_USER_MUTATION, {"id": resolved})
    follow = result["data"]["insert_followed_user"]
    if follow.get("error"):
        return [TextContent(type="text", text=f"Error: {follow['error']}")]
    return [
        TextContent(
            type="text", text=json.dumps({"followed": follow.get("followed_user_id") is not None})
        )
    ]


async def handle_unfollow_user(arguments: dict[str, Any]) -> list[TextContent]:
    """Unfollow a Hardcover user by user_id or username."""
    resolved = await _resolve_user_id(arguments)
    if isinstance(resolved, str):
        return [TextContent(type="text", text=resolved)]

    result = await execute(UNFOLLOW_USER_MUTATION, {"id": resolved})
    deleted = result["data"]["delete_followed_user"]
    if deleted.get("error"):
        return [TextContent(type="text", text=f"Error: {deleted['error']}")]
    return [
        TextContent(
            type="text",
            text=json.dumps({"unfollowed": deleted.get("followed_user_id") is not None}),
        )
    ]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="follow_user",
            description=(
                "Follow another Hardcover user, identified by user_id or username (provide one; "
                "user_id wins if both are given). Their activity then appears in "
                "get_activity_feed. Returns {followed: true} on success, or an error message if "
                "the user isn't found or the API rejects it. Reverse with unfollow_user."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "Hardcover user ID to follow.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Username to follow (resolved to an ID).",
                    },
                },
            },
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=True,
            ),
        ),
        handle_follow_user,
        toolset="social",
    ),
    ToolSpec(
        Tool(
            name="unfollow_user",
            description=(
                "Stop following a Hardcover user, identified by user_id or username (provide "
                "one; user_id wins if both are given). Their activity no longer appears in "
                "get_activity_feed. Returns {unfollowed: true} on success, or an error message "
                "if the user isn't found or the API rejects it. Inverse of follow_user."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "Hardcover user ID to unfollow.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Username to unfollow (resolved to an ID).",
                    },
                },
            },
            annotations=UPDATE,
        ),
        handle_unfollow_user,
        toolset="social",
    ),
]
