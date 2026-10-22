"""Hardcover MCP server — entry point and tool registration."""

import asyncio
import os
import sys
import traceback
from collections.abc import Mapping
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent

from hardcover_mcp.client import HardcoverAPIError
from hardcover_mcp.tools import (
    activity,
    authors,
    books,
    discovery,
    follow,
    goals,
    journal,
    library,
    lists,
    prompts,
    publishers,
    series,
    user,
)
from hardcover_mcp.tools._registry import CORE, TOOLSETS, Handler, ToolSpec
from hardcover_mcp.tools._validation import ToolError

# ── Tool registry ──
# Each tool module exports TOOLS: list[ToolSpec] next to its handlers.
# Adding a new tool = one ToolSpec in its module. Adding a new module = one entry here.

_MODULES = (
    user,
    books,
    authors,
    series,
    publishers,
    discovery,
    library,
    goals,
    lists,
    journal,
    activity,
    follow,
    prompts,
)


def _collect_tools() -> list[ToolSpec]:
    """Gather every module's TOOLS and check registry invariants.

    Raises
    ------
    ValueError
        If a tool name is duplicated, a tool lacks annotations, or a toolset is unknown.
    """
    specs = [spec for module in _MODULES for spec in module.TOOLS]
    seen: set[str] = set()
    for spec in specs:
        name = spec.tool.name
        if name in seen:
            raise ValueError(f"Duplicate tool name: {name}")
        seen.add(name)
        if spec.tool.annotations is None:
            raise ValueError(f"Tool {name} has no annotations")
        if spec.toolset not in TOOLSETS:
            raise ValueError(f"Tool {name} has unknown toolset '{spec.toolset}'")
        if not spec.scopes:
            raise ValueError(f"Tool {name} declares no API scopes")
        # Read-only mode and read-only keys must agree: a write scope means the tool writes.
        writes = any(scope.startswith("write:") for scope in spec.scopes)
        if writes == bool(spec.tool.annotations.read_only_hint):
            raise ValueError(f"Tool {name} scopes disagree with its read_only_hint")
    return specs


TOOL_REGISTRY: list[ToolSpec] = _collect_tools()

# ── Tool selection (HARDCOVER_TOOLSETS / HARDCOVER_READ_ONLY) ──

_TRUTHY = {"1", "true", "yes", "on"}


def select_tools(specs: list[ToolSpec], env: Mapping[str, str]) -> list[ToolSpec]:
    """Filter tools by the toolsets and read-only mode configured in ``env``.

    ``HARDCOVER_TOOLSETS`` is a comma-separated list of toolset names (default: all).
    The ``core`` toolset is always included. ``HARDCOVER_READ_ONLY`` set to a truthy
    value keeps only tools annotated as read-only.

    Raises
    ------
    ValueError
        If ``HARDCOVER_TOOLSETS`` names an unknown toolset.
    """
    raw = env.get("HARDCOVER_TOOLSETS", "").strip().lower()
    requested = {name.strip() for name in raw.split(",") if name.strip()}
    if not requested or "all" in requested:
        enabled = set(TOOLSETS)
    else:
        unknown = requested - set(TOOLSETS)
        if unknown:
            raise ValueError(
                f"Unknown toolset(s) in HARDCOVER_TOOLSETS: {', '.join(sorted(unknown))}. "
                f"Valid: all, {', '.join(TOOLSETS)}."
            )
        enabled = requested | {CORE}

    read_only = env.get("HARDCOVER_READ_ONLY", "").strip().lower() in _TRUTHY
    return [
        spec
        for spec in specs
        if spec.toolset in enabled and (not read_only or _is_read_only(spec))
    ]


def _is_read_only(spec: ToolSpec) -> bool:
    """Whether a tool is annotated as read-only."""
    return bool(spec.tool.annotations and spec.tool.annotations.read_only_hint)


_active_tools: list[ToolSpec] = TOOL_REGISTRY
_dispatch: dict[str, Handler] = {spec.tool.name: spec.handler for spec in TOOL_REGISTRY}


def configure(env: Mapping[str, str]) -> None:
    """Set the active tool list from ``env`` (see ``select_tools``)."""
    global _active_tools, _dispatch
    _active_tools = select_tools(TOOL_REGISTRY, env)
    _dispatch = {spec.tool.name: spec.handler for spec in _active_tools}


async def list_tools(ctx: Any, params: Any) -> ListToolsResult:
    """Return the schemas of all enabled MCP tools."""
    return ListToolsResult(tools=[spec.tool for spec in _active_tools])


async def call_tool(ctx: Any, params: Any) -> CallToolResult:
    """Dispatch an MCP tool call to the matching handler."""
    handler = _dispatch.get(params.name)
    if not handler:
        if any(spec.tool.name == params.name for spec in TOOL_REGISTRY):
            text = f"Tool {params.name} is disabled by HARDCOVER_TOOLSETS or HARDCOVER_READ_ONLY."
        else:
            text = f"Unknown tool: {params.name}"
        return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)
    try:
        content = await handler(params.arguments or {})
        return CallToolResult(content=content)
    except ToolError as exc:
        # Bad input or a rejected action: the message is the whole story.
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {exc}")], is_error=True
        )
    except HardcoverAPIError as exc:
        # Known API failures already carry a user-facing message; a traceback adds noise.
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error in {params.name}: {exc}")],
            is_error=True,
        )
    except Exception as exc:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Error in {params.name}: {exc}\n{traceback.format_exc()}",
                )
            ],
            is_error=True,
        )


server = Server("hardcover", on_list_tools=list_tools, on_call_tool=call_tool)


async def _run() -> None:
    """Start the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Entry point for the hardcover-mcp CLI."""
    try:
        configure(os.environ)
    except ValueError as exc:
        sys.exit(f"hardcover-mcp: {exc}")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
