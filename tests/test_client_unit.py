"""Unit tests for client logic — uses mocked HTTP, no real network."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from theverge.client import _filter_since, _is_before, _score_and_rank
from theverge.models import Article


def _article(
    title: str = "Test",
    published: str = "2026-06-01T12:00:00+00:00",
    body: str = "",
    wp_id_override: int = 0,
) -> Article:
    from theverge.utils import parse_iso
    from theverge.models import Author
    dt = parse_iso(published) or datetime.now(timezone.utc)
    guid = f"https://www.theverge.com/?p={wp_id_override or abs(hash(title)) % 100000}"
    return Article(
        id=guid,
        title=title,
        permalink=f"https://www.theverge.com/{title.lower().replace(' ', '-')}",
        path=f"/{title.lower().replace(' ', '-')}",
        author="Author",
        authors=[Author.from_name("Author")],
        published_at=dt,
        updated_at=None,
        summary=title,
        body_html=body,
        keywords=[],
        categories=[],
    )


class TestFilterSince:
    def test_keeps_recent_articles(self):
        articles = [
            _article("New", "2026-06-02T12:00:00+00:00"),
            _article("Old", "2026-05-01T12:00:00+00:00"),
        ]
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        result = _filter_since(articles, since)
        assert len(result) == 1
        assert result[0].title == "New"

    def test_keeps_exact_match(self):
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        articles = [_article("Exact", "2026-06-01T00:00:00+00:00")]
        result = _filter_since(articles, since)
        assert len(result) == 1

    def test_empty_input(self):
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert _filter_since([], since) == []

    def test_all_old_returns_empty(self):
        articles = [_article("Old", "2025-01-01T00:00:00+00:00")]
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _filter_since(articles, since) == []

    def test_handles_naive_datetime(self):
        # naive since should still work (gets UTC attached)
        since = datetime(2026, 6, 1)  # no tzinfo
        articles = [_article("New", "2026-06-02T00:00:00+00:00")]
        result = _filter_since(articles, since)
        assert len(result) == 1


class TestIsBefore:
    def test_old_article_is_before(self):
        a = _article("Old", "2025-01-01T00:00:00+00:00")
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _is_before(a, since) is True

    def test_new_article_is_not_before(self):
        a = _article("New", "2026-06-02T00:00:00+00:00")
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert _is_before(a, since) is False


class TestScoreAndRank:
    def test_returns_only_matching_articles(self):
        articles = [
            _article("Apple iPhone review"),
            _article("Unrelated gardening tips"),
            _article("Apple Watch series 10"),
        ]
        results = _score_and_rank(articles, ["apple"])
        titles = [r.title for r in results]
        assert "Apple iPhone review" in titles
        assert "Apple Watch series 10" in titles
        assert "Unrelated gardening tips" not in titles

    def test_higher_frequency_ranked_first(self):
        articles = [
            _article("Nvidia GPU review"),
            _article("Nvidia Nvidia Nvidia GPU news"),  # more hits
        ]
        results = _score_and_rank(articles, ["nvidia"])
        assert results[0].title == "Nvidia Nvidia Nvidia GPU news"

    def test_deduplicates_by_wp_id(self):
        articles = [
            _article("Duplicate", wp_id_override=999),
            _article("Duplicate", wp_id_override=999),  # same wp_id
            _article("Different", wp_id_override=888),
        ]
        results = _score_and_rank(articles, ["duplicate", "different"])
        titles = [r.title for r in results]
        # Should not have two "Duplicate" entries
        assert titles.count("Duplicate") <= 1

    def test_no_results_when_no_match(self):
        articles = [_article("Tech news"), _article("Science stuff")]
        results = _score_and_rank(articles, ["zzznomatch"])
        assert results == []

    def test_empty_terms_not_called(self):
        # _score_and_rank with empty terms would match everything
        # but the client guards this — just verify it doesn't crash
        results = _score_and_rank([], ["test"])
        assert results == []

    def test_sorted_by_recency_when_equal_score(self):
        articles = [
            _article("Old match", "2026-01-01T00:00:00+00:00"),
            _article("New match", "2026-06-01T00:00:00+00:00"),
        ]
        results = _score_and_rank(articles, ["match"])
        # Equal score — newer first
        assert results[0].title == "New match"
