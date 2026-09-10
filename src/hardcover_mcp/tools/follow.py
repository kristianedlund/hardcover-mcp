"""Tools: follow_user and unfollow_user."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.activity import GET_USER_ID_BY_USERNAME_QUERY

FOLLOW_USER_MUTATION = """
mutation FollowUser($id: Int!) {
    insert_follow(followable_id: $id, followable_type: "User") {
        follow
        error
    }
}
"""

UNFOLLOW_USER_MUTATION = """
mutation UnfollowUser($id: Int!) {
    delete_follow(followable_id: $id, followable_type: "User") {
        success
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
    follow = result["data"]["insert_follow"]
    if follow.get("error"):
        return [TextContent(type="text", text=f"Error: {follow['error']}")]
    return [TextContent(type="text", text=json.dumps({"followed": bool(follow.get("follow"))}))]


async def handle_unfollow_user(arguments: dict[str, Any]) -> list[TextContent]:
    """Unfollow a Hardcover user by user_id or username."""
    resolved = await _resolve_user_id(arguments)
    if isinstance(resolved, str):
        return [TextContent(type="text", text=resolved)]

    result = await execute(UNFOLLOW_USER_MUTATION, {"id": resolved})
    deleted = result["data"]["delete_follow"]
    if deleted.get("error"):
        return [TextContent(type="text", text=f"Error: {deleted['error']}")]
    return [
        TextContent(type="text", text=json.dumps({"unfollowed": bool(deleted.get("success"))}))
    ]
