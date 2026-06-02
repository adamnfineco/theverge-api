"""__NEXT_DATA__ extraction and enrichment helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from .models import Article, Author, AuthorProfile, Category, Image
from .utils import html_field, plain_field, thumb, parse_iso, blocks_to_html

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)


def extract(html: str) -> dict:
    """Pull __NEXT_DATA__ JSON from a page HTML string."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("No __NEXT_DATA__ found in page")
    return json.loads(m.group(1))


def page_props(data: dict) -> dict:
    return data.get("props", {}).get("pageProps", {})


def hydration_responses(data: dict) -> list[dict]:
    return page_props(data).get("hydration", {}).get("responses", [])


# ---------------------------------------------------------------------------
# Feed page
# ---------------------------------------------------------------------------

def feed_page(data: dict) -> tuple[list[Article], bool]:
    """Extract articles and pagination state from a category/section page."""
    nodes: list[Article] = []
    has_next = False

    for resp in hydration_responses(data):
        node = resp.get("data", {}).get("node", {})
        feed = node.get("categoryLayoutPosts") or {}
        raw_nodes = feed.get("nodes", [])
        page_info = feed.get("pageInfo", {})
        has_next = page_info.get("hasNextPage", False)
        for n in raw_nodes:
            if n.get("id"):
                nodes.append(article_from_node(n))

    return nodes, has_next


def homepage_feed(data: dict) -> list[Article]:
    """Extract articles from the homepage __NEXT_DATA__."""
    nodes: list[Article] = []
    seen: set[str] = set()

    for resp in hydration_responses(data):
        resource = resp.get("data", {}).get("resource", {})
        if not resource:
            continue
        for key in ("hero", "river"):
            section = resource.get(key, {})
            raw_nodes = (
                section.get("nodes")
                or section.get("posts", {}).get("nodes", [])
                or []
            )
            for n in raw_nodes:
                if n.get("id") and n["id"] not in seen:
                    seen.add(n["id"])
                    nodes.append(article_from_node(n))

    return nodes


# ---------------------------------------------------------------------------
# Article detail
# ---------------------------------------------------------------------------

def article_detail(data: dict) -> Optional[Article]:
    """Extract a single article from a detail page __NEXT_DATA__."""
    for resp in hydration_responses(data):
        rd = resp.get("data", {})
        node = rd.get("post") or rd.get("node")
        if node and node.get("__typename") in (
            "PostResourceType", "QuickPostResourceType", "StreamResourceType"
        ):
            return article_from_node(node)
    return None


# ---------------------------------------------------------------------------
# Author profile
# ---------------------------------------------------------------------------

def author_profile(data: dict) -> Optional[AuthorProfile]:
    """Extract author profile from an /authors/ page."""
    for resp in hydration_responses(data):
        node = resp.get("data", {}).get("node", {})
        if node.get("__typename") == "AuthorProfileResourceType":
            posts_raw = node.get("posts", {}).get("nodes", [])
            return AuthorProfile(
                name=node.get("name", ""),
                path=node.get("path", ""),
                permalink=node.get("permalink", ""),
                title=node.get("title"),
                bio=html_field(node.get("longBio") or node.get("shortBio")),
                profile_image_url=thumb(node.get("profileImage"), "square"),
                feed_link=node.get("feedLink"),
                social_links=node.get("socialLinks") or [],
                recent_posts=[article_from_node(p) for p in posts_raw if p.get("id")],
                raw=node,
            )
    return None


# ---------------------------------------------------------------------------
# Sections / categories
# ---------------------------------------------------------------------------

def sections(data: dict) -> list[Category]:
    cat_list = page_props(data).get("categoryList") or []
    return [Category.from_next(c) for c in cat_list]


def popular(data: dict) -> list[dict]:
    return page_props(data).get("mostPopularArticles") or []


# ---------------------------------------------------------------------------
# Enrichment index
# ---------------------------------------------------------------------------

def build_index(data: dict) -> dict[Any, dict]:
    """Index all article nodes by wpId and id for fast lookup."""
    index: dict = {}
    for resp in hydration_responses(data):
        node = resp.get("data", {}).get("node", {})
        for feed_key in ("categoryLayoutPosts", "hero"):
            feed = node.get(feed_key) or {}
            posts = feed if feed_key == "categoryLayoutPosts" else feed.get("posts", {})
            for n in posts.get("nodes", []):
                if n.get("wpId"):
                    index[n["wpId"]] = n
                if n.get("id"):
                    index[n["id"]] = n
        resource = resp.get("data", {}).get("resource", {})
        for key in ("hero",):
            for n in (resource.get(key) or {}).get("nodes", []):
                if n.get("wpId"):
                    index[n["wpId"]] = n
    return index


def apply_enrichment(article: Article, node: dict) -> None:
    """Bolt rich metadata from a __NEXT_DATA__ node onto an RSS article."""
    meta = _node_meta(node)
    if meta.get("hero_image"):
        article.hero_image = meta["hero_image"]
    if meta.get("dek"):
        article.dek = meta["dek"]
    if meta.get("resource_type"):
        article.resource_type = meta["resource_type"]
    if meta.get("authors"):
        article.authors = meta["authors"]
    if meta.get("categories"):
        article.categories = meta["categories"]
    article.is_live = meta.get("is_live", False)
    article.raw_next = node


# ---------------------------------------------------------------------------
# Node → Article
# ---------------------------------------------------------------------------

def article_from_node(raw: dict) -> Article:
    meta = _node_meta(raw)
    authors = meta.get("authors", [])
    return Article(
        id=raw.get("id", ""),
        title=meta.get("title", ""),
        permalink=raw.get("permalink", ""),
        path=raw.get("path", urlparse(raw.get("permalink", "")).path),
        author=", ".join(a.name for a in authors),
        authors=authors,
        published_at=parse_iso(meta.get("publishedAt", "")) or datetime.now(timezone.utc),
        updated_at=parse_iso(meta.get("updatedAt")),
        summary=meta.get("dek", "") or "",
        body_html=meta.get("body_html", ""),
        keywords=[],
        categories=meta.get("categories", []),
        resource_type=meta.get("resource_type"),
        dek=meta.get("dek"),
        hero_image=meta.get("hero_image"),
        is_live=meta.get("is_live", False),
        raw_next=raw,
    )


def _node_meta(raw: dict) -> dict:
    authors = [Author.from_next(a) for a in (raw.get("authors") or [])]
    categories = [Category.from_next(c) for c in (raw.get("categories") or [])]
    hero = (
        Image.from_lede(raw.get("ledeMedia"))
        or Image.from_quick_attachment(raw.get("quickAttachment"))
    )
    body = blocks_to_html(raw.get("blocks") or [])
    return {
        "id": raw.get("id", ""),
        "title": raw.get("title", ""),
        "publishedAt": raw.get("publishedAt", ""),
        "updatedAt": raw.get("updatedAt"),
        "authors": authors,
        "categories": categories,
        "dek": html_field(raw.get("dek")),
        "hero_image": hero,
        "body_html": body,
        "resource_type": raw.get("resourceType"),
        "is_live": raw.get("liveBadge", False),
    }
