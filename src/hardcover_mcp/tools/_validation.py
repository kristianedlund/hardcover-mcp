"""Shared input validation helpers for tool handlers."""

from typing import Any


class ToolError(ValueError):
    """A tool call that failed on its own terms: bad input, or an action the API rejected.

    ``call_tool`` returns it to the client as ``Error: <message>`` with ``isError`` set and
    no traceback. Raise it for failures only. Answers like "No book found." or "Book not in
    your library." are valid results, so handlers return them as normal text.

    Subclasses ``ValueError`` so the ``_require_*`` validators can raise it directly.
    """


def _require_int(value: Any, name: str) -> int:
    """Convert a value to int or raise ToolError with a user-friendly message."""
    try:
        return int(value)
    except (ValueError, TypeError):  # fmt: skip
        raise ToolError(f"'{name}' must be an integer, got: {value!r}") from None


def _require_float(value: Any, name: str) -> float:
    """Convert a value to float or raise ToolError with a user-friendly message."""
    try:
        return float(value)
    except (ValueError, TypeError):  # fmt: skip
        raise ToolError(f"'{name}' must be a number, got: {value!r}") from None


def _require_iso_date(value: Any, name: str) -> str:
    """Validate and return an ISO 8601 date string (YYYY-MM-DD)."""
    from datetime import date as _date

    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"'{name}' must be a non-empty ISO 8601 date string")
    normalized = value.strip()
    try:
        _date.fromisoformat(normalized)
    except ValueError:
        raise ToolError(
            f"'{name}' must be an ISO 8601 date (YYYY-MM-DD), got: {value!r}"
        ) from None
    return normalized
