from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
import anthropic
from bs4 import BeautifulSoup
from briefing.models import Item, normalize_url
from briefing.sources._fetch import fetch_with_fallback as http_get

MODEL = os.environ.get("BRIEFING_MODEL", "claude-sonnet-4-6")

def _client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_PROMPT = (
    "Fetch this page and extract the main news/article headlines: {url}\n"
    "Return ONLY valid JSON, no markdown fences:\n"
    '{{"items": [{{"title": "...", "url": "https://...", "summary": "one line"}}]}}'
)

def _page_links(url):
    """Normalised set of links actually on the page, or None if we can't read
    it ourselves (JS-gated / blocked) and so can't check Claude's answer."""
    try:
        html = http_get(url, timeout=30, retries=1).text
    except Exception as e:
        print(f"[claude_fetch] can't verify links for {url}: {e}", flush=True)
        return None
    links = {normalize_url(urljoin(url, a["href"]))
             for a in BeautifulSoup(html, "html.parser").find_all("a", href=True)}
    return links or None

def fetch_claude(cfg) -> list[Item]:
    client = _client()
    # Anthropic server-side web-fetch tool. If a future SDK changes the tool
    # type string or beta header, update these two values per Anthropic docs;
    # behavior is otherwise unchanged.
    msg = client.messages.create(
        model=MODEL, max_tokens=1500,
        tools=[{"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 3}],
        extra_headers={"anthropic-beta": "web-fetch-2025-09-10"},
        messages=[{"role": "user", "content": _PROMPT.format(url=cfg["url"])}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    text = re.sub(r"^```[a-z]*\n?|```$", "", text.strip(), flags=re.MULTILINE)
    data = json.loads(text)
    candidates = []
    for it in data.get("items", []):
        if not it.get("url"):
            continue
        url = urljoin(cfg["url"], it["url"])
        if url.startswith(("http://", "https://")):
            candidates.append({**it, "url": url})
    # Guard against invented URLs: when we can read the page ourselves, keep
    # only links that really appear on it. If *none* match, our copy is most
    # likely a JS shell without the article list, so the check can't judge.
    real = _page_links(cfg["url"])
    if real is not None:
        verified = [c for c in candidates if normalize_url(c["url"]) in real]
        if verified:
            for c in candidates:
                if c not in verified:
                    print(f"[claude_fetch] dropping link not on page: {c['url']}", flush=True)
            candidates = verified
        elif candidates:
            print(f"[claude_fetch] no links matched {cfg['url']} (JS-rendered?); "
                  "keeping Claude's list unverified", flush=True)
    out = []
    for it in candidates:
        out.append(Item.make(
            source=cfg["name"], source_type="claude_fetch",
            title=it.get("title", "(untitled)"), url=it["url"],
            summary=it.get("summary", ""), published=datetime.now(timezone.utc),
        ))
    return out
