"""Internal utilities for parsing Verge data payloads."""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Verge field helpers
# ---------------------------------------------------------------------------

def html_field(field: Any) -> Optional[str]:
    """Extract .html from a Verge rich text field (list or dict)."""
    if not field:
        return None
    if isinstance(field, list):
        return " ".join(item.get("html", "") for item in field if item.get("html")) or None
    if isinstance(field, dict):
        return field.get("html")
    return None


def plain_field(field: Any) -> Optional[str]:
    if not field:
        return None
    if isinstance(field, dict):
        return field.get("plaintext") or field.get("html")
    return None


def thumb(field: Any, key: str = "square") -> Optional[str]:
    if not field:
        return None
    return (field.get("thumbnails") or {}).get(key, {}).get("url")


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_rfc2822(s: str) -> Optional[datetime]:
    try:
        return parsedate_to_datetime(s)
    except Exception:
        return None


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return parse_rfc2822(s) or parse_iso(s)


def since_hours(n: float) -> datetime:
    """Return a timezone-aware datetime n hours ago. Useful for since= filtering."""
    return datetime.now(timezone.utc) - timedelta(hours=n)


# ---------------------------------------------------------------------------
# TTL cache — zero deps, pure stdlib
# ---------------------------------------------------------------------------

class TTLCache:
    """
    Simple in-memory TTL cache keyed on strings.

    Parameters
    ----------
    ttl : float
        Seconds before a cached entry expires. 0 disables caching.
    """

    def __init__(self, ttl: float = 300.0) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any:
        """Return cached value or None if missing/expired."""
        if self._ttl <= 0:
            return None
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        """Store a value with the current timestamp."""
        if self._ttl > 0:
            self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        """Evict all entries."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# HTML cleaning
# ---------------------------------------------------------------------------

# Tracking query params to strip from URLs
_TRACKING_PARAMS = re.compile(
    r"[&?](?:"
    r"utm_\w+"
    r"|irclickid|afsrc|irgwc"
    r"|gclid|fbclid|msclkid"
    r"|hsa_\w+"
    r"|_ga|_gl"
    r"|mc_\w+"
    r"|ref_src|ref_url"
    r")=[^&]*",
    re.IGNORECASE,
)

# Attributes to strip from all tags (keep: src, href, alt, title, width, height, loading, type)
_STRIP_ATTRS = re.compile(
    r'\s+(?:class|data-[\w-]+|style|id|tabindex|aria-[\w-]+|rel|target|crossorigin|fetchpriority)'
    r'(?:=(?:"[^"]*"|\'[^\']*\'|[^\s>]*))?',
    re.IGNORECASE,
)

def clean_html(html: str) -> str:
    """
    Clean article body HTML:
    - Strip tracking parameters from links
    - Remove data-*, class, style, id attributes
    - Keep structural content and src/href/alt intact
    """
    if not html:
        return html

    # Strip tracking params from href values
    def clean_href(m: re.Match) -> str:
        href = m.group(0)
        href = _TRACKING_PARAMS.sub("", href)
        # Clean up dangling ? or &
        href = re.sub(r'\?&', '?', href)
        href = re.sub(r'[?&]$', '', href)
        return href

    html = re.sub(r'href="[^"]*"', clean_href, html)

    # Strip noisy attributes
    html = _STRIP_ATTRS.sub("", html)

    # Remove empty attribute strings left behind
    html = re.sub(r'\s+(?=[ />])', " ", html)

    return html


# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """HTMLParser subclass that converts HTML to readable plain text."""

    BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                  "li", "blockquote", "figure", "figcaption", "tr"}
    SKIP_TAGS = {"script", "style", "head", "nav", "footer", "iframe",
                 "noscript", "svg", "img"}
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0
        self._current_skip: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            self._current_skip = tag
        if self._skip_depth:
            return
        if tag in self.BLOCK_TAGS:
            self._parts.append("\n")
        elif tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._skip_depth:
            return
        if tag in self.BLOCK_TAGS or tag in self.HEADING_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        import html as _html
        self._parts.append(_html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        import html as _html
        self._parts.append(_html.unescape(f"&#{name};"))

    def get_text(self) -> str:
        text = "".join(self._parts)
        # Collapse runs of whitespace/newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()


def html_to_text(html_str: str) -> str:
    """
    Convert HTML to clean plain text. No external dependencies.

    Preserves paragraph breaks, strips all tags, handles entities.
    """
    if not html_str:
        return ""
    extractor = _TextExtractor()
    extractor.feed(html_str)
    return extractor.get_text()


# ---------------------------------------------------------------------------
# __NEXT_DATA__ block → HTML
# ---------------------------------------------------------------------------

def blocks_to_html(blocks: list[dict]) -> str:
    """Convert __NEXT_DATA__ content blocks to HTML string."""
    parts: list[str] = []
    for block in blocks:
        tn = block.get("__typename", "")

        if tn == "CoreParagraphBlockType":
            for pc in block.get("paragraphContents") or []:
                h = pc.get("html", "")
                if h:
                    parts.append(f"<p>{h}</p>")

        elif tn == "CoreHeadingBlockType":
            level = block.get("level", 2)
            h = html_field(block.get("content") or block.get("heading"))
            if h:
                parts.append(f"<h{level}>{h}</h{level}>")

        elif tn == "CoreImageBlockType":
            url = (block.get("thumbnail") or {}).get("url")
            alt = block.get("alt", "")
            caption = plain_field(block.get("caption"))
            if url:
                parts.append(f'<figure><img src="{url}" alt="{alt}"/>')
                if caption:
                    parts.append(f"<figcaption>{caption}</figcaption>")
                parts.append("</figure>")

        elif tn == "CoreQuoteBlockType":
            h = html_field(block.get("quote") or block.get("value"))
            if h:
                parts.append(f"<blockquote>{h}</blockquote>")

        elif tn == "CoreListBlockType":
            items = block.get("items") or []
            tag = "ol" if block.get("ordered") else "ul"
            inner = "".join(f"<li>{html_field(i) or ''}</li>" for i in items)
            if inner:
                parts.append(f"<{tag}>{inner}</{tag}>")

        elif tn == "CoreEmbedBlockType":
            src = block.get("url") or block.get("embedUrl")
            if src:
                parts.append(f'<iframe src="{src}" loading="lazy"></iframe>')

        elif tn == "CorePullquoteBlockType":
            h = html_field(block.get("value") or block.get("citation"))
            if h:
                parts.append(f"<blockquote class='pullquote'>{h}</blockquote>")

    return "\n".join(parts)
