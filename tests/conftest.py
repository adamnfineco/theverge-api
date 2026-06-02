"""Shared fixtures for the theverge test suite."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tech_rss() -> str:
    return (FIXTURES / "tech_feed.rss").read_text()


@pytest.fixture
def quickposts_rss() -> str:
    return (FIXTURES / "quickposts_feed.rss").read_text()


@pytest.fixture
def tech_next_data() -> dict:
    return json.loads((FIXTURES / "tech_next_data.json").read_text())


@pytest.fixture
def author_next_data() -> dict:
    return json.loads((FIXTURES / "author_next_data.json").read_text())
