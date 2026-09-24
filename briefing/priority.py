"""Reading priority — label each selected item by how important it is for the
reader to read *today*, judged against a short profile of who they are.

Optional and off by default. Configure in `config.yaml`:

    priority:
      enabled: true
      org: "Your company"      # who "us" is in the labels' reasoning
      max_first: 3             # cap on "Read first" so the label stays meaningful
      context: |               # what you do, who you sell to, who you compete with
        ...

Each item gets `extra["priority"]` in TIERS ("first", "today", "later") and,
for the top two tiers, `extra["why"]`: one line on what it means for `org`.
One Claude call per edition; on any failure the items are returned unlabeled
and the edition renders exactly as it would with priority off.

`context` is sent to Claude and the `why` lines appear in the email and web
edition, so keep it to what you're comfortable publishing if the repo or site
is public.
"""
from __future__ import annotations
import os
import anthropic
from briefing.llm import claude_json

TIERS = ("first", "today", "later")
LABELS = {"first": "Read first", "today": "Read today", "later": "Later"}
_RANK = {t: n for n, t in enumerate(TIERS)}


def _client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def is_enabled(cfg) -> bool:
    return bool(cfg) and bool(cfg.get("enabled")) and bool((cfg.get("context") or "").strip())


def rank(item) -> int:
    """Sort key: first < today < later < unlabeled."""
    return _RANK.get(item.extra.get("priority"), len(TIERS))


def _prompt(items, cfg) -> str:
    org = cfg.get("org") or "the reader's company"
    max_first = int(cfg.get("max_first", 3))
    catalogue = "\n".join(f"[{n}] {i.source} | {i.title} | {i.summary[:300]}"
                          for n, i in enumerate(items))
    return (
        f"You triage the daily reading list for the team at {org}.\n\n"
        f"About {org}:\n{cfg['context'].strip()}\n\n"
        "For each numbered item, decide how important it is for them to read TODAY:\n"
        f'- "first": directly affects {org}: a competitor or comparable product, their '
        "buyers or market segment, their product category, or regulation, funding or "
        "security news that changes what they should do this quarter.\n"
        '- "today": useful soon: a technique they could apply to the product, or a '
        "meaningful shift in their market or in AI capabilities they build on.\n"
        '- "later": general context; fine to skip today.\n'
        f'Be strict: at most {max_first} items are "first", and most items are "later". '
        f'For "first" and "today" items add "why": one plain sentence, at most 20 words, '
        f"on what it means for {org} specifically. Do not restate the headline or hype it.\n"
        "List every item, most important first. Return ONLY JSON:\n"
        '{"items": [{"i": <index>, "p": "first|today|later", "why": "..."}]}\n\n'
        + catalogue
    )


def prioritize(items, cfg) -> list:
    """Label `items` in place (see module doc) and return them. No-op when
    disabled; leaves items unlabeled if Claude's answer can't be used."""
    if not is_enabled(cfg) or not items:
        return items
    data = claude_json(_prompt(items, cfg), max_tokens=min(4000, 300 + 60 * len(items)),
                       context="priority", client_factory=lambda: _client())
    if data is None or not isinstance(data.get("items"), list):
        print("[priority] ranking failed; edition goes out unlabeled", flush=True)
        return items
    max_first = int(cfg.get("max_first", 3))
    seen, n_first = set(), 0
    for row in data["items"]:
        if not isinstance(row, dict):
            continue
        idx, tier = row.get("i"), row.get("p")
        if not isinstance(idx, int) or not 0 <= idx < len(items) or idx in seen:
            continue
        if tier not in TIERS:
            continue
        seen.add(idx)
        if tier == "first":
            # Claude lists most important first, so the cap keeps the top ones.
            n_first += 1
            if n_first > max_first:
                tier = "today"
        item = items[idx]
        item.extra["priority"] = tier
        why = str(row.get("why") or "").strip()
        if tier != "later" and why:
            item.extra["why"] = why
    for n, item in enumerate(items):
        if n not in seen:  # Claude answered but skipped it: treat as low priority
            item.extra["priority"] = "later"
    counts = {t: sum(1 for i in items if i.extra.get("priority") == t) for t in TIERS}
    print(f"[priority] {counts}", flush=True)
    return items


def order_themes(themes) -> list:
    """Within each theme, put higher-priority items first (stable)."""
    for theme in themes:
        theme["items"] = sorted(theme["items"], key=rank)
    return themes


def reading_list(themes) -> list:
    """The day's "Read first" items, in theme order."""
    return [i for t in themes for i in t["items"] if i.extra.get("priority") == "first"]
