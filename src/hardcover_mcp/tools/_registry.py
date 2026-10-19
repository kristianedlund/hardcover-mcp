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
    """A tool's MCP schema, its handler, and the toolset it belongs to."""

    tool: Tool
    handler: Handler
    toolset: str


# Behavior hints shared across tools. Every tool calls the external Hardcover API.
# Read-only lookups with no side effects.
READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
# Creates new records; repeating the call creates more.
CREATE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True
)
# Overwrites or removes existing state; repeating with the same args changes nothing further.
UPDATE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True
)
# Permanently deletes a record.
DELETE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True
)
