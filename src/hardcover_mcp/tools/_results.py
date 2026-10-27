"""The shared result shape for tools that return several items."""

import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.tools._validation import ToolError


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


def mutation_payload(result: dict[str, Any], field: str) -> dict[str, Any]:
    """``result["data"][field]`` of a mutation, or a ``ToolError`` if Hardcover returned null.

    Hardcover answers some rejected writes with a null payload instead of an error.
    """
    payload = (result.get("data") or {}).get(field)
    if payload is None:
        raise ToolError(f"Hardcover didn't confirm the change ({field} returned nothing).")
    return payload


def returned_object(payload: dict[str, Any], key: str, what: str) -> dict[str, Any]:
    """``payload[key]``, or a ``ToolError`` naming ``what`` if it's missing or null."""
    value = payload.get(key)
    if not value:
        raise ToolError(f"Hardcover didn't return the {what}; check whether it was saved.")
    return value
