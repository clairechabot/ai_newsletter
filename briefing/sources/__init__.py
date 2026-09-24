from __future__ import annotations
from briefing.sources.base import safe_fetch, write_step_summary
from briefing.sources.rss import fetch_rss
from briefing.sources.scrape import fetch_scrape
from briefing.sources.claude_fetch import fetch_claude
from briefing.sources import sites as _sites

def _youtube(cfg, recency_hours):
    from briefing.sources.youtube import fetch_youtube
    return fetch_youtube(cfg)

def _site(cfg, recency_hours):
    return _sites.get(cfg["module"])(cfg)

DISPATCH = {
    "rss": lambda c, rh: fetch_rss(c, recency_hours=rh),
    "scrape": lambda c, rh: fetch_scrape(c),
    "claude_fetch": lambda c, rh: fetch_claude(c),
    "youtube": _youtube,
    "site": _site,
}

def fetch_all(cfg) -> list:
    items, report = [], {}
    for s in cfg.sources:
        adapter = DISPATCH[s["type"]]
        items.extend(safe_fetch(s.get("name", s["type"]),
                                lambda s=s: adapter(s, cfg.recency_hours), report))
    write_step_summary(report)
    return items
