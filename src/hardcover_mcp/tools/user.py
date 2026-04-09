"""Tools: me (authenticated user info)."""

import json

from mcp.types import TextContent

from hardcover_mcp.client import execute

# Cached after first call — used by other tools that need user_id
_cached_user: dict | None = None

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


async def get_current_user() -> dict:
    """Return the authenticated user, using cache if available."""
    global _cached_user
    if _cached_user is None:
        result = await execute(ME_QUERY)
        users = result["data"]["me"]
        if not users:
            raise RuntimeError("No user returned — is your token valid?")
        _cached_user = users[0]
    return _cached_user


async def handle_me() -> list[TextContent]:
    """Handle the 'me' tool call."""
    user = await get_current_user()
    return [TextContent(type="text", text=json.dumps(user, indent=2))]
