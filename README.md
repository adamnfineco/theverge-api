# theverge

Unofficial Python client for The Verge. Pulls full-text articles, feeds, newsletters, and author profiles.

**Not affiliated with or endorsed by The Verge or Vox Media.**
The Verge produces great journalism. If you use this library, please consider subscribing: [theverge.com/subscribe](https://www.theverge.com/subscribe)

---

## Install

```bash
pip install httpx
# clone this repo, then:
pip install -e .
```

PyPI package coming once stable.

## Quick start

```python
from theverge import VergeClient

client = VergeClient()

# Latest articles — full body HTML, no truncation
articles = client.feed()
print(articles[0].title)
print(articles[0].body_html[:500])

# Section feeds
tech  = client.feed("tech")
games = client.feed("games")
ai    = client.feed("ai")

# Rich metadata (hero images, dek, post type) — one extra request
enriched = client.feed("tech", enrich=True)
print(enriched[0].hero_image.url)
print(enriched[0].dek)
```

## All methods

### `feed(section="", enrich=False) → list[Article]`

Fetch up to 30 recent articles from a section.

```python
client.feed()                           # homepage — all content
client.feed("tech")                     # tech section
client.feed("reviews")                  # reviews
client.feed("science")
client.feed("entertainment")
client.feed("transportation")
client.feed("games")
client.feed("ai")
client.feed("policy")
client.feed("gadgets")
client.feed("tech", enrich=True)        # includes hero images + dek
```

### `feed_iter(section="", enrich=False) → Iterator[Article]`

Lazily paginate through all articles in a section. RSS for the first batch (full body), `__NEXT_DATA__` for older pages.

```python
for article in client.feed_iter("games"):
    print(article.title, article.published_at)
```

### `article(path_or_url) → Article`

Fetch a single article with full body and rich metadata.

```python
post = client.article("/tech/941146/thermacell-liv-2-dot-0-smart-mosquito")
post = client.article("https://www.theverge.com/tech/941146/...")
print(post.title)
print(post.dek)
print(post.body_html)
print(post.hero_image.url)
```

### `quick_posts() → list[Article]`

Short-form news items (quick posts feed).

```python
posts = client.quick_posts()
```

### `newsletter(name) → list[Article]`

Full-text newsletter feeds.

```python
client.newsletter("installer")     # Installer newsletter
client.newsletter("notepad")       # Notepad
client.newsletter("regulator")     # Regulator
client.newsletter("the-stepback")  # The Stepback
client.newsletter("optimizer")     # Optimizer
```

### `reviews(enrich=False) → list[Article]`

Reviews feed.

```python
reviews = client.reviews(enrich=True)
```

### `author(slug) → AuthorProfile`

Author profile with recent posts.

```python
profile = client.author("nilay-patel")
print(profile.name)
print(profile.title)
print(profile.bio)
for post in profile.recent_posts:
    print(post.title)
```

### `search(query) → list[Article]`

Keyword search across the latest feed. Matches title, summary, and keywords.

```python
results = client.search("nvidia rtx spark")
```

### `popular() → list[dict]`

Most popular articles from the homepage.

```python
trending = client.popular()
for item in trending:
    print(item["title"], item["url"])
```

### `sections() → list[Category]`

All site sections and categories.

```python
sections = client.sections()
for s in sections:
    print(s.title, s.slug)
```

---

## Article fields

```python
article.title           # str
article.permalink       # str — full URL
article.path            # str — relative path
article.author          # str — display name
article.authors         # list[Author] — enriched author objects
article.published_at    # datetime
article.updated_at      # datetime | None
article.summary         # str — one-sentence description
article.dek             # str | None — subtitle (requires enrich=True or .article())
article.body_html       # str — full article HTML
article.keywords        # list[str]
article.categories      # list[Category]
article.resource_type   # "post" | "quickPost" | "stream" | None
article.hero_image      # Image | None (requires enrich=True or .article())
article.image           # Image | None — hero if available, else first from body
article.is_live         # bool — live blog active
article.wp_id           # int — WordPress post ID
article.is_quick_post   # bool
article.is_stream       # bool
article.to_dict()       # dict — JSON-serializable
```

## Author fields

```python
profile.name
profile.title           # job title e.g. "Editor in Chief"
profile.bio
profile.profile_image_url
profile.feed_link       # RSS feed URL for this author
profile.social_links    # list[dict]
profile.recent_posts    # list[Article]
```

---

## Rate limiting

Default: 0.5s between requests. Adjust with:

```python
client = VergeClient(rate_limit_delay=1.0)
```

---

## Context manager

```python
with VergeClient() as client:
    articles = client.feed("tech")
```

---

## License

MIT. See [LICENSE](LICENSE).

This project is not affiliated with, authorized by, or endorsed by The Verge or Vox Media.
