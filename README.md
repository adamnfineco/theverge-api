# theverge-api

Unofficial Python client for The Verge. Pull full-text articles, section feeds, newsletters, and author profiles into your own projects.

---

## Disclaimer

**This project is not affiliated with, authorized by, sponsored by, or endorsed by The Verge, Vox Media, or any of their affiliates.** "The Verge" is a trademark of Vox Media, LLC. This is an independent open source project with no relationship to The Verge or its parent company.

## Subscription requirement

**You must have an active paid subscription to The Verge to use this library.**

This library accesses content from The Verge's subscriber RSS feeds, which are provided as a benefit to paying subscribers. Using this library without a subscription violates The Verge's terms of service and undermines the journalism you're reading.

Subscribe here: [theverge.com/subscribe](https://www.theverge.com/subscribe)

By using this library you confirm that you are a current paying subscriber to The Verge.

---

## Install

```bash
pip install httpx
git clone https://github.com/adamnfineco/theverge-api
cd theverge-api
pip install -e .
```

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

## Methods

### `feed(section="", enrich=False) → list[Article]`

Up to 30 recent articles from a section.

```python
client.feed()                           # all content
client.feed("tech")
client.feed("reviews")
client.feed("science")
client.feed("entertainment")
client.feed("transportation")
client.feed("games")
client.feed("ai")
client.feed("policy")
client.feed("gadgets")
client.feed("tech", enrich=True)        # adds hero images + dek
```

### `feed_iter(section="", enrich=False) → Iterator[Article]`

Lazy pagination through all articles in a section.

```python
for article in client.feed_iter("games"):
    print(article.title, article.published_at)
```

### `article(path_or_url) → Article`

Single article with full body and rich metadata.

```python
post = client.article("/tech/941146/thermacell-liv-2-dot-0-smart-mosquito")
post = client.article("https://www.theverge.com/tech/941146/...")
print(post.title)
print(post.dek)
print(post.body_html)
print(post.hero_image.url)
```

### `quick_posts() → list[Article]`

Short-form news items.

```python
posts = client.quick_posts()
```

### `newsletter(name) → list[Article]`

Full-text newsletter feeds.

```python
client.newsletter("installer")
client.newsletter("notepad")
client.newsletter("regulator")
client.newsletter("the-stepback")
client.newsletter("optimizer")
```

### `reviews(enrich=False) → list[Article]`

```python
reviews = client.reviews(enrich=True)
```

### `author(slug) → AuthorProfile`

Author profile with recent posts.

```python
profile = client.author("nilay-patel")
print(profile.name)           # "Nilay Patel"
print(profile.title)          # "Editor-in-Chief"
print(profile.bio)
for post in profile.recent_posts:
    print(post.title)
```

### `search(query) → list[Article]`

Keyword search across the latest feed.

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
```

---

## Article fields

```python
article.title           # str
article.permalink       # str
article.path            # str
article.author          # str — display name
article.authors         # list[Author]
article.published_at    # datetime
article.updated_at      # datetime | None
article.summary         # str
article.dek             # str | None
article.body_html       # str — full HTML
article.keywords        # list[str]
article.categories      # list[Category]
article.resource_type   # "post" | "quickPost" | "stream" | None
article.hero_image      # Image | None
article.image           # Image | None — hero or first from body
article.is_live         # bool
article.wp_id           # int
article.is_quick_post   # bool
article.is_stream       # bool
article.to_dict()       # JSON-serializable dict
```

## Author fields

```python
profile.name
profile.title
profile.bio
profile.profile_image_url
profile.feed_link
profile.social_links    # list[dict]
profile.recent_posts    # list[Article]
```

---

## Rate limiting

Default: 0.5s between requests.

```python
client = VergeClient(rate_limit_delay=1.0)
```

## Context manager

```python
with VergeClient() as client:
    articles = client.feed("tech")
```

---

## How it works

This library combines two data sources:

1. **Subscriber RSS feeds** — The Verge publishes full-text RSS feeds as a subscriber benefit. These provide complete article body HTML, author, timestamps, and keywords with no truncation.
2. **`__NEXT_DATA__` SSR payloads** — The Verge's Next.js frontend embeds rich structured data in every page, including hero images, subtitles (dek), post type, and pagination. Available via `enrich=True` or `.article()`.

No headless browser, no session spoofing. Just RSS and public SSR data.

---

## License

MIT. See [LICENSE](LICENSE).

---

*This project is not affiliated with, authorized by, sponsored by, or endorsed by The Verge or Vox Media, LLC.*
