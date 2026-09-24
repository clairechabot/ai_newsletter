"""Seedcamp portfolio parser — worked example ported from Ellipsis
athena/scrapers/seedcamp.py (simplified to the briefing Item contract)."""
from __future__ import annotations
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from briefing.sources._fetch import fetch as http_get
from briefing.models import Item

PAGE_URL = "https://seedcamp.com/our-companies/"

def fetch(cfg) -> list[Item]:
    resp = http_get(PAGE_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    for card in soup.select("div.company__item"):
        name_el = card.select_one("span.company__item__name")
        if not name_el:
            continue
        link = card.select_one("a.company__item__link")
        desc = card.select_one("div.company__item__description__content")
        out.append(Item.make(
            source=cfg["name"], source_type="site",
            title=name_el.get_text(strip=True),
            url=(link.get("href").strip() if link and link.get("href") else PAGE_URL),
            summary=desc.get_text(strip=True) if desc else "",
            published=datetime.now(timezone.utc),
        ))
    return out
