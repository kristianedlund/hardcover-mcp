"""Unit-test guard: nothing under tests/tools may send a real request to Hardcover."""

import pytest

from hardcover_mcp import client


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse():
        raise AssertionError("a unit test tried to call Hardcover; mock execute where it's used")

    monkeypatch.setattr(client, "_http_client", refuse)
