"""GraphQL client wrapper for the Hardcover API."""

import asyncio
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

API_URL = os.environ.get("HARDCOVER_API_URL", "https://api.hardcover.app/v1/graphql")

# Rate limiting: 60 requests per minute
_RATE_LIMIT = 60
_RATE_WINDOW = 60.0  # seconds
_request_timestamps: list[float] = []

# Retry config for 429 responses
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # seconds, doubles each retry


async def _wait_for_rate_limit() -> None:
    """Block until we're under the rate limit."""
    now = time.monotonic()
    # Prune timestamps older than the window
    while _request_timestamps and _request_timestamps[0] < now - _RATE_WINDOW:
        _request_timestamps.pop(0)
    if len(_request_timestamps) >= _RATE_LIMIT:
        sleep_until = _request_timestamps[0] + _RATE_WINDOW
        await asyncio.sleep(sleep_until - now)
    _request_timestamps.append(time.monotonic())


def _get_token() -> str:
    """Read the API token from the environment."""
    token = os.environ.get("HARDCOVER_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "HARDCOVER_API_TOKEN is not set. Get your token from https://hardcover.app/account/api"
        )
    return token


async def execute(
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a GraphQL query against the Hardcover API.

    Returns the full JSON response body. Raises on HTTP or GraphQL errors.
    """
    await _wait_for_rate_limit()

    token = _get_token()
    headers = {
        "authorization": token,
        "content-type": "application/json",
        "user-agent": "hardcover-mcp/0.1.0",
    }
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    backoff = _RETRY_BACKOFF
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(API_URL, json=payload, headers=headers)

        if response.status_code == 429:
            last_error = httpx.HTTPStatusError(
                "Rate limited", request=response.request, response=response
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            raise last_error

        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Invalid JSON from API: {exc}") from exc

        if "errors" in data:
            messages = "; ".join(e.get("message", str(e)) for e in data["errors"])
            raise RuntimeError(f"GraphQL error: {messages}")

        return data

    raise last_error  # unreachable, but keeps type checker happy
