# Daily Briefing Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a forkable private-template repo that turns configured web/news/RSS sources into a filtered, themed daily-briefing email, runnable on GitHub Actions.

**Architecture:** A source-adapter pipeline (the Ellipsis `athena/scrapers/` pattern). Every source adapter returns a list of the same `Item`; the pipeline then dedups, filters (one of four modes), enriches + themes with the Anthropic API, renders HTML, and emails via SMTP. Config (sources + interests) lives in a committed `config.yaml`; only secrets live in GitHub Secrets.

**Tech Stack:** Python 3.12, `pyyaml`, `feedparser`, `beautifulsoup4`, `requests`, `anthropic`, `google-api-python-client` (optional YouTube), `pytest`. Runtime: GitHub Actions.

**Reference (read-only):** the existing working code at `C:\Users\clmch\smart-digest\main.py` is the source of the ported theming/email/YouTube logic. The approved spec is `C:\Users\clmch\smart-digest\docs\superpowers\specs\2026-06-04-daily-briefing-skeleton-design.md`.

---

## File structure

```
daily-briefing/
├── config.yaml                  user-edited: sources, interests, filter mode
├── config.example.yaml          shipped example
├── main.py                      entrypoint: load config -> run pipeline
├── briefing/
│   ├── __init__.py
│   ├── models.py                Item dataclass            (Task 1)
│   ├── config.py                load + validate config    (Task 2)
│   ├── history.py               dedup persistence         (Task 10)
│   ├── filter.py                4 filter modes            (Task 11)
│   ├── enrich.py                Claude summaries + themes (Task 12)
│   ├── email.py                 HTML build + SMTP send    (Task 13)
│   ├── pipeline.py              orchestrator              (Task 14)
│   └── sources/
│       ├── __init__.py          registry: type -> adapter (Task 9)
│       ├── base.py              Source contract + result  (Task 3)
│       ├── _fetch.py            hardened HTTP fetch        (Task 4)
│       ├── rss.py               RSS adapter                (Task 5)
│       ├── scrape.py            generic selector scraper   (Task 7)
│       ├── claude_fetch.py      Claude web-fetch adapter   (Task 8)
│       ├── youtube.py           optional YouTube adapter   (Task 6b)
│       └── sites/
│           ├── __init__.py      auto-discovery             (Task 6)
│           ├── _example.py      copy-me template           (Task 6)
│           └── seedcamp.py      worked example             (Task 6)
├── tests/                       pytest mirror of the above
├── .github/workflows/daily.yml  scheduled cron             (Task 15)
├── README.md                    setup walkthrough          (Task 16)
├── CLAUDE.md                    add-a-source guide         (Task 16)
├── requirements.txt
└── history.json                 dedup state (seed: {"seen_ids": []})
```

---

## Task 0: Repo bootstrap

**Files:**
- Create: local clone of `clairechabot/daily-briefing`, `requirements.txt`, `pytest.ini`, package dirs, `.gitignore`, `history.json`

- [ ] **Step 1: Clone the empty repo and enter it**

```bash
cd /c/Users/clmch
gh repo clone clairechabot/daily-briefing
cd daily-briefing
```

- [ ] **Step 2: Create the virtualenv and requirements**

Create `requirements.txt`:
```
pyyaml>=6.0
feedparser>=6.0
beautifulsoup4>=4.12
requests>=2.31
anthropic>=0.40
google-api-python-client>=2.120
isodate>=0.6.1
```
Create `requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.0
```
Run:
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

- [ ] **Step 3: Create package skeleton + config files**

```bash
mkdir -p briefing/sources/sites tests/sources/sites tests/fixtures
touch briefing/__init__.py briefing/sources/__init__.py briefing/sources/sites/__init__.py
touch tests/__init__.py
```
Create `pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
```
Create `.gitignore`:
```
.venv/
__pycache__/
*.pyc
.env
```
Create `history.json`:
```json
{"seen_ids": []}
```

- [ ] **Step 4: Verify pytest runs (zero tests)**

Run: `.venv/Scripts/python -m pytest -q`
Expected: `no tests ran` (exit 5) — confirms pytest is wired.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: bootstrap daily-briefing skeleton (deps, layout, pytest)"
```

---

## Task 1: Item model

**Files:**
- Create: `briefing/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from datetime import datetime, timezone
from briefing.models import Item

def test_item_has_stable_id_from_url_when_not_given():
    a = Item.make(source="BBC", source_type="rss", title="T",
                  url="https://x.com/a", summary="s",
                  published=datetime(2026, 6, 4, tzinfo=timezone.utc))
    b = Item.make(source="BBC", source_type="rss", title="T2",
                  url="https://x.com/a", summary="s2",
                  published=datetime(2026, 6, 4, tzinfo=timezone.utc))
    assert a.id == b.id  # same url -> same id

def test_item_make_uses_explicit_id_when_given():
    it = Item.make(source="YT", source_type="youtube", title="V",
                   url="https://youtu.be/x", summary="",
                   published=datetime(2026, 6, 4, tzinfo=timezone.utc),
                   id="vid123")
    assert it.id == "vid123"
    assert it.extra == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: briefing.models`.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/models.py
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Item:
    source: str
    source_type: str
    title: str
    url: str
    summary: str
    published: datetime
    id: str
    extra: dict = field(default_factory=dict)

    @classmethod
    def make(cls, *, source, source_type, title, url, summary, published,
             id=None, extra=None):
        if not id:
            id = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return cls(source=source, source_type=source_type, title=title,
                   url=url, summary=summary, published=published, id=id,
                   extra=extra or {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add briefing/models.py tests/test_models.py
git commit -m "feat: Item model with url-derived stable id"
```

---

## Task 2: Config loader

**Files:**
- Create: `briefing/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from briefing.config import load_config, ConfigError

VALID = """
briefing: {title: "T"}
filter: {mode: interests, interests: ["ai"], max_items: 10, recency_hours: 24, per_source_cap: 5}
sources:
  - {type: rss, name: "BBC", url: "http://x/rss"}
"""

def test_load_valid(tmp_path):
    p = tmp_path / "c.yaml"; p.write_text(VALID, encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.title == "T"
    assert cfg.filter_mode == "interests"
    assert cfg.max_items == 10
    assert cfg.sources[0]["type"] == "rss"

def test_bad_filter_mode_raises(tmp_path):
    bad = VALID.replace("mode: interests", "mode: nonsense")
    p = tmp_path / "c.yaml"; p.write_text(bad, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(str(p))

def test_source_missing_type_raises(tmp_path):
    bad = VALID.replace('{type: rss, name: "BBC", url: "http://x/rss"}', '{name: "BBC"}')
    p = tmp_path / "c.yaml"; p.write_text(bad, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(str(p))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: briefing.config`.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/config.py
from __future__ import annotations
from dataclasses import dataclass
import yaml

VALID_MODES = {"interests", "recent", "per_source_cap", "claude_curate"}
VALID_TYPES = {"rss", "site", "scrape", "claude_fetch", "youtube"}

class ConfigError(Exception):
    pass

@dataclass
class Config:
    title: str
    filter_mode: str
    interests: list
    max_items: int
    per_source_cap: int
    recency_hours: int
    sources: list

def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    f = raw.get("filter", {})
    mode = f.get("mode", "recent")
    if mode not in VALID_MODES:
        raise ConfigError(f"filter.mode must be one of {sorted(VALID_MODES)}, got {mode!r}")
    sources = raw.get("sources", [])
    if not sources:
        raise ConfigError("config has no sources")
    for s in sources:
        t = s.get("type")
        if t not in VALID_TYPES:
            raise ConfigError(f"source has invalid/missing type: {s!r}")
    return Config(
        title=raw.get("briefing", {}).get("title", "Daily Briefing"),
        filter_mode=mode,
        interests=f.get("interests", []),
        max_items=int(f.get("max_items", 25)),
        per_source_cap=int(f.get("per_source_cap", 5)),
        recency_hours=int(f.get("recency_hours", 24)),
        sources=sources,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add briefing/config.py tests/test_config.py
git commit -m "feat: config loader with mode + source-type validation"
```

---

## Task 3: Source contract

**Files:**
- Create: `briefing/sources/base.py`
- Test: `tests/sources/test_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_base.py
from briefing.sources.base import safe_fetch

def test_safe_fetch_returns_items_on_success():
    out = safe_fetch("ok", lambda: ["a", "b"])
    assert out == ["a", "b"]

def test_safe_fetch_swallows_errors_to_empty_list(capsys):
    def boom():
        raise RuntimeError("dead site")
    out = safe_fetch("BadSite", boom)
    assert out == []
    assert "BadSite" in capsys.readouterr().out  # logged, not raised
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/sources/test_base.py -v`
Expected: FAIL — module not found. (Add `tests/sources/__init__.py` if needed: `touch tests/sources/__init__.py tests/sources/sites/__init__.py`.)

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/sources/base.py
"""Source adapter contract. Each adapter exposes fetch(source_cfg) -> list[Item]."""
from __future__ import annotations

def safe_fetch(name, thunk):
    """Run a source's fetch; on ANY error log and return [] so one dead
    source never kills the briefing (Ellipsis fail-soft pattern)."""
    try:
        return thunk()
    except Exception as e:  # boundary: external sites/APIs are untrusted
        print(f"[source:{name}] FAILED, skipping: {e}", flush=True)
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/sources/test_base.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add briefing/sources/base.py tests/sources/
git commit -m "feat: source fail-soft wrapper"
```

---

## Task 4: Hardened fetch helper

**Files:**
- Create: `briefing/sources/_fetch.py`
- Test: `tests/sources/test_fetch.py`

Ports `athena/scrapers/__init__.py` (retries + browser User-Agent + timeout).

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_fetch.py
import requests
from unittest.mock import patch, Mock
from briefing.sources._fetch import fetch, BROWSER_HEADERS

def test_browser_user_agent_present():
    assert "Mozilla/5.0" in BROWSER_HEADERS["User-Agent"]

def test_retries_then_succeeds():
    calls = {"n": 0}
    def side_effect(*a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            raise requests.ConnectionError("flaky")
        m = Mock(); m.raise_for_status = Mock(); return m
    with patch("briefing.sources._fetch.requests.request", side_effect=side_effect):
        fetch("http://x", retries=3, retry_delay=0)
    assert calls["n"] == 2

def test_raises_after_all_retries():
    with patch("briefing.sources._fetch.requests.request",
               side_effect=requests.ConnectionError("down")):
        try:
            fetch("http://x", retries=2, retry_delay=0)
            assert False, "expected RequestException"
        except requests.RequestException:
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/sources/test_fetch.py -v`
Expected: FAIL — `briefing.sources._fetch` not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/sources/_fetch.py
"""Hardened HTTP fetch, ported from Ellipsis athena/scrapers/__init__.py.
Retries with backoff, browser User-Agent, timeout, raise_for_status."""
from __future__ import annotations
import time
import requests

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

def fetch(url, method="GET", headers=None, timeout=60, retries=3,
          retry_delay=5, **kwargs):
    hdrs = {**BROWSER_HEADERS, **(headers or {})}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(method, url, headers=hdrs, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(retry_delay)
    raise last_err
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/sources/test_fetch.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add briefing/sources/_fetch.py tests/sources/test_fetch.py
git commit -m "feat: hardened fetch helper (ported from Ellipsis)"
```

---

## Task 5: RSS adapter

**Files:**
- Create: `briefing/sources/rss.py`
- Test: `tests/sources/test_rss.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_rss.py
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from briefing.sources.rss import fetch_rss

def _fake_parsed():
    now = datetime.now(timezone.utc)
    class E(dict):
        __getattr__ = dict.get
    return type("P", (), {"entries": [
        {"title": "Fresh", "link": "http://x/1",
         "summary": "s1", "published_parsed": (now).timetuple()},
        {"title": "Old", "link": "http://x/2",
         "summary": "s2", "published_parsed": (now - timedelta(days=10)).timetuple()},
    ]})()

def test_rss_maps_and_respects_recency():
    cfg = {"type": "rss", "name": "BBC", "url": "http://x/rss"}
    with patch("briefing.sources.rss.feedparser.parse", return_value=_fake_parsed()):
        items = fetch_rss(cfg, recency_hours=24)
    assert len(items) == 1
    assert items[0].title == "Fresh"
    assert items[0].source == "BBC"
    assert items[0].source_type == "rss"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/sources/test_rss.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/sources/rss.py
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import calendar
import feedparser
from briefing.models import Item

def _to_dt(struct) -> datetime:
    return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)

def fetch_rss(cfg, recency_hours=24) -> list[Item]:
    parsed = feedparser.parse(cfg["url"])
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/sources/test_rss.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add briefing/sources/rss.py tests/sources/test_rss.py
git commit -m "feat: RSS source adapter"
```

---

## Task 6: Bespoke `sites/` package (auto-discovery + example + worked seedcamp)

**Files:**
- Create: `briefing/sources/sites/__init__.py`, `briefing/sources/sites/_example.py`, `briefing/sources/sites/seedcamp.py`
- Test: `tests/sources/sites/test_sites.py`, `tests/fixtures/seedcamp.html`

- [ ] **Step 1: Write the failing test**

Create `tests/fixtures/seedcamp.html`:
```html
<html><body>
<div class="company__item ai">
  <span class="company__item__name">Acme AI</span>
  <div class="company__item__description__content">An AI company.</div>
  <a class="company__item__link" href="https://acme.ai">site</a>
</div>
<div class="company__item">
  <span class="company__item__name">Beta Co</span>
  <div class="company__item__description__content">A thing.</div>
  <a class="company__item__link" href="https://beta.co">site</a>
</div>
</body></html>
```

```python
# tests/sources/sites/test_sites.py
from pathlib import Path
from unittest.mock import patch, Mock
from briefing.sources.sites import discover, get
import briefing.sources.sites.seedcamp as seedcamp

def test_discover_finds_seedcamp_not_example():
    mods = discover()
    assert "seedcamp" in mods
    assert "_example" not in mods  # underscore-prefixed are templates

def test_get_returns_callable():
    assert callable(get("seedcamp"))

def test_seedcamp_parses_fixture():
    html = (Path(__file__).parents[2] / "fixtures" / "seedcamp.html").read_text(encoding="utf-8")
    resp = Mock(); resp.text = html
    with patch("briefing.sources.sites.seedcamp.fetch", return_value=resp):
        items = seedcamp.fetch({"type": "site", "name": "Seedcamp", "module": "seedcamp"})
    assert {i.title for i in items} == {"Acme AI", "Beta Co"}
    assert all(i.source_type == "site" for i in items)
    assert items[0].url.startswith("https://")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/sources/sites/test_sites.py -v`
Expected: FAIL — `discover` / module not found.

- [ ] **Step 3: Write the implementations**

```python
# briefing/sources/sites/__init__.py
"""Bespoke per-site parsers (the Ellipsis model). Each <site>.py module
exposes fetch(source_cfg) -> list[Item]. Underscore-prefixed files are
templates, not sources."""
from __future__ import annotations
import importlib
import pkgutil

def discover() -> dict:
    out = {}
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        out[mod.name] = mod.name
    return out

def get(module_name):
    mod = importlib.import_module(f"{__name__}.{module_name}")
    return mod.fetch
```

```python
# briefing/sources/sites/_example.py
"""TEMPLATE — copy this file to <yoursite>.py and edit. Then add to config.yaml:
    - { type: site, name: "Your Site", module: "yoursite" }

Contract: fetch(cfg) -> list[Item]. Use the shared `fetch` helper (browser UA +
retries). Always return a list; raise on real errors (the pipeline fails it soft).
"""
from __future__ import annotations
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from briefing.sources._fetch import fetch
from briefing.models import Item

PAGE_URL = "https://example.com/news"

def fetch(cfg) -> list[Item]:  # noqa: F811 (intentionally shadows helper name in module scope)
    from briefing.sources._fetch import fetch as http_get
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
```

> Note: `_example.py` is a template only (never imported by `discover()`). Keep it import-safe but it is not executed by tests.

```python
# briefing/sources/sites/seedcamp.py
"""Seedcamp portfolio parser — worked example ported from Ellipsis
athena/scrapers/seedcamp.py (simplified to the briefing Item contract)."""
from __future__ import annotations
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from briefing.sources._fetch import fetch
from briefing.models import Item

PAGE_URL = "https://seedcamp.com/our-companies/"

def fetch(cfg) -> list[Item]:  # noqa: F811
    from briefing.sources._fetch import fetch as http_get
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
```

> The local `fetch(cfg)` import-of-`http_get` pattern avoids the name clash between the adapter entrypoint `fetch` and the HTTP helper `fetch`. Keep this exact shape when copying `_example.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/sources/sites/test_sites.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add briefing/sources/sites/ tests/sources/sites/ tests/fixtures/seedcamp.html
git commit -m "feat: bespoke sites package (auto-discovery + example + seedcamp)"
```

---

## Task 6b: Optional YouTube adapter

**Files:**
- Create: `briefing/sources/youtube.py`
- Test: `tests/sources/test_youtube.py`

Ported from `main.py` (`_yt_search_channel`), simplified: single fetch pass (the 5-minute double-fetch is dropped — unnecessary for a personal briefing and slows CI).

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_youtube.py
from unittest.mock import patch, MagicMock
from briefing.sources.youtube import fetch_youtube

def _fake_yt():
    yt = MagicMock()
    yt.search().list().execute.return_value = {"items": [
        {"id": {"videoId": "v1"}, "snippet": {
            "title": "Vid", "channelTitle": "Chan",
            "publishedAt": "2026-06-04T00:00:00Z",
            "thumbnails": {"high": {"url": "http://t/v1.jpg"}}}}
    ]}
    return yt

def test_youtube_maps_to_items():
    cfg = {"type": "youtube", "name": "Chan", "channel_id": "UC1"}
    with patch("briefing.sources.youtube._build_youtube", return_value=_fake_yt()):
        items = fetch_youtube(cfg, max_per_channel=2)
    assert items[0].id == "v1"
    assert items[0].source_type == "youtube"
    assert items[0].extra["embed_url"].endswith("v1?rel=0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/sources/test_youtube.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/sources/youtube.py
from __future__ import annotations
import os
from datetime import datetime, timezone
from googleapiclient.discovery import build
from briefing.models import Item

def _build_youtube():
    return build("youtube", "v3", developerKey=os.environ["YOUTUBE_API_KEY"])

def fetch_youtube(cfg, max_per_channel=2) -> list[Item]:
    yt = _build_youtube()
    resp = yt.search().list(
        part="snippet", channelId=cfg["channel_id"],
        order="date", maxResults=max_per_channel, type="video",
    ).execute()
    out = []
    for it in resp.get("items", []):
        vid = it["id"]["videoId"]
        snip = it["snippet"]
        out.append(Item.make(
            source=cfg["name"], source_type="youtube",
            title=snip["title"], url=f"https://www.youtube.com/watch?v={vid}",
            summary=snip.get("description", ""),
            published=datetime.now(timezone.utc), id=vid,
            extra={
                "embed_url": f"https://www.youtube.com/embed/{vid}?rel=0",
                "thumbnail": snip["thumbnails"]["high"]["url"],
                "channel": snip["channelTitle"],
            },
        ))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/sources/test_youtube.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add briefing/sources/youtube.py tests/sources/test_youtube.py
git commit -m "feat: optional YouTube adapter (single-pass)"
```

---

## Task 7: Generic scrape adapter

**Files:**
- Create: `briefing/sources/scrape.py`
- Test: `tests/sources/test_scrape.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_scrape.py
from unittest.mock import patch, Mock
from briefing.sources.scrape import fetch_scrape

HTML = """<html><body>
<div class="post"><h2><a href="https://s/1">First</a></h2><p class="excerpt">e1</p></div>
<div class="post"><h2><a href="https://s/2">Second</a></h2><p class="excerpt">e2</p></div>
</body></html>"""

def test_scrape_uses_selectors():
    cfg = {"type": "scrape", "name": "Static", "url": "http://s",
           "item_selector": ".post", "title_selector": "h2 a",
           "link_selector": "h2 a", "summary_selector": "p.excerpt"}
    resp = Mock(); resp.text = HTML
    with patch("briefing.sources.scrape.fetch", return_value=resp):
        items = fetch_scrape(cfg)
    assert [i.title for i in items] == ["First", "Second"]
    assert items[0].url == "https://s/1"
    assert items[0].summary == "e1"
    assert items[0].source_type == "scrape"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/sources/test_scrape.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/sources/scrape.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/sources/test_scrape.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add briefing/sources/scrape.py tests/sources/test_scrape.py
git commit -m "feat: generic config-selector scrape adapter"
```

---

## Task 8: Claude web-fetch adapter

**Files:**
- Create: `briefing/sources/claude_fetch.py`
- Test: `tests/sources/test_claude_fetch.py`

> **Implementation note:** this uses the Anthropic server-side **web-fetch tool**. Before writing Step 3, invoke the `claude-api` skill to confirm the exact tool `type` string and beta header for the installed `anthropic` SDK version, and adjust the `tools=[...]` block accordingly. The test mocks the client, so it is not blocked by that confirmation.

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_claude_fetch.py
import json
from unittest.mock import patch, MagicMock
from briefing.sources.claude_fetch import fetch_claude

def _fake_client(payload):
    client = MagicMock()
    block = MagicMock(); block.type = "text"; block.text = json.dumps(payload)
    msg = MagicMock(); msg.content = [block]
    client.messages.create.return_value = msg
    return client

def test_claude_fetch_parses_items():
    cfg = {"type": "claude_fetch", "name": "NoFeed", "url": "https://nf.com"}
    payload = {"items": [
        {"title": "A", "url": "https://nf.com/a", "summary": "sa"},
        {"title": "B", "url": "https://nf.com/b", "summary": "sb"},
    ]}
    with patch("briefing.sources.claude_fetch._client", return_value=_fake_client(payload)):
        items = fetch_claude(cfg)
    assert [i.title for i in items] == ["A", "B"]
    assert items[0].source_type == "claude_fetch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/sources/test_claude_fetch.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/sources/claude_fetch.py
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
import anthropic
from briefing.models import Item

MODEL = os.environ.get("BRIEFING_MODEL", "claude-sonnet-4-6")

def _client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_PROMPT = (
    "Fetch this page and extract the main news/article headlines: {url}\n"
    "Return ONLY valid JSON, no markdown fences:\n"
    '{{"items": [{{"title": "...", "url": "https://...", "summary": "one line"}}]}}'
)

def fetch_claude(cfg) -> list[Item]:
    client = _client()
    msg = client.messages.create(
        model=MODEL, max_tokens=1500,
        tools=[{"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 3}],
        extra_headers={"anthropic-beta": "web-fetch-2025-09-10"},
        messages=[{"role": "user", "content": _PROMPT.format(url=cfg["url"])}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    text = re.sub(r"^```[a-z]*\n?|```$", "", text.strip(), flags=re.MULTILINE)
    data = json.loads(text)
    out = []
    for it in data.get("items", []):
        if not it.get("url"):
            continue
        out.append(Item.make(
            source=cfg["name"], source_type="claude_fetch",
            title=it.get("title", "(untitled)"), url=it["url"],
            summary=it.get("summary", ""), published=datetime.now(timezone.utc),
        ))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/sources/test_claude_fetch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add briefing/sources/claude_fetch.py tests/sources/test_claude_fetch.py
git commit -m "feat: claude_fetch adapter (Anthropic web-fetch tool)"
```

---

## Task 9: Source registry

**Files:**
- Modify: `briefing/sources/__init__.py`
- Test: `tests/sources/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_registry.py
from unittest.mock import patch
from briefing.sources import fetch_all
from briefing.config import Config

def _cfg(sources):
    return Config(title="t", filter_mode="recent", interests=[], max_items=10,
                  per_source_cap=5, recency_hours=24, sources=sources)

def test_dispatches_by_type_and_fails_soft():
    sources = [
        {"type": "rss", "name": "Good", "url": "http://x"},
        {"type": "rss", "name": "Bad", "url": "http://y"},
    ]
    def fake_rss(cfg, recency_hours):
        if cfg["name"] == "Bad":
            raise RuntimeError("boom")
        from briefing.models import Item
        from datetime import datetime, timezone
        return [Item.make(source="Good", source_type="rss", title="T",
                          url="http://x/1", summary="", published=datetime.now(timezone.utc))]
    with patch("briefing.sources.fetch_rss", side_effect=fake_rss):
        items = fetch_all(_cfg(sources))
    assert [i.source for i in items] == ["Good"]  # Bad failed soft, dropped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/sources/test_registry.py -v`
Expected: FAIL — `fetch_all` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/sources/__init__.py
from __future__ import annotations
from briefing.sources.base import safe_fetch
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
    items = []
    for s in cfg.sources:
        adapter = DISPATCH[s["type"]]
        items.extend(safe_fetch(s.get("name", s["type"]),
                                lambda s=s: adapter(s, cfg.recency_hours)))
    return items
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/sources/test_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add briefing/sources/__init__.py tests/sources/test_registry.py
git commit -m "feat: source registry with per-source fail-soft dispatch"
```

---

## Task 10: History / dedup

**Files:**
- Create: `briefing/history.py`
- Test: `tests/test_history.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history.py
from datetime import datetime, timezone
from briefing.history import load_history, save_history, drop_seen
from briefing.models import Item

def _item(uid):
    return Item.make(source="s", source_type="rss", title="t",
                     url=f"http://x/{uid}", summary="", published=datetime.now(timezone.utc), id=uid)

def test_drop_seen_filters_known_ids():
    hist = {"seen_ids": ["a"]}
    fresh = drop_seen([_item("a"), _item("b")], hist)
    assert [i.id for i in fresh] == ["b"]

def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "h.json"
    save_history(str(p), {"seen_ids": ["x", "y"]})
    assert load_history(str(p))["seen_ids"] == ["x", "y"]

def test_load_missing_file_returns_empty(tmp_path):
    assert load_history(str(tmp_path / "nope.json")) == {"seen_ids": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_history.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/history.py
from __future__ import annotations
import json
import os

def load_history(path) -> dict:
    if not os.path.exists(path):
        return {"seen_ids": []}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("seen_ids", [])
    return data

def save_history(path, hist) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(hist, fh, indent=2)

def drop_seen(items, hist) -> list:
    seen = set(hist.get("seen_ids", []))
    return [i for i in items if i.id not in seen]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_history.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add briefing/history.py tests/test_history.py
git commit -m "feat: history load/save + dedup"
```

---

## Task 11: Filter modes

**Files:**
- Create: `briefing/filter.py`
- Test: `tests/test_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filter.py
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from briefing.models import Item
from briefing.filter import apply_filter
from briefing.config import Config

def _items(n, source="s"):
    now = datetime.now(timezone.utc)
    return [Item.make(source=source, source_type="rss", title=f"T{i}",
                      url=f"http://x/{i}", summary=f"s{i}",
                      published=now - timedelta(minutes=i), id=str(i)) for i in range(n)]

def _cfg(mode, **kw):
    base = dict(title="t", filter_mode=mode, interests=["ai"], max_items=5,
                per_source_cap=2, recency_hours=24, sources=[])
    base.update(kw)
    return Config(**base)

def test_recent_caps_at_max_items():
    out = apply_filter(_items(10), _cfg("recent", max_items=5))
    assert len(out) == 5

def test_per_source_cap_limits_per_source():
    items = _items(3, "A") + _items(3, "B")
    out = apply_filter(items, _cfg("per_source_cap", per_source_cap=2, max_items=99))
    by = {}
    for i in out:
        by[i.source] = by.get(i.source, 0) + 1
    assert by == {"A": 2, "B": 2}

def test_interests_keeps_high_scored_only(monkeypatch):
    items = _items(3)
    # score item "0"=90, "1"=10, "2"=80
    scores = {"0": 90, "1": 10, "2": 80}
    with patch("briefing.filter._score_items", return_value=scores):
        out = apply_filter(items, _cfg("interests", max_items=5))
    assert {i.id for i in out} == {"0", "2"}  # >= 50 threshold
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_filter.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/filter.py
from __future__ import annotations
import os
import json
import re
import anthropic

SCORE_THRESHOLD = 50
MODEL = os.environ.get("BRIEFING_MODEL", "claude-sonnet-4-6")

def _client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def _score_items(items, interests) -> dict:
    catalogue = "\n".join(f"[{i.id}] {i.title} :: {i.summary[:200]}" for i in items)
    prompt = (
        f"Reader interests: {', '.join(interests)}.\n"
        "Score each item 0-100 for how well it matches the interests.\n"
        "Return ONLY JSON: {\"scores\": {\"<id>\": <int>}}.\n\n" + catalogue
    )
    msg = _client().messages.create(model=MODEL, max_tokens=1000,
        messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    text = re.sub(r"^```[a-z]*\n?|```$", "", text.strip(), flags=re.MULTILINE)
    return {str(k): int(v) for k, v in json.loads(text)["scores"].items()}

def _curate(items, interests) -> list:
    catalogue = "\n".join(f"[{i.id}] {i.title} :: {i.summary[:200]}" for i in items)
    steer = f"Reader leans toward: {', '.join(interests)}.\n" if interests else ""
    prompt = (steer + "Pick the genuinely most interesting/important items.\n"
              "Return ONLY JSON: {\"keep\": [\"<id>\", ...]}.\n\n" + catalogue)
    msg = _client().messages.create(model=MODEL, max_tokens=1000,
        messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    text = re.sub(r"^```[a-z]*\n?|```$", "", text.strip(), flags=re.MULTILINE)
    keep = set(str(x) for x in json.loads(text)["keep"])
    return [i for i in items if i.id in keep]

def apply_filter(items, cfg) -> list:
    mode = cfg.filter_mode
    if mode == "recent":
        ordered = sorted(items, key=lambda i: i.published, reverse=True)
        return ordered[:cfg.max_items]
    if mode == "per_source_cap":
        counts, out = {}, []
        for i in sorted(items, key=lambda i: i.published, reverse=True):
            if counts.get(i.source, 0) < cfg.per_source_cap:
                counts[i.source] = counts.get(i.source, 0) + 1
                out.append(i)
        return out[:cfg.max_items]
    if mode == "interests":
        scores = _score_items(items, cfg.interests)
        kept = [i for i in items if scores.get(i.id, 0) >= SCORE_THRESHOLD]
        kept.sort(key=lambda i: scores.get(i.id, 0), reverse=True)
        return kept[:cfg.max_items]
    if mode == "claude_curate":
        return _curate(items, cfg.interests)[:cfg.max_items]
    raise ValueError(f"unknown filter mode {mode}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_filter.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add briefing/filter.py tests/test_filter.py
git commit -m "feat: 4 filter modes (recent/per-source/interests/curate)"
```

---

## Task 12: Enrich (summaries + themes)

**Files:**
- Create: `briefing/enrich.py`
- Test: `tests/test_enrich.py`

Ported/adapted from `main.py` `group_into_themes` (now operates on `Item`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich.py
import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from briefing.models import Item
from briefing.enrich import group_into_themes

def _item(uid):
    return Item.make(source="s", source_type="rss", title=f"T{uid}",
                     url=f"http://x/{uid}", summary="sum", published=datetime.now(timezone.utc), id=uid)

def _client(payload):
    c = MagicMock(); block = MagicMock(); block.type = "text"; block.text = json.dumps(payload)
    msg = MagicMock(); msg.content = [block]; c.messages.create.return_value = msg
    return c

def test_group_into_themes_maps_indices():
    items = [_item("0"), _item("1")]
    payload = {"themes": [{"name": "Theme A", "emoji": "X", "indices": [0, 1]}]}
    with patch("briefing.enrich._client", return_value=_client(payload)):
        themes = group_into_themes(items)
    assert themes[0]["name"] == "Theme A"
    assert len(themes[0]["items"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_enrich.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/enrich.py
from __future__ import annotations
import os
import json
import re
import anthropic

MODEL = os.environ.get("BRIEFING_MODEL", "claude-sonnet-4-6")

def _client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def group_into_themes(items) -> list:
    """Cluster items into 3-4 magazine-style themes. Returns
    [{"name", "emoji", "items": [Item, ...]}]."""
    if not items:
        return []
    catalogue = "\n".join(
        f"[{idx}] {i.source} | {i.title} | {i.summary[:200]}"
        for idx, i in enumerate(items)
    )
    prompt = (
        "You are the editor of a witty daily briefing.\n"
        "Group the numbered items into 3-4 creative theme names. Every item "
        "belongs to exactly one theme. Return ONLY JSON, no fences:\n"
        '{"themes": [{"name": "Theme", "emoji": "X", "indices": [0,3]}]}\n\n'
        + catalogue
    )
    msg = _client().messages.create(model=MODEL, max_tokens=800,
        messages=[{"role": "user", "content": prompt}])
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    raw = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE)
    data = json.loads(raw)
    out = []
    for theme in data["themes"]:
        chosen = [items[i] for i in theme["indices"] if i < len(items)]
        if chosen:
            out.append({"name": theme["name"], "emoji": theme.get("emoji", "*"),
                        "items": chosen})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_enrich.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add briefing/enrich.py tests/test_enrich.py
git commit -m "feat: theme grouping over Item list (ported)"
```

---

## Task 13: Email render + send

**Files:**
- Create: `briefing/email.py`
- Test: `tests/test_email.py`

Adapted from `main.py` `build_html_email` / `send_email`; one generic card renderer keyed off `Item` (special-cases YouTube embeds).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_email.py
from datetime import datetime, timezone
from briefing.models import Item
from briefing.email import build_html_email

def _item(t, st="rss", extra=None):
    return Item.make(source="Src", source_type=st, title=t, url="http://x/1",
                     summary="a summary", published=datetime.now(timezone.utc), extra=extra or {})

def test_build_html_contains_title_and_cards():
    themes = [{"name": "Theme A", "emoji": "X", "items": [_item("Headline One")]}]
    html = build_html_email("Claire's Briefing", themes)
    assert "Claire's Briefing" in html
    assert "Theme A" in html
    assert "Headline One" in html
    assert "http://x/1" in html

def test_youtube_item_renders_embed():
    yt = _item("Vid", st="youtube", extra={"embed_url": "http://e/v1", "thumbnail": "http://t/1"})
    html = build_html_email("B", [{"name": "T", "emoji": "X", "items": [yt]}])
    assert "http://e/v1" in html or "http://t/1" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_email.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/email.py
from __future__ import annotations
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_CSS = (
    "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f5f5f7;margin:0}"
    ".wrapper{max-width:640px;margin:0 auto;padding:24px}"
    ".header h1{margin:0 0 4px}.date{color:#888;font-size:13px}"
    ".theme-title{font-size:18px;font-weight:700;margin:24px 0 8px}"
    ".card{background:#fff;border-radius:10px;padding:14px;margin:10px 0;"
    "box-shadow:0 1px 3px rgba(0,0,0,.08)}"
    ".card a{color:#1a1a1a;text-decoration:none;font-weight:600}"
    ".src{color:#999;font-size:12px}.footer{color:#aaa;font-size:12px;margin-top:24px}"
)

def _card(item) -> str:
    if item.source_type == "youtube":
        thumb = item.extra.get("thumbnail", "")
        media = f'<a href="{item.url}"><img src="{thumb}" width="100%" style="border-radius:8px"></a>'
    else:
        media = ""
    return (f'<div class="card"><div class="src">{item.source}</div>'
            f'<a href="{item.url}">{item.title}</a>'
            f'<p>{item.summary}</p>{media}</div>')

def build_html_email(title, themes) -> str:
    now = datetime.now(timezone.utc).strftime("%A, %B %d")
    blocks = ""
    for theme in themes:
        cards = "".join(_card(i) for i in theme["items"])
        blocks += f'<p class="theme-title">{theme["emoji"]} {theme["name"]}</p>{cards}'
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<style>{_CSS}</style></head><body><div class="wrapper">'
            f'<div class="header"><h1>{title}</h1><div class="date">{now}</div></div>'
            f'{blocks}<div class="footer">Curated by Claude</div></div></body></html>')

def send_email(title, html) -> None:
    sender = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_PASSWORD"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{title} - {datetime.now(timezone.utc).strftime('%b %d, %Y')}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(host, port) as server:
        server.ehlo(); server.starttls(); server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    print(f"[email] sent to {recipient}", flush=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_email.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add briefing/email.py tests/test_email.py
git commit -m "feat: HTML email render + SMTP send (adapted)"
```

---

## Task 14: Pipeline orchestrator

**Files:**
- Create: `briefing/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
from datetime import datetime, timezone
from unittest.mock import patch
from briefing.models import Item
from briefing.config import Config
from briefing.pipeline import run

def _cfg():
    return Config(title="B", filter_mode="recent", interests=[], max_items=5,
                  per_source_cap=2, recency_hours=24,
                  sources=[{"type": "rss", "name": "S", "url": "http://x"}])

def _item(uid):
    return Item.make(source="S", source_type="rss", title="T", url=f"http://x/{uid}",
                     summary="s", published=datetime.now(timezone.utc), id=uid)

def test_run_dedups_filters_and_sends(tmp_path):
    hist_path = str(tmp_path / "h.json")
    sent = {}
    with patch("briefing.pipeline.fetch_all", return_value=[_item("a"), _item("b")]), \
         patch("briefing.pipeline.load_history", return_value={"seen_ids": ["a"]}), \
         patch("briefing.pipeline.group_into_themes",
               side_effect=lambda items: [{"name": "T", "emoji": "X", "items": items}]), \
         patch("briefing.pipeline.send_email",
               side_effect=lambda title, html: sent.update(title=title, html=html)), \
         patch("briefing.pipeline.save_history") as save:
        run(_cfg(), history_path=hist_path)
    assert "b" in sent["html"] or "T" in sent["html"]  # fresh item themed + sent
    # history updated to include the newly-seen fresh id "b"
    saved = save.call_args[0][1]["seen_ids"]
    assert "b" in saved and "a" in saved

def test_run_no_fresh_items_skips_send(tmp_path):
    with patch("briefing.pipeline.fetch_all", return_value=[_item("a")]), \
         patch("briefing.pipeline.load_history", return_value={"seen_ids": ["a"]}), \
         patch("briefing.pipeline.send_email") as send, \
         patch("briefing.pipeline.save_history"):
        run(_cfg(), history_path=str(tmp_path / "h.json"))
    send.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# briefing/pipeline.py
from __future__ import annotations
from briefing.sources import fetch_all
from briefing.history import load_history, save_history, drop_seen
from briefing.filter import apply_filter
from briefing.enrich import group_into_themes
from briefing.email import build_html_email, send_email

def run(cfg, history_path="history.json") -> None:
    raw = fetch_all(cfg)
    print(f"[pipeline] fetched {len(raw)} items", flush=True)
    hist = load_history(history_path)
    fresh = drop_seen(raw, hist)
    print(f"[pipeline] {len(fresh)} fresh after dedup", flush=True)
    if not fresh:
        print("[pipeline] nothing new; skipping email", flush=True)
        return
    selected = apply_filter(fresh, cfg)
    print(f"[pipeline] {len(selected)} after filter ({cfg.filter_mode})", flush=True)
    themes = group_into_themes(selected)
    html = build_html_email(cfg.title, themes)
    send_email(cfg.title, html)
    hist["seen_ids"] = list({*hist.get("seen_ids", []), *(i.id for i in fresh)})
    save_history(history_path, hist)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_pipeline.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the FULL suite + commit**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all green.
```bash
git add briefing/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestrator (fetch->dedup->filter->theme->email)"
```

---

## Task 15: Entrypoint + GitHub Actions workflow

**Files:**
- Create: `main.py`, `.github/workflows/daily.yml`, `config.example.yaml`, `config.yaml`

- [ ] **Step 1: Create `main.py`**

```python
# main.py
from briefing.config import load_config
from briefing.pipeline import run

if __name__ == "__main__":
    cfg = load_config("config.yaml")
    run(cfg, history_path="history.json")
```

- [ ] **Step 2: Create `config.example.yaml` and copy to `config.yaml`**

```yaml
# config.example.yaml
briefing:
  title: "My Daily Briefing"

filter:
  mode: interests          # interests | recent | per_source_cap | claude_curate
  interests:
    - "AI policy in Europe"
    - "longevity research"
  max_items: 25
  per_source_cap: 5
  recency_hours: 24

sources:
  - { type: rss,  name: "BBC World", url: "http://feeds.bbci.co.uk/news/world/rss.xml" }
  - { type: site, name: "Seedcamp", module: "seedcamp" }
  # - { type: scrape, name: "Static Site", url: "https://example.com/news",
  #     item_selector: ".post", title_selector: "h2 a", link_selector: "h2 a" }
  # - { type: claude_fetch, name: "No-Feed Site", url: "https://example.com" }
  # - { type: youtube, name: "Veritasium", channel_id: "UCxxxx" }
```

```bash
cp config.example.yaml config.yaml
```

- [ ] **Step 3: Create `.github/workflows/daily.yml`**

```yaml
name: Daily Briefing
on:
  schedule:
    - cron: '0 7 * * *'   # 07:00 UTC daily
  workflow_dispatch:
jobs:
  run:
    runs-on: ubuntu-latest
    permissions:
      contents: write       # commit history.json back
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - name: Run briefing
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          EMAIL_SENDER:      ${{ secrets.EMAIL_SENDER }}
          EMAIL_PASSWORD:    ${{ secrets.EMAIL_PASSWORD }}
          EMAIL_RECIPIENT:   ${{ secrets.EMAIL_RECIPIENT }}
          SMTP_HOST:         ${{ secrets.SMTP_HOST }}
          SMTP_PORT:         ${{ secrets.SMTP_PORT }}
          YOUTUBE_API_KEY:   ${{ secrets.YOUTUBE_API_KEY }}
        run: python main.py
      - name: Commit history
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add history.json
          git diff --cached --quiet || git commit -m "chore: update history [skip ci]"
          git push
```

- [ ] **Step 4: Smoke-run locally against a 1-source config (network)**

Set env vars locally (PowerShell): `$env:ANTHROPIC_API_KEY=...` etc., then:
Run: `.venv/Scripts/python main.py`
Expected: logs `fetched N items` → `fresh ...` → either an email or `nothing new`. If no SMTP creds, expect it to fail at send only — fetch/filter/theme stages must log first.

- [ ] **Step 5: Commit**

```bash
git add main.py config.example.yaml config.yaml .github/workflows/daily.yml
git commit -m "feat: entrypoint, example config, daily Actions workflow"
```

---

## Task 16: README + CLAUDE.md

**Files:**
- Create: `README.md`, `CLAUDE.md`

- [ ] **Step 1: Write `README.md`**

Include these sections verbatim as the skeleton:
```markdown
# Daily Briefing

Turn a list of web/news/RSS sources into one filtered, themed email every morning.

## Quick start (your own copy)
1. Click **"Use this template"** → create your own **private** repo.
2. In your repo: **Settings → Secrets and variables → Actions → New repository secret**. Add:
   - `ANTHROPIC_API_KEY` (from console.anthropic.com — pay-as-you-go, ~cents/day)
   - `EMAIL_SENDER`, `EMAIL_PASSWORD` (Gmail: use an App Password), `EMAIL_RECIPIENT`
   - optional: `SMTP_HOST`, `SMTP_PORT`, `YOUTUBE_API_KEY`
3. Edit **`config.yaml`** — your sources + interests (or ask Claude to; see CLAUDE.md).
4. **Actions** tab → enable workflows → **Run workflow** to test.
5. It then runs daily at 07:00 UTC. Change the time in `.github/workflows/daily.yml`.

## Choosing a source type
- **RSS (easiest):** most sites have a feed. Try `https://SITE/feed` or `/rss`. One config line.
- **Bespoke `site` parser (most powerful):** copy `briefing/sources/sites/_example.py` to
  `<yoursite>.py`, edit the selectors, add `{ type: site, module: "<yoursite>" }`. See `seedcamp.py`.
- **`scrape` (quick, brittle):** config CSS selectors for a simple static page.
- **`claude_fetch` (zero effort, costs tokens):** Claude reads the page. Just a URL.

## Filter modes (`filter.mode`)
`recent` (no AI) · `per_source_cap` (no AI) · `interests` (Claude scores vs your list) ·
`claude_curate` (Claude free-picks). `max_items` caps the whole email.

## Cost
Free filters run first; only survivors reach Claude. A daily briefing is typically a few cents/day.
GitHub free private Actions minutes (~2,000/mo) easily cover a daily run.

## Run locally (testing)
`pip install -r requirements.txt`, set the env vars above, `python main.py`.
```

- [ ] **Step 2: Write `CLAUDE.md`**

```markdown
# CLAUDE.md — how to extend this repo

This is a daily-briefing generator. Sources are adapters that all return `briefing.models.Item`.
The pipeline (`briefing/pipeline.py`) is source-agnostic: fetch → dedup → filter → theme → email.

## Adding a source when asked (decision order)
1. **Has an RSS feed?** Add one line to `config.yaml`: `{ type: rss, name: "X", url: "<feed>" }`.
2. **No feed, real site?** Write a bespoke parser: copy `briefing/sources/sites/_example.py` to
   `briefing/sources/sites/<name>.py`, edit selectors so `fetch(cfg)` returns `list[Item]`, then add
   `{ type: site, name: "X", module: "<name>" }`. Mirror `seedcamp.py`. Add a fixture-based test in
   `tests/sources/sites/`.
3. **Trivial static page?** Use a `scrape` config line with `item_selector`/`title_selector`/`link_selector`.
4. **JS-gated / zero effort?** Use `{ type: claude_fetch, name: "X", url: "<page>" }`.

## Invariants
- Every adapter returns `list[Item]` and uses `briefing.sources._fetch.fetch` for HTTP (browser UA + retries).
- Adapters fail soft (the registry wraps them); raising on a real error is fine.
- Never put sources/interests in Secrets — only API keys + email creds. Config lives in `config.yaml`.
- Run `pytest -q` before committing.
```

- [ ] **Step 3: Run full suite (sanity) + commit**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all green.
```bash
git add README.md CLAUDE.md
git commit -m "docs: README setup guide + CLAUDE.md extension guide"
```

---

## Task 17: Push to GitHub

**Files:** none (publish)

- [ ] **Step 1: Push `main` to the private template repo**

```bash
git push -u origin main
```

- [ ] **Step 2: Verify the workflow is registered**

Run: `gh workflow list -R clairechabot/daily-briefing`
Expected: `Daily Briefing` appears.

- [ ] **Step 3: Confirm template flag still set**

Run: `gh repo view clairechabot/daily-briefing --json isTemplate`
Expected: `{"isTemplate": true}`.

- [ ] **Step 4: (Manual, by Claire) trigger a test run once Secrets are set**

Document for Claire: add the 4 required Secrets, then `gh workflow run "Daily Briefing" -R clairechabot/daily-briefing` and watch `gh run watch`.

---

## Self-review notes (coverage vs spec)

- Spec §6 Item → Task 1. §7 config → Task 2. §8 `_fetch` → Task 4; `rss` → 5; `sites/` bespoke → 6; `scrape` → 7; `claude_fetch` → 8; `youtube` → 6b; registry+fail-soft → 3, 9. §9 filter modes → 11. §10 enrich/email → 12, 13. §11 history → 10. §12 runtime/Actions → 15. §13 distribution + §16 caveats → README Task 16. §14 CLAUDE.md → 16. §15 deps → Task 0. §17 testing → tests in every task + full-suite gates in Tasks 14/16.
- Naming consistency: `fetch_all`, `apply_filter`, `group_into_themes`, `build_html_email(title, themes)`, `send_email(title, html)`, `run(cfg, history_path)`, `Item.make(...)`, history key `seen_ids` — used identically across tasks.
- Known follow-up (not blocking): `claude_fetch` web-fetch tool spec to be confirmed against the installed SDK via the `claude-api` skill at Task 8 Step 3 (test is mocked, so non-blocking).
```
