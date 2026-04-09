"""Hardcover MCP server — entry point and tool registration."""

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from hardcover_mcp.tools.user import handle_me
from hardcover_mcp.tools.books import handle_search_books, handle_get_book
from hardcover_mcp.tools.library import handle_get_user_library

server = Server("hardcover")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="me",
            description="Get info about the authenticated Hardcover user (id, username, name, books count).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="search_books",
            description="Search for books on Hardcover by title, author, or ISBN. Returns id, title, slug, authors, rating, and pages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (title, author name, or ISBN).",
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (default 10, max 25).",
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (default 1).",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_book",
            description="Get detailed info about a specific book by its Hardcover ID or slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover book ID.",
                    },
                    "slug": {
                        "type": "string",
                        "description": "Hardcover book slug (e.g. 'project-hail-mary').",
                    },
                },
            },
        ),
        Tool(
            name="get_user_library",
            description="Get books from your Hardcover library. Optionally filter by status: Want to Read, Currently Reading, Read, Paused, Did Not Finish.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: 'Want to Read', 'Currently Reading', 'Read', 'Paused', 'Did Not Finish'. Omit for all.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max books to return (default 25, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Offset for pagination (default 0).",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "me":
        return await handle_me()
    if name == "search_books":
        return await handle_search_books(arguments)
    if name == "get_book":
        return await handle_get_book(arguments)
    if name == "get_user_library":
        return await handle_get_user_library(arguments)

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Entry point for the hardcover-mcp CLI."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
