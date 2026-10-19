"""Tests for the GraphQL client: request construction, errors, and rate limiting."""

import httpx
import pytest

from hardcover_mcp import client

_REQUEST = httpx.Request("POST", "https://api.hardcover.app/v1/graphql")


def _response(status: int = 200, json=None, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status, json={"data": {}} if json is None else json, headers=headers, request=_REQUEST
    )


class _FakeAsyncClient:
    """Returns queued responses and records request headers, without network access."""

    responses: list[httpx.Response] = []  # noqa: RUF012 - reset per test by the fixture
    captured_headers: list[dict] = []  # noqa: RUF012

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        _FakeAsyncClient.captured_headers.append(headers)
        return _FakeAsyncClient.responses.pop(0)


@pytest.fixture(autouse=True)
def sleeps(monkeypatch) -> list[float]:
    """Fresh rate-limit state, a fake HTTP client, a token, and recorded (not real) sleeps."""
    client._request_timestamps.clear()
    monkeypatch.setattr(client, "_blocked_until", 0.0)
    monkeypatch.setattr(client, "_daily_reset_at", None)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token-not-real")
    recorded: list[float] = []

    async def fake_sleep(seconds):
        recorded.append(seconds)

    monkeypatch.setattr(client.asyncio, "sleep", fake_sleep)
    _FakeAsyncClient.responses = []
    _FakeAsyncClient.captured_headers = []
    yield recorded
    client._request_timestamps.clear()


# ── Request construction ──


async def test_execute_sends_bearer_prefixed_authorization_header():
    _FakeAsyncClient.responses = [_response()]

    await client.execute("query { me { id } }")

    assert _FakeAsyncClient.captured_headers[0]["authorization"] == "Bearer test-token-not-real"


async def test_execute_does_not_double_prefix_existing_bearer_token(monkeypatch):
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "Bearer test-token-not-real")
    _FakeAsyncClient.responses = [_response()]

    await client.execute("query { me { id } }")

    assert _FakeAsyncClient.captured_headers[0]["authorization"] == "Bearer test-token-not-real"


async def test_user_agent_carries_package_version():
    _FakeAsyncClient.responses = [_response()]

    await client.execute("query { me { id } }")

    user_agent = _FakeAsyncClient.captured_headers[0]["user-agent"]
    assert user_agent.startswith(f"hardcover-mcp/{client._VERSION} ")
    assert client._VERSION not in ("unknown", "0.7.1")


async def test_execute_raises_without_token(monkeypatch):
    monkeypatch.delenv("HARDCOVER_API_TOKEN", raising=False)

    with pytest.raises(client.HardcoverAPIError, match="HARDCOVER_API_TOKEN is not set"):
        await client.execute("query { me { id } }")


# ── Auth and scope errors ──


async def test_401_explains_invalid_or_expired_token():
    _FakeAsyncClient.responses = [
        _response(401, {"error": "invalid_token", "error_description": "Token expired"})
    ]

    with pytest.raises(client.HardcoverAPIError) as exc:
        await client.execute("query { me { id } }")

    assert "missing, invalid, or expired" in str(exc.value)
    assert "Token expired" in str(exc.value)
    assert client.NEW_API_KEY_URL in str(exc.value)


async def test_403_insufficient_scope_names_scopes_and_links_a_key():
    _FakeAsyncClient.responses = [
        _response(403, {"error": "insufficient_scope", "scope": "write:lists read:lists"})
    ]

    with pytest.raises(client.HardcoverAPIError) as exc:
        await client.execute("mutation { delete_list(id: 1) { id } }")

    message = str(exc.value)
    assert "write:lists, read:lists" in message
    assert f"{client.NEW_API_KEY_URL}?scope=write%3Alists%20read%3Alists" in message


async def test_403_request_exceeds_capacity_is_not_retried():
    _FakeAsyncClient.responses = [
        _response(403, {"errors": ["request_exceeds_capacity"], "message": "too many fields"})
    ]

    with pytest.raises(client.HardcoverAPIError, match="burst limit"):
        await client.execute("query { a: me { id } }")

    assert len(_FakeAsyncClient.captured_headers) == 1


async def test_403_other_reason_is_reported():
    _FakeAsyncClient.responses = [_response(403, {"error": "account suspended"})]

    with pytest.raises(client.HardcoverAPIError, match="denied access: account suspended"):
        await client.execute("query { me { id } }")


async def test_graphql_errors_raise_api_error():
    _FakeAsyncClient.responses = [_response(200, {"errors": [{"message": "boom"}]})]

    with pytest.raises(client.HardcoverAPIError, match="GraphQL error: boom"):
        await client.execute("query { me { id } }")


def test_new_key_link_without_scopes():
    assert client.new_key_link() == client.NEW_API_KEY_URL


# ── Rate limiting ──


def test_parse_ratelimit_header():
    parsed = client._parse_ratelimit('"Free";r=8;t=0, "daily";r=4231;t=51234')

    assert parsed == {"Free": {"r": 8, "t": 0}, "daily": {"r": 4231, "t": 51234}}


def test_parse_ratelimit_skips_malformed_entries():
    assert client._parse_ratelimit('garbage, "Free";r=1') == {}


async def test_429_waits_for_retry_after(sleeps):
    _FakeAsyncClient.responses = [_response(429, {}, {"retry-after": "7"}), _response()]

    await client.execute("query { me { id } }")

    assert 7.0 in sleeps
    assert len(_FakeAsyncClient.captured_headers) == 2


async def test_503_is_retried_with_backoff(sleeps):
    _FakeAsyncClient.responses = [_response(503, {}), _response()]

    await client.execute("query { me { id } }")

    assert client._RETRY_BACKOFF in sleeps


async def test_429_gives_up_after_max_retries():
    _FakeAsyncClient.responses = [_response(429, {}) for _ in range(client._MAX_RETRIES + 1)]

    with pytest.raises(httpx.HTTPStatusError):
        await client.execute("query { me { id } }")


async def test_exhausted_per_minute_bucket_delays_next_request(sleeps):
    _FakeAsyncClient.responses = [
        _response(headers={"ratelimit": '"Free";r=0;t=12, "daily";r=100;t=500'}),
        _response(),
    ]

    await client.execute("query { me { id } }")
    await client.execute("query { me { id } }")

    assert any(10 < s <= 12 for s in sleeps)


async def test_exhausted_daily_quota_fails_fast():
    _FakeAsyncClient.responses = [_response(headers={"ratelimit": '"daily";r=0;t=3600'})]

    await client.execute("query { me { id } }")  # the last allowed request still succeeds
    with pytest.raises(client.HardcoverAPIError, match="daily API limit"):
        await client.execute("query { me { id } }")

    assert len(_FakeAsyncClient.captured_headers) == 1


async def test_429_with_daily_quota_used_up_fails_fast():
    _FakeAsyncClient.responses = [
        _response(429, {}, {"ratelimit": '"daily";r=0;t=3600', "retry-after": "3600"}),
    ]

    with pytest.raises(client.HardcoverAPIError, match="daily API limit"):
        await client.execute("query { me { id } }")
