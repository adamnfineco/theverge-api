"""
Integration / E2E tests — hit the real Verge website.

These tests require a live internet connection and are NOT run by default.
Run with: pytest -m integration

They verify that The Verge hasn't changed its feed/page structure in a way
that breaks the library. If these fail, the site structure may have changed
and fixtures + parsing logic may need updating.
"""

import asyncio
from datetime import timezone

import pytest

from theverge import AsyncVergeClient, VergeClient, since_hours
from theverge.models import Article, AuthorProfile

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Sync integration tests
# ---------------------------------------------------------------------------

class TestVergeClientIntegration:
    @pytest.fixture(scope="class")
    def client(self):
        with VergeClient(rate_limit_delay=0.5, cache_ttl=300) as c:
            yield c

    def test_feed_returns_articles(self, client):
        articles = client.feed()
        assert len(articles) > 0
        assert all(isinstance(a, Article) for a in articles)

    def test_feed_articles_have_body(self, client):
        articles = client.feed("tech")
        bodies = [a for a in articles if len(a.body_html) > 100]
        assert len(bodies) > 10, "Subscriber feed should have full body HTML"

    def test_feed_with_enrich(self, client):
        articles = client.feed("tech", enrich=True)
        enriched = [a for a in articles if a.hero_image or a.dek]
        assert len(enriched) > 0, "Enrichment should add hero images or deks"

    def test_feed_since_filters(self, client):
        recent = client.feed("tech", since=since_hours(48))
        all_articles = client.feed("tech")
        assert len(recent) <= len(all_articles)
        for a in recent:
            age_hours = (
                __import__("datetime").datetime.now(timezone.utc) - a.published_at
            ).total_seconds() / 3600
            assert age_hours <= 49, f"Article too old: {a.title} ({age_hours:.1f}h)"

    def test_article_detail(self, client):
        # Get a real article path from the feed
        articles = client.feed("tech")
        assert articles, "Need articles to test detail fetch"
        a = client.article(articles[0].path)
        assert a.title
        assert len(a.body_html) > 100

    def test_quick_posts(self, client):
        posts = client.quick_posts()
        assert len(posts) > 0
        assert all(isinstance(a, Article) for a in posts)

    def test_newsletter_installer(self, client):
        nl = client.newsletter("installer")
        assert len(nl) > 0
        bodies = [a for a in nl if len(a.body_html) > 500]
        assert len(bodies) > 0, "Installer newsletter should have long body content"

    def test_author_profile(self, client):
        profile = client.author("nilay-patel")
        assert isinstance(profile, AuthorProfile)
        assert profile.name == "Nilay Patel"
        assert profile.title
        assert len(profile.recent_posts) > 0

    def test_search_returns_relevant_results(self, client):
        results = client.search("microsoft windows")
        assert len(results) > 0
        # At least one result should have "microsoft" or "windows" in title
        relevant = [r for r in results if
                    "microsoft" in r.title.lower() or "windows" in r.title.lower()]
        assert len(relevant) > 0

    def test_sections_returns_categories(self, client):
        sections = client.sections()
        assert len(sections) > 10
        slugs = [s.slug for s in sections]
        assert any("tech" in s for s in slugs)

    def test_popular_returns_dicts(self, client):
        popular = client.popular()
        assert len(popular) > 0
        assert all(isinstance(p, dict) for p in popular)
        assert all("title" in p for p in popular)

    def test_reviews_feed(self, client):
        reviews = client.reviews()
        assert len(reviews) > 0

    def test_cache_works(self, client):
        import time
        # First call
        client.feed("tech")
        # Second call should hit cache
        t0 = time.monotonic()
        client.feed("tech")
        elapsed = time.monotonic() - t0
        assert elapsed < 0.05, f"Cache miss? {elapsed:.3f}s"

    def test_body_text_extraction(self, client):
        articles = client.feed("tech")
        a = next((x for x in articles if x.body_html), None)
        assert a is not None
        text = a.body_text
        assert len(text) > 50
        assert "<" not in text

    def test_to_json_from_json_roundtrip(self, client):
        articles = client.feed("tech")
        a = articles[0]
        restored = Article.from_json(a.to_json())
        assert restored.title == a.title
        assert restored.wp_id == a.wp_id

    def test_feed_iter_paginates(self, client):
        seen = []
        for a in client.feed_iter("tech"):
            seen.append(a)
            if len(seen) >= 45:  # past first RSS batch of 30
                break
        assert len(seen) >= 40, "Should paginate past 30 via __NEXT_DATA__"

    def test_fetch_body_hydrates_metadata_article(self, client):
        # Get articles beyond the RSS batch
        all_articles = list(client.feed_iter("tech"))
        empty_body = [a for a in all_articles if not a.body_html]
        if not empty_body:
            pytest.skip("All articles in feed have body (unexpected but OK)")
        a = empty_body[0]
        a.fetch_body(client)
        assert len(a.body_html) > 100


# ---------------------------------------------------------------------------
# Async integration tests
# ---------------------------------------------------------------------------

class TestAsyncVergeClientIntegration:
    """Async integration tests — each test creates its own client to avoid event loop issues."""

    @pytest.mark.asyncio
    async def test_async_feed(self):
        async with AsyncVergeClient(rate_limit_delay=0.5, cache_ttl=300) as c:
            articles = await c.feed("tech")
            assert len(articles) > 0

    @pytest.mark.asyncio
    async def test_async_since(self):
        async with AsyncVergeClient(rate_limit_delay=0.5, cache_ttl=300) as c:
            recent = await c.feed("tech", since=since_hours(48))
            assert isinstance(recent, list)

    @pytest.mark.asyncio
    async def test_async_search_concurrent(self):
        async with AsyncVergeClient(rate_limit_delay=0.5, cache_ttl=300) as c:
            results = await c.search("nvidia spark")
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_async_article(self):
        async with AsyncVergeClient(rate_limit_delay=0.5, cache_ttl=300) as c:
            articles = await c.feed("tech")
            assert articles
            full = await c.article(articles[0].path)
            assert full.title

    @pytest.mark.asyncio
    async def test_async_author(self):
        async with AsyncVergeClient(rate_limit_delay=0.5) as c:
            profile = await c.author("david-pierce")
            assert profile.name == "David Pierce"

    @pytest.mark.asyncio
    async def test_async_feed_iter(self):
        async with AsyncVergeClient(rate_limit_delay=0.5, cache_ttl=300) as c:
            count = 0
            async for a in c.feed_iter("tech"):
                count += 1
                if count >= 5:
                    break
            assert count == 5

    @pytest.mark.asyncio
    async def test_fetch_body_async(self):
        async with AsyncVergeClient(rate_limit_delay=0.5, cache_ttl=300) as c:
            all_articles = []
            async for a in c.feed_iter("tech"):
                all_articles.append(a)
                if len(all_articles) >= 50:
                    break
            empty = [a for a in all_articles if not a.body_html]
            if not empty:
                pytest.skip("No empty-body articles in first 50")
            a = empty[0]
            await a.fetch_body_async(c)
            assert len(a.body_html) > 100
