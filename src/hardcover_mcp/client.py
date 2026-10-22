"""GraphQL client wrapper for the Hardcover API."""

import asyncio
import os
import re
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_API_URL = "https://api.hardcover.app/v1/graphql"
API_KEYS_URL = "https://hardcover.app/account/api"
NEW_API_KEY_URL = "https://hardcover.app/account/api/keys/new"

try:
    _VERSION = version("hardcover-mcp")
except PackageNotFoundError:  # running from a source tree without an install
    _VERSION = "unknown"
USER_AGENT = f"hardcover-mcp/{_VERSION} (+https://github.com/kristianedlund/hardcover-mcp)"

# Rate limiting: 60 requests per minute
_RATE_LIMIT = 60
_RATE_WINDOW = 60.0  # seconds
_request_timestamps: list[float] = []

# Set from the API's RateLimit header: monotonic time before which no request should be sent,
# and whether the daily quota is used up (with the monotonic time it resets).
_blocked_until: float = 0.0
_daily_reset_at: float | None = None

# Retry config for 429 / 503 responses
_MAX_RETRIES = 5
_RETRY_BACKOFF = 3.0  # seconds, doubles each retry
_RETRYABLE_STATUSES = {429, 503}

# One HTTP client per event loop, so requests reuse open connections (keep-alive).
_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


class HardcoverAPIError(RuntimeError):
    """A failure reported by the Hardcover API, with a message meant for the user."""


def new_key_link(scopes: list[str] | None = None) -> str:
    """Link to Hardcover's new-API-key form, optionally with scopes pre-selected."""
    if not scopes:
        return NEW_API_KEY_URL
    return f"{NEW_API_KEY_URL}?scope={quote(' '.join(scopes))}"


async def _wait_for_rate_limit() -> None:
    """Block until we're under the rate limit, or fail fast if the daily quota is used up."""
    global _daily_reset_at
    now = time.monotonic()
    if _daily_reset_at is not None:
        if now < _daily_reset_at:
            raise HardcoverAPIError(
                "Hardcover's daily API limit for this token is used up. It resets at midnight "
                "UTC; your current usage is shown at " + API_KEYS_URL + "."
            )
        _daily_reset_at = None
    if now < _blocked_until:
        await asyncio.sleep(_blocked_until - now)
        now = time.monotonic()
    # Prune timestamps older than the window
    while _request_timestamps and _request_timestamps[0] < now - _RATE_WINDOW:
        _request_timestamps.pop(0)
    if len(_request_timestamps) >= _RATE_LIMIT:
        sleep_until = _request_timestamps[0] + _RATE_WINDOW
        await asyncio.sleep(sleep_until - now)
    _request_timestamps.append(time.monotonic())


def _parse_ratelimit(header: str) -> dict[str, dict[str, int]]:
    """Parse an IETF ``RateLimit`` header, e.g. ``"Free";r=8;t=0, "daily";r=4231;t=51234``.

    Returns ``{bucket_name: {"r": remaining, "t": seconds_until_reset}}``; malformed entries
    are skipped.
    """
    buckets: dict[str, dict[str, int]] = {}
    for item in header.split(","):
        name_match = re.match(r'\s*"([^"]+)"', item)
        if not name_match:
            continue
        params = dict(re.findall(r";\s*([a-z]+)=(\d+)", item))
        if "r" in params and "t" in params:
            buckets[name_match.group(1)] = {"r": int(params["r"]), "t": int(params["t"])}
    return buckets


def _record_rate_limit(headers: httpx.Headers) -> None:
    """Update local throttling state from the API's ``RateLimit`` header, if present."""
    global _blocked_until, _daily_reset_at
    header = headers.get("ratelimit")
    if not header:
        return
    now = time.monotonic()
    for name, bucket in _parse_ratelimit(header).items():
        if bucket["r"] > 0:
            continue
        if name == "daily":
            _daily_reset_at = now + bucket["t"]
        else:
            _blocked_until = max(_blocked_until, now + bucket["t"])


def _retry_delay(response: httpx.Response, fallback: float) -> float:
    """Seconds to wait before retrying: ``Retry-After`` when given, else ``fallback``."""
    retry_after = response.headers.get("retry-after", "")
    return float(retry_after) if retry_after.strip().isdigit() else fallback


def _error_body(response: httpx.Response) -> dict[str, Any]:
    """The JSON error body of a failed response, or ``{}`` if it isn't JSON."""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _auth_error(response: httpx.Response) -> HardcoverAPIError:
    """Translate a 401/403 response into a user-facing error."""
    body = _error_body(response)
    detail = body.get("error_description") or body.get("message") or ""
    detail_suffix = f" ({detail})" if detail else ""

    if response.status_code == 401:
        return HardcoverAPIError(
            "Hardcover rejected the API token: it is missing, invalid, or expired"
            f"{detail_suffix}. Create a new key at {NEW_API_KEY_URL} and update "
            "HARDCOVER_API_TOKEN."
        )

    error = body.get("error")
    errors = body.get("errors")
    if error == "insufficient_scope":
        scopes = str(body.get("scope") or "").split()
        missing = ", ".join(scopes) if scopes else "unknown"
        return HardcoverAPIError(
            f"Your Hardcover API token is missing the scope(s) this tool needs: {missing}. "
            f"Create a key that includes them: {new_key_link(scopes)}"
        )
    if isinstance(errors, list) and "request_exceeds_capacity" in errors:
        return HardcoverAPIError(
            "This request asks Hardcover for more data at once than your plan's burst limit "
            "allows. This is a bug in hardcover-mcp; please report it."
        )
    if error == "unsupported_operation":
        return HardcoverAPIError(
            f"Hardcover doesn't allow this operation with API tokens{detail_suffix}."
        )
    reason = error or detail or "no reason given"
    return HardcoverAPIError(f"Hardcover denied access: {reason}.")


def _http_client() -> httpx.AsyncClient:
    """The shared HTTP client, created on first use.

    A client is bound to the event loop it was first used on, so a different running loop
    (e.g. a new one per test) gets a new client.
    """
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client.is_closed or _client_loop is not loop:
        _client = httpx.AsyncClient(timeout=30.0)
        _client_loop = loop
    return _client


async def aclose() -> None:
    """Close the shared HTTP client, if one is open. The next request opens a new one."""
    global _client, _client_loop
    if _client is not None and _client_loop is asyncio.get_running_loop():
        await _client.aclose()
    _client = None
    _client_loop = None


def _api_url() -> str:
    """The GraphQL endpoint: ``HARDCOVER_API_URL`` if set, else Hardcover's API.

    Only ``https://`` URLs are accepted, since every request carries the API token.
    """
    url = os.environ.get("HARDCOVER_API_URL", "").strip() or DEFAULT_API_URL
    if not url.startswith("https://"):
        raise HardcoverAPIError(f"HARDCOVER_API_URL must be an https:// URL, got: {url!r}")
    return url


def _get_token() -> str:
    """Read the API token from the environment."""
    token = os.environ.get("HARDCOVER_API_TOKEN", "").strip()
    if not token:
        raise HardcoverAPIError(
            f"HARDCOVER_API_TOKEN is not set. Create a key at {NEW_API_KEY_URL}"
        )
    return token


async def execute(
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a GraphQL query against the Hardcover API.

    Parameters
    ----------
    query : str
        GraphQL query or mutation string.
    variables : dict[str, Any] | None
        GraphQL variables to include in the request payload.

    Returns
    -------
    dict[str, Any]
        Full JSON response body from the API.

    Raises
    ------
    HardcoverAPIError
        If ``HARDCOVER_API_TOKEN`` is missing, the token is rejected or lacks a scope,
        the daily limit is used up, the response is not valid JSON, or the response
        contains GraphQL errors.
    httpx.HTTPStatusError
        If the API returns another non-success HTTP status, or 429/503 persists after
        retries.
    """
    await _wait_for_rate_limit()

    url = _api_url()
    token = _get_token()
    if not token.startswith("Bearer "):
        token = f"Bearer {token}"
    headers = {
        "authorization": token,
        "content-type": "application/json",
        "user-agent": USER_AGENT,
    }
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    backoff = _RETRY_BACKOFF

    for attempt in range(_MAX_RETRIES + 1):
        response = await _http_client().post(url, json=payload, headers=headers)

        _record_rate_limit(response.headers)

        if response.status_code in _RETRYABLE_STATUSES:
            if _daily_reset_at is not None:
                await _wait_for_rate_limit()  # raises the daily-limit error
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_retry_delay(response, backoff))
                backoff *= 2
                continue
            response.raise_for_status()

        if response.status_code in (401, 403):
            raise _auth_error(response)

        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as exc:
            raise HardcoverAPIError(f"Invalid JSON from API: {exc}") from exc

        if "errors" in data:
            messages = "; ".join(e.get("message", str(e)) for e in data["errors"])
            raise HardcoverAPIError(f"GraphQL error: {messages}")

        return data

    raise AssertionError("unreachable")  # the loop always returns or raises
