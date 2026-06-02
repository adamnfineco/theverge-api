"""RSS feed URL registry and parsing."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from .models import Article, Author, Category, Image
from .utils import parse_rfc2822, parse_iso

BASE_URL = "https://www.theverge.com"

_NS = {
    "atom":    "http://www.w3.org/2005/Atom",
    "media":   "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc":      "http://purl.org/dc/elements/1.1/",
}

# Named subscriber full-text feeds
SUBSCRIBER_FEEDS: dict[str, str] = {
    # All content
    "all":            "/rss/partner/subscriber-only-full-feed/rss.xml",
    "quick_posts":    "/rss/quickposts",
    # Sections
    "tech":           "/rss/partner/subscriber-only-tech/rss.xml",
    "reviews":        "/rss/partner/subscriber-only-reviews/rss.xml",
    "science":        "/rss/partner/subscriber-only-science/rss.xml",
    "entertainment":  "/rss/partner/subscriber-only-entertainment/rss.xml",
    "transportation": "/rss/partner/subscriber-only-transportation/rss.xml",
    # Newsletters
    "notepad":        "/rss/partner/subscriber-only-notepad/rss.xml",
    "regulator":      "/rss/partner/subscriber-only-regulator/rss.xml",
    "the-stepback":   "/rss/partner/subscriber-only-the-stepback/rss.xml",
    "installer":      "/rss/partner/subscriber-only-installer/rss.xml",
    "optimizer":      "/rss/partner/subscriber-only-optimizer-newsletter/rss.xml",
}

# Public section RSS feeds (fallback / additional sections)
PUBLIC_SECTION_FEEDS: dict[str, str] = {
    "tech":           "/rss/tech/index.xml",
    "games":          "/rss/games/index.xml",
    "science":        "/rss/science/index.xml",
    "entertainment":  "/rss/entertainment/index.xml",
    "transportation": "/rss/transportation/index.xml",
    "ai":             "/rss/ai-artificial-intelligence/index.xml",
    "policy":         "/rss/policy/index.xml",
    "gadgets":        "/rss/gadgets/index.xml",
}

NEWSLETTERS = ["notepad", "regulator", "the-stepback", "installer", "optimizer"]


def rss_path(section: str, public: bool = False) -> str:
    """Resolve section name to RSS feed path."""
    if not public and section in SUBSCRIBER_FEEDS:
        return SUBSCRIBER_FEEDS[section]
    if section in PUBLIC_SECTION_FEEDS:
        return PUBLIC_SECTION_FEEDS[section]
    if section:
        return f"/rss/{section}/index.xml"
    return SUBSCRIBER_FEEDS["all"]


def parse_feed(xml_text: str) -> list[Article]:
    """Parse RSS or Atom feed XML into Article list."""
    root = ET.fromstring(xml_text)

    # RSS 2.0
    items = root.findall(".//item")
    if items:
        return _parse_rss2(items)

    # Atom
    ns = _NS["atom"]
    entries = root.findall(f"{{{ns}}}entry")
    if entries:
        return _parse_atom(entries)

    return []


def _parse_rss2(items: list[ET.Element]) -> list[Article]:
    articles = []
    for item in items:

        def t(tag: str, ns_key: str = "") -> str:
            full = f"{{{_NS[ns_key]}}}{tag}" if ns_key else tag
            el = item.find(full)
            return (el.text or "").strip() if el is not None else ""

        title     = html.unescape(t("title"))
        link      = t("link")
        guid      = t("guid")
        author    = t("creator", "dc")
        pubdate   = t("pubDate")
        summary   = html.unescape(t("description"))
        body      = t("encoded", "content")
        kw_raw    = t("keywords", "media")

        published_at = parse_rfc2822(pubdate) or datetime.now(timezone.utc)
        keywords = [k.strip() for k in kw_raw.split(",") if k.strip()] if kw_raw else []
        path = urlparse(link).path

        articles.append(Article(
            id=guid,
            title=title,
            permalink=link,
            path=path,
            author=author,
            authors=[Author.from_name(author)] if author else [],
            published_at=published_at,
            updated_at=None,
            summary=summary,
            body_html=body,
            keywords=keywords,
            categories=[],
            raw_rss={"title": title, "link": link, "guid": guid},
        ))
    return articles


def _parse_atom(entries: list[ET.Element]) -> list[Article]:
    ns = _NS["atom"]
    articles = []

    for e in entries:
        def t(tag: str) -> str:
            el = e.find(f"{{{ns}}}{tag}")
            return (el.text or "").strip() if el is not None else ""

        def ta(tag: str, attr: str) -> str:
            el = e.find(f"{{{ns}}}{tag}")
            return el.get(attr, "") if el is not None else ""

        title       = html.unescape(t("title"))
        link        = ta("link", "href")
        guid        = t("id")
        author      = e.findtext(f"{{{ns}}}author/{{{ns}}}name", "").strip()
        published   = t("published")
        summary     = html.unescape(t("summary"))
        body_el     = e.find(f"{{{ns}}}content")
        body        = (body_el.text or "") if body_el is not None else ""
        cats        = [c.get("term", "") for c in e.findall(f"{{{ns}}}category")]

        published_at = parse_iso(published) or datetime.now(timezone.utc)
        path = urlparse(link).path

        articles.append(Article(
            id=guid,
            title=title,
            permalink=link,
            path=path,
            author=author,
            authors=[Author.from_name(author)] if author else [],
            published_at=published_at,
            updated_at=None,
            summary=summary,
            body_html=body,
            keywords=[],
            categories=[Category(title=c) for c in cats if c],
            raw_rss={"title": title, "link": link, "guid": guid},
        ))
    return articles
