"""
theverge — Unofficial Python client for The Verge.

Not affiliated with or endorsed by The Verge or Vox Media.
Please support independent journalism: https://www.theverge.com/subscribe

Requires an active paid subscription to The Verge.

Usage:
    from theverge import VergeClient, AsyncVergeClient, since_hours

    # Sync
    with VergeClient() as client:
        articles = client.feed("tech", since=since_hours(24))
        print(articles[0].title)
        print(articles[0].body_text)

    # Async
    import asyncio
    async def main():
        async with AsyncVergeClient() as client:
            articles = await client.feed("tech")
            results  = await client.search("nvidia spark")

    asyncio.run(main())
"""

from .client import AsyncVergeClient, VergeClient
from .models import Article, Author, AuthorProfile, Category, Image
from .utils import since_hours

__all__ = [
    "VergeClient",
    "AsyncVergeClient",
    "Article",
    "Author",
    "AuthorProfile",
    "Category",
    "Image",
    "since_hours",
]
__version__ = "0.2.0"
