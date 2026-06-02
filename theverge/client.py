"""Main VergeClient — the public interface."""

from __future__ import annotations

import time
from typing import Any, Iterator, Optional
from urllib.parse import urljoin

import httpx

from . import next_data as nd
from .feeds import NEWSLETTERS, parse_feed, rss_path
from .models import Article, AuthorProfile, Category

BASE_URL = "https://www.theverge.com"
PAGE_SIZE = 40

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class VergeClient:
    """
    Unofficial Python client for The Verge.

    Not affiliated with or endorsed by The Verge or Vox Media.
    Please support independent journalism: https://www.theverge.com/subscribe

    Sources:
      - Subscriber RSS feeds for full-text article content
      - __NEXT_DATA__ SSR payloads for rich metadata (enrich=True)

    Parameters
    ----------
    rate_limit_delay : float
        Seconds to wait between requests. Default 0.5.
    timeout : float
        Request timeout in seconds.

    Example
    -------
    >>> from theverge import VergeClient
    >>> client = VergeClient()
    >>> articles = client.feed("tech")
    >>> print(articles[0].title)
    """

    def __init__(
        self,
        rate_limit_delay: float = 0.5,
        timeout: float = 15.0,
    ) -> None:
        self._delay = rate_limit_delay
        self._http = httpx.Client(
            headers=_DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )
        self._last_req: float = 0.0

    # ------------------------------------------------------------------
    # Feed methods
    # ------------------------------------------------------------------

    def feed(
        self,
        section: str = "",
        enrich: bool = False,
    ) -> list[Article]:
        """
        Fetch the latest articles from a section feed.

        Parameters
        ----------
        section : str
            Section slug. Options include:
              - "" (empty) — full homepage feed
              - "tech", "reviews", "science", "entertainment",
                "transportation", "games", "ai", "policy", "gadgets"
              - Any valid Verge section slug
        enrich : bool
            Fetch __NEXT_DATA__ for hero images, dek, and post type.
            Costs one extra HTTP request.

        Returns
        -------
        list[Article]
            Up to 30 articles with full body HTML.
        """
        articles = self._rss(section)
        if enrich and articles:
            self._enrich(articles, section)
        return articles

    def feed_iter(
        self,
        section: str = "",
        enrich: bool = False,
    ) -> Iterator[Article]:
        """
        Lazily iterate articles in a section — RSS first, then paginated
        __NEXT_DATA__ for older content.

        The first batch (up to 30) comes from RSS with full body HTML.
        Subsequent pages come from __NEXT_DATA__ (metadata only unless
        you call .article() on each to get the full body).

        Parameters
        ----------
        section : str
            Section slug. Same options as feed().
        enrich : bool
            Enrich the RSS batch with __NEXT_DATA__ metadata.
        """
        first = self._rss(section)
        if enrich and first:
            self._enrich(first, section)
        yield from first

        seen = {a.id for a in first}
        offset = PAGE_SIZE

        while True:
            nodes, has_next = self._next_feed_page(section, offset)
            new = [a for a in nodes if a.id not in seen]
            if not new:
                break
            seen.update(a.id for a in new)
            yield from new
            if not has_next:
                break
            offset += PAGE_SIZE

    # ------------------------------------------------------------------
    # Article detail
    # ------------------------------------------------------------------

    def article(self, path_or_url: str) -> Article:
        """
        Fetch a single article with full body + rich metadata.

        Parameters
        ----------
        path_or_url : str
            Relative path e.g. "/tech/941146/thermacell-..." or full URL.

        Returns
        -------
        Article
            Full article with body_html, hero_image, dek, authors, etc.

        Raises
        ------
        ValueError
            If the page doesn't contain a recognizable article.
        """
        url = _to_url(path_or_url)
        data = self._next(url)
        result = nd.article_detail(data)
        if result is None:
            raise ValueError(f"Could not parse article from {url}")
        return result

    # ------------------------------------------------------------------
    # Content types
    # ------------------------------------------------------------------

    def quick_posts(self) -> list[Article]:
        """Fetch the quick posts feed (short-form news items)."""
        return self._rss("quick_posts")

    def newsletter(self, name: str) -> list[Article]:
        """
        Fetch a newsletter feed.

        Parameters
        ----------
        name : str
            One of: notepad, regulator, the-stepback, installer, optimizer
        """
        if name not in NEWSLETTERS:
            raise ValueError(
                f"Unknown newsletter '{name}'. "
                f"Available: {', '.join(NEWSLETTERS)}"
            )
        return self._rss(name)

    def reviews(self, enrich: bool = False) -> list[Article]:
        """Fetch the reviews feed."""
        return self.feed("reviews", enrich=enrich)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def sections(self) -> list[Category]:
        """
        Return all site sections and categories.

        Fetches the homepage once and returns the full category list
        from __NEXT_DATA__.
        """
        data = self._next(BASE_URL)
        return nd.sections(data)

    def popular(self) -> list[dict]:
        """
        Return the most popular articles from the homepage.

        Returns a list of lightweight dicts (title, url, author, image_url,
        publish_date, tags). Simpler shape than Article — separate data source.
        """
        data = self._next(BASE_URL)
        return nd.popular(data)

    def author(self, slug: str) -> AuthorProfile:
        """
        Fetch an author profile with their recent articles.

        Parameters
        ----------
        slug : str
            Author URL slug e.g. "nilay-patel", "david-pierce".

        Returns
        -------
        AuthorProfile
            Name, bio, title, profile image, social links, recent posts.

        Raises
        ------
        ValueError
            If the author page can't be parsed.
        """
        url = f"{BASE_URL}/authors/{slug}"
        data = self._next(url)
        profile = nd.author_profile(data)
        if profile is None:
            raise ValueError(f"Could not parse author profile from {url}")
        return profile

    def search(self, query: str) -> list[Article]:
        """
        Search The Verge for articles matching a query.

        Note: The Verge's search page loads results client-side, so this
        method fetches the public RSS feed and filters by keyword match
        against title and summary. For better results, use feed() with a
        relevant section.

        Parameters
        ----------
        query : str
            Search terms.

        Returns
        -------
        list[Article]
            Articles whose title or summary contain any query term.
        """
        terms = [t.lower().strip() for t in query.split() if t.strip()]
        if not terms:
            return []

        all_articles = self._rss("")
        results = []
        for a in all_articles:
            text = (a.title + " " + a.summary + " " + " ".join(a.keywords)).lower()
            if any(term in text for term in terms):
                results.append(a)
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rss(self, section: str) -> list[Article]:
        path = rss_path(section)
        url = urljoin(BASE_URL, path)
        self._throttle()
        resp = self._http.get(url)
        resp.raise_for_status()
        return parse_feed(resp.text)

    def _next(self, url: str) -> dict:
        self._throttle()
        resp = self._http.get(url)
        resp.raise_for_status()
        return nd.extract(resp.text)

    def _next_feed_page(self, section: str, offset: int) -> tuple[list[Article], bool]:
        url = f"{BASE_URL}/{section}" if section else BASE_URL
        if offset > 0:
            url = f"{url}?offset={offset}"
        try:
            data = self._next(url)
            return nd.feed_page(data)
        except Exception:
            return [], False

    def _enrich(self, articles: list[Article], section: str) -> None:
        url = f"{BASE_URL}/{section}" if section else BASE_URL
        try:
            data = self._next(url)
            index = nd.build_index(data)
            for article in articles:
                node = index.get(article.wp_id) or index.get(article.id)
                if node:
                    nd.apply_enrichment(article, node)
        except Exception:
            pass  # enrichment is best-effort

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_req
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last_req = time.monotonic()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "VergeClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def _to_url(path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        return path_or_url
    return urljoin(BASE_URL, path_or_url)
