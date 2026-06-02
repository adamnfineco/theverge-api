"""Data models for The Verge API wrapper."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse


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

    def to_dict(self) -> dict:
        """Serialize to a plain dict — useful for JSON output."""
        return {
            "id": self.id,
            "wp_id": self.wp_id,
            "title": self.title,
            "permalink": self.permalink,
            "path": self.path,
            "author": self.author,
            "authors": [{"name": a.name, "permalink": a.permalink} for a in self.authors],
            "published_at": self.published_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "summary": self.summary,
            "dek": self.dek,
            "keywords": self.keywords,
            "categories": [{"title": c.title, "slug": c.slug} for c in self.categories],
            "resource_type": self.resource_type,
            "is_live": self.is_live,
            "hero_image": {
                "url": self.hero_image.url,
                "alt": self.hero_image.alt,
                "width": self.hero_image.width,
                "height": self.hero_image.height,
            } if self.hero_image else None,
            "body_html": self.body_html,
        }
