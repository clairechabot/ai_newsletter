"""Preview images — give each selected item a picture, the way the Newsletter
repo does: the image the publisher already declares for link previews.

Optional and off by default. Enable in `config.yaml`:

    images:
      enabled: true
      timeout: 10      # seconds per article page (default 10)
      workers: 8       # pages fetched in parallel (default 8)

Runs after filtering, so it only touches the ~25 items that ship. Order of
preference, cheapest first:

1. an image the source already supplied (`extra["image"]`: RSS media, or
   `extra["thumbnail"]` for YouTube), no request needed;
2. the article page's `og:image` / `twitter:image` meta tag.

Stores the result as `extra["image"]` (an absolute http(s) URL; images are
hotlinked, not downloaded). Fails soft per item: a slow, blocked or image-less
page just leaves that item without a picture.

The same page fetch measures the article for a read time: words in
`<article>` (else `<main>`, else `<body>`) at 230 words a minute, rounded up,
stored as `extra["minutes"]`. Pages too short to be the real article (a
paywall or consent wall) leave it unset, and renderers fall back to 3 minutes.
"""
from __future__ import annotations
import math
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from briefing.sources._fetch import fetch as http_get

# Checked in order; og:image is what nearly every publisher sets for previews.
_META = (
    ("property", "og:image:secure_url"), ("property", "og:image"), ("name", "og:image"),
    ("name", "twitter:image"), ("property", "twitter:image"), ("name", "twitter:image:src"),
)
_MAX_HTML = 600_000  # enough for the head and a long article body; skip the rest
WPM = 230            # reading speed for `extra["minutes"]`
_MIN_WORDS = 120     # fewer than this is a stub or a wall, not the article
_NOT_TEXT = ("script", "style", "noscript", "nav", "header", "footer", "aside", "form",
             "svg", "figure", "template")


def is_enabled(cfg) -> bool:
    return bool(cfg) and bool(cfg.get("enabled"))


def absolute_image_url(url, base="") -> str:
    """Resolve `url` against `base` and keep it only if it's http(s)."""
    url = (url or "").strip()
    if not url:
        return ""
    if base:
        url = urljoin(base, url)
    return url if url.startswith(("http://", "https://")) else ""


def image_from_html(html, base_url) -> str:
    """The page's declared preview image, or "" if it declares none."""
    soup = BeautifulSoup(html or "", "html.parser")
    for attr, value in _META:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            url = absolute_image_url(tag["content"], base_url)
            if url:
                return url
    link = soup.find("link", rel="image_src")
    if link and link.get("href"):
        return absolute_image_url(link["href"], base_url)
    return ""


def article_words(html) -> int:
    """Words of running text in the page's article (see module doc)."""
    soup = BeautifulSoup(html or "", "html.parser")
    root = soup.find("article") or soup.find("main") or soup.body or soup
    for tag in root.find_all(_NOT_TEXT):
        tag.decompose()
    return len(re.findall(r"\w+", root.get_text(" ")))


def read_minutes_from_words(words) -> int | None:
    """Whole minutes at WPM, or None when `words` is too few to trust."""
    return math.ceil(words / WPM) if words >= _MIN_WORDS else None


def _page(url, timeout) -> tuple:
    """(preview image, read minutes or None) for the article at `url`."""
    try:
        resp = http_get(url, timeout=timeout, retries=1)
    except Exception as e:  # blocked, slow or gone: this item just has no picture
        print(f"[images] no page for {url}: {e}", flush=True)
        return "", None
    ctype = str(getattr(resp, "headers", {}).get("content-type", "")).lower()
    if ctype and "html" not in ctype:
        return "", None
    html = resp.text[:_MAX_HTML]
    try:
        minutes = read_minutes_from_words(article_words(html))
    except Exception:  # odd markup: no read time, the image may still be found
        minutes = None
    return image_from_html(html, getattr(resp, "url", "") or url), minutes


def add_images(items, cfg) -> list:
    """Set `extra["image"]` (and `extra["minutes"]`) on as many of `items` as
    possible (see module doc)."""
    if not is_enabled(cfg) or not items:
        return items
    todo = []
    for item in items:
        known = absolute_image_url(item.extra.get("image") or item.extra.get("thumbnail"))
        if known:
            item.extra["image"] = known
        # Videos have no article to measure; every other page is fetched for
        # its read time even when the feed already gave us the picture.
        if item.source_type != "youtube" and absolute_image_url(item.url) \
                and not (known and item.extra.get("minutes")):
            todo.append(item)
    if todo:
        timeout = int(cfg.get("timeout", 10))
        with ThreadPoolExecutor(max_workers=max(1, int(cfg.get("workers", 8)))) as pool:
            found = pool.map(lambda i: _page(i.url, timeout), todo)
            for item, (url, minutes) in zip(todo, found):
                if url and not item.extra.get("image"):
                    item.extra["image"] = url
                if minutes and not item.extra.get("minutes"):
                    item.extra["minutes"] = minutes
    have = sum(1 for i in items if i.extra.get("image"))
    timed = sum(1 for i in items if i.extra.get("minutes"))
    print(f"[images] {have}/{len(items)} items have a preview image, {timed} a read time",
          flush=True)
    return items
