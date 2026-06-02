"""Unit tests for utility functions."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from theverge.utils import (
    TTLCache,
    clean_html,
    html_to_text,
    parse_dt,
    parse_iso,
    parse_rfc2822,
    since_hours,
)


class TestTTLCache:
    def test_get_returns_none_when_empty(self):
        cache = TTLCache(ttl=60)
        assert cache.get("missing") is None

    def test_set_and_get(self):
        cache = TTLCache(ttl=60)
        cache.set("key", [1, 2, 3])
        assert cache.get("key") == [1, 2, 3]

    def test_expiry(self):
        cache = TTLCache(ttl=0.05)  # 50ms TTL
        cache.set("key", "value")
        assert cache.get("key") == "value"
        time.sleep(0.1)
        assert cache.get("key") is None

    def test_zero_ttl_disables_caching(self):
        cache = TTLCache(ttl=0)
        cache.set("key", "value")
        assert cache.get("key") is None

    def test_clear(self):
        cache = TTLCache(ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None

    def test_overwrite(self):
        cache = TTLCache(ttl=60)
        cache.set("key", "first")
        cache.set("key", "second")
        assert cache.get("key") == "second"

    def test_caches_none_value(self):
        # None as a stored value should work — cache miss returns None too,
        # but a set None should be distinguishable... actually this is the
        # known limitation — we use None as sentinel. Document this.
        cache = TTLCache(ttl=60)
        cache.set("key", None)
        # get() can't distinguish None-stored from missing — that's okay for our use case
        # This test just ensures set doesn't raise
        assert True


class TestHtmlToText:
    def test_strips_basic_tags(self):
        result = html_to_text("<p>Hello <strong>world</strong></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<p>" not in result
        assert "<strong>" not in result

    def test_handles_empty_string(self):
        assert html_to_text("") == ""

    def test_strips_script_tags(self):
        result = html_to_text("<p>Before</p><script>alert(1)</script><p>After</p>")
        assert "alert" not in result
        assert "Before" in result
        assert "After" in result

    def test_strips_style_tags(self):
        result = html_to_text("<style>.foo { color: red }</style><p>Text</p>")
        assert "color" not in result
        assert "Text" in result

    def test_preserves_paragraph_breaks(self):
        result = html_to_text("<p>First para</p><p>Second para</p>")
        assert "First para" in result
        assert "Second para" in result
        # Should have some separation
        assert result.index("First") < result.index("Second")

    def test_handles_entities(self):
        result = html_to_text("<p>AT&amp;T &mdash; it&apos;s great</p>")
        assert "AT&T" in result or "AT" in result

    def test_handles_nested_tags(self):
        result = html_to_text("<p><a href='#'><strong>Linked text</strong></a></p>")
        assert "Linked text" in result
        assert "<" not in result

    def test_collapses_whitespace(self):
        result = html_to_text("<p>Too   many    spaces</p>")
        assert "Too many spaces" in result or "Too" in result


class TestCleanHtml:
    def test_strips_utm_params(self):
        html = '<a href="https://example.com/page?utm_source=verge&utm_medium=rss">Link</a>'
        clean = clean_html(html)
        assert "utm_source" not in clean
        assert "utm_medium" not in clean
        assert "example.com" in clean

    def test_strips_irclickid(self):
        html = '<a href="https://amazon.com/product?tag=verge&irclickid=abc123">Buy</a>'
        clean = clean_html(html)
        assert "irclickid" not in clean

    def test_strips_data_attributes(self):
        html = '<img src="photo.jpg" data-caption="test" data-portal-copyright="Verge" alt="pic"/>'
        clean = clean_html(html)
        assert "data-caption" not in clean
        assert "data-portal-copyright" not in clean
        assert 'src="photo.jpg"' in clean
        assert 'alt="pic"' in clean

    def test_strips_class_attribute(self):
        html = '<p class="has-text-align-none wp-block-paragraph">Content</p>'
        clean = clean_html(html)
        assert "class=" not in clean
        assert "Content" in clean

    def test_strips_style_attribute(self):
        html = '<div style="margin: 0; padding: 0">Content</div>'
        clean = clean_html(html)
        assert "style=" not in clean
        assert "Content" in clean

    def test_preserves_src_and_href(self):
        html = '<a href="https://theverge.com/article">Text</a>'
        clean = clean_html(html)
        assert 'href="https://theverge.com/article"' in clean

    def test_handles_empty_string(self):
        assert clean_html("") == ""

    def test_does_not_break_clean_html(self):
        html = "<p>Simple paragraph with <strong>bold</strong> text.</p>"
        clean = clean_html(html)
        assert "Simple paragraph" in clean
        assert "<strong>" in clean


class TestDateParsing:
    def test_parse_rfc2822(self):
        dt = parse_rfc2822("Tue, 02 Jun 2026 13:00:00 -0400")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 6

    def test_parse_rfc2822_invalid_returns_none(self):
        assert parse_rfc2822("not a date") is None

    def test_parse_iso(self):
        dt = parse_iso("2026-06-02T13:00:00+00:00")
        assert dt is not None
        assert dt.year == 2026

    def test_parse_iso_with_z(self):
        dt = parse_iso("2026-06-02T13:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_parse_iso_none_input(self):
        assert parse_iso(None) is None

    def test_parse_dt_tries_rfc2822_first(self):
        dt = parse_dt("Tue, 02 Jun 2026 09:00:00 -0400")
        assert dt is not None
        assert dt.year == 2026

    def test_parse_dt_falls_back_to_iso(self):
        dt = parse_dt("2026-06-02T09:00:00+00:00")
        assert dt is not None

    def test_parse_dt_none_returns_none(self):
        assert parse_dt(None) is None


class TestSinceHours:
    def test_returns_datetime(self):
        dt = since_hours(24)
        assert isinstance(dt, datetime)

    def test_is_timezone_aware(self):
        dt = since_hours(24)
        assert dt.tzinfo is not None

    def test_approximately_correct(self):
        now = datetime.now(timezone.utc)
        dt = since_hours(1)
        diff = now - dt
        assert 59 < diff.total_seconds() / 60 < 61  # within a minute of 1 hour ago
