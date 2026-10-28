"""Shared input validation helpers for tool handlers."""

import math
from datetime import date
from typing import Any


class ToolError(ValueError):
    """A tool call that failed on its own terms: bad input, or an action the API rejected.

    ``call_tool`` returns it to the client as ``Error: <message>`` with ``isError`` set and
    no traceback. Raise it for failures only:

    - A write tool whose target doesn't exist raises it (the action didn't happen).
    - A read tool that finds nothing isn't a failure. A list returns an empty page; a lookup
      of one object returns a short plain-text answer such as "No book found.".

    Subclasses ``ValueError`` so the ``_require_*`` validators can raise it directly.
    """


def _require_int(value: Any, name: str) -> int:
    """Convert a value to int or raise ToolError with a user-friendly message."""
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):  # fmt: skip
        raise ToolError(f"'{name}' must be an integer, got: {value!r}") from None


def _require_count(
    value: Any, name: str, *, default: int, minimum: int = 0, maximum: int | None = None
) -> int:
    """A whole-number argument such as a limit, offset, or page.

    ``default`` when not given, an error below ``minimum`` (or for a bool), capped at
    ``maximum``.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        raise ToolError(f"'{name}' must be an integer, got: {value!r}")
    number = _require_int(value, name)
    if number < minimum:
        raise ToolError(f"'{name}' must be at least {minimum}, got: {value!r}")
    return number if maximum is None else min(number, maximum)


def _require_bool(value: Any, name: str, *, default: bool = False) -> bool:
    """A true/false argument; also accepts the strings "true" and "false"."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ToolError(f"'{name}' must be true or false, got: {value!r}")


def _require_str(value: Any, name: str) -> str | None:
    """An optional string argument; None if not given."""
    if value is None or isinstance(value, str):
        return value
    raise ToolError(f"'{name}' must be a string, got: {value!r}")


def _require_float(value: Any, name: str) -> float:
    """Convert a value to a finite float or raise ToolError with a user-friendly message."""
    try:
        number = float(value)
    except (ValueError, TypeError):  # fmt: skip
        raise ToolError(f"'{name}' must be a number, got: {value!r}") from None
    if not math.isfinite(number):
        raise ToolError(f"'{name}' must be a number, got: {value!r}")
    return number


def _require_iso_date(value: Any, name: str) -> str:
    """Validate a date and return it as ``YYYY-MM-DD``.

    Normalised, because Python also accepts forms like ``20260101`` and dates are compared as
    text later on.
    """
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"'{name}' must be a non-empty ISO 8601 date string")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        raise ToolError(
            f"'{name}' must be an ISO 8601 date (YYYY-MM-DD), got: {value!r}"
        ) from None


# Privacy settings are the same everywhere in the API: 1 public, 2 followers, 3 private.
PRIVACY_LABELS: dict[int, str] = {1: "public", 2: "followers", 3: "private"}
_PRIVACY_IDS: dict[str, int] = {
    **{label: pid for pid, label in PRIVACY_LABELS.items()},
    "followers_only": 2,
}
# Shared JSON-schema description for every tool's ``privacy`` argument.
PRIVACY_DESCRIPTION = "Who can see it: 'public', 'followers', or 'private' (or 1, 2, 3)."


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
    """The privacy id from a tool's ``privacy`` argument, or None if it wasn't passed.

    Rejects the removed ``privacy_setting_id`` argument rather than ignoring it, so an old
    call asking for a private entry doesn't quietly get a public one.
    """
    if arguments.get("privacy_setting_id") is not None:
        raise ToolError("'privacy_setting_id' was removed; use 'privacy'.")
    privacy = arguments.get("privacy")
    return None if privacy is None else _require_privacy(privacy)


def privacy_label(privacy_id: int | None) -> str | None:
    """The output label for a privacy id: 'public', 'followers', 'private', or None."""
    if privacy_id is None:
        return None
    return PRIVACY_LABELS.get(privacy_id, f"unknown ({privacy_id})")
