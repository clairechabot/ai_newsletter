from __future__ import annotations
from datetime import datetime, timezone, timedelta
import calendar
import feedparser
from briefing.sources._fetch import fetch, fetch_with_fallback
from briefing.models import Item

def _to_dt(struct) -> datetime:
    return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)

def _has_entries(resp) -> bool:
    return len(feedparser.parse(resp.content).entries) > 0

def fetch_rss(cfg, recency_hours=24) -> list[Item]:
    # Always go through the hardened fetch (browser UA + retries); feedparser's
    # own fetcher has neither and gets bot-walled more often.
    if cfg.get("proxy"):
        # Publisher blocks datacenter IPs (e.g. Cloudflare 403s on CI runners).
        # A 200 challenge page parses to zero entries, so that also falls back.
        resp = fetch_with_fallback(cfg["url"], validate=_has_entries, timeout=30)
    else:
        resp = fetch(cfg["url"], timeout=30)
    parsed = feedparser.parse(resp.content)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=recency_hours)
    out = []
    for e in parsed.entries:
        struct = e.get("published_parsed") or e.get("updated_parsed")
        published = _to_dt(struct) if struct else datetime.now(timezone.utc)
        if published < cutoff:
            continue
        out.append(Item.make(
            source=cfg["name"], source_type="rss",
            title=e.get("title", "(untitled)"),
            url=e.get("link", ""), summary=e.get("summary", ""),
            published=published,
        ))
    return out
