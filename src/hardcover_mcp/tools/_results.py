"""The shared result shape for tools that return several items."""

import json
from typing import Any

from mcp.types import TextContent


def list_result(
    key: str, items: list[Any], *, offset: int, total: int | None = None
) -> list[TextContent]:
    """``{total, returned, offset, <key>: items}`` as the tool's text content.

    ``total`` (all matches, not just this page) is included only when the API can count
    them cheaply; tool descriptions say which tools have it.
    """
    output: dict[str, Any] = {} if total is None else {"total": total}
    output.update(returned=len(items), offset=offset)
    output[key] = items
    return [TextContent(type="text", text=json.dumps(output, indent=2))]
