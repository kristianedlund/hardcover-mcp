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


# Privacy settings are the same everywhere in the API: 1 public, 2 followers, 3 private.
PRIVACY_LABELS: dict[int, str] = {1: "public", 2: "followers", 3: "private"}
_PRIVACY_IDS: dict[str, int] = {
    **{label: pid for pid, label in PRIVACY_LABELS.items()},
    "followers_only": 2,
}
# Shared JSON-schema description for every tool's ``privacy`` argument.
PRIVACY_DESCRIPTION = "Who can see it: 'public', 'followers', or 'private' (or 1, 2, 3)."
# Kept on set_journal_entry and set_reading_goal so existing callers keep working.
PRIVACY_SETTING_ID_DESCRIPTION = "Deprecated: use privacy. 1 public, 2 followers, 3 private."


def _require_privacy(value: Any, name: str = "privacy") -> int:
    """Resolve a privacy label (any case; ``followers_only`` too) or 1/2/3 to its id."""
    if isinstance(value, int) and not isinstance(value, bool) and value in PRIVACY_LABELS:
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key.isdigit() and int(key) in PRIVACY_LABELS:
            return int(key)
        if key in _PRIVACY_IDS:
            return _PRIVACY_IDS[key]
    raise ToolError(
        f"'{name}' must be 'public', 'followers', or 'private' (or 1, 2, 3), got: {value!r}"
    )


def _privacy_argument(arguments: dict[str, Any]) -> int | None:
    """The privacy id from ``privacy``, or from the deprecated ``privacy_setting_id`` alias."""
    privacy = arguments.get("privacy")
    legacy = arguments.get("privacy_setting_id")
    if privacy is None:
        return None if legacy is None else _require_privacy(legacy, "privacy_setting_id")
    resolved = _require_privacy(privacy)
    if legacy is not None and _require_privacy(legacy, "privacy_setting_id") != resolved:
        raise ToolError("'privacy' and 'privacy_setting_id' disagree; pass only 'privacy'.")
    return resolved


def privacy_label(privacy_id: int | None) -> str | None:
    """The output label for a privacy id: 'public', 'followers', 'private', or None."""
    if privacy_id is None:
        return None
    return PRIVACY_LABELS.get(privacy_id, f"unknown ({privacy_id})")
