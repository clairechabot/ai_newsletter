"""TEMPLATE — copy this file to <yoursite>.py and edit, then add to config.yaml:
    - { type: site, name: "Your Site", module: "yoursite" }

Contract: fetch(cfg) -> list[Item]. Use the shared HTTP helper (imported as
http_get: browser UA + retries). Tests patch <module>.http_get. Always return a list;
raising on a real error is fine (the registry fails it soft)."""
from __future__ import annotations
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from briefing.sources._fetch import fetch as http_get
from briefing.models import Item

PAGE_URL = "https://example.com/news"

def fetch(cfg) -> list[Item]:
    resp = http_get(PAGE_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    for card in soup.select(".article"):
        title_el = card.select_one("h2 a")
        if not title_el:
            continue
        out.append(Item.make(
            source=cfg["name"], source_type="site",
            title=title_el.get_text(strip=True),
            url=title_el.get("href", ""),
            summary=(card.select_one("p") or title_el).get_text(strip=True),
            published=datetime.now(timezone.utc),
        ))
    return out
