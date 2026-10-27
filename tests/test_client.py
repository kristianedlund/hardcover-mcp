"""Tests for the GraphQL client: request construction, errors, and rate limiting."""

import subprocess
import sys

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
    captured_urls: list[str] = []  # noqa: RUF012
    instances: int = 0

    def __init__(self, *args, **kwargs):
        _FakeAsyncClient.instances += 1
        self.is_closed = False

    async def aclose(self):
        self.is_closed = True

    async def post(self, url, json=None, headers=None):
        _FakeAsyncClient.captured_headers.append(headers)
        _FakeAsyncClient.captured_urls.append(url)
        response = _FakeAsyncClient.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def sleeps(monkeypatch) -> list[float]:
    """Fresh rate-limit state, a fake HTTP client, a token, and recorded (not real) sleeps."""
    client._request_timestamps.clear()
    monkeypatch.setattr(client, "_blocked_until", 0.0)
    monkeypatch.setattr(client, "_daily_reset_at", None)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(client, "_client", None)
    monkeypatch.setattr(client, "_client_loop", None)
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token-not-real")
    monkeypatch.delenv("HARDCOVER_API_URL", raising=False)
    recorded: list[float] = []

    async def fake_sleep(seconds):
        recorded.append(seconds)

    monkeypatch.setattr(client.asyncio, "sleep", fake_sleep)
    _FakeAsyncClient.responses = []
    _FakeAsyncClient.captured_headers = []
    _FakeAsyncClient.captured_urls = []
    _FakeAsyncClient.instances = 0
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

    with pytest.raises(client.HardcoverAPIError, match=r"busy \(HTTP 429\).*5 retries"):
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


# ── Connection reuse ──


async def test_requests_share_one_http_client():
    _FakeAsyncClient.responses = [_response(), _response(429, {}), _response()]

    await client.execute("query { me { id } }")
    await client.execute("query { me { id } }")  # includes a retry

    assert len(_FakeAsyncClient.captured_headers) == 3
    assert _FakeAsyncClient.instances == 1


async def test_new_event_loop_gets_a_new_client(monkeypatch):
    _FakeAsyncClient.responses = [_response(), _response()]
    await client.execute("query { me { id } }")
    monkeypatch.setattr(client, "_client_loop", object())  # as if created on another loop

    await client.execute("query { me { id } }")

    assert _FakeAsyncClient.instances == 2


async def test_aclose_closes_and_the_next_request_reopens():
    _FakeAsyncClient.responses = [_response(), _response()]
    await client.execute("query { me { id } }")
    first = client._client

    await client.aclose()
    assert first.is_closed
    assert client._client is None

    await client.execute("query { me { id } }")
    assert _FakeAsyncClient.instances == 2


async def test_aclose_without_a_client_is_a_no_op():
    await client.aclose()
    assert client._client is None


# ── Endpoint and environment ──


async def test_default_api_url():
    _FakeAsyncClient.responses = [_response()]

    await client.execute("query { me { id } }")

    assert _FakeAsyncClient.captured_urls == [client.DEFAULT_API_URL]


async def test_custom_https_api_url_is_used(monkeypatch):
    monkeypatch.setenv("HARDCOVER_API_URL", "https://proxy.example/v1/graphql")
    _FakeAsyncClient.responses = [_response()]

    await client.execute("query { me { id } }")

    assert _FakeAsyncClient.captured_urls == ["https://proxy.example/v1/graphql"]


@pytest.mark.parametrize("url", ["http://evil.example/graphql", "ftp://x", "api.hardcover.app"])
async def test_non_https_api_url_is_refused_before_sending(monkeypatch, url):
    monkeypatch.setenv("HARDCOVER_API_URL", url)

    with pytest.raises(client.HardcoverAPIError, match="must be an https:// URL"):
        await client.execute("query { me { id } }")

    assert _FakeAsyncClient.captured_urls == []


def test_importing_the_package_does_not_load_dotenv():
    # A stray .env above the install directory must not configure the server.
    code = "import sys, hardcover_mcp.server; print('dotenv' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


# ── Network and HTTP errors ──


async def test_timeout_is_a_clear_error_and_not_retried():
    _FakeAsyncClient.responses = [httpx.ReadTimeout("slow"), _response()]

    with pytest.raises(client.HardcoverAPIError, match="didn't answer within 30 seconds"):
        await client.execute("mutation { x }")

    assert len(_FakeAsyncClient.captured_headers) == 1  # no second attempt


async def test_connection_failure_is_a_clear_error():
    _FakeAsyncClient.responses = [httpx.ConnectError("name resolution failed")]

    with pytest.raises(client.HardcoverAPIError, match="Couldn't reach Hardcover"):
        await client.execute("query { me { id } }")


@pytest.mark.parametrize("status", [400, 404, 500, 502])
async def test_other_http_errors_are_clear_errors(status):
    _FakeAsyncClient.responses = [_response(status, {})]

    with pytest.raises(client.HardcoverAPIError, match=f"HTTP {status}"):
        await client.execute("query { me { id } }")


# ── Retry waits ──


async def test_long_retry_after_gives_up_instead_of_waiting(sleeps):
    _FakeAsyncClient.responses = [_response(429, {}, {"retry-after": "86400"}), _response()]

    with pytest.raises(client.HardcoverAPIError, match="wait 86400 seconds"):
        await client.execute("query { me { id } }")

    assert len(_FakeAsyncClient.captured_headers) == 1  # no retry sent
    assert all(s <= client._MAX_WAIT for s in sleeps)


async def test_retry_waits_for_the_ratelimit_reset(sleeps):
    # No Retry-After, but the RateLimit header says the bucket resets in 30 s: waiting only
    # the 3 s backoff would send a retry that's sure to fail.
    blocked = _response(429, {}, {"ratelimit": '"Free";r=0;t=30'})
    _FakeAsyncClient.responses = [blocked, _response()]

    await client.execute("query { me { id } }")

    assert len(_FakeAsyncClient.captured_headers) == 2
    assert any(29 <= s <= 30 for s in sleeps)


async def test_long_ratelimit_reset_gives_up(sleeps):
    blocked = _response(429, {}, {"ratelimit": '"Free";r=0;t=600'})
    _FakeAsyncClient.responses = [blocked, _response()]

    with pytest.raises(client.HardcoverAPIError, match="Try again then"):
        await client.execute("query { me { id } }")

    assert len(_FakeAsyncClient.captured_headers) == 1


async def test_retries_count_toward_the_per_minute_window():
    _FakeAsyncClient.responses = [_response(503, {}), _response()]

    await client.execute("query { me { id } }")

    assert len(client._request_timestamps) == 2


async def test_long_block_before_a_request_gives_up(monkeypatch):
    monkeypatch.setattr(client, "_blocked_until", client.time.monotonic() + 600)
    _FakeAsyncClient.responses = [_response()]

    with pytest.raises(client.HardcoverAPIError, match="rate limit asks to wait"):
        await client.execute("query { me { id } }")

    assert _FakeAsyncClient.captured_headers == []
