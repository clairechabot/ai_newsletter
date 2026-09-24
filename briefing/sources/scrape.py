from __future__ import annotations
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from briefing.sources._fetch import fetch
from briefing.models import Item

def fetch_scrape(cfg) -> list[Item]:
    resp = fetch(cfg["url"])
    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    for card in soup.select(cfg["item_selector"]):
        title_el = card.select_one(cfg["title_selector"])
        if not title_el:
            continue
        link_el = card.select_one(cfg.get("link_selector", cfg["title_selector"]))
        summ_el = card.select_one(cfg["summary_selector"]) if cfg.get("summary_selector") else None
        out.append(Item.make(
            source=cfg["name"], source_type="scrape",
            title=title_el.get_text(strip=True),
            url=(link_el.get("href") if link_el else ""),
            summary=(summ_el.get_text(strip=True) if summ_el else ""),
            published=datetime.now(timezone.utc),
        ))
    return out
