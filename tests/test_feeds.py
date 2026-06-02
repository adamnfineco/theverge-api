"""Unit tests for RSS feed parsing — no network required."""

from datetime import datetime, timezone

import pytest

from theverge.feeds import parse_feed
from theverge.models import Article


class TestRSS2Parsing:
    def test_returns_list_of_articles(self, tech_rss):
        articles = parse_feed(tech_rss)
        assert isinstance(articles, list)
        assert len(articles) > 0

    def test_article_has_required_fields(self, tech_rss):
        a = parse_feed(tech_rss)[0]
        assert isinstance(a, Article)
        assert a.title
        assert a.permalink.startswith("https://www.theverge.com/")
        assert a.author
        assert isinstance(a.published_at, datetime)

    def test_body_html_is_populated(self, tech_rss):
        articles = parse_feed(tech_rss)
        # At least some articles should have full body from subscriber feed
        bodies = [a for a in articles if len(a.body_html) > 100]
        assert len(bodies) > 0, "Expected at least some articles with body HTML"

    def test_wp_id_extracted_from_guid(self, tech_rss):
        a = parse_feed(tech_rss)[0]
        assert a.wp_id > 0, f"wp_id should be positive int, got {a.wp_id}"

    def test_keywords_parsed(self, tech_rss):
        articles = parse_feed(tech_rss)
        articles_with_kw = [a for a in articles if a.keywords]
        assert len(articles_with_kw) > 0

    def test_published_at_is_timezone_aware(self, tech_rss):
        a = parse_feed(tech_rss)[0]
        assert a.published_at.tzinfo is not None

    def test_path_is_relative(self, tech_rss):
        a = parse_feed(tech_rss)[0]
        assert a.path.startswith("/")
        assert not a.path.startswith("http")

    def test_summary_is_populated(self, tech_rss):
        a = parse_feed(tech_rss)[0]
        assert len(a.summary) > 10

    def test_author_list_populated(self, tech_rss):
        a = parse_feed(tech_rss)[0]
        assert len(a.authors) == 1
        assert a.authors[0].name == a.author


class TestAtomParsing:
    """The public /rss/index.xml is Atom format — test it separately."""

    ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>The Verge</title>
      <entry>
        <title type="html"><![CDATA[Test Article Title]]></title>
        <link rel="alternate" type="text/html" href="https://www.theverge.com/tech/123/test-article"/>
        <id>https://www.theverge.com/?p=123</id>
        <author><name>Test Author</name></author>
        <published>2026-06-01T12:00:00+00:00</published>
        <summary type="html"><![CDATA[Test summary text.]]></summary>
        <category term="Tech"/>
        <category term="News"/>
      </entry>
    </feed>"""

    def test_atom_feed_parsed(self):
        articles = parse_feed(self.ATOM_SAMPLE)
        assert len(articles) == 1

    def test_atom_title(self):
        a = parse_feed(self.ATOM_SAMPLE)[0]
        assert a.title == "Test Article Title"

    def test_atom_author(self):
        a = parse_feed(self.ATOM_SAMPLE)[0]
        assert a.author == "Test Author"

    def test_atom_categories(self):
        a = parse_feed(self.ATOM_SAMPLE)[0]
        titles = [c.title for c in a.categories]
        assert "Tech" in titles
        assert "News" in titles

    def test_atom_published_at(self):
        a = parse_feed(self.ATOM_SAMPLE)[0]
        assert a.published_at.year == 2026
        assert a.published_at.month == 6


class TestQuickPostsParsing:
    def test_quickposts_parsed(self, quickposts_rss):
        articles = parse_feed(quickposts_rss)
        assert len(articles) > 0

    def test_quickposts_have_titles(self, quickposts_rss):
        articles = parse_feed(quickposts_rss)
        for a in articles:
            assert a.title
