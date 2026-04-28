"""Shared pytest configuration and fixtures."""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

# Auto-skip tests marked @pytest.mark.integration when HARDCOVER_API_TOKEN is absent.
_has_token = bool(os.environ.get("HARDCOVER_API_TOKEN", "").strip())


def pytest_collection_modifyitems(config, items):
    if _has_token:
        return
    skip = pytest.mark.skip(reason="HARDCOVER_API_TOKEN not set")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
