"""Hardcover MCP server — entry point and tool registration."""

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from hardcover_mcp.tools.user import handle_me

server = Server("hardcover")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="me",
            description="Get info about the authenticated Hardcover user (id, username, name, books count).",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "me":
        return await handle_me()

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Entry point for the hardcover-mcp CLI."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
