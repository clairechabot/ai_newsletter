# Daily Briefing Skeleton — Design Spec

**Date:** 2026-06-04
**Status:** Approved design, pre-implementation
**Author:** Claire C (with Claude)

## 1. Purpose

A **forkable, private template repository** that turns a list of web/news sources into a
filtered daily-briefing email. The owner invites people as read collaborators; each person
clicks "Use this template" to create their **own private repo**, adds their **own API key and
interests**, and gets their own personal briefing. Nobody shares secrets, config, or output.

This is a productization of the existing `smart-digest/main.py` (a working Reddit + YouTube
digest) into a clean, config-driven, give-it-away skeleton, restructured to follow the Ellipsis
`athena/scrapers/` source-adapter pattern.

## 2. Goals

- A non-coder customizes the whole briefing by editing **one file** (`config.yaml`) or by
  **asking Claude** to edit it.
- Adding a news source is **one config line**, not a code change (for RSS and Claude-fetch).
- All four filtering modes available and selectable in config.
- Faithful reuse of Ellipsis's non-RSS scraping technique (requests + BeautifulSoup + browser
  User-Agent + a shared retrying fetch helper).
- Runs unattended in the cloud with no machine of the user's own (GitHub Actions), billed to the
  recipient's own GitHub account + API key.
- Honest cost control: cheap filters run before any paid Claude call; a single hard item cap.

## 3. Non-goals

- Not a shared/team briefing (each person gets their own copy). 
- Not a Playwright/headless-browser scraper. JS-gated pages use the `claude_fetch` source type
  instead. (Mirrors Ellipsis: its 13 no-feed scrapers all use requests+bs4; Playwright is only
  in the gated DocSend/LinkedIn extractors, which are out of scope here.)
- No web UI, no database. State is a committed `history.json`.
- Reddit support is **dropped** (was in `smart-digest`); YouTube is kept as optional.

## 4. Architecture overview

Pipeline, source-agnostic after fetch (the key idea):

```
config.yaml ─▶ load ─▶ [sources/*] fetch ─▶ Item[] ─▶ dedup(history)
                                                         ─▶ filter (1 of 4 modes)
                                                         ─▶ enrich (Claude summaries)
                                                         ─▶ theme grouping (Claude)
                                                         ─▶ HTML email ─▶ send (SMTP)
                                                         ─▶ write back history.json
```

Every source adapter returns the **same `Item` shape**, so the pipeline never knows or cares
where an item came from. Adding a source type never touches the pipeline.

## 5. Repo layout

```
daily-briefing/
├── config.yaml                  ← the file users edit (sources, interests, filter mode)
├── main.py                      ← thin entrypoint: load config → run pipeline
├── briefing/
│   ├── __init__.py
│   ├── pipeline.py              orchestrates the run
│   ├── config.py                load + validate config.yaml
│   ├── models.py                the Item dataclass
│   ├── history.py               dedup persistence (history.json)
│   ├── filter.py                the 4 filter modes
│   ├── enrich.py                Claude summaries + theme grouping   (ported from main.py)
│   ├── email.py                 HTML email build + send             (ported from main.py)
│   └── sources/
│       ├── __init__.py          registry: config "type" → adapter
│       ├── base.py              the Source contract
│       ├── _fetch.py            shared hardened HTTP fetch (retries + browser UA + timeout)
│       ├── rss.py               general news + niche sites (feedparser)
│       ├── scrape.py            generic config-selector scraper (trivial static pages)
│       ├── claude_fetch.py      no-feed/JS sites (Claude web-fetch tool reads the page)
│       ├── youtube.py           optional (ported from main.py)
│       └── sites/               ← bespoke parser per site (the Ellipsis way, primary)
│           ├── __init__.py      auto-discovers each <site>.py module
│           ├── _example.py      annotated template to copy (contract + worked example)
│           └── seedcamp.py      one file per site: own selectors/logic → Item[]
├── .github/workflows/daily.yml  scheduled cron (adapt the existing one)
├── history.json                 dedup state (committed back by Actions)
├── requirements.txt
├── README.md                    setup walkthrough for a non-coder
└── CLAUDE.md                    lets Claude add sources for the user
```

## 6. The `Item` model (`briefing/models.py`)

```python
@dataclass
class Item:
    source: str        # display name, e.g. "BBC World"
    source_type: str   # "rss" | "site" | "scrape" | "claude_fetch" | "youtube"
    title: str
    url: str
    summary: str       # raw excerpt/description (pre-Claude)
    published: datetime # timezone-aware UTC
    id: str            # stable id for dedup (url-hash or native id)
    extra: dict        # source-specific (video duration, etc.)
```

## 7. Config schema (`config.yaml`)

```yaml
briefing:
  title: "Claire's Morning Briefing"

filter:
  mode: interests          # interests | recent | per_source_cap | claude_curate
  interests:               # used by interests + claude_curate (as steering)
    - "AI policy in Europe"
    - "longevity research"
  max_items: 25            # HARD cap on the whole email (cost + noise guardrail)
  per_source_cap: 5        # used by per_source_cap mode
  recency_hours: 24

sources:
  - { type: rss,    name: "BBC World", url: "http://feeds.bbci.co.uk/news/world/rss.xml" }
  - { type: site,   name: "Seedcamp", module: "seedcamp" }        # bespoke parser in sources/sites/seedcamp.py
  - { type: scrape, name: "Static Site", url: "https://example.com/news",
      item_selector: ".post", title_selector: "h2 a", link_selector: "h2 a",
      summary_selector: "p.excerpt" }            # summary_selector optional
  - { type: claude_fetch, name: "No-Feed JS Site", url: "https://example.com" }
  - { type: youtube, name: "Veritasium", channel_id: "UCxxxx" }   # optional
```

Config (sources + interests) lives in the committed file. **Only true secrets** live in GitHub
Secrets: `ANTHROPIC_API_KEY`, `EMAIL_SENDER`, `EMAIL_PASSWORD`, `EMAIL_RECIPIENT`,
`SMTP_HOST`/`SMTP_PORT` (optional), `YOUTUBE_API_KEY` (only if a youtube source is used).

## 8. Source adapters

All adapters implement `base.py`'s contract: `fetch(source_cfg) -> list[Item]`, and **fail soft**
— on any error they log and return `[]` so one dead source never kills the briefing (Ellipsis's
`try/except RequestException: log + return` pattern).

- **`_fetch.py`** — shared HTTP helper copied from Ellipsis `athena/scrapers/__init__.py`:
  `requests.request` with **3 retries, 5s backoff, 60s timeout, `raise_for_status()`**, and a
  browser `User-Agent` (`Mozilla/5.0 ... Chrome/120 Safari/537.36`). Used by `rss.py` and
  `scrape.py`.
- **`rss.py`** — `feedparser` over the feed URL; map entries → `Item`; respect `recency_hours`.
- **`sites/<site>.py` (the primary no-feed path)** — **one bespoke parser file per site**, the
  exact Ellipsis model (`athena/scrapers/seedcamp.py`). Each module exports
  `fetch(source_cfg) -> list[Item]`, uses the shared `_fetch` (browser UA + retries) +
  `BeautifulSoup`, and has full freedom for that site's quirks (pagination, custom selectors,
  sector/tag logic, date parsing). `sites/__init__.py` auto-discovers modules; `config.yaml`
  enables one via `{ type: site, module: "<name>" }`. `_example.py` is an annotated template to
  copy. This is the recommended path for the recipient (strong coder + Claude Max can write a new
  site parser in minutes). `seedcamp.py` ships as a real worked example, ported from Ellipsis.
- **`scrape.py` (convenience only)** — generic config-selector scraper for trivial static pages
  where a bespoke file is overkill: `_fetch(url, browser UA) → BeautifulSoup(...)` then
  `soup.select(item_selector)` + `select_one(title/link/summary_selector)`. Same technique as a
  `sites/` parser, just driven by config instead of code.
- **`claude_fetch.py`** — calls the Claude API with the **web-fetch tool**; Claude opens the page
  and returns headline/url/summary as structured output → `Item`. No selectors; survives
  redesigns. Costs a few tokens per site. Works inside GitHub Actions.
- **`youtube.py`** — ported from `main.py` (double-fetch, no-Shorts duration filter). Optional;
  only active if a `youtube` source is present and `YOUTUBE_API_KEY` is set.

## 9. Filter modes (`briefing/filter.py`)

Selected by `filter.mode`; all converge on the same `max_items` cap.

| Mode | Behavior | Claude cost |
|---|---|---|
| `recent` | dedup + last `recency_hours`, keep all | none |
| `per_source_cap` | newest `per_source_cap` per source | none |
| `interests` | Claude scores each item vs `interests`, keep top by score | cheap |
| `claude_curate` | Claude freely picks the most interesting, `interests` as soft steer | cheap |

**Cost discipline (Ellipsis "gate before you spend"):** dedup + recency run FIRST (free), so only
survivors reach any paid Claude call. `max_items` is a hard ceiling on what gets summarized/emailed.

## 10. Enrich + email (ported from `main.py`)

- **`enrich.py`** — Claude per-item summaries and `group_into_themes` (kept from `main.py`). The
  existing AI-likelihood reject logic is retained as an optional pre-filter for `scrape`/`rss`
  text if desired (configurable; off by default).
- **`email.py`** — `build_html_email` (collapsible themed cards) + `send_email` (SMTP), kept from
  `main.py`. Output stays free of em/en-dashes (matches Ellipsis house style; nice-to-have).

## 11. History / dedup (`briefing/history.py`)

Single committed `history.json` of seen item ids. Generalized from the current
`seen_reddit_ids/seen_youtube_ids` to one `seen_ids` list keyed by `Item.id`. The Actions workflow
commits it back after each run (the existing "Commit & push history" step).

## 12. Runtime

> **Claude compute = API key (decided).** The pipeline calls the Anthropic API with the
> `anthropic` SDK using `ANTHROPIC_API_KEY` (pay-as-you-go, ~cents/day). The recipient's Claude
> **Max** plan is for *building and extending* the repo (writing `sites/` parsers, talking to
> Claude), **not** for running it — so every runtime below uses the API key, including the Claude
> routine. (A Max-via-`claude`-CLI runtime was considered and rejected as unnecessary complexity
> for a negligible cost saving.)

- **Primary — GitHub Actions** (adapt existing `.github/workflows/daily.yml`): scheduled cron +
  `workflow_dispatch`, secrets injected as env, `contents: write` to commit `history.json` back.
  ~2,000 free private-repo minutes/month; a twice-daily run uses a small fraction.
- **Secondary — local run** (README): `pip install -r requirements.txt`, set env vars, `python
  main.py`. For testing or offline use; requires the user's machine to be awake.
- **Alternative — Claude scheduled routine** (README): for recipients who already use Claude Code,
  schedule `python main.py` as a routine. Heavier dependency (needs Claude Code + subscription),
  so documented as an alternative, not the default.

## 13. Distribution (private template)

1. Owner marks repo as a **Template** and invites each person as a **read collaborator**.
2. Recipient clicks **"Use this template"** → their own private repo (no history, no secrets carried).
3. Recipient adds Secrets: `ANTHROPIC_API_KEY`, `EMAIL_SENDER`, `EMAIL_PASSWORD`,
   `EMAIL_RECIPIENT` (+ optional SMTP / YouTube).
4. Recipient edits `config.yaml` (or asks Claude to).
5. Recipient enables Actions → "Run workflow" to test → it then runs on schedule.

Each recipient's runs are billed to their own GitHub account and Anthropic API key.

## 14. `CLAUDE.md` (the "add a source by talking to Claude" workflow)

Documents the `Item` contract, the source registry, and the decision order so a recipient can open
their repo in Claude and say "add The Economist":
1. Has an RSS feed? → add one `rss` config line (no code).
2. No feed → write a **bespoke `sources/sites/<site>.py`** by copying `_example.py` (the primary,
   most capable path) and add a `{ type: site, module: "<site>" }` line. Recommended for this
   recipient.
3. Trivial static page where a file is overkill → a `scrape` config line with selectors.
4. JS-gated / zero-effort → a `claude_fetch` line (Claude reads the page; uses tokens).

The recipient (strong coder + Claude Max) defaults to option 2 for real sites; options 3-4 are
shortcuts for trivial or throwaway sources.

## 15. Dependencies (`requirements.txt`)

```
pyyaml
feedparser
beautifulsoup4
requests
anthropic
google-api-python-client   # only needed if youtube sources used
isodate                    # youtube duration parsing
```
(`praw` removed — Reddit dropped.)

## 16. Risks / honest caveats (for the README)

- **Any scraper is brittle** — bespoke `sites/` parsers and `scrape` selectors both break on a
  site redesign. Mitigation: per-source soft fail (one dead site never kills the briefing) +
  per-source unit tests with a saved HTML fixture so a break is caught loudly. README tells users
  to try `rss` first, then a bespoke `sites/` parser, with `claude_fetch` as the redesign-proof
  (but token-costing) fallback.
- **Claude appears in up to 3 places** (`claude_fetch`, `interests`/`claude_curate`, summaries/
  theming). `max_items` + free pre-filters are the single guardrail against a surprise bill.
- **GitHub free private Actions minutes are finite** (~2,000/mo) — fine for daily use; stated.

## 17. Testing

- Unit: each adapter returns `Item[]` from a fixture (sample feed XML / HTML / mocked Claude); each
  fails soft to `[]` on error.
- Unit: each filter mode respects `max_items` and `recency_hours`.
- Unit: dedup excludes ids already in `history.json`.
- End-to-end: `python main.py` against a tiny 1-source config produces a non-empty HTML email
  (SMTP mocked) and updates `history.json`.

## 18. What is ported vs new

- **Ported from `main.py`:** Claude summaries, `group_into_themes`, `build_html_email`,
  `send_email`, YouTube double-fetch + no-Shorts logic, history persistence, the Actions workflow.
- **New:** `config.yaml` + loader, the `Item` model, the source registry + `base.py`, `_fetch.py`,
  `rss.py`, `scrape.py`, `claude_fetch.py`, the `sites/` bespoke-parser package (`__init__.py`
  auto-discovery + `_example.py` template + `seedcamp.py` worked example ported from Ellipsis),
  the 4-mode `filter.py`, `README.md`, `CLAUDE.md`.
- **Removed:** Reddit (`praw`, `fetch_reddit_posts`, `_fetch_op_comments`).
```
