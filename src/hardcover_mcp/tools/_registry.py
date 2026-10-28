"""Shared types for tool registration: ToolSpec, annotation presets, and toolset names."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from mcp.types import TextContent, Tool, ToolAnnotations

Handler = Callable[[dict[str, Any]], Awaitable[list[TextContent]]]

# Toolsets users can enable via HARDCOVER_TOOLSETS. "core" is always loaded.
CORE = "core"
TOOLSETS = (CORE, "catalog", "library", "lists", "journal", "social")


@dataclass(frozen=True)
class ToolSpec:
    """A tool's MCP schema, its handler, its toolset, and the API token scopes it needs."""

    tool: Tool
    handler: Handler
    toolset: str
    # Hardcover API scopes the tool's queries/mutations require (see the docs' Actions page).
    scopes: tuple[str, ...]


def scopes_for(specs: list[ToolSpec]) -> list[str]:
    """Sorted union of the scopes needed by ``specs``."""
    return sorted({scope for spec in specs for scope in spec.scopes})


# Behavior hints shared across tools. Every tool calls the external Hardcover API.
# Read-only lookups with no side effects.
READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
# Overwrites or removes existing state; repeating with the same args changes nothing further.
UPDATE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True
)
# Permanently deletes a record: the same hints as UPDATE (destructive, safe to repeat).
DELETE = UPDATE
