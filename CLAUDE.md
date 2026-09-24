# CLAUDE.md - how to extend this repo

This is a daily-briefing generator. Sources are adapters that all return `briefing.models.Item`.
The pipeline (`briefing/pipeline.py`) is source-agnostic: fetch -> dedup -> filter -> theme ->
render (email + optional web edition).

## Optional features (all off by default, config-driven)
- **email.mode** (`email.py`): `full` emails everything; `cover` emails a short cover + TOC that
  links to the web edition. `EMAIL_RECIPIENT` may be a comma-separated list (each reader gets
  their own message). `email.subject: top_pick` puts the lead headline in the subject line;
  `email.from_name` sets the inbox sender name.
- **priority** (`priority.py`): one Claude call after filtering labels each item `first` /
  `today` / `later` (in `item.extra["priority"]`, plus `extra["why"]`) against a company profile
  in `priority.context`; themes are re-sorted by it and both renderers show badges and a
  "Read first today" list. Fails soft to unlabeled items.
- **palette** (`theme.py`): every colour the email and web edition use lives in `PALETTE`; CSS in
  `email.py` / `web.py` references `$name` placeholders filled by `theme.css()`.
- **voice** (`voice.py`): an editor persona that writes the daily greeting and steers theme names.
  Always fails soft (no greeting on any error / when disabled). Recent greetings are kept in
  `history.json` (`recent_greetings`) and fed back as an avoid-list for variety.
- **web** (`web.py`): builds a browsable `docs/index.html`, a permanent `docs/editions/<date>-<slot>.html`,
  and rebuilds `docs/archive.html`. Served by GitHub Pages (`/docs`) or pushed to a separate repo.
- **editions** (`editions.py`): AM/PM editions chosen by local hour; match the cron in `daily.yml`.

## Adding a source when asked (decision order)
1. **Has an RSS feed?** Add one line to `config.yaml`: `{ type: rss, name: "X", url: "<feed>" }`.
   If the publisher 403s datacenter IPs (Cloudflare), add `proxy: true` to route through a relay.
2. **No feed, real site?** Write a bespoke parser: copy `briefing/sources/sites/_example.py` to
   `briefing/sources/sites/<name>.py`, edit selectors so `fetch(cfg)` returns `list[Item]`, then add
   `{ type: site, name: "X", module: "<name>" }`. Mirror `seedcamp.py`. Add a fixture-based test in
   `tests/sources/sites/`. The HTTP helper is imported as `http_get` so tests can patch it.
3. **Trivial static page?** Use a `scrape` config line with `item_selector` / `title_selector` /
   `link_selector` (and optional `summary_selector`).
4. **JS-gated / zero effort?** Use `{ type: claude_fetch, name: "X", url: "<page>" }`. Links Claude
   returns are checked against the page's real `<a href>`s when the page is readable.

Dedup: item ids are sha1 of the *normalised* URL (`models.normalize_url`: no www, fragment,
tracking params); `history.drop_seen` also matches a title fingerprint so the same story from two
feeds only runs once.

## Invariants
- Every adapter returns `list[Item]` and uses `briefing.sources._fetch.fetch` for HTTP (browser UA +
  retries). Use `fetch_with_fallback` for bot-blocked publishers (relay retry on 403/429/etc).
- Adapters fail soft (the registry wraps each in `safe_fetch`); raising on a real error is fine.
- LLM steps that return JSON go through `briefing.llm.claude_json` (retries once, returns None,
  never raises); callers must have a non-LLM fallback so a Claude outage never skips an edition.
- Optional features stay optional: new config keys must default to off so a minimal config still works.
- Never put sources/interests in Secrets - only API keys + email creds. Config lives in `config.yaml`.
- Render/voice helpers (`web.py`, `voice.py`) take no network at import and escape all user/source text.
- Run `./.venv/Scripts/python.exe -m pytest -q` (or `pytest -q`) before committing.
