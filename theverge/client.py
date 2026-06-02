"""Verge clients — synchronous (VergeClient) and async (AsyncVergeClient)."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, AsyncIterator, Iterator, Optional
from urllib.parse import urljoin

import httpx

from . import next_data as nd
from .feeds import NEWSLETTERS, SUBSCRIBER_FEEDS, parse_feed, rss_path
from .models import Article, AuthorProfile, Category
from .utils import TTLCache

BASE_URL = "https://www.theverge.com"
PAGE_SIZE = 40

# Sections to scan when search() has no explicit sections arg
_SEARCH_SECTIONS = ["all", "tech", "games", "science", "entertainment", "transportation"]

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ---------------------------------------------------------------------------
# Synchronous client
# ---------------------------------------------------------------------------

class VergeClient:
    """
    Unofficial synchronous Python client for The Verge.

    Not affiliated with or endorsed by The Verge or Vox Media.
    Requires an active paid subscription: https://www.theverge.com/subscribe

    Parameters
    ----------
    rate_limit_delay : float
        Seconds to wait between requests. Default 0.5.
    timeout : float
        Request timeout in seconds.
    cache_ttl : float
        Seconds to cache responses in memory. 0 disables caching. Default 300.

    Example
    -------
    >>> from theverge import VergeClient
    >>> with VergeClient() as client:
    ...     articles = client.feed("tech")
    ...     print(articles[0].title)
    """

    def __init__(
        self,
        rate_limit_delay: float = 0.5,
        timeout: float = 15.0,
        cache_ttl: float = 300.0,
    ) -> None:
        self._delay = rate_limit_delay
        self._cache = TTLCache(ttl=cache_ttl)
        self._http = httpx.Client(
            headers=_DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )
        self._last_req: float = 0.0

    # ------------------------------------------------------------------
    # Feed
    # ------------------------------------------------------------------

    def feed(
        self,
        section: str = "",
        enrich: bool = False,
        since: Optional[datetime] = None,
    ) -> list[Article]:
        """
        Fetch the latest articles from a section feed.

        Parameters
        ----------
        section : str
            Section slug: "tech", "reviews", "science", "entertainment",
            "transportation", "games", "ai", "policy", "gadgets", or ""
            for the full homepage feed.
        enrich : bool
            Fetch __NEXT_DATA__ for hero images, dek, and post type.
            Costs one extra HTTP request.
        since : datetime | None
            Only return articles published at or after this datetime.
            Timezone-aware recommended. Use since_hours(n) for convenience.

        Returns
        -------
        list[Article]
            Up to 30 articles with full body HTML.
        """
        articles = self._rss(section)
        if since:
            articles = _filter_since(articles, since)
        if enrich and articles:
            self._enrich(articles, section)
        return articles

    def feed_iter(
        self,
        section: str = "",
        enrich: bool = False,
        since: Optional[datetime] = None,
    ) -> Iterator[Article]:
        """
        Lazily iterate articles — RSS first (~30), then paginated __NEXT_DATA__.

        Articles from page 2+ have no body_html. Call article.fetch_body(client)
        to hydrate individual articles on demand.

        Parameters
        ----------
        section : str
            Section slug. Same options as feed().
        enrich : bool
            Enrich the first RSS batch with __NEXT_DATA__ metadata.
        since : datetime | None
            Stop iteration once articles are older than this datetime.
            RSS feed is newest-first, so this provides early exit.
        """
        first = self._rss(section)
        if enrich and first:
            self._enrich(first, section)

        for a in first:
            if since and _is_before(a, since):
                return
            yield a

        seen = {a.id for a in first}
        offset = PAGE_SIZE

        while True:
            nodes, has_next = self._next_feed_page(section, offset)
            new = [a for a in nodes if a.id not in seen]
            if not new:
                break
            seen.update(a.id for a in new)
            for a in new:
                if since and _is_before(a, since):
                    return
                yield a
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
            Relative path e.g. "/tech/941146/..." or full URL.

        Returns
        -------
        Article

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

    def quick_posts(self, since: Optional[datetime] = None) -> list[Article]:
        """Fetch the quick posts feed (short-form news items)."""
        articles = self._rss("quick_posts")
        return _filter_since(articles, since) if since else articles

    def newsletter(self, name: str, since: Optional[datetime] = None) -> list[Article]:
        """
        Fetch a newsletter feed.

        Parameters
        ----------
        name : str
            One of: notepad, regulator, the-stepback, installer, optimizer
        since : datetime | None
            Filter to articles published at or after this datetime.
        """
        if name not in NEWSLETTERS:
            raise ValueError(
                f"Unknown newsletter '{name}'. "
                f"Available: {', '.join(NEWSLETTERS)}"
            )
        articles = self._rss(name)
        return _filter_since(articles, since) if since else articles

    def reviews(
        self,
        enrich: bool = False,
        since: Optional[datetime] = None,
    ) -> list[Article]:
        """Fetch the reviews feed."""
        return self.feed("reviews", enrich=enrich, since=since)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def sections(self) -> list[Category]:
        """Return all site sections and categories from homepage __NEXT_DATA__."""
        data = self._next(BASE_URL)
        return nd.sections(data)

    def popular(self) -> list[dict]:
        """
        Return the most popular articles from the homepage.

        Returns lightweight dicts: title, url, author, image_url,
        publish_date, tags.
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
        """
        url = f"{BASE_URL}/authors/{slug}"
        data = self._next(url)
        profile = nd.author_profile(data)
        if profile is None:
            raise ValueError(f"Could not parse author profile from {url}")
        return profile

    def search(
        self,
        query: str,
        sections: Optional[list[str]] = None,
    ) -> list[Article]:
        """
        Search for articles matching a query across multiple section feeds.

        Fetches multiple feeds concurrently, deduplicates, and scores by
        term frequency. More thorough than filtering a single feed.

        Parameters
        ----------
        query : str
            Search terms — space-separated words.
        sections : list[str] | None
            Which section feeds to scan. Defaults to all major sections.
            Use ["all"] to search only the main full feed.

        Returns
        -------
        list[Article]
            Deduplicated results sorted by relevance then recency.
        """
        terms = [t.lower().strip() for t in query.split() if t.strip()]
        if not terms:
            return []

        scan = sections or _SEARCH_SECTIONS
        all_articles: list[Article] = []

        with ThreadPoolExecutor(max_workers=min(len(scan), 4)) as pool:
            futures = {pool.submit(self._rss, s): s for s in scan}
            for future in as_completed(futures):
                try:
                    all_articles.extend(future.result())
                except Exception:
                    pass

        return _score_and_rank(all_articles, terms)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Evict all cached responses."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rss(self, section: str) -> list[Article]:
        path = rss_path(section)
        url = urljoin(BASE_URL, path)
        cached = self._cache.get(f"rss:{section}")
        if cached is not None:
            return cached
        self._throttle()
        resp = self._http.get(url)
        resp.raise_for_status()
        result = parse_feed(resp.text)
        self._cache.set(f"rss:{section}", result)
        return result

    def _next(self, url: str) -> dict:
        cached = self._cache.get(f"next:{url}")
        if cached is not None:
            return cached
        self._throttle()
        resp = self._http.get(url)
        resp.raise_for_status()
        result = nd.extract(resp.text)
        self._cache.set(f"next:{url}", result)
        return result

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
            pass

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


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------

class AsyncVergeClient:
    """
    Unofficial async Python client for The Verge.

    Drop-in async counterpart to VergeClient. Use with asyncio for
    concurrent fetching of multiple feeds.

    Not affiliated with or endorsed by The Verge or Vox Media.
    Requires an active paid subscription: https://www.theverge.com/subscribe

    Example
    -------
    >>> import asyncio
    >>> from theverge import AsyncVergeClient
    >>>
    >>> async def main():
    ...     async with AsyncVergeClient() as client:
    ...         articles = await client.feed("tech")
    ...         print(articles[0].title)
    >>>
    >>> asyncio.run(main())
    """

    def __init__(
        self,
        rate_limit_delay: float = 0.5,
        timeout: float = 15.0,
        cache_ttl: float = 300.0,
    ) -> None:
        self._delay = rate_limit_delay
        self._cache = TTLCache(ttl=cache_ttl)
        self._http = httpx.AsyncClient(
            headers=_DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )
        self._last_req: float = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Feed
    # ------------------------------------------------------------------

    async def feed(
        self,
        section: str = "",
        enrich: bool = False,
        since: Optional[datetime] = None,
    ) -> list[Article]:
        """Async version of VergeClient.feed()."""
        articles = await self._rss(section)
        if since:
            articles = _filter_since(articles, since)
        if enrich and articles:
            await self._enrich(articles, section)
        return articles

    async def feed_iter(
        self,
        section: str = "",
        enrich: bool = False,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[Article]:
        """
        Async lazy iterator over articles. Use with async for.

        Example
        -------
        async for article in client.feed_iter("tech"):
            print(article.title)
        """
        first = await self._rss(section)
        if enrich and first:
            await self._enrich(first, section)

        for a in first:
            if since and _is_before(a, since):
                return
            yield a

        seen = {a.id for a in first}
        offset = PAGE_SIZE

        while True:
            nodes, has_next = await self._next_feed_page(section, offset)
            new = [a for a in nodes if a.id not in seen]
            if not new:
                break
            seen.update(a.id for a in new)
            for a in new:
                if since and _is_before(a, since):
                    return
                yield a
            if not has_next:
                break
            offset += PAGE_SIZE

    # ------------------------------------------------------------------
    # Article detail
    # ------------------------------------------------------------------

    async def article(self, path_or_url: str) -> Article:
        """Async version of VergeClient.article()."""
        url = _to_url(path_or_url)
        data = await self._next(url)
        result = nd.article_detail(data)
        if result is None:
            raise ValueError(f"Could not parse article from {url}")
        return result

    # ------------------------------------------------------------------
    # Content types
    # ------------------------------------------------------------------

    async def quick_posts(self, since: Optional[datetime] = None) -> list[Article]:
        """Async version of VergeClient.quick_posts()."""
        articles = await self._rss("quick_posts")
        return _filter_since(articles, since) if since else articles

    async def newsletter(self, name: str, since: Optional[datetime] = None) -> list[Article]:
        """Async version of VergeClient.newsletter()."""
        if name not in NEWSLETTERS:
            raise ValueError(
                f"Unknown newsletter '{name}'. Available: {', '.join(NEWSLETTERS)}"
            )
        articles = await self._rss(name)
        return _filter_since(articles, since) if since else articles

    async def reviews(
        self,
        enrich: bool = False,
        since: Optional[datetime] = None,
    ) -> list[Article]:
        """Async version of VergeClient.reviews()."""
        return await self.feed("reviews", enrich=enrich, since=since)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def sections(self) -> list[Category]:
        """Async version of VergeClient.sections()."""
        data = await self._next(BASE_URL)
        return nd.sections(data)

    async def popular(self) -> list[dict]:
        """Async version of VergeClient.popular()."""
        data = await self._next(BASE_URL)
        return nd.popular(data)

    async def author(self, slug: str) -> AuthorProfile:
        """Async version of VergeClient.author()."""
        url = f"{BASE_URL}/authors/{slug}"
        data = await self._next(url)
        profile = nd.author_profile(data)
        if profile is None:
            raise ValueError(f"Could not parse author profile from {url}")
        return profile

    async def search(
        self,
        query: str,
        sections: Optional[list[str]] = None,
    ) -> list[Article]:
        """
        Async multi-feed search — fetches all feeds concurrently with asyncio.gather.

        Significantly faster than the sync version for large section lists.
        """
        terms = [t.lower().strip() for t in query.split() if t.strip()]
        if not terms:
            return []

        scan = sections or _SEARCH_SECTIONS
        results = await asyncio.gather(
            *[self._rss(s) for s in scan],
            return_exceptions=True,
        )
        all_articles: list[Article] = []
        for r in results:
            if isinstance(r, list):
                all_articles.extend(r)

        return _score_and_rank(all_articles, terms)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Evict all cached responses."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _rss(self, section: str) -> list[Article]:
        path = rss_path(section)
        url = urljoin(BASE_URL, path)
        cached = self._cache.get(f"rss:{section}")
        if cached is not None:
            return cached
        await self._throttle()
        resp = await self._http.get(url)
        resp.raise_for_status()
        result = parse_feed(resp.text)
        self._cache.set(f"rss:{section}", result)
        return result

    async def _next(self, url: str) -> dict:
        cached = self._cache.get(f"next:{url}")
        if cached is not None:
            return cached
        await self._throttle()
        resp = await self._http.get(url)
        resp.raise_for_status()
        result = nd.extract(resp.text)
        self._cache.set(f"next:{url}", result)
        return result

    async def _next_feed_page(self, section: str, offset: int) -> tuple[list[Article], bool]:
        url = f"{BASE_URL}/{section}" if section else BASE_URL
        if offset > 0:
            url = f"{url}?offset={offset}"
        try:
            data = await self._next(url)
            return nd.feed_page(data)
        except Exception:
            return [], False

    async def _enrich(self, articles: list[Article], section: str) -> None:
        url = f"{BASE_URL}/{section}" if section else BASE_URL
        try:
            data = await self._next(url)
            index = nd.build_index(data)
            for article in articles:
                node = index.get(article.wp_id) or index.get(article.id)
                if node:
                    nd.apply_enrichment(article, node)
        except Exception:
            pass

    async def _throttle(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_req
            if elapsed < self._delay:
                await asyncio.sleep(self._delay - elapsed)
            self._last_req = time.monotonic()

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncVergeClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _to_url(path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        return path_or_url
    return urljoin(BASE_URL, path_or_url)


def _filter_since(articles: list[Article], since: datetime) -> list[Article]:
    """Return only articles published at or after since."""
    since_aware = _ensure_aware(since)
    return [a for a in articles if _ensure_aware(a.published_at) >= since_aware]


def _is_before(article: Article, since: datetime) -> bool:
    """True if article is older than since (for early-exit in iterators)."""
    return _ensure_aware(article.published_at) < _ensure_aware(since)


def _ensure_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC) if it isn't already."""
    if dt.tzinfo is None:
        from datetime import timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _score_and_rank(articles: list[Article], terms: list[str]) -> list[Article]:
    """
    Deduplicate articles, score by term frequency, sort by score then recency.
    """
    # Deduplicate by wp_id (prefer non-zero) then by id
    seen_ids: set[str] = set()
    seen_wpids: set[int] = set()
    deduped: list[Article] = []
    for a in articles:
        key = str(a.wp_id) if a.wp_id else a.id
        if key in seen_ids:
            continue
        seen_ids.add(key)
        deduped.append(a)

    # Score
    scored: list[tuple[int, Article]] = []
    for a in deduped:
        text = (
            (a.title + " ") * 3           # title weighted 3x
            + (a.summary + " ") * 2       # summary 2x
            + " ".join(a.keywords) + " "  # keywords 1x
        ).lower()
        score = sum(text.count(term) for term in terms)
        if score > 0:
            scored.append((score, a))

    scored.sort(key=lambda x: (-x[0], -x[1].published_at.timestamp()))
    return [a for _, a in scored]
