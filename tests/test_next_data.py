"""Unit tests for __NEXT_DATA__ extraction — no network."""

import pytest

from theverge import next_data as nd
from theverge.models import Article, AuthorProfile, Category


class TestExtract:
    def test_extracts_dict(self, tech_next_data):
        assert isinstance(tech_next_data, dict)
        assert "props" in tech_next_data
        assert "page" in tech_next_data

    def test_raises_on_missing_script(self):
        with pytest.raises(ValueError, match="No __NEXT_DATA__"):
            nd.extract("<html><body>no script here</body></html>")

    def test_page_route(self, tech_next_data):
        assert "tech" in tech_next_data.get("page", "").lower() or \
               "resource" in tech_next_data.get("page", "").lower()

    def test_gssp_flag(self, tech_next_data):
        # The Verge uses SSR, not SSG
        assert tech_next_data.get("gssp") is True


class TestFeedPage:
    def test_returns_articles_and_bool(self, tech_next_data):
        articles, has_next = nd.feed_page(tech_next_data)
        assert isinstance(articles, list)
        assert isinstance(has_next, bool)

    def test_articles_have_titles(self, tech_next_data):
        articles, _ = nd.feed_page(tech_next_data)
        if articles:
            for a in articles:
                assert a.title

    def test_articles_have_ids(self, tech_next_data):
        articles, _ = nd.feed_page(tech_next_data)
        if articles:
            for a in articles:
                assert a.id

    def test_pagination_state(self, tech_next_data):
        _, has_next = nd.feed_page(tech_next_data)
        # Tech section has many pages
        assert has_next is True


class TestSections:
    def test_returns_list(self, tech_next_data):
        cats = nd.sections(tech_next_data)
        assert isinstance(cats, list)

    def test_categories_have_titles(self, tech_next_data):
        cats = nd.sections(tech_next_data)
        assert len(cats) > 0
        for c in cats[:5]:
            assert c.title

    def test_category_type(self, tech_next_data):
        cats = nd.sections(tech_next_data)
        for c in cats:
            assert isinstance(c, Category)


class TestBuildIndex:
    def test_returns_dict(self, tech_next_data):
        index = nd.build_index(tech_next_data)
        assert isinstance(index, dict)

    def test_index_has_entries(self, tech_next_data):
        index = nd.build_index(tech_next_data)
        assert len(index) > 0

    def test_index_keys_are_wp_ids_or_strings(self, tech_next_data):
        index = nd.build_index(tech_next_data)
        for key in list(index.keys())[:5]:
            assert isinstance(key, (int, str))


class TestAuthorProfile:
    def test_extracts_author(self, author_next_data):
        profile = nd.author_profile(author_next_data)
        assert profile is not None
        assert isinstance(profile, AuthorProfile)

    def test_author_has_name(self, author_next_data):
        profile = nd.author_profile(author_next_data)
        assert profile.name

    def test_author_has_title(self, author_next_data):
        profile = nd.author_profile(author_next_data)
        # Nilay Patel should have a title
        assert profile.title

    def test_author_has_recent_posts(self, author_next_data):
        profile = nd.author_profile(author_next_data)
        assert len(profile.recent_posts) > 0
        for post in profile.recent_posts:
            assert isinstance(post, Article)
            assert post.title

    def test_author_to_dict(self, author_next_data):
        profile = nd.author_profile(author_next_data)
        d = profile.to_dict()
        assert "name" in d
        assert "recent_posts" in d
        assert isinstance(d["recent_posts"], list)
