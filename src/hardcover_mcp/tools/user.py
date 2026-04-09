"""Tools: me (authenticated user info)."""

import json
import time
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute

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
    """Return the authenticated user, using cache if available."""
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
