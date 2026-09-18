"""Tests for the GraphQL client's request construction."""

import httpx
import pytest

from hardcover_mcp import client


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": {}}


class _FakeAsyncClient:
    """Records the headers/kwargs passed to post() without making a real request."""

    captured_headers: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        _FakeAsyncClient.captured_headers = headers
        return _FakeResponse()


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    client._request_timestamps.clear()
    yield
    client._request_timestamps.clear()


async def test_execute_sends_bearer_prefixed_authorization_header(monkeypatch):
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token-not-real")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    await client.execute("query { me { id } }")

    headers = _FakeAsyncClient.captured_headers
    assert headers is not None
    assert headers["authorization"] == "Bearer test-token-not-real"


async def test_execute_raises_without_token(monkeypatch):
    monkeypatch.delenv("HARDCOVER_API_TOKEN", raising=False)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(RuntimeError, match="HARDCOVER_API_TOKEN is not set"):
        await client.execute("query { me { id } }")
