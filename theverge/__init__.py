"""
theverge — Unofficial Python client for The Verge.

Not affiliated with or endorsed by The Verge or Vox Media.
Please support independent journalism: https://www.theverge.com/subscribe

Usage:
    from theverge import VergeClient

    client = VergeClient()
    articles = client.feed("tech")
"""

from .client import VergeClient
from .models import Article, Author, Category, Image

__all__ = ["VergeClient", "Article", "Author", "Category", "Image"]
__version__ = "0.1.0"
