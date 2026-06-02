"""Unit tests for Article/Author/Image/Category models — no network."""

import json
from datetime import datetime, timezone

import pytest

from theverge.feeds import parse_feed
from theverge.models import Article, Author, Category, Image


@pytest.fixture
def sample_article(tech_rss) -> Article:
    return parse_feed(tech_rss)[0]


class TestArticleProperties:
    def test_wp_id(self, sample_article):
        assert sample_article.wp_id > 0

    def test_image_falls_back_to_body(self, sample_article):
        # RSS articles have no hero_image by default
        # image property should extract first img from body_html
        if sample_article.body_html:
            img = sample_article.image
            # May be None if no img tag, but should not raise
            assert img is None or isinstance(img, Image)

    def test_is_quick_post_false_for_regular(self, sample_article):
        # RSS feed doesn't set resource_type
        assert not sample_article.is_quick_post

    def test_author_names(self, sample_article):
        names = sample_article.author_names
        assert isinstance(names, list)
        assert len(names) > 0
        assert all(isinstance(n, str) for n in names)


class TestBodyText:
    def test_body_text_is_string(self, sample_article):
        text = sample_article.body_text
        assert isinstance(text, str)

    def test_body_text_shorter_than_html(self, sample_article):
        if sample_article.body_html:
            assert len(sample_article.body_text) < len(sample_article.body_html)

    def test_body_text_has_no_tags(self, sample_article):
        text = sample_article.body_text
        assert "<p>" not in text
        assert "<div>" not in text
        assert "<a " not in text

    def test_body_text_empty_when_no_body(self):
        a = _minimal_article(body_html="")
        assert a.body_text == ""

    def test_body_text_strips_script_tags(self):
        a = _minimal_article(body_html="<p>Hello</p><script>alert(1)</script><p>World</p>")
        text = a.body_text
        assert "alert" not in text
        assert "Hello" in text
        assert "World" in text


class TestBodyClean:
    def test_body_clean_is_string(self, sample_article):
        assert isinstance(sample_article.body_clean, str)

    def test_body_clean_strips_tracking_params(self):
        html = '<p><a href="https://example.com/?utm_source=verge&utm_medium=rss&ref=real">Link</a></p>'
        a = _minimal_article(body_html=html)
        clean = a.body_clean
        assert "utm_source" not in clean
        assert "utm_medium" not in clean
        # The real URL part should still be there
        assert "example.com" in clean

    def test_body_clean_strips_data_attributes(self):
        html = '<img src="img.jpg" data-caption="foo" data-portal-copyright="bar" alt="test"/>'
        a = _minimal_article(body_html=html)
        clean = a.body_clean
        assert "data-caption" not in clean
        assert "data-portal-copyright" not in clean
        assert 'src="img.jpg"' in clean
        assert 'alt="test"' in clean

    def test_body_clean_strips_class_attributes(self):
        html = '<p class="has-text-align-none wp-block-paragraph">Text</p>'
        a = _minimal_article(body_html=html)
        clean = a.body_clean
        assert 'class=' not in clean
        assert "Text" in clean


class TestSerialization:
    def test_to_dict_returns_dict(self, sample_article):
        d = sample_article.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_required_keys(self, sample_article):
        d = sample_article.to_dict()
        for key in ["id", "title", "permalink", "path", "author",
                    "published_at", "body_html", "keywords", "categories"]:
            assert key in d, f"Missing key: {key}"

    def test_to_json_is_valid_json(self, sample_article):
        j = sample_article.to_json()
        parsed = json.loads(j)
        assert parsed["title"] == sample_article.title

    def test_to_json_with_indent(self, sample_article):
        j = sample_article.to_json(indent=2)
        assert "\n" in j

    def test_from_dict_round_trip(self, sample_article):
        d = sample_article.to_dict()
        restored = Article.from_dict(d)
        assert restored.title == sample_article.title
        assert restored.permalink == sample_article.permalink
        assert restored.wp_id == sample_article.wp_id
        assert restored.published_at.isoformat() == sample_article.published_at.isoformat()

    def test_from_json_round_trip(self, sample_article):
        j = sample_article.to_json()
        restored = Article.from_json(j)
        assert restored.title == sample_article.title
        assert restored.author == sample_article.author

    def test_from_dict_handles_missing_optional_fields(self):
        minimal = {
            "id": "https://www.theverge.com/?p=1",
            "title": "Test",
            "permalink": "https://www.theverge.com/test",
            "path": "/test",
            "author": "Author",
            "authors": [],
            "published_at": "2026-01-01T00:00:00+00:00",
            "updated_at": None,
            "summary": "",
            "body_html": "",
            "keywords": [],
            "categories": [],
        }
        a = Article.from_dict(minimal)
        assert a.title == "Test"
        assert a.dek is None
        assert a.hero_image is None

    def test_from_dict_restores_authors(self, sample_article):
        d = sample_article.to_dict()
        restored = Article.from_dict(d)
        assert len(restored.authors) == len(sample_article.authors)
        if restored.authors:
            assert restored.authors[0].name == sample_article.authors[0].name

    def test_from_dict_restores_categories(self, sample_article):
        d = sample_article.to_dict()
        restored = Article.from_dict(d)
        assert len(restored.categories) == len(sample_article.categories)


class TestImageFromBody:
    def test_extracts_first_image(self):
        html = '<p>Text</p><figure><img src="https://cdn.example.com/photo.jpg" alt="desc"/></figure>'
        a = _minimal_article(body_html=html)
        img = a.image
        assert img is not None
        assert "photo.jpg" in img.url

    def test_returns_none_when_no_image(self):
        a = _minimal_article(body_html="<p>No image here.</p>")
        assert a.image is None

    def test_hero_image_takes_precedence(self):
        hero = Image(url="https://hero.example.com/img.jpg")
        body_html = '<img src="https://body.example.com/img.jpg"/>'
        a = _minimal_article(body_html=body_html, hero_image=hero)
        assert a.image.url == hero.url


class TestAuthor:
    def test_from_name(self):
        a = Author.from_name("Nilay Patel")
        assert a.name == "Nilay Patel"
        assert a.path == ""

    def test_from_dict_round_trip(self):
        a = Author(name="Test Author", path="/authors/test", title="Editor")
        d = a.to_dict()
        restored = Author.from_dict(d)
        assert restored.name == a.name
        assert restored.title == a.title


class TestCategory:
    def test_from_dict_round_trip(self):
        c = Category(title="Tech", slug="tech", path="/tech", id="abc123")
        d = c.to_dict()
        restored = Category.from_dict(d)
        assert restored.title == c.title
        assert restored.slug == c.slug


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_article(body_html: str = "", hero_image=None) -> Article:
    return Article(
        id="https://www.theverge.com/?p=1",
        title="Test Article",
        permalink="https://www.theverge.com/test",
        path="/test",
        author="Test Author",
        authors=[],
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=None,
        summary="A test article.",
        body_html=body_html,
        keywords=[],
        categories=[],
        hero_image=hero_image,
    )
