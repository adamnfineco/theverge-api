"""Data models for The Verge API wrapper."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse

if TYPE_CHECKING:
    # Avoid circular import — only used for type hints on fetch_body
    from .client import VergeClient


@dataclass
class Author:
    name: str
    path: str = ""
    permalink: str = ""
    title: Optional[str] = None        # job title e.g. "Editor in Chief"
    bio: Optional[str] = None
    profile_image_url: Optional[str] = None
    social_links: list[dict] = field(default_factory=list)

    @classmethod
    def from_next(cls, raw: dict) -> "Author":
        from .utils import html_field, thumb
        return cls(
            name=raw.get("name", ""),
            path=raw.get("path", ""),
            permalink=raw.get("permalink", ""),
            title=raw.get("title"),
            bio=html_field(raw.get("shortBio") or raw.get("longBio")),
            profile_image_url=thumb(raw.get("profileImage"), "square"),
            social_links=raw.get("socialLinks") or [],
        )

    @classmethod
    def from_name(cls, name: str) -> "Author":
        return cls(name=name)

    @classmethod
    def from_dict(cls, d: dict) -> "Author":
        return cls(
            name=d.get("name", ""),
            path=d.get("path", ""),
            permalink=d.get("permalink", ""),
            title=d.get("title"),
            bio=d.get("bio"),
            profile_image_url=d.get("profile_image_url"),
            social_links=d.get("social_links", []),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "permalink": self.permalink,
            "title": self.title,
            "bio": self.bio,
            "profile_image_url": self.profile_image_url,
        }


@dataclass
class Image:
    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    alt: Optional[str] = None
    credit: Optional[str] = None

    @classmethod
    def from_lede(cls, raw: dict | None) -> Optional["Image"]:
        if not raw:
            return None
        img = raw.get("image") or {}
        thumbs = img.get("thumbnails") or {}
        src = (thumbs.get("horizontal") or thumbs.get("square") or {}).get("url")
        return cls(url=src) if src else None

    @classmethod
    def from_quick_attachment(cls, raw: dict | None) -> Optional["Image"]:
        if not raw:
            return None
        from .utils import plain_field
        thumb = raw.get("thumbnail") or {}
        url = thumb.get("url", "")
        return cls(
            url=url,
            width=thumb.get("originalWidth"),
            height=thumb.get("originalHeight"),
            alt=raw.get("alt"),
            credit=plain_field(raw.get("credit")),
        ) if url else None

    @classmethod
    def from_body(cls, body_html: str) -> Optional["Image"]:
        """Extract first image from article body HTML."""
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', body_html)
        if not m:
            return None
        src = m.group(1)
        alt_m = re.search(r'alt=["\']([^"\']*)["\']', m.group(0))
        return cls(url=src, alt=alt_m.group(1) if alt_m else None)

    @classmethod
    def from_dict(cls, d: dict | None) -> Optional["Image"]:
        if not d:
            return None
        return cls(
            url=d.get("url", ""),
            width=d.get("width"),
            height=d.get("height"),
            alt=d.get("alt"),
            credit=d.get("credit"),
        )

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "width": self.width,
            "height": self.height,
            "alt": self.alt,
            "credit": self.credit,
        }


@dataclass
class Category:
    title: str
    slug: str = ""
    path: str = ""
    id: str = ""

    @classmethod
    def from_next(cls, raw: dict) -> "Category":
        return cls(
            id=raw.get("id", ""),
            title=raw.get("title", ""),
            slug=raw.get("slug", ""),
            path=raw.get("path", raw.get("permalink", "")),
        )

    @classmethod
    def from_keyword(cls, kw: str) -> "Category":
        slug = kw.strip().lower().replace(" ", "-")
        return cls(title=kw.strip(), slug=slug)

    @classmethod
    def from_dict(cls, d: dict) -> "Category":
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            slug=d.get("slug", ""),
            path=d.get("path", ""),
        )

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "slug": self.slug, "path": self.path}


@dataclass
class AuthorProfile:
    """Full author profile from an /authors/ page."""
    name: str
    path: str
    permalink: str
    title: Optional[str]
    bio: Optional[str]
    profile_image_url: Optional[str]
    feed_link: Optional[str]
    social_links: list[dict]
    recent_posts: list["Article"]
    raw: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "permalink": self.permalink,
            "title": self.title,
            "bio": self.bio,
            "profile_image_url": self.profile_image_url,
            "feed_link": self.feed_link,
            "social_links": self.social_links,
            "recent_posts": [p.to_dict() for p in self.recent_posts],
        }


@dataclass
class Article:
    # Core identity
    id: str                          # wp guid e.g. https://www.theverge.com/?p=941146
    title: str
    permalink: str
    path: str

    # Authorship & timing
    author: str                      # display name (RSS dc:creator)
    authors: list[Author]            # enriched list when available
    published_at: datetime
    updated_at: Optional[datetime]

    # Content
    summary: str                     # one-sentence description
    body_html: str                   # full article HTML
    keywords: list[str]

    # Classification
    categories: list[Category]

    # Rich metadata — populated via enrich=True or .article()
    resource_type: Optional[str] = None   # "post" | "quickPost" | "stream"
    dek: Optional[str] = None
    hero_image: Optional[Image] = None
    is_live: bool = False

    # Raw payloads
    raw_rss: dict = field(default_factory=dict, repr=False)
    raw_next: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def wp_id(self) -> int:
        m = re.search(r'[?&]p=(\d+)', self.id)
        return int(m.group(1)) if m else 0

    @property
    def image(self) -> Optional[Image]:
        """Best available image — hero if enriched, else first from body."""
        return self.hero_image or Image.from_body(self.body_html)

    @property
    def author_names(self) -> list[str]:
        return [a.name for a in self.authors] if self.authors else [self.author]

    @property
    def is_quick_post(self) -> bool:
        return self.resource_type == "quickPost"

    @property
    def is_stream(self) -> bool:
        return self.resource_type == "stream"

    @property
    def body_text(self) -> str:
        """Plain text version of body_html — tags stripped, whitespace normalized."""
        from .utils import html_to_text
        return html_to_text(self.body_html)

    @property
    def body_clean(self) -> str:
        """Cleaned body HTML — tracking params and noisy attributes removed."""
        from .utils import clean_html
        return clean_html(self.body_html)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a JSON-serializable dict."""
        return {
            "id": self.id,
            "wp_id": self.wp_id,
            "title": self.title,
            "permalink": self.permalink,
            "path": self.path,
            "author": self.author,
            "authors": [a.to_dict() for a in self.authors],
            "published_at": self.published_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "summary": self.summary,
            "dek": self.dek,
            "keywords": self.keywords,
            "categories": [c.to_dict() for c in self.categories],
            "resource_type": self.resource_type,
            "is_live": self.is_live,
            "hero_image": self.hero_image.to_dict() if self.hero_image else None,
            "body_html": self.body_html,
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        """Reconstruct an Article from a to_dict() output."""
        from .utils import parse_dt

        authors = [Author.from_dict(a) for a in (d.get("authors") or [])]
        categories = [Category.from_dict(c) for c in (d.get("categories") or [])]
        hero = Image.from_dict(d.get("hero_image"))

        published_at = parse_dt(d.get("published_at")) or datetime.now(timezone.utc)
        updated_at = parse_dt(d.get("updated_at"))

        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            permalink=d.get("permalink", ""),
            path=d.get("path", ""),
            author=d.get("author", ""),
            authors=authors,
            published_at=published_at,
            updated_at=updated_at,
            summary=d.get("summary", ""),
            body_html=d.get("body_html", ""),
            keywords=d.get("keywords", []),
            categories=categories,
            resource_type=d.get("resource_type"),
            dek=d.get("dek"),
            hero_image=hero,
            is_live=d.get("is_live", False),
        )

    @classmethod
    def from_json(cls, s: str) -> "Article":
        """Reconstruct an Article from a to_json() string."""
        return cls.from_dict(json.loads(s))

    # ------------------------------------------------------------------
    # Lazy body fetching
    # ------------------------------------------------------------------

    def fetch_body(self, client: Any) -> "Article":
        """
        Fetch and attach full body HTML if not already present.

        Use when this article came from __NEXT_DATA__ pagination (page 2+)
        where body_html is empty. Mutates in place, returns self.

        Parameters
        ----------
        client : VergeClient or AsyncVergeClient
            A client instance to use for fetching. For async, use
            await article.fetch_body_async(client) instead.
        """
        if self.body_html:
            return self
        full = client.article(self.permalink)
        self.body_html = full.body_html
        if not self.dek:
            self.dek = full.dek
        if not self.hero_image:
            self.hero_image = full.hero_image
        return self

    async def fetch_body_async(self, client: Any) -> "Article":
        """
        Async version of fetch_body. Use with AsyncVergeClient.

        Example
        -------
        async with AsyncVergeClient() as c:
            async for article in c.feed_iter("tech"):
                if not article.body_html:
                    await article.fetch_body_async(c)
                print(article.body_text)
        """
        if self.body_html:
            return self
        full = await client.article(self.permalink)
        self.body_html = full.body_html
        if not self.dek:
            self.dek = full.dek
        if not self.hero_image:
            self.hero_image = full.hero_image
        return self
