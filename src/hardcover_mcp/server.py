"""Hardcover MCP server — entry point and tool registration."""

import asyncio
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from hardcover_mcp.tools.authors import handle_get_author
from hardcover_mcp.tools.books import handle_get_book, handle_search_books
from hardcover_mcp.tools.editions import handle_get_edition
from hardcover_mcp.tools.library import (
    handle_add_user_book_read,
    handle_delete_user_book,
    handle_delete_user_book_read,
    handle_get_user_book,
    handle_get_user_library,
    handle_get_user_reviews,
    handle_set_user_book,
    handle_update_user_book_read,
)
from hardcover_mcp.tools.lists import (
    handle_add_book_to_list,
    handle_create_list,
    handle_delete_list,
    handle_get_list,
    handle_get_my_lists,
    handle_remove_book_from_list,
    handle_update_list,
)
from hardcover_mcp.tools.series import handle_get_series
from hardcover_mcp.tools.stats import handle_get_reading_stats
from hardcover_mcp.tools.user import handle_me

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
            description="Get authenticated user info (id, username, name, books count).",
            inputSchema={"type": "object", "properties": {}},
        ),
        lambda args: handle_me(),
    ),
    (
        Tool(
            name="get_reading_stats",
            description=(
                "Get library reading statistics: total books, books per status, "
                "average rating, and books read in a given year."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": (
                            "Year for the 'books_read_this_year' count (default: current year)."
                        ),
                    },
                },
            },
        ),
        handle_get_reading_stats,
    ),
    (
        Tool(
            name="search_books",
            description=(
                "Search Hardcover by title, author, or ISBN. Supports multiple entity types: "
                "books (default), authors, series, lists, users, publishers, characters, "
                "and prompts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (title, author name, ISBN, etc.).",
                    },
                    "query_type": {
                        "type": "string",
                        "description": "Entity type to search (default: 'Book').",
                        "enum": [
                            "Book",
                            "Author",
                            "Series",
                            "List",
                            "User",
                            "Publisher",
                            "Character",
                            "Prompt",
                        ],
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
            description="Get books from your library. Filter by reading status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Status filter (e.g. 'Read', 'Currently Reading').",
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
            description="Get your library entry for a book: status, rating, reads.",
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
            name="get_user_reviews",
            description=(
                "List your reviews, newest first. Includes review text, rating, and book info."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max reviews to return (default 25, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                },
            },
        ),
        handle_get_user_reviews,
    ),
    (
        Tool(
            name="get_my_lists",
            description="Get your Hardcover lists. Returns id, name, books count, privacy.",
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
    (
        Tool(
            name="get_series",
            description="Get a book series by id, slug, or name with books in reading order.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover series ID.",
                    },
                    "slug": {
                        "type": "string",
                        "description": "Series slug (e.g. 'the-stormlight-archive').",
                    },
                    "name": {
                        "type": "string",
                        "description": "Exact series name (e.g. 'The Stormlight Archive').",
                    },
                },
            },
        ),
        handle_get_series,
    ),
    (
        Tool(
            name="get_author",
            description="Get an author's details and books by Hardcover ID, slug, or name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover author ID.",
                    },
                    "slug": {
                        "type": "string",
                        "description": "Author slug (e.g. 'brandon-sanderson').",
                    },
                    "name": {
                        "type": "string",
                        "description": "Author name (e.g. 'Brandon Sanderson').",
                    },
                    "books_limit": {
                        "type": "integer",
                        "description": "Max books to return (default 20, max 100).",
                    },
                },
            },
        ),
        handle_get_author,
    ),
    (
        Tool(
            name="get_edition",
            description="Get edition details by Hardcover ID, ISBN-13, or ASIN.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover edition ID.",
                    },
                    "isbn_13": {
                        "type": "string",
                        "description": "ISBN-13 of the edition (e.g. '9780547928227').",
                    },
                    "asin": {
                        "type": "string",
                        "description": "Amazon ASIN of the edition.",
                    },
                },
            },
        ),
        handle_get_edition,
    ),
    # ── Write: library ──
    (
        Tool(
            name="set_user_book",
            description=(
                "Set a book's status, rating, review, and private notes."
                " Preserves unspecified fields."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID.",
                    },
                    "status": {
                        "type": "string",
                        "description": "Status name (e.g. 'Read') or numeric ID (1-5).",
                    },
                    "rating": {
                        "type": "number",
                        "description": "Rating (e.g. 4.0, 3.5). Omit to leave unchanged.",
                    },
                    "review_raw": {
                        "type": "string",
                        "description": "Plain-text review content (converted to Slate format).",
                    },
                    "review_has_spoilers": {
                        "type": "boolean",
                        "description": "Whether the review contains spoilers.",
                    },
                    "reviewed_at": {
                        "type": "string",
                        "description": "ISO date of the review (e.g. '2025-06-01').",
                    },
                    "private_notes": {
                        "type": "string",
                        "description": "Private notes visible only to you.",
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
            description=(
                "Add a reading date or progress entry. Updates active read if one exists."
                " Supports page progress and audiobook time tracking."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Book ID (auto-resolves your user_book).",
                    },
                    "user_book_id": {
                        "type": "integer",
                        "description": "user_book ID if known (skips lookup).",
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
                    "progress_seconds": {
                        "type": "integer",
                        "description": "Seconds of audiobook listened to so far.",
                    },
                },
            },
        ),
        handle_add_user_book_read,
    ),
    (
        Tool(
            name="update_user_book_read",
            description=(
                "Update a reading date or progress entry. Preserves unspecified fields."
                " Supports page progress and audiobook time tracking."
            ),
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
                    "progress_seconds": {
                        "type": "integer",
                        "description": "Seconds of audiobook listened to so far.",
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
                        "description": "public/followers_only/private. Default: public.",
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
            description="Remove a book from a list. Use id or list_id + book_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "list_book ID. If unknown, use list_id + book_id.",
                    },
                    "list_id": {
                        "type": "integer",
                        "description": "List ID (use with book_id to find list_book).",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Book ID (use with list_id to find list_book).",
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
    """Return all registered MCP tool schemas."""
    return [tool for tool, _ in TOOL_REGISTRY]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch an MCP tool call to the matching handler."""
    handler = _DISPATCH.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return await handler(arguments)
    except Exception as exc:
        return [
            TextContent(
                type="text",
                text=f"Error in {name}: {exc}\n{traceback.format_exc()}",
            )
        ]


async def _run() -> None:
    """Start the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Entry point for the hardcover-mcp CLI."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
