"""Tools: get_user_library, get_user_book, set_user_book, ownership, reading log, delete."""

import json
from typing import Any

from mcp.types import TextContent, Tool, ToolAnnotations

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import DELETE, READ, UPDATE, ToolSpec
from hardcover_mcp.tools._results import list_result, mutation_payload, returned_object
from hardcover_mcp.tools._validation import (
    PRIVACY_DESCRIPTION,
    ToolError,
    _require_bool,
    _require_count,
    _require_float,
    _require_int,
    _require_privacy,
    _require_str,
    privacy_label,
)
from hardcover_mcp.tools.books import author_names
from hardcover_mcp.tools.editions import EDITION_FIELDS, format_edition
from hardcover_mcp.tools.user import get_current_user

STATUS_MAP: dict[int, str] = {
    1: "Want to Read",
    2: "Currently Reading",
    3: "Read",
    4: "Paused",
    5: "Did Not Finish",
    6: "Ignored",
}

STATUS_NAME_TO_ID: dict[str, int] = {v.lower(): k for k, v in STATUS_MAP.items()}
# The status names, for the ``enum`` of every status argument's schema.
STATUS_NAMES: list[str] = list(STATUS_MAP.values())

# ── Shared field fragments ──

_USER_BOOK_FIELDS = """
    id
    book_id
    status_id
    rating
    updated_at
    book {
        title
        slug
        contributions {
            contribution
            author {
                name
            }
        }
    }
"""

_USER_BOOK_DETAIL_FIELDS = (
    """
    id
    book_id
    status_id
    privacy_setting_id
    rating
    updated_at
    review_raw
    review_has_spoilers
    reviewed_at
    private_notes
    edition {"""
    + EDITION_FIELDS
    + """    }
    user_book_reads(order_by: {id: desc}) {
        id
        started_at
        finished_at
        progress_pages
        progress_seconds
    }
    book {
        title
        slug
        pages
        contributions {
            contribution
            author {
                name
            }
        }
    }
"""
)


# ── Read: get_user_library (single query, optional status filter) ──

_REVIEW_FIELDS = """
    review_raw
    review_has_spoilers
    reviewed_at
"""

LIBRARY_SORT_FIELDS: dict[str, str] = {
    "updated": "updated_at",
    "rating": "rating",
    "date_added": "date_added",
    "reviewed": "reviewed_at",
}


# Ownership is per edition, kept in the user's "owned" list; filtering through that
# relation keeps the owned filter to one query.
_OWNED_FILTER = ', book: {list_books: {list: {slug: {_eq: "owned"}, user_id: {_eq: $user_id}}}}'


def _render_library_query(
    with_status: bool,
    order_field: str,
    order_dir: str,
    with_review: bool = False,
    with_owned: bool = False,
) -> str:
    """Render a GetUserLibrary query with optional status/review/owned filters and sort.

    ``order_field``/``order_dir`` come from validated maps (never raw user
    input), so they are interpolated directly — Hasura order_by keys are
    enums and can't be GraphQL variables. Entries without a value sort last in
    either direction, and ``id`` breaks ties so ``offset`` pages don't overlap.
    """
    status_filter = ", status_id: {_eq: $status_id}" if with_status else ""
    status_filter += ", has_review: {_eq: true}" if with_review else ""
    status_filter += _OWNED_FILTER if with_owned else ""
    status_var = ", $status_id: Int!" if with_status else ""
    fields = _USER_BOOK_FIELDS + (_REVIEW_FIELDS if with_review else "")
    return f"""
query GetUserLibrary($user_id: Int!, $limit: Int!, $offset: Int!{status_var}) {{
    user_books(
        where: {{user_id: {{_eq: $user_id}}{status_filter}}},
        limit: $limit,
        offset: $offset,
        order_by: [{{{order_field}: {order_dir}_nulls_last}}, {{id: desc}}]
    ) {{
        {fields}
    }}
    user_books_aggregate(
        where: {{user_id: {{_eq: $user_id}}{status_filter}}}
    ) {{
        aggregate {{ count }}
    }}
}}
"""


_USER_BOOK_FIELDS_WITH_READS = (
    _USER_BOOK_FIELDS
    + """
    user_book_reads(
        where: {finished_at: {_gte: $start_date, _lte: $end_date}},
        order_by: {finished_at: desc},
        limit: 1
    ) {
        started_at
        finished_at
    }
"""
)


def _render_library_by_date_query(with_status: bool = False, with_owned: bool = False) -> str:
    """Render the finished-date-range library query, optionally filtered by status or owned.

    Sorted by ``last_read_date`` (the entry's latest finish date): ``user_books`` can't be
    ordered by a read's ``finished_at``, so the caller's sort doesn't apply.
    """
    extra_filter = ", status_id: {_eq: $status_id}" if with_status else ""
    extra_filter += _OWNED_FILTER if with_owned else ""
    status_var = ", $status_id: Int!" if with_status else ""
    return f"""
query GetUserLibraryByDateRange(
    $user_id: Int!, $limit: Int!, $offset: Int!, $start_date: date!, $end_date: date!{status_var}
) {{
    user_books(
        where: {{
            user_id: {{_eq: $user_id}},
            user_book_reads: {{finished_at: {{_gte: $start_date, _lte: $end_date}}}}{extra_filter}
        }},
        limit: $limit,
        offset: $offset,
        order_by: [{{last_read_date: desc_nulls_last}}, {{id: desc}}]
    ) {{
        {_USER_BOOK_FIELDS_WITH_READS}
    }}
    user_books_aggregate(
        where: {{
            user_id: {{_eq: $user_id}},
            user_book_reads: {{finished_at: {{_gte: $start_date, _lte: $end_date}}}}{extra_filter}
        }}
    ) {{
        aggregate {{ count }}
    }}
}}
"""


# ── Read: get_user_book ──

GET_USER_BOOK_QUERY = f"""
query GetUserBook($user_id: Int!, $book_id: Int!) {{
    user_books(
        where: {{user_id: {{_eq: $user_id}}, book_id: {{_eq: $book_id}}}},
        limit: 1,
        order_by: {{updated_at: desc}}
    ) {{
        {_USER_BOOK_DETAIL_FIELDS}
    }}
    # Your lists the book is on, minus the internal Owned list (ownership shows elsewhere).
    list_books(
        where: {{
            book_id: {{_eq: $book_id}},
            list: {{user_id: {{_eq: $user_id}}, slug: {{_neq: "owned"}}}}
        }},
        order_by: [{{list: {{name: asc}}}}, {{id: asc}}]
    ) {{
        position
        list {{
            id
            name
        }}
    }}
}}
"""

GET_BOOK_ID_BY_SLUG_QUERY = """
query GetBookIdBySlug($slug: String!) {
    books(where: {slug: {_eq: $slug}}, limit: 1) {
        id
    }
}
"""


def _format_user_book(ub: dict[str, Any]) -> dict[str, Any]:
    """Format a user_book record into a flat summary dict."""
    book = ub.get("book") or {}
    authors = author_names(book)
    result: dict[str, Any] = {
        "user_book_id": ub["id"],
        "book_id": ub["book_id"],
        "title": book.get("title"),
        "slug": book.get("slug"),
        "authors": authors,
        "status": status_label(ub["status_id"]),
        "rating": ub.get("rating"),
        "updated_at": ub.get("updated_at"),
    }
    reads = ub.get("user_book_reads")
    if reads:
        result["finished_at"] = reads[0].get("finished_at")
        result["started_at"] = reads[0].get("started_at")
    return result


def _list_memberships(list_books: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``{id, name, position}`` per list, once per list even if several editions are on it."""
    lists: dict[int, dict[str, Any]] = {}
    for lb in list_books:
        lst = lb.get("list") or {}
        if lst.get("id") is not None and lst["id"] not in lists:
            lists[lst["id"]] = {
                "id": lst["id"],
                "name": lst.get("name"),
                "position": lb.get("position"),
            }
    return list(lists.values())


def _format_user_book_detail(ub: dict[str, Any]) -> dict[str, Any]:
    """Format a user_book record into a detailed dict including reads, review, and edition."""
    book = ub.get("book") or {}
    authors = author_names(book)
    return {
        "user_book_id": ub["id"],
        "book_id": ub["book_id"],
        "title": book.get("title"),
        "slug": book.get("slug"),
        "pages": book.get("pages"),
        "authors": authors,
        "status": status_label(ub["status_id"]),
        "privacy": privacy_label(ub.get("privacy_setting_id")),
        "rating": ub.get("rating"),
        "updated_at": ub.get("updated_at"),
        "review_raw": ub.get("review_raw"),
        "review_has_spoilers": ub.get("review_has_spoilers"),
        "reviewed_at": ub.get("reviewed_at"),
        "private_notes": ub.get("private_notes"),
        "edition": format_edition(ub["edition"]) if ub.get("edition") else None,
        "reads": ub.get("user_book_reads", []),
    }


async def handle_get_user_library(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch books from the authenticated user's library.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``status`` (str), ``start_date`` (str, ISO 8601 date),
        ``end_date`` (str, ISO 8601 date), ``sort`` (str, default ``'updated'``),
        ``order`` (str, ``'asc'`` or ``'desc'``, default ``'desc'``),
        ``limit`` (int, default 25, max 100), ``offset`` (int, default 0),
        ``has_review`` (bool) — only reviewed books, with review fields, sorted by
        review date unless ``sort`` is given. Not combinable with a date range.
        ``owned`` (bool) — only library books with an edition in your Owned list.

    Returns
    -------
    list[TextContent]
        JSON with ``total`` count, ``returned``, ``offset``, and ``books`` list.
    """
    limit = _require_count(arguments.get("limit"), "limit", default=25, minimum=1, maximum=100)
    offset = _require_count(arguments.get("offset"), "offset", default=0)
    status = arguments.get("status")
    start_date = _require_str(arguments.get("start_date"), "start_date")
    end_date = _require_str(arguments.get("end_date"), "end_date")
    has_review = _require_bool(arguments.get("has_review"), "has_review")
    owned = _require_bool(arguments.get("owned"), "owned")
    sort = _require_str(arguments.get("sort"), "sort") or ("reviewed" if has_review else "updated")
    order = _require_str(arguments.get("order"), "order") or "desc"

    if sort not in LIBRARY_SORT_FIELDS:
        valid = ", ".join(LIBRARY_SORT_FIELDS)
        raise ToolError(f"unknown sort '{sort}'. Valid: {valid}")
    if order not in ("asc", "desc"):
        raise ToolError("order must be 'asc' or 'desc'.")
    if has_review and start_date is not None:
        raise ToolError("has_review can't be combined with start_date/end_date.")
    if (start_date is None) != (end_date is None):
        raise ToolError("start_date and end_date must both be provided.")
    if start_date is not None and (
        arguments.get("sort") is not None or arguments.get("order") is not None
    ):
        raise ToolError(
            "a date range is always sorted by finish date, newest first; drop sort/order."
        )
    status_id = _resolve_status_id(status)

    user = await get_current_user()
    user_id = user["id"]

    order_field = LIBRARY_SORT_FIELDS[sort]
    order_dir = order

    vars: dict[str, Any] = {"user_id": user_id, "limit": limit, "offset": offset}
    if status_id is not None:
        vars["status_id"] = status_id
    if start_date is not None:
        query = _render_library_by_date_query(with_status=status_id is not None, with_owned=owned)
        vars.update(start_date=start_date, end_date=end_date)
    else:
        query = _render_library_query(
            with_status=status_id is not None,
            with_review=has_review,
            with_owned=owned,
            order_field=order_field,
            order_dir=order_dir,
        )
    result = await execute(query, vars)

    total = result["data"]["user_books_aggregate"]["aggregate"]["count"]
    user_books = result["data"]["user_books"]
    formatter = _format_user_review if has_review else _format_user_book
    formatted = [formatter(ub) for ub in user_books]

    return list_result("books", formatted, offset=offset, total=total)


async def handle_get_user_book(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch the user's library entry for a single book.

    Parameters
    ----------
    arguments : dict[str, Any]
        Provide ``book_id`` (int) or ``slug`` (str) to identify the book.

    Returns
    -------
    list[TextContent]
        JSON with status, rating, reading history, and ``lists`` (your lists the book is
        on, as ``{id, name, position}``; the Owned list is left out).
    """
    book_id = arguments.get("book_id")
    slug = arguments.get("slug")

    if not book_id and not slug:
        raise ToolError("provide 'book_id' or 'slug'.")

    # Resolve slug to book_id if needed
    if not book_id:
        slug_result = await execute(GET_BOOK_ID_BY_SLUG_QUERY, {"slug": slug})
        books = slug_result["data"]["books"]
        if not books:
            return [TextContent(type="text", text=f"No book found with slug '{slug}'.")]
        book_id = books[0]["id"]

    user = await get_current_user()
    result = await execute(
        GET_USER_BOOK_QUERY,
        {
            "user_id": user["id"],
            "book_id": _require_int(book_id, "book_id"),
        },
    )
    user_books = result["data"]["user_books"]
    if not user_books:
        return [TextContent(type="text", text="Book not in your library.")]

    output = _format_user_book_detail(user_books[0])
    output["lists"] = _list_memberships(result["data"].get("list_books") or [])
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


def _format_user_review(ub: dict[str, Any]) -> dict[str, Any]:
    """Format a reviewed user_book: the library summary plus review fields."""
    return {
        **_format_user_book(ub),
        "review_raw": ub.get("review_raw"),
        "review_has_spoilers": ub.get("review_has_spoilers"),
        "reviewed_at": ub.get("reviewed_at"),
    }


# ── Write: edition ownership (used by set_user_book) ──

EDITION_OWNED_MUTATION = """
mutation EditionOwned($id: Int!) {
    edition_owned(id: $id) {
        id
        list_book {
            id
        }
    }
}
"""

CHECK_EDITION_OWNED_QUERY = """
query CheckEditionOwned($user_id: Int!, $edition_id: Int!) {
    lists(where: {slug: {_eq: "owned"}, user_id: {_eq: $user_id}}, limit: 1) {
        list_books(where: {edition_id: {_eq: $edition_id}}, limit: 1) {
            id
        }
    }
}
"""


async def _set_edition_owned(edition_id: int, owned: bool) -> bool:
    """Make an edition's ownership match ``owned``; return whether anything changed.

    ``edition_owned`` is a toggle, so the Owned list is checked first — repeating a call is a
    no-op.
    """
    user = await get_current_user()
    existing = await execute(
        CHECK_EDITION_OWNED_QUERY,
        {"user_id": user["id"], "edition_id": edition_id},
    )
    lists = existing["data"]["lists"]
    currently_owned = bool(lists and lists[0]["list_books"])
    if currently_owned == owned:
        return False
    mutation_payload(await execute(EDITION_OWNED_MUTATION, {"id": edition_id}), "edition_owned")
    return True


# ── Write: set_user_book ──

FIND_USER_BOOK_QUERY = """
query FindUserBook($user_id: Int!, $book_id: Int!) {
    user_books(
        where: {user_id: {_eq: $user_id}, book_id: {_eq: $book_id}},
        limit: 1,
        order_by: {updated_at: desc}
    ) {
        id
        status_id
        privacy_setting_id
        rating
        review_slate
        review_has_spoilers
        reviewed_at
        private_notes
        edition_id
    }
}
"""

INSERT_USER_BOOK_MUTATION = """
mutation InsertUserBook($object: UserBookCreateInput!) {
    insert_user_book(object: $object) {
        error
        id
        user_book {
            id
            book_id
            status_id
            privacy_setting_id
            rating
            edition_id
        }
    }
}
"""

UPDATE_USER_BOOK_MUTATION = """
mutation UpdateUserBook($id: Int!, $object: UserBookUpdateInput!) {
    update_user_book(id: $id, object: $object) {
        error
        id
        user_book {
            id
            book_id
            status_id
            privacy_setting_id
            rating
            edition_id
        }
    }
}
"""


def _resolve_status_id(status: Any, name: str = "status") -> int | None:
    """A status name (any case) or id 1-6 as its id, or None if not given.

    Raises
    ------
    ToolError
        For anything else, listing the valid names.
    """
    if status is None:
        return None
    if isinstance(status, int) and not isinstance(status, bool) and status in STATUS_MAP:
        return status
    if isinstance(status, str):
        key = status.strip().lower()
        if key.isdigit() and int(key) in STATUS_MAP:
            return int(key)
        if key in STATUS_NAME_TO_ID:
            return STATUS_NAME_TO_ID[key]
    raise ToolError(f"unknown {name} {status!r}. Valid: {', '.join(STATUS_NAMES)} (or 1-6).")


def status_label(status_id: int | None) -> str | None:
    """The output label for a status id, e.g. 'Read'; ``unknown (<id>)`` if unrecognised."""
    if status_id is None:
        return None
    return STATUS_MAP.get(status_id, f"unknown ({status_id})")


def _text_to_slate(text: str) -> list[dict[str, Any]]:
    """Convert plain text to Slate JSON paragraph nodes.

    Splits on double newlines so each paragraph becomes a separate node.
    Single newlines within a paragraph are preserved as-is.
    """
    paragraphs = text.split("\n\n")
    return [
        {"type": "p", "children": [{"text": paragraph}]} for paragraph in paragraphs if paragraph
    ]


async def handle_set_user_book(arguments: dict[str, Any]) -> list[TextContent]:
    """Set or update a book's status, rating, review, notes, privacy, edition, and ownership.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``book_id`` (int).
        Optional: ``status`` (str or int), ``rating`` (float),
        ``review_raw`` (str), ``review_has_spoilers`` (bool),
        ``reviewed_at`` (str), ``private_notes`` (str),
        ``privacy`` (str or int; public/followers/private or 1/2/3),
        ``edition_id`` (int), ``owned`` (bool) — ownership of ``edition_id``, or of the
        entry's current edition when ``edition_id`` isn't given.
        Unspecified fields are preserved on existing entries.

    Returns
    -------
    list[TextContent]
        JSON with the resulting ``user_book_id``, ``status``, ``privacy``,
        ``rating``, and ``edition_id``; plus ``owned`` and ``owned_changed`` when
        ``owned`` was given.
    """
    book_id = arguments.get("book_id")
    if not book_id:
        raise ToolError("'book_id' is required.")

    user = await get_current_user()
    user_id = user["id"]

    status = arguments.get("status")
    status_id = _resolve_status_id(status)

    privacy = arguments.get("privacy")
    privacy_setting_id = None if privacy is None else _require_privacy(privacy)

    rating = arguments.get("rating")
    review_raw = arguments.get("review_raw")
    review_has_spoilers = arguments.get("review_has_spoilers")
    reviewed_at = arguments.get("reviewed_at")
    private_notes = arguments.get("private_notes")
    edition_id = arguments.get("edition_id")
    owned = arguments.get("owned")
    if owned is not None and not isinstance(owned, bool):
        raise ToolError("'owned' must be true or false.")

    # Convert plain-text review to Slate JSON if provided
    review_slate = _text_to_slate(review_raw) if review_raw is not None else None

    book_id_int = _require_int(book_id, "book_id")
    if rating is not None:
        _require_float(rating, "rating")
    if edition_id is not None:
        edition_id = _require_int(edition_id, "edition_id")

    # Check if user_book already exists
    existing = await execute(
        FIND_USER_BOOK_QUERY,
        {
            "user_id": user_id,
            "book_id": book_id_int,
        },
    )
    existing_books = existing["data"]["user_books"]

    # Ownership is per edition: check one is known before writing anything.
    owned_edition_id = edition_id
    if owned_edition_id is None and existing_books:
        owned_edition_id = existing_books[0].get("edition_id")
    if owned is not None and owned_edition_id is None:
        raise ToolError(
            "'owned' needs an edition. Pass edition_id (list a book's editions "
            "with get_book(include_editions=true))."
        )

    if existing_books:
        # Merge: preserve existing fields the caller didn't specify
        current = existing_books[0]
        obj: dict[str, Any] = {}
        obj["status_id"] = status_id if status_id is not None else current["status_id"]
        if rating is not None:
            obj["rating"] = _require_float(rating, "rating")
        elif current.get("rating") is not None:
            obj["rating"] = current["rating"]

        # Review fields are only sent when the caller changes them: sending any of them
        # requires the write:reviews scope, and update_user_book leaves omitted fields as
        # they are (verified by the integration review test).
        if review_slate is not None:
            obj["review_slate"] = review_slate
        if review_has_spoilers is not None:
            obj["review_has_spoilers"] = review_has_spoilers
        if reviewed_at is not None:
            obj["reviewed_at"] = reviewed_at
        if private_notes is not None:
            obj["private_notes"] = private_notes
        elif current.get("private_notes") is not None:
            obj["private_notes"] = current["private_notes"]
        if privacy_setting_id is not None:
            obj["privacy_setting_id"] = privacy_setting_id
        elif current.get("privacy_setting_id") is not None:
            obj["privacy_setting_id"] = current["privacy_setting_id"]
        if edition_id is not None:
            obj["edition_id"] = edition_id
        elif current.get("edition_id") is not None:
            obj["edition_id"] = current["edition_id"]

        ub_id = current["id"]
        result = await execute(UPDATE_USER_BOOK_MUTATION, {"id": ub_id, "object": obj})
        mutation_result = mutation_payload(result, "update_user_book")
    else:
        obj = {}
        obj["book_id"] = book_id_int
        if status_id is not None:
            obj["status_id"] = status_id
        if rating is not None:
            obj["rating"] = _require_float(rating, "rating")
        if review_slate is not None:
            obj["review_slate"] = review_slate
        if review_has_spoilers is not None:
            obj["review_has_spoilers"] = review_has_spoilers
        if reviewed_at is not None:
            obj["reviewed_at"] = reviewed_at
        if private_notes is not None:
            obj["private_notes"] = private_notes
        if privacy_setting_id is not None:
            obj["privacy_setting_id"] = privacy_setting_id
        if edition_id is not None:
            obj["edition_id"] = edition_id

        result = await execute(INSERT_USER_BOOK_MUTATION, {"object": obj})
        mutation_result = mutation_payload(result, "insert_user_book")

    if mutation_result.get("error"):
        raise ToolError(str(mutation_result["error"]))

    ub = returned_object(mutation_result, "user_book", "library entry")
    output = {
        "user_book_id": ub.get("id"),
        "book_id": ub.get("book_id"),
        "status": status_label(ub.get("status_id")),
        "privacy": privacy_label(ub.get("privacy_setting_id")),
        "rating": ub.get("rating"),
        "edition_id": ub.get("edition_id"),
    }
    if owned is not None:
        output["owned"] = owned
        output["owned_changed"] = await _set_edition_owned(owned_edition_id, owned)
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ── Write: user_book_reads ──

INSERT_USER_BOOK_READ_MUTATION = """
mutation InsertUserBookRead($userBookId: Int!, $userBookRead: DatesReadInput!) {
    insert_user_book_read(user_book_id: $userBookId, user_book_read: $userBookRead) {
        error
        id
        user_book_read {
            id
            user_book_id
            started_at
            finished_at
            progress_pages
            progress_seconds
            edition_id
        }
    }
}
"""

UPDATE_USER_BOOK_READ_MUTATION = """
mutation UpdateUserBookRead($id: Int!, $object: DatesReadInput!) {
    update_user_book_read(id: $id, object: $object) {
        error
        id
        user_book_read {
            id
            user_book_id
            started_at
            finished_at
            progress_pages
            progress_seconds
            edition_id
        }
    }
}
"""

FIND_ACTIVE_READ_QUERY = """
query FindActiveRead($user_book_id: Int!) {
    user_book_reads(
        where: {user_book_id: {_eq: $user_book_id}, finished_at: {_is_null: true}},
        order_by: {id: desc},
        limit: 1
    ) {
        id
        started_at
        finished_at
        progress_pages
        progress_seconds
        edition_id
    }
}
"""

# Scoped to your library, so edits and deletes by id only reach your own reads.
GET_USER_BOOK_READ_QUERY = """
query GetUserBookRead($id: Int!, $user_id: Int!) {
    user_book_reads(
        where: {id: {_eq: $id}, user_book: {user_id: {_eq: $user_id}}},
        limit: 1
    ) {
        id
        started_at
        finished_at
        progress_pages
        progress_seconds
        edition_id
    }
}
"""


def _merge_read_input(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Merge updates onto existing read fields so unchanged values aren't nulled out."""
    merged: dict[str, Any] = {}
    for field in ("started_at", "finished_at", "progress_pages", "progress_seconds", "edition_id"):
        if field in updates:
            merged[field] = updates[field]
        elif existing.get(field) is not None:
            merged[field] = existing[field]
    return merged


def _build_read_input(arguments: dict[str, Any]) -> dict[str, Any]:
    """Extract read fields from tool arguments."""
    read_input: dict[str, Any] = {}
    if arguments.get("started_at"):
        read_input["started_at"] = arguments["started_at"]
    if arguments.get("finished_at"):
        read_input["finished_at"] = arguments["finished_at"]
    if arguments.get("progress_pages") is not None:
        read_input["progress_pages"] = _require_int(arguments["progress_pages"], "progress_pages")
    if arguments.get("progress_seconds") is not None:
        read_input["progress_seconds"] = _require_int(
            arguments["progress_seconds"], "progress_seconds"
        )
    if arguments.get("edition_id") is not None:
        read_input["edition_id"] = _require_int(arguments["edition_id"], "edition_id")
    return read_input


def _continues_read(active: dict[str, Any], read_input: dict[str, Any]) -> bool:
    """Whether a call without a read id continues the unfinished read.

    It doesn't when it gives a start date different from the unfinished read's, or a finish
    date before that read started: then it's another read (e.g. logging a past read while
    you're reading the book again).
    """
    current = active.get("started_at")
    if current is None:
        return True
    started, finished = read_input.get("started_at"), read_input.get("finished_at")
    if started is not None and str(started)[:10] != str(current)[:10]:
        return False
    return finished is None or str(finished)[:10] >= str(current)[:10]


OWN_USER_BOOK_QUERY = """
query OwnUserBook($id: Int!, $user_id: Int!) {
    user_books(where: {id: {_eq: $id}, user_id: {_eq: $user_id}}, limit: 1) {
        id
    }
}
"""


async def _own_read(read_id: int) -> dict[str, Any]:
    """Your read with ``read_id``; ``ToolError`` if there's none."""
    user = await get_current_user()
    found = await execute(GET_USER_BOOK_READ_QUERY, {"id": read_id, "user_id": user["id"]})
    reads = found["data"]["user_book_reads"]
    if not reads:
        raise ToolError("no read of yours with that id.")
    return reads[0]


async def _resolve_user_book_id(arguments: dict[str, Any]) -> int:
    """Resolve your library entry's id from ``user_book_id`` or ``book_id``.

    Raises ``ToolError`` when neither is given, or the entry isn't in your library.
    """
    user_book_id = arguments.get("user_book_id")
    if user_book_id:
        user_book_id = _require_int(user_book_id, "user_book_id")
        user = await get_current_user()
        found = await execute(OWN_USER_BOOK_QUERY, {"id": user_book_id, "user_id": user["id"]})
        if not found["data"]["user_books"]:
            raise ToolError("no library entry of yours with that user_book_id.")
        return user_book_id

    book_id = arguments.get("book_id")
    if not book_id:
        raise ToolError("provide 'book_id' or 'user_book_id'.")

    user = await get_current_user()
    existing = await execute(
        FIND_USER_BOOK_QUERY,
        {
            "user_id": user["id"],
            "book_id": _require_int(book_id, "book_id"),
        },
    )
    ubs = existing["data"]["user_books"]
    if not ubs:
        raise ToolError("book not in your library. Use set_user_book first.")
    return ubs[0]["id"]


async def _add_user_book_read(arguments: dict[str, Any]) -> list[TextContent]:
    """Add or update a reading date entry for a book.

    If an unfinished read exists and the call continues it (see ``_continues_read``), it is
    updated rather than creating a duplicate; otherwise a new read is inserted.

    Parameters
    ----------
    arguments : dict[str, Any]
        Provide ``book_id`` or ``user_book_id`` to identify the library entry.
        Optional: ``started_at``, ``finished_at`` (ISO 8601), ``progress_pages`` (int),
        ``progress_seconds`` (int, for audiobooks).

    Returns
    -------
    list[TextContent]
        JSON with the created or updated read entry.
    """
    user_book_id = await _resolve_user_book_id(arguments)

    read_input = _build_read_input(arguments)
    if not read_input:
        raise ToolError(
            "provide 'started_at', 'finished_at', 'progress_pages', or 'progress_seconds'."
        )

    # Continue an unfinished read instead of creating a duplicate, unless this is another read
    active = await execute(FIND_ACTIVE_READ_QUERY, {"user_book_id": user_book_id})
    active_reads = active["data"]["user_book_reads"]

    if active_reads and _continues_read(active_reads[0], read_input):
        existing_read = active_reads[0]
        merged = _merge_read_input(existing_read, read_input)
        result = await execute(
            UPDATE_USER_BOOK_READ_MUTATION,
            {
                "id": existing_read["id"],
                "object": merged,
            },
        )
        mutation_result = mutation_payload(result, "update_user_book_read")
    else:
        result = await execute(
            INSERT_USER_BOOK_READ_MUTATION,
            {
                "userBookId": user_book_id,
                "userBookRead": read_input,
            },
        )
        mutation_result = mutation_payload(result, "insert_user_book_read")

    if mutation_result.get("error"):
        raise ToolError(str(mutation_result["error"]))

    return [
        TextContent(
            type="text",
            text=json.dumps(returned_object(mutation_result, "user_book_read", "read"), indent=2),
        )
    ]


async def _update_user_book_read(arguments: dict[str, Any]) -> list[TextContent]:
    """Update an existing reading date entry.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``id`` (int, user_book_read ID).
        Optional: ``started_at``, ``finished_at`` (ISO 8601), ``progress_pages`` (int),
        ``progress_seconds`` (int, for audiobooks).
        Unspecified fields are preserved.

    Returns
    -------
    list[TextContent]
        JSON with the updated read entry.
    """
    read_id = arguments.get("id")
    if not read_id:
        raise ToolError("'id' (user_book_read id) is required.")

    read_input = _build_read_input(arguments)
    if not read_input:
        raise ToolError(
            "provide 'started_at', 'finished_at', 'progress_pages', or 'progress_seconds'."
        )

    # Fetch current values and merge so unchanged fields aren't nulled out
    read_id_int = _require_int(read_id, "id")

    merged = _merge_read_input(await _own_read(read_id_int), read_input)

    result = await execute(
        UPDATE_USER_BOOK_READ_MUTATION,
        {
            "id": read_id_int,
            "object": merged,
        },
    )
    mutation_result = mutation_payload(result, "update_user_book_read")

    if mutation_result.get("error"):
        raise ToolError(str(mutation_result["error"]))

    return [
        TextContent(
            type="text",
            text=json.dumps(returned_object(mutation_result, "user_book_read", "read"), indent=2),
        )
    ]


async def handle_set_user_book_read(arguments: dict[str, Any]) -> list[TextContent]:
    """Edit a read entry by ``id``, or log dates/progress for a book (see
    ``_add_user_book_read``) when no ``id`` is given."""
    if arguments.get("id") is not None:
        return await _update_user_book_read(arguments)
    return await _add_user_book_read(arguments)


# ── Write: delete ──

DELETE_USER_BOOK_READ_MUTATION = """
mutation DeleteUserBookRead($id: Int!) {
    delete_user_book_read(id: $id) {
        __typename
    }
}
"""

DELETE_USER_BOOK_MUTATION = """
mutation DeleteUserBook($id: Int!) {
    delete_user_book(id: $id) {
        __typename
    }
}
"""


async def handle_delete_user_book_read(arguments: dict[str, Any]) -> list[TextContent]:
    """Delete a reading date entry by ID.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``id`` (int, user_book_read ID).

    Returns
    -------
    list[TextContent]
        JSON confirmation with ``deleted: true`` and the entry ID.
    """
    read_id = arguments.get("id")
    if not read_id:
        raise ToolError("'id' (user_book_read id) is required.")

    read_id_int = _require_int(read_id, "id")

    await _own_read(read_id_int)
    await execute(DELETE_USER_BOOK_READ_MUTATION, {"id": read_id_int})
    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": read_id_int}))]


async def handle_delete_user_book(arguments: dict[str, Any]) -> list[TextContent]:
    """Remove a book from the user's library entirely.

    Parameters
    ----------
    arguments : dict[str, Any]
        Provide ``book_id`` or ``user_book_id`` to identify the library entry.

    Returns
    -------
    list[TextContent]
        JSON confirmation with ``deleted: true`` and the ``user_book_id``.
    """
    resolved = await _resolve_user_book_id(arguments)

    await execute(DELETE_USER_BOOK_MUTATION, {"id": resolved})
    return [TextContent(type="text", text=json.dumps({"deleted": True, "user_book_id": resolved}))]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="get_user_library",
            description=(
                "List books in your own library (any status), paginated with limit/offset. "
                "Read-only. Filter by status, by finished-date range (start_date + end_date), "
                "or has_review=true for books you have reviewed (adds review text, spoiler "
                "flag, and review date; newest review first). Sort by updated, rating, "
                "date_added, or reviewed. Returns user_book_id, book_id, title, authors, "
                "status, and rating per book (with a date range, also the read's dates). "
                "E.g. sort='rating' for top-rated; "
                "a date range answers 'what did I read in May?' (always newest finish first, "
                "so it can't take sort/order). owned=true keeps only books "
                "with an edition in your Owned list (set with set_user_book); owned books "
                "that aren't in your library are not listed. Filters combine, e.g. owned=true "
                "with status='Want to Read'. For one book's full entry use get_user_book."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": STATUS_NAMES,
                        "description": "Only books with this status.",
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
                        "description": (
                            "Sort field: 'updated' (default), 'rating', 'date_added', or "
                            "'reviewed' (default when has_review=true)."
                        ),
                        "enum": ["updated", "rating", "date_added", "reviewed"],
                    },
                    "order": {
                        "type": "string",
                        "description": "Sort direction: 'desc' (default) or 'asc'.",
                        "enum": ["desc", "asc"],
                    },
                    "has_review": {
                        "type": "boolean",
                        "description": (
                            "Only books you have reviewed, with review fields included. "
                            "Can't be combined with start_date/end_date."
                        ),
                    },
                    "owned": {
                        "type": "boolean",
                        "description": (
                            "Only books with an edition in your Owned list. Combines with the "
                            "other filters."
                        ),
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
            annotations=READ,
        ),
        handle_get_user_library,
        toolset="library",
        scopes=("read:library", "read:lists", "read:me"),
    ),
    ToolSpec(
        Tool(
            name="get_user_book",
            description=(
                "Get your own library entry for one book: pass book_id or slug (book_id wins "
                "if both are given). Read-only. "
                "Returns user_book_id, status, rating, privacy, review, private notes, chosen "
                "edition, and every read entry (with their ids, needed by "
                "set_user_book_read/delete_user_book_read), plus the lists of yours it's on "
                "(not Owned; change them with set_list_book). Returns 'Book not in your "
                "library' if you haven't added it, or 'No book found with slug …' for an "
                "unknown slug. This is your relationship to the book; for "
                "the book itself (description, pages, community rating) use get_book, and to "
                "browse many of your books use get_user_library."
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
            annotations=READ,
        ),
        handle_get_user_book,
        toolset="library",
        scopes=("read:catalog", "read:library", "read:lists", "read:me"),
    ),
    ToolSpec(
        Tool(
            name="set_user_book",
            description=(
                "Add a book to your library or update your entry for it: status, rating, "
                "review, privacy, private notes, edition, and whether you own it. Upsert: "
                "creates the entry if the book isn't in your library yet, otherwise overwrites "
                "only the fields you pass. owned=true/false marks ownership of edition_id (or of "
                "the entry's current edition if edition_id is omitted; errors if there is "
                "none); passing edition_id also makes it the edition you're reading. Ownership "
                "changes are idempotent. Returns user_book_id, status, privacy, rating, "
                "edition_id, and owned/owned_changed when owned was given. Use "
                "set_user_book_read for start/finish dates and progress, set_list_book for "
                "custom lists, and delete_user_book to remove the book."
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
                        "enum": STATUS_NAMES,
                        "description": "Reading status.",
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
                        "description": PRIVACY_DESCRIPTION,
                    },
                    "edition_id": {
                        "type": "integer",
                        "description": (
                            "Edition ID (from get_book). Sets which edition you're reading."
                        ),
                    },
                    "owned": {
                        "type": "boolean",
                        "description": (
                            "true/false: you own (or no longer own) edition_id, or the "
                            "current edition if edition_id is omitted."
                        ),
                    },
                },
                "required": ["book_id"],
            },
            annotations=UPDATE,
        ),
        handle_set_user_book,
        toolset="library",
        scopes=("read:library", "read:lists", "read:me", "write:library", "write:reviews"),
    ),
    ToolSpec(
        Tool(
            name="set_user_book_read",
            description=(
                "Log or edit reading dates and progress (pages or audiobook seconds). With id "
                "(a user_book_read id from get_user_book): edit that read, overwriting only the "
                "fields you pass, e.g. to fix a past finish date. Without id: pass book_id or "
                "user_book_id; if the book has an unfinished read it is updated (progress, a "
                "later finish date, or the same start date), otherwise a new read is created, "
                "e.g. a re-read or a past read with its own dates. The book must already be "
                "in your library (add it with set_user_book). Returns the read entry with its "
                "id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "user_book_read ID to edit. Omit to log on a book.",
                    },
                    "book_id": {
                        "type": "integer",
                        "description": "Without id: book ID (auto-resolves your user_book).",
                    },
                    "user_book_id": {
                        "type": "integer",
                        "description": "Without id: user_book ID if known (skips lookup).",
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
            # May overwrite an existing read; without id, repeating can create another read.
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=False,
                open_world_hint=True,
            ),
        ),
        handle_set_user_book_read,
        toolset="library",
        scopes=("read:library", "read:me", "write:library"),
    ),
    ToolSpec(
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
            annotations=DELETE,
        ),
        handle_delete_user_book_read,
        toolset="library",
        scopes=("read:library", "read:me", "write:library"),
    ),
    ToolSpec(
        Tool(
            name="delete_user_book",
            description=(
                "Permanently remove a book from your library (by book_id or user_book_id), "
                "including its status, rating, review, and private notes. Cannot be "
                "undone. Returns {deleted: true, user_book_id}. To change status instead use "
                "set_user_book; to take it off a custom list use set_list_book(on_list=false)."
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
            annotations=DELETE,
        ),
        handle_delete_user_book,
        toolset="library",
        scopes=("read:library", "read:me", "write:library"),
    ),
]
