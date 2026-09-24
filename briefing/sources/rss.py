from __future__ import annotations
from datetime import datetime, timezone, timedelta
import calendar
import re
import feedparser
from bs4 import BeautifulSoup
from briefing.sources._fetch import fetch, fetch_with_fallback
from briefing.models import Item

def _to_dt(struct) -> datetime:
    return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)

def _plain(html, limit=500) -> str:
    """Feed summaries are often HTML; the pipeline and renderers want text."""
    text = BeautifulSoup(html or "", "html.parser").get_text(" ")
    text = re.sub(r"\s+", " ", text).strip()
    # WordPress feeds append "The post <title> appeared first on <site>."
    text = re.sub(r"\s*The post .{1,300}? appeared first on .{1,120}?\.?\s*$", "", text)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text

def _is_image(url, mime="", medium="") -> bool:
    return (medium == "image" or (mime or "").startswith("image/")
            or bool(re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", url or "", re.I)))

def _entry_image(e) -> str:
    """An image the feed itself supplies for this entry (media:content,
    media:thumbnail or an image enclosure), or "" when it gives none."""
    for m in e.get("media_content") or []:
        if m.get("url") and _is_image(m["url"], m.get("type", ""), m.get("medium", "")):
            return m["url"]
    for m in e.get("media_thumbnail") or []:
        if m.get("url"):
            return m["url"]
    for enc in e.get("enclosures") or []:
        href = enc.get("href") or enc.get("url")
        if href and _is_image(href, enc.get("type", "")):
            return href
    return ""

def _has_entries(resp) -> bool:
    return len(feedparser.parse(resp.content).entries) > 0

def fetch_rss(cfg, recency_hours=24) -> list[Item]:
    timeout = int(cfg.get("timeout", 30))  # optional per-feed override for slow hosts
    # Always go through the hardened fetch (browser UA + retries); feedparser's
    # own fetcher has neither and gets bot-walled more often.
    if cfg.get("proxy"):
        # Publisher blocks datacenter IPs (e.g. Cloudflare 403s on CI runners).
        # A 200 challenge page parses to zero entries, so that also falls back.
        resp = fetch_with_fallback(cfg["url"], validate=_has_entries, timeout=timeout)
    else:
        resp = fetch(cfg["url"], timeout=timeout)
    parsed = feedparser.parse(resp.content)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=recency_hours)
    out = []
    for e in parsed.entries:
        struct = e.get("published_parsed") or e.get("updated_parsed")
        published = _to_dt(struct) if struct else datetime.now(timezone.utc)
        if published < cutoff:
            continue
        image = _entry_image(e)
        out.append(Item.make(
            source=cfg["name"], source_type="rss",
            title=re.sub(r"\s+", " ", e.get("title") or "").strip() or "(untitled)",
            url=e.get("link", ""), summary=_plain(e.get("summary", "")),
            published=published, extra={"image": image} if image else None,
        ))
    return out
