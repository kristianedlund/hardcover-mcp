"""Hardcover MCP server — entry point and tool registration."""

import asyncio
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations

from hardcover_mcp.tools.activity import handle_get_activity_feed
from hardcover_mcp.tools.authors import handle_get_author
from hardcover_mcp.tools.books import handle_get_book, handle_get_characters, handle_search_books
from hardcover_mcp.tools.discovery import handle_get_trending_books, handle_get_vibes
from hardcover_mcp.tools.editions import handle_get_edition
from hardcover_mcp.tools.follow import handle_follow_user, handle_unfollow_user
from hardcover_mcp.tools.goals import handle_get_reading_goal, handle_set_reading_goal
from hardcover_mcp.tools.journal import (
    handle_add_journal_entry,
    handle_delete_journal_entry,
    handle_get_reading_journal,
)
from hardcover_mcp.tools.library import (
    handle_add_user_book_read,
    handle_delete_user_book,
    handle_delete_user_book_read,
    handle_get_owned_books,
    handle_get_user_book,
    handle_get_user_library,
    handle_get_user_reviews,
    handle_set_edition_owned,
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
from hardcover_mcp.tools.prompts import handle_answer_prompt, handle_get_prompts
from hardcover_mcp.tools.publishers import handle_get_publisher
from hardcover_mcp.tools.series import handle_get_series
from hardcover_mcp.tools.stats import handle_get_reading_stats
from hardcover_mcp.tools.user import handle_get_user, handle_me

# ── Tool registry ──
# Each entry: (Tool schema, handler function)
# Adding a new tool = one entry here, one handler function. Nothing else.

Handler = Callable[[dict[str, Any]], Awaitable[list[TextContent]]]

# Behavior hints shared across tools. Every tool calls the external Hardcover API.
# Read-only lookups with no side effects.
_READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
# Creates new records; repeating the call creates more.
_CREATE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True
)
# Overwrites or removes existing state; repeating with the same args changes nothing further.
_UPDATE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True
)
# Permanently deletes a record.
_DELETE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True
)

TOOL_REGISTRY: list[tuple[Tool, Handler]] = [
    # ── Read ──
    (
        Tool(
            name="me",
            description=(
                "Get the profile of the user who owns the configured API token: id, username, "
                "name, and books count. Read-only. Use this to find your own user id; to look "
                "up someone else use get_user. Fails if the token is missing or invalid."
            ),
            inputSchema={"type": "object", "properties": {}},
            annotations=_READ,
        ),
        lambda args: handle_me(),
    ),
    (
        Tool(
            name="get_user",
            description=(
                "Look up another Hardcover user's public profile by id, username, or name "
                "(provide one; name resolves to the top search match). Read-only. Returns bio, "
                "book/follower counts, and privacy. Set include_library=true to also fetch their "
                "recent library entries; a private user's library comes back empty unless you "
                "follow them. For your own profile use me; for their activity use "
                "get_activity_feed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover user ID.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Hardcover username (e.g. 'adam').",
                    },
                    "name": {
                        "type": "string",
                        "description": "Display name to search for (resolves to the top match).",
                    },
                    "include_library": {
                        "type": "boolean",
                        "description": "If true, include recent library entries (default false).",
                    },
                    "library_status": {
                        "type": "string",
                        "description": (
                            "Filter library entries by status (e.g. 'Read', 'Currently Reading')."
                        ),
                    },
                    "library_limit": {
                        "type": "integer",
                        "description": "Max library entries to return (default 10, max 50).",
                    },
                },
            },
            annotations=_READ,
        ),
        handle_get_user,
    ),
    (
        Tool(
            name="get_activity_feed",
            description=(
                "Get recent social activity events (status changes, ratings, reviews, list "
                "updates), newest first. Read-only. Defaults to the feed of users you follow "
                "(empty if you follow nobody); pass user_id or username for one user's activity. "
                "Returns event type, book, user, and timestamp per event. For your own detailed "
                "notes, quotes, and progress log use get_reading_journal; for your review texts "
                "use get_user_reviews."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "Fetch one user's activity by Hardcover user ID.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Fetch one user's activity by username.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max events to return (default 25, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                },
            },
            annotations=_READ,
        ),
        handle_get_activity_feed,
    ),
    (
        Tool(
            name="get_reading_stats",
            description=(
                "Get aggregate statistics for your own library: total books, count per status, "
                "average rating, and books finished in a given year (default: current year). "
                "Read-only. Use for summary numbers; to list the actual books use "
                "get_user_library, and for goal progress use get_reading_goal."
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
            annotations=_READ,
        ),
        handle_get_reading_stats,
    ),
    (
        Tool(
            name="search_books",
            description=(
                "Full-text search across Hardcover's catalog by title, author, ISBN, or keyword; "
                "set query_type to search authors, series, lists, users, publishers, characters, "
                "or prompts instead of books. Read-only. Returns a total 'found' count, the page "
                "number, and compact hits (id, slug, name/title, plus type-specific fields) "
                "ranked by relevance unless 'sort' is given. Use it to discover ids, then call "
                "get_book, get_author, get_series, etc. for full details. If you already have an "
                "id, slug, or ISBN, call the matching get_* tool directly."
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
                    "sort": {
                        "type": "string",
                        "description": (
                            "Typesense sort expression, e.g. 'rating:desc' or "
                            "'users_count:desc' for most popular first."
                        ),
                    },
                    "filter_by": {
                        "type": "string",
                        "description": (
                            "Typesense filter expression, e.g. 'release_year:>2020' or "
                            "'release_year:[2020..2024]'."
                        ),
                    },
                },
                "required": ["query"],
            },
            annotations=_READ,
        ),
        handle_search_books,
    ),
    (
        Tool(
            name="get_book",
            description=(
                "Get catalog details for one book (the work, across all editions) by Hardcover "
                "id or slug, including title, authors, pages, and community rating. Read-only. "
                "Use search_books first if you only have a title. For a specific printing or "
                "ISBN use get_edition; for your own status/rating of the book use get_user_book."
            ),
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
            annotations=_READ,
        ),
        handle_get_book,
    ),
    (
        Tool(
            name="get_characters",
            description=(
                "List the characters linked to a book by its Hardcover book id. Read-only. "
                "Returns each character's id, name, slug, and description (not paginated). "
                "Returns a 'No characters found' message when the book has none. To find a "
                "character by name across all books, use search_books with "
                "query_type='Character'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID.",
                    },
                },
                "required": ["book_id"],
            },
            annotations=_READ,
        ),
        handle_get_characters,
    ),
    (
        Tool(
            name="get_user_library",
            description=(
                "List books in your own library (any status), paginated with limit/offset. "
                "Read-only. Filter by status or by finished-date range (start_date + end_date); "
                "sort by updated, rating, or date_added. Returns user_book_id, book_id, title, "
                "authors, status, rating, and read dates per book. E.g. sort='rating', "
                "order='desc' for top-rated; a date range answers 'what did I read in May?'. "
                "For one book's full entry use get_user_book; for owned copies use "
                "get_owned_books."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Status filter (e.g. 'Read', 'Currently Reading').",
                    },
                    "start_date": {
                        "type": "string",
                        "description": (
                            "Earliest finished_at date (ISO 8601, e.g. '2025-01-01'). "
                            "Must be paired with end_date."
                        ),
                    },
                    "end_date": {
                        "type": "string",
                        "description": (
                            "Latest finished_at date (ISO 8601, e.g. '2025-12-31'). "
                            "Must be paired with start_date."
                        ),
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort field: 'updated' (default), 'rating', or 'date_added'.",  # noqa: E501
                        "enum": ["updated", "rating", "date_added"],
                    },
                    "order": {
                        "type": "string",
                        "description": "Sort direction: 'desc' (default) or 'asc'.",
                        "enum": ["desc", "asc"],
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
            annotations=_READ,
        ),
        handle_get_user_library,
    ),
    (
        Tool(
            name="get_user_book",
            description=(
                "Get your own library entry for one book (by book_id or slug). Read-only. "
                "Returns user_book_id, status, rating, privacy, review, private notes, chosen "
                "edition, and every read entry (with their ids, needed by "
                "update_user_book_read/delete_user_book_read). Returns 'Book not in your "
                "library' if you haven't added it. To browse many books use get_user_library."
            ),
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
            annotations=_READ,
        ),
        handle_get_user_book,
    ),
    (
        Tool(
            name="get_user_reviews",
            description=(
                "List the reviews you have written, newest first, paginated with limit/offset. "
                "Read-only. Returns review text, spoiler flag, rating, review date, and book "
                "info. Only covers your own reviews; for other users' activity use "
                "get_activity_feed. To write or edit a review use set_user_book."
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
            annotations=_READ,
        ),
        handle_get_user_reviews,
    ),
    (
        Tool(
            name="get_owned_books",
            description=(
                "List the editions you have marked as owned (your physical/digital copies), "
                "newest first, paginated with page/per_page. Read-only. Returns total count and, "
                "per book, title, authors, and edition details. Ownership is separate from "
                "reading status: use get_user_library for your reading shelves, and "
                "set_edition_owned to change ownership."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "description": "Page number (default 1).",
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (default 20, max 100).",
                    },
                },
            },
            annotations=_READ,
        ),
        handle_get_owned_books,
    ),
    (
        Tool(
            name="get_reading_goal",
            description=(
                "Get your active (non-archived) reading goals, soonest end date first. "
                "Read-only. Returns each goal's id, target, metric (book/page), progress, date "
                "range, and state; 'goals' is an empty array if you have none. To create or "
                "change a goal use set_reading_goal."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max goals to return (default 10, max 100).",
                    },
                },
            },
            annotations=_READ,
        ),
        handle_get_reading_goal,
    ),
    (
        Tool(
            name="get_my_lists",
            description=(
                "List the lists you own, most recently updated first, paginated with "
                "limit/offset. Read-only. Returns id, name, slug, description, books count, and "
                "privacy, but not the books themselves; use get_list with an id for those. "
                "Returns an empty array if you have no lists."
            ),
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
            annotations=_READ,
        ),
        handle_get_my_lists,
    ),
    (
        Tool(
            name="get_list",
            description=(
                "Get one list (yours or another user's) by id, with its books in list order. "
                "Read-only. Returns the list's name, description, privacy, and books count, plus "
                "a 'books' array (position, book_id, title, slug, authors) paginated with "
                "book_limit/book_offset. Find ids with get_my_lists or "
                "search_books(query_type='List')."
            ),
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
            annotations=_READ,
        ),
        handle_get_list,
    ),
    (
        Tool(
            name="get_series",
            description=(
                "Get a book series by id, slug, or name (provide one; a name resolves to the "
                "top search match). Read-only. Returns series info (author, books count, "
                "completed flag) and all its books in reading order with position, title, "
                "release year, and rating. Use search_books(query_type='Series') if a name "
                "might be ambiguous."
            ),
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
            annotations=_READ,
        ),
        handle_get_series,
    ),
    (
        Tool(
            name="get_author",
            description=(
                "Get an author by Hardcover id, slug, or name (provide at least one; a name "
                "resolves to the top search match). Read-only. Returns bio, birth/death year, "
                "book and reader counts, and up to books_limit of their books (title, year, "
                "rating). Use search_books(query_type='Author') to compare several candidates."
            ),
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
            annotations=_READ,
        ),
        handle_get_author,
    ),
    (
        Tool(
            name="get_trending_books",
            description=(
                "Get the books trending on Hardcover in a time window ('duration', default "
                "'week'), ranked most popular first and paginated with limit/offset. Read-only. "
                "Returns book_id, slug, title, authors, rating, and release year. For curated "
                "themed collections use get_vibes; for a custom query use search_books with "
                "sort='users_count:desc'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "duration": {
                        "type": "string",
                        "description": "Time window (default 'week').",
                        "enum": ["all", "week", "month", "three_month", "one_year"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max books to return (default 25, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                },
            },
            annotations=_READ,
        ),
        handle_get_trending_books,
    ),
    (
        Tool(
            name="get_vibes",
            description=(
                "List Hardcover 'vibes': curated, themed book recommendation collections "
                "(e.g. 'Hidden Gem Fantasy'). Read-only. Only featured vibes are returned unless "
                "featured=false. Each vibe includes title, description, likes, and up to "
                "books_per_vibe books. For popularity rankings use get_trending_books; for "
                "user-made lists use get_list."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "featured": {
                        "type": "boolean",
                        "description": "If true (default), return only featured vibes.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max vibes to return (default 10, max 50).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                    "books_per_vibe": {
                        "type": "integer",
                        "description": "Books to include per vibe (default 10, max 50).",
                    },
                },
            },
            annotations=_READ,
        ),
        handle_get_vibes,
    ),
    (
        Tool(
            name="get_publisher",
            description=(
                "Look up a publisher by Hardcover id, slug, or name (provide one; a name "
                "resolves to the top search match). Read-only. Returns name, editions count, "
                "parent publisher, and a page of its editions (edition_id, title, format, book "
                "id/title, rating, release year) via editions_limit/editions_offset."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Hardcover publisher ID.",
                    },
                    "slug": {
                        "type": "string",
                        "description": "Publisher slug (e.g. 'tor-books').",
                    },
                    "name": {
                        "type": "string",
                        "description": "Publisher name (e.g. 'Tor Books').",
                    },
                    "editions_limit": {
                        "type": "integer",
                        "description": "Max editions to return (default 20, max 100).",
                    },
                    "editions_offset": {
                        "type": "integer",
                        "description": "Offset for editions pagination (default 0).",
                    },
                },
            },
            annotations=_READ,
        ),
        handle_get_publisher,
    ),
    (
        Tool(
            name="get_edition",
            description=(
                "Get one specific edition (a particular printing, ebook, or audiobook of a "
                "book) by exactly one of Hardcover id, ISBN-13, or ASIN. Read-only. Returns "
                "format, pages, audio length, release date, language, publisher, and the "
                "parent book. Use this to get the edition_id needed by set_edition_owned, "
                "set_user_book, or audiobook progress; for the work as a whole use get_book."
            ),
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
            annotations=_READ,
        ),
        handle_get_edition,
    ),
    # ── Write: library ──
    (
        Tool(
            name="set_user_book",
            description=(
                "Add a book to your library or update your existing entry for it: status, "
                "rating, review, privacy, private notes, and edition. Upsert: creates the entry "
                "if the book isn't in your library yet, otherwise overwrites only the fields you "
                "pass and preserves the rest. Returns user_book_id, status, privacy, rating, and "
                "edition_id. Use add_user_book_read for start/finish dates and progress; use "
                "add_book_to_list for custom lists; use delete_user_book to remove the book."
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
                    "privacy": {
                        "type": "string",
                        "description": (
                            "Privacy setting: 'Public', 'Followers', or 'Private'"
                            " (or numeric ID 1/2/3)."
                        ),
                    },
                    "edition_id": {
                        "type": "integer",
                        "description": (
                            "Edition ID (from get_edition). Sets which edition you're reading."
                        ),
                    },
                },
                "required": ["book_id"],
            },
            annotations=_UPDATE,
        ),
        handle_set_user_book,
    ),
    (
        Tool(
            name="set_reading_goal",
            description=(
                "Create or update a reading goal. Upsert: if an active goal with the same metric, "
                "start_date, and end_date exists, its target, description, and privacy are "
                "overwritten; otherwise a new goal is created. Returns the goal with id, target, "
                "progress, and state. Use get_reading_goal to see existing goals first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "integer",
                        "description": "Target count to reach by end_date.",
                    },
                    "metric": {
                        "type": "string",
                        "description": "Goal metric: 'book' or 'page'.",
                        "enum": ["book", "page"],
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date (ISO 8601, e.g. '2026-01-01').",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date (ISO 8601, e.g. '2026-12-31').",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional goal description.",
                    },
                    "privacy_setting_id": {
                        "type": "integer",
                        "description": "Optional privacy setting ID.",
                    },
                },
                "required": ["goal", "metric", "start_date", "end_date"],
            },
            annotations=_UPDATE,
        ),
        handle_set_reading_goal,
    ),
    (
        Tool(
            name="set_edition_owned",
            description=(
                "Mark a specific edition as owned (true) or not owned (false). Idempotent: if "
                "the edition is already in the requested state nothing changes. Returns "
                "edition_id, owned, and 'toggled' (whether a change was made). Ownership is "
                "independent of reading status (set_user_book). Get the edition_id from "
                "get_edition (by ISBN-13 or ASIN) first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "edition_id": {
                        "type": "integer",
                        "description": "Edition ID (from get_edition).",
                    },
                    "owned": {
                        "type": "boolean",
                        "description": "true to mark as owned, false to un-own.",
                    },
                },
                "required": ["edition_id", "owned"],
            },
            annotations=_UPDATE,
        ),
        handle_set_edition_owned,
    ),
    (
        Tool(
            name="add_user_book_read",
            description=(
                "Log reading dates or progress for a book already in your library (by book_id or "
                "user_book_id). If the book has an unfinished read, that read is updated with the "
                "fields you pass; otherwise a new read (e.g. a re-read) is created. Supports "
                "page progress and audiobook seconds. Returns the read entry with its id. Use "
                "update_user_book_read to edit a specific past read by id. Add the book with "
                "set_user_book first if it isn't in your library."
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
                    "edition_id": {
                        "type": "integer",
                        "description": "Edition ID (required for audiobook progress tracking).",
                    },
                },
            },
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=False,
                open_world_hint=True,
            ),
        ),
        handle_add_user_book_read,
    ),
    (
        Tool(
            name="update_user_book_read",
            description=(
                "Edit one existing read entry by its user_book_read id (from get_user_book), "
                "e.g. to fix a start/finish date on a past read. Overwrites only the fields you "
                "pass and preserves the rest. Supports page progress and audiobook seconds. "
                "Returns the updated read entry. To log new progress without knowing the id, use "
                "add_user_book_read."
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
                    "edition_id": {
                        "type": "integer",
                        "description": "Edition ID (required for audiobook progress tracking).",
                    },
                },
                "required": ["id"],
            },
            annotations=_UPDATE,
        ),
        handle_update_user_book_read,
    ),
    (
        Tool(
            name="delete_user_book_read",
            description=(
                "Permanently delete one read entry (a single start/finish/progress record) by "
                "its user_book_read id from get_user_book. The book stays in your library with "
                "its status, rating, and review; only that read is removed. Cannot be undone. "
                "Returns {deleted: true, id}. To remove the whole book use delete_user_book."
            ),
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
            annotations=_DELETE,
        ),
        handle_delete_user_book_read,
    ),
    (
        Tool(
            name="delete_user_book",
            description=(
                "Permanently remove a book from your library (by book_id or user_book_id), "
                "including its status, rating, review, and private notes. Cannot be "
                "undone. Returns {deleted: true, user_book_id}. To change status instead use "
                "set_user_book; to remove it only from a custom list use remove_book_from_list."
            ),
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
            annotations=_DELETE,
        ),
        handle_delete_user_book,
    ),
    # ── Write: lists ──
    (
        Tool(
            name="create_list",
            description=(
                "Create a new, empty custom list owned by you. Each call creates a separate "
                "list, so check get_my_lists first to avoid duplicates. Returns the new list's "
                "id, name, slug, description, and privacy. To rename or change an existing list "
                "use update_list; to add books use add_book_to_list with the returned id."
            ),
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
            annotations=_CREATE,
        ),
        handle_create_list,
    ),
    (
        Tool(
            name="update_list",
            description=(
                "Change the name, description, or privacy of a list you own (pass at least one). "
                "Only the fields you pass are overwritten. Returns the updated list. Does not "
                "change the list's books: use add_book_to_list/remove_book_from_list for that, "
                "and create_list to make a new list."
            ),
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
            annotations=_UPDATE,
        ),
        handle_update_list,
    ),
    (
        Tool(
            name="delete_list",
            description=(
                "Permanently delete a list you own by id. The books themselves stay in your "
                "library; only the list and its entries are removed. Cannot be undone. Returns "
                "{deleted: true, id}. To remove a single book use remove_book_from_list."
            ),
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
            annotations=_DELETE,
        ),
        handle_delete_list,
    ),
    (
        Tool(
            name="add_book_to_list",
            description=(
                "Add a book to one of your custom lists, optionally at a given position. Does "
                "not add the book to your library or change its reading status (use "
                "set_user_book for that). Not idempotent: check get_list first if the book may "
                "already be on the list. Returns the new list entry (id, list_id, book_id, "
                "position). Find list ids with get_my_lists and book ids with search_books."
            ),
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
            annotations=_CREATE,
        ),
        handle_add_book_to_list,
    ),
    (
        Tool(
            name="remove_book_from_list",
            description=(
                "Remove a book from one of your custom lists, identified by the list entry id "
                "or by list_id + book_id. The book stays in your library with its status and "
                "rating. Errors if the book isn't on that list. Returns {deleted: true, id}. To "
                "remove the book from your library entirely use delete_user_book."
            ),
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
            annotations=_DELETE,
        ),
        handle_remove_book_from_list,
    ),
    (
        Tool(
            name="get_reading_journal",
            description=(
                "Get your own reading journal, newest first: notes, quotes, status changes, "
                "ratings, reviews, and progress updates. Read-only. Filter by book_id and/or "
                "event type; paginate with limit/offset. Returns each entry's id, event, text, "
                "timestamp, and book. This is your personal log; for what people you follow are "
                "doing use get_activity_feed, and for review texts only use get_user_reviews."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Filter entries to a specific book by Hardcover book ID.",
                    },
                    "event": {
                        "type": "string",
                        "description": (
                            "Filter by event type. Examples: 'note', 'quote', "
                            "'status_currently_reading', 'status_read', 'rated', "
                            "'reviewed', 'progress_updated'."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries to return (default 25, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                },
            },
            annotations=_READ,
        ),
        handle_get_reading_journal,
    ),
    (
        Tool(
            name="add_journal_entry",
            description=(
                "Add a new note or quote to your reading journal for a book. Each call creates a "
                "separate entry; there is no edit tool, so to change one delete it with "
                "delete_journal_entry and add it again. Public by default (privacy_setting_id "
                "1). Returns the created entry with its id. Only notes and quotes can be added "
                "here; status, rating, and progress changes go through set_user_book and "
                "add_user_book_read."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID.",
                    },
                    "entry": {
                        "type": "string",
                        "description": "Journal entry text.",
                    },
                    "event": {
                        "type": "string",
                        "enum": ["note", "quote"],
                        "description": "Journal event type.",
                    },
                    "edition_id": {
                        "type": "integer",
                        "description": "Optional Hardcover edition ID.",
                    },
                    "privacy_setting_id": {
                        "type": "integer",
                        "description": "Optional privacy setting ID (1 public, 2 followers, 3 private).",  # noqa: E501
                    },
                },
                "required": ["book_id", "entry", "event"],
            },
            annotations=_CREATE,
        ),
        handle_add_journal_entry,
    ),
    (
        Tool(
            name="delete_journal_entry",
            description=(
                "Permanently delete one of your reading journal entries by id (from "
                "get_reading_journal). Only that entry is removed; the book, its status, and "
                "other entries are unaffected. Cannot be undone. Returns {deleted: true, id}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Reading journal entry ID.",
                    },
                },
                "required": ["id"],
            },
            annotations=_DELETE,
        ),
        handle_delete_journal_entry,
    ),
    # ── Prompts ──
    (
        Tool(
            name="get_prompts",
            description=(
                "List community book prompts (questions like 'best sci-fi of 2025'), most "
                "answered first, paginated with limit/offset. Read-only. Set featured=true for "
                "featured prompts only. Returns id, question, description, answers_count, and "
                "books_count. Pass a prompt id to answer_prompt to submit a book."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "featured": {
                        "type": "boolean",
                        "description": "If true, return only featured prompts (default false).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max prompts to return (default 25, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                },
            },
            annotations=_READ,
        ),
        handle_get_prompts,
    ),
    (
        Tool(
            name="answer_prompt",
            description=(
                "Submit a book as your answer to a community prompt. Each call inserts a new "
                "answer rather than replacing an earlier one. Returns the created answer (id, "
                "prompt_id, book_id). Find prompt ids with get_prompts and book ids with "
                "search_books."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt_id": {
                        "type": "integer",
                        "description": "Hardcover prompt ID (use get_prompts to find IDs).",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Hardcover book ID to submit as the answer.",
                    },
                },
                "required": ["prompt_id", "book_id"],
            },
            annotations=_CREATE,
        ),
        handle_answer_prompt,
    ),
    # ── Follow ──
    (
        Tool(
            name="follow_user",
            description=(
                "Follow another Hardcover user, identified by user_id or username (provide one; "
                "user_id wins if both are given). Their activity then appears in "
                "get_activity_feed. Returns {followed: true} on success, or an error message if "
                "the user isn't found or the API rejects it. Reverse with unfollow_user."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "Hardcover user ID to follow.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Username to follow (resolved to an ID).",
                    },
                },
            },
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=True,
            ),
        ),
        handle_follow_user,
    ),
    (
        Tool(
            name="unfollow_user",
            description=(
                "Stop following a Hardcover user, identified by user_id or username (provide "
                "one; user_id wins if both are given). Their activity no longer appears in "
                "get_activity_feed. Returns {unfollowed: true} on success, or an error message "
                "if the user isn't found or the API rejects it. Inverse of follow_user."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "integer",
                        "description": "Hardcover user ID to unfollow.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Username to unfollow (resolved to an ID).",
                    },
                },
            },
            annotations=_UPDATE,
        ),
        handle_unfollow_user,
    ),
]

# Build dispatch lookup
_DISPATCH: dict[str, Handler] = {tool.name: handler for tool, handler in TOOL_REGISTRY}


async def list_tools(ctx: Any, params: Any) -> ListToolsResult:
    """Return all registered MCP tool schemas."""
    return ListToolsResult(tools=[tool for tool, _ in TOOL_REGISTRY])


async def call_tool(ctx: Any, params: Any) -> CallToolResult:
    """Dispatch an MCP tool call to the matching handler."""
    handler = _DISPATCH.get(params.name)
    if not handler:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {params.name}")],
            is_error=True,
        )
    try:
        content = await handler(params.arguments or {})
        return CallToolResult(content=content)
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
    asyncio.run(_run())


if __name__ == "__main__":
    main()
