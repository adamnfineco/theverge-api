"""Internal utilities for parsing Verge data payloads."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional


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
