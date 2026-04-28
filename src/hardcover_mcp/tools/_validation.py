"""Shared input validation helpers for tool handlers."""

from typing import Any


def _require_int(value: Any, name: str) -> int:
    """Convert a value to int or raise ValueError with a user-friendly message."""
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"'{name}' must be an integer, got: {value!r}") from None


def _require_float(value: Any, name: str) -> float:
    """Convert a value to float or raise ValueError with a user-friendly message."""
    try:
        return float(value)
    except (ValueError, TypeError):
        raise ValueError(f"'{name}' must be a number, got: {value!r}") from None
