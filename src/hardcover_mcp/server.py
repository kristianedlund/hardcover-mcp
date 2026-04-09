"""Hardcover MCP server — entry point and tool registration."""

import asyncio
import traceback
from typing import Any, Callable, Awaitable

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from hardcover_mcp.tools.user import handle_me
from hardcover_mcp.tools.books import handle_search_books, handle_get_book
from hardcover_mcp.tools.library import (
    handle_get_user_library,
    handle_get_user_book,
    handle_set_user_book,
    handle_add_user_book_read,
    handle_update_user_book_read,
    handle_delete_user_book_read,
    handle_delete_user_book,
)
from hardcover_mcp.tools.lists import (
    handle_get_my_lists,
    handle_get_list,
    handle_create_list,
    handle_update_list,
    handle_delete_list,
    handle_add_book_to_list,
    handle_remove_book_from_list,
)

server = Server("hardcover")

# ── Tool registry ──
# Each entry: (Tool schema, handler function)
# Adding a new tool = one entry here, one handler function. Nothing else.

Handler = Callable[[dict[str, Any]], Awaitable[list[TextContent]]]

TOOL_REGISTRY: list[tuple[Tool, Handler]] = [
    # ── Read ──
    (
        Tool(
            name="me",
            description="Get info about the authenticated Hardcover user (id, username, name, books count).",
            inputSchema={"type": "object", "properties": {}},
        ),
        lambda args: handle_me(),
    ),
    (
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
        handle_search_books,
    ),
    (
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
        handle_get_book,
    ),
    (
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
        handle_get_user_library,
    ),
    (
        Tool(
            name="get_user_book",
            description="Get your library entry for a specific book: status, rating, and reading dates. Use book_id or slug.",
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
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
        handle_get_user_book,
    ),
    (
        Tool(
            name="get_my_lists",
            description="Get your Hardcover lists (scoped to your account). Returns id, name, slug, description, books count, and privacy.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max lists to return (default 50, max 200).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Offset for pagination (default 0).",
                    },
                },
            },
        ),
        handle_get_my_lists,
    ),
    (
        Tool(
            name="get_list",
            description="Get a specific Hardcover list with its books by list ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover list ID (use get_my_lists to find IDs).",
                    },
                    "book_limit": {
                        "type": "integer",
                        "description": "Max books to return (default 25, max 100).",
                    },
                    "book_offset": {
                        "type": "integer",
                        "description": "Offset for book pagination (default 0).",
                    },
                },
                "required": ["id"],
            },
        ),
        handle_get_list,
    ),
    # ── Write: library ──
    (
        Tool(
            name="set_user_book",
            description="Add a book to your library or update its status/rating. Preserves existing fields you don't specify.",
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID.",
                    },
                    "status": {
                        "type": "string",
                        "description": "Status: 'Want to Read', 'Currently Reading', 'Read', 'Paused', 'Did Not Finish', or numeric ID (1-5).",
                    },
                    "rating": {
                        "type": "number",
                        "description": "Rating (e.g. 4.0, 3.5). Omit to leave unchanged.",
                    },
                },
                "required": ["book_id"],
            },
        ),
        handle_set_user_book,
    ),
    (
        Tool(
            name="add_user_book_read",
            description="Add or update a reading date entry for a book. If an active (unfinished) read exists, updates it instead of creating a duplicate.",
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID (will look up your user_book automatically).",
                    },
                    "user_book_id": {
                        "type": "integer",
                        "description": "Directly specify user_book ID if known (avoids extra lookup).",
                    },
                    "started_at": {
                        "type": "string",
                        "description": "Date started reading (ISO 8601, e.g. '2025-01-15').",
                    },
                    "finished_at": {
                        "type": "string",
                        "description": "Date finished reading (ISO 8601, e.g. '2025-02-20').",
                    },
                    "progress_pages": {
                        "type": "integer",
                        "description": "Pages read so far.",
                    },
                },
            },
        ),
        handle_add_user_book_read,
    ),
    (
        Tool(
            name="update_user_book_read",
            description="Update an existing reading date entry (started/finished/progress). Preserves fields you don't specify.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "The user_book_read ID to update.",
                    },
                    "started_at": {
                        "type": "string",
                        "description": "Date started reading (ISO 8601).",
                    },
                    "finished_at": {
                        "type": "string",
                        "description": "Date finished reading (ISO 8601).",
                    },
                    "progress_pages": {
                        "type": "integer",
                        "description": "Pages read so far.",
                    },
                },
                "required": ["id"],
            },
        ),
        handle_update_user_book_read,
    ),
    (
        Tool(
            name="delete_user_book_read",
            description="Delete a reading date entry by its ID. This cannot be undone.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "The user_book_read ID to delete.",
                    },
                },
                "required": ["id"],
            },
        ),
        handle_delete_user_book_read,
    ),
    (
        Tool(
            name="delete_user_book",
            description="Remove a book from your library entirely. This cannot be undone.",
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID (will look up your library entry).",
                    },
                    "user_book_id": {
                        "type": "integer",
                        "description": "Directly specify user_book ID if known.",
                    },
                },
            },
        ),
        handle_delete_user_book,
    ),
    # ── Write: lists ──
    (
        Tool(
            name="create_list",
            description="Create a new Hardcover list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the new list.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description.",
                    },
                    "privacy": {
                        "type": "string",
                        "description": "Privacy: 'public', 'followers_only', 'private'. Default: public.",
                    },
                },
                "required": ["name"],
            },
        ),
        handle_create_list,
    ),
    (
        Tool(
            name="update_list",
            description="Update an existing Hardcover list's name, description, or privacy.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover list ID.",
                    },
                    "name": {
                        "type": "string",
                        "description": "New name.",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description.",
                    },
                    "privacy": {
                        "type": "string",
                        "description": "Privacy: 'public', 'followers_only', 'private'.",
                    },
                },
                "required": ["id"],
            },
        ),
        handle_update_list,
    ),
    (
        Tool(
            name="delete_list",
            description="Delete a Hardcover list by ID. This cannot be undone.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover list ID to delete.",
                    },
                },
                "required": ["id"],
            },
        ),
        handle_delete_list,
    ),
    (
        Tool(
            name="add_book_to_list",
            description="Add a book to a Hardcover list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "list_id": {
                        "type": "integer",
                        "description": "Hardcover list ID.",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID to add.",
                    },
                    "position": {
                        "type": "integer",
                        "description": "Position in the list (optional).",
                    },
                },
                "required": ["list_id", "book_id"],
            },
        ),
        handle_add_book_to_list,
    ),
    (
        Tool(
            name="remove_book_from_list",
            description="Remove a book from a Hardcover list. Provide either the list_book ID directly, or list_id + book_id to look it up.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "The list_book ID (direct). If unknown, provide list_id + book_id instead.",
                    },
                    "list_id": {
                        "type": "integer",
                        "description": "Hardcover list ID (used with book_id to look up the list_book).",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID (used with list_id to look up the list_book).",
                    },
                },
            },
        ),
        handle_remove_book_from_list,
    ),
]

# Build dispatch lookup
_DISPATCH: dict[str, Handler] = {tool.name: handler for tool, handler in TOOL_REGISTRY}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [tool for tool, _ in TOOL_REGISTRY]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handler = _DISPATCH.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return await handler(arguments)
    except Exception as exc:
        return [TextContent(
            type="text",
            text=f"Error in {name}: {exc}\n{traceback.format_exc()}",
        )]


async def _run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Entry point for the hardcover-mcp CLI."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
