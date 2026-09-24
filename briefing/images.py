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
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from briefing.sources._fetch import fetch as http_get

# Checked in order; og:image is what nearly every publisher sets for previews.
_META = (
    ("property", "og:image:secure_url"), ("property", "og:image"), ("name", "og:image"),
    ("name", "twitter:image"), ("property", "twitter:image"), ("name", "twitter:image:src"),
)
_MAX_HTML = 300_000  # preview tags live in <head>; don't parse whole long articles


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


def _page_image(url, timeout) -> str:
    try:
        resp = http_get(url, timeout=timeout, retries=1)
    except Exception as e:  # blocked, slow or gone: this item just has no picture
        print(f"[images] no page for {url}: {e}", flush=True)
        return ""
    ctype = str(getattr(resp, "headers", {}).get("content-type", "")).lower()
    if ctype and "html" not in ctype:
        return ""
    return image_from_html(resp.text[:_MAX_HTML], getattr(resp, "url", "") or url)


def add_images(items, cfg) -> list:
    """Set `extra["image"]` on as many of `items` as possible (see module doc)."""
    if not is_enabled(cfg) or not items:
        return items
    todo = []
    for item in items:
        known = absolute_image_url(item.extra.get("image") or item.extra.get("thumbnail"))
        if known:
            item.extra["image"] = known
        elif absolute_image_url(item.url):
            todo.append(item)
    if todo:
        timeout = int(cfg.get("timeout", 10))
        with ThreadPoolExecutor(max_workers=max(1, int(cfg.get("workers", 8)))) as pool:
            found = pool.map(lambda i: _page_image(i.url, timeout), todo)
            for item, url in zip(todo, found):
                if url:
                    item.extra["image"] = url
    have = sum(1 for i in items if i.extra.get("image"))
    print(f"[images] {have}/{len(items)} items have a preview image", flush=True)
    return items
