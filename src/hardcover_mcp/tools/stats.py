"""Tools: get_reading_stats — library statistics via user_books_aggregate."""

import json
from datetime import date
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.user import get_current_user

# Uses aliased user_books_aggregate calls to fetch all counts in one round trip.
# Each alias maps to a distinct where-filter; GraphQL executes them in parallel.
GET_READING_STATS_QUERY = """
query GetReadingStats($user_id: Int!, $year_start: date!, $year_end: date!) {
    total: user_books_aggregate(where: {user_id: {_eq: $user_id}}) {
        aggregate { count }
    }
    want_to_read: user_books_aggregate(
        where: {user_id: {_eq: $user_id}, status_id: {_eq: 1}}
    ) {
        aggregate { count }
    }
    currently_reading: user_books_aggregate(
        where: {user_id: {_eq: $user_id}, status_id: {_eq: 2}}
    ) {
        aggregate { count }
    }
    read: user_books_aggregate(
        where: {user_id: {_eq: $user_id}, status_id: {_eq: 3}}
    ) {
        aggregate { count }
    }
    paused: user_books_aggregate(
        where: {user_id: {_eq: $user_id}, status_id: {_eq: 4}}
    ) {
        aggregate { count }
    }
    did_not_finish: user_books_aggregate(
        where: {user_id: {_eq: $user_id}, status_id: {_eq: 5}}
    ) {
        aggregate { count }
    }
    ignored: user_books_aggregate(
        where: {user_id: {_eq: $user_id}, status_id: {_eq: 6}}
    ) {
        aggregate { count }
    }
    ratings: user_books_aggregate(
        where: {user_id: {_eq: $user_id}, rating: {_is_null: false}}
    ) {
        aggregate { avg { rating } }
    }
    read_in_year: user_books_aggregate(
        where: {
            user_id: {_eq: $user_id},
            status_id: {_eq: 3},
            user_book_reads: {finished_at: {_gte: $year_start, _lte: $year_end}}
        }
    ) {
        aggregate { count }
    }
}
"""


def _format_reading_stats(data: dict[str, Any], year: int) -> dict[str, Any]:
    """Format the aliased user_books_aggregate payload into a reading stats summary.

    Parameters
    ----------
    data : dict[str, Any]
        Raw ``data`` payload from the GraphQL response, containing aliased
        aggregate results (``total``, ``want_to_read``, ``currently_reading``,
        ``read``, ``did_not_finish``, ``paused``, ``ignored``, ``ratings``,
        ``read_in_year``).
    year : int
        Calendar year used for the ``books_read_this_year`` count.

    Returns
    -------
    dict[str, Any]
        Dict with keys ``total_books``, ``by_status`` (nested counts per status),
        ``average_rating`` (rounded to 2 dp, or ``None`` if no ratings exist),
        and ``books_read_this_year``.
    """
    avg_raw = data["ratings"]["aggregate"]["avg"]["rating"]
    avg_rating = round(avg_raw, 2) if avg_raw is not None else None

    return {
        "total_books": data["total"]["aggregate"]["count"],
        "by_status": {
            "want_to_read": data["want_to_read"]["aggregate"]["count"],
            "currently_reading": data["currently_reading"]["aggregate"]["count"],
            "read": data["read"]["aggregate"]["count"],
            "did_not_finish": data["did_not_finish"]["aggregate"]["count"],
            "paused": data["paused"]["aggregate"]["count"],
            "ignored": data["ignored"]["aggregate"]["count"],
        },
        "average_rating": avg_rating,
        "books_read_this_year": data["read_in_year"]["aggregate"]["count"],
        "year": year,
    }


async def handle_get_reading_stats(arguments: dict[str, Any]) -> list[TextContent]:
    """Return library statistics for the authenticated user.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``year`` (int) — calendar year for the ``books_read_this_year``
        count. Defaults to the current year.

    Returns
    -------
    list[TextContent]
        Single-element list with JSON-formatted reading statistics containing
        ``total_books``, ``by_status``, ``average_rating``,
        ``books_read_this_year``, and ``year``.
    """
    # --- 1. Resolve year parameter (defaults to current year)
    year_raw = arguments.get("year")
    year = _require_int(year_raw, "year") if year_raw is not None else date.today().year

    year_start = f"{year}-01-01"
    year_end = f"{year}-12-31"

    # --- 2. Fetch authenticated user
    user = await get_current_user()
    user_id = user["id"]

    # --- 3. Execute all aggregates in a single query
    result = await execute(
        GET_READING_STATS_QUERY,
        {
            "user_id": user_id,
            "year_start": year_start,
            "year_end": year_end,
        },
    )

    # --- 4. Format and return
    stats = _format_reading_stats(result["data"], year)
    return [TextContent(type="text", text=json.dumps(stats, indent=2))]
