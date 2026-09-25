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

The same call clusters duplicate coverage: when several items report the same
event, one is kept as the lead (with the others in `extra["also"]`, an
event-level `extra["cluster_title"]` and the group's best tier) and the rest
are dropped from the returned list. Leads also carry `extra["rank"]`, their
place in Claude's ordering, so the reading order follows it across themes.

`triage(themes)` turns the labelled themes into what the renderers show: one
numbered reading order (Read first, then Read today) and everything else as a
skim list per section.

`context` is sent to Claude and the `why` lines appear in the email and web
edition, so keep it to what you're comfortable publishing if the repo or site
is public.
"""
from __future__ import annotations
import os
from briefing.llm import claude_json, make_client

TIERS = ("first", "today", "later")
DEFAULT_MINUTES = 3  # read time when the article couldn't be measured
LABELS = {"first": "Read first", "today": "Read today", "later": "Later"}
_RANK = {t: n for n, t in enumerate(TIERS)}


def _client():
    return make_client()


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
        "If two or more items report the very same event (one launch, deal or "
        "announcement, not merely the same topic), keep the one with the fullest coverage "
        'as the lead and give every other one "same_as": <lead index>. Give the lead '
        '"cluster_title": one plain headline for the whole event, at most 14 words, and '
        'write its "why" for the event as a whole.\n'
        "List every item, most important first. Return ONLY JSON:\n"
        '{"items": [{"i": <index>, "p": "first|today|later", "why": "...", '
        '"same_as": <index, only for duplicates>, "cluster_title": "..., only on a lead"}]}\n\n'
        + catalogue
    )


def _root(idx, same_as) -> int:
    """The lead `idx` is clustered under, following chains; a cycle means
    no cluster, so the item stays its own lead."""
    seen, cur = {idx}, idx
    while cur in same_as:
        cur = same_as[cur]
        if cur in seen:
            return idx
        seen.add(cur)
    return cur


def prioritize(items, cfg) -> list:
    """Label `items` in place (see module doc) and return the list without
    the duplicates folded into a cluster lead. No-op when disabled; returns
    the items unlabeled and unclustered if Claude's answer can't be used."""
    if not is_enabled(cfg) or not items:
        return items
    data = claude_json(_prompt(items, cfg), max_tokens=min(5000, 300 + 80 * len(items)),
                       context="priority", client_factory=lambda: _client())
    if data is None or not isinstance(data.get("items"), list):
        print("[priority] ranking failed; edition goes out unlabeled", flush=True)
        return items
    rows = {}  # index -> row, in Claude's order (most important first)
    for row in data["items"]:
        if not isinstance(row, dict):
            continue
        idx, tier = row.get("i"), row.get("p")
        if not isinstance(idx, int) or not 0 <= idx < len(items) or idx in rows:
            continue
        if tier not in TIERS:
            continue
        rows[idx] = row
    for n in range(len(items)):
        if n not in rows:  # Claude answered but skipped it: treat as low priority
            rows[n] = {"i": n, "p": "later"}
    pos = {idx: n for n, idx in enumerate(rows)}

    same_as = {}
    for idx, row in rows.items():
        target = row.get("same_as")
        if isinstance(target, int) and not isinstance(target, bool) \
                and 0 <= target < len(items) and target != idx:
            same_as[idx] = target
    groups = {}  # lead index -> [member indices], members in Claude's order
    for idx in rows:
        lead = _root(idx, same_as)
        if lead != idx:
            groups.setdefault(lead, []).append(idx)
    members = {m for ms in groups.values() for m in ms}

    leads = sorted((i for i in rows if i not in members),
                   key=lambda i: min([pos[i]] + [pos[m] for m in groups.get(i, [])]))
    max_first = int(cfg.get("max_first", 3))
    n_first = 0
    for n, idx in enumerate(leads):
        group = [idx] + groups.get(idx, [])
        tier = min((rows[g]["p"] for g in group), key=_RANK.get)  # the group's best tier
        if tier == "first":
            # Claude lists most important first, so the cap keeps the top ones.
            n_first += 1
            if n_first > max_first:
                tier = "today"
        item = items[idx]
        item.extra["priority"] = tier
        item.extra["rank"] = n
        why = next((str(rows[g].get("why") or "").strip() for g in group
                    if str(rows[g].get("why") or "").strip()), "")
        if tier != "later" and why:
            item.extra["why"] = why
        if len(group) > 1:
            item.extra["also"] = [items[m] for m in groups[idx]]
            title = next((str(rows[g].get("cluster_title") or "").strip() for g in group
                          if str(rows[g].get("cluster_title") or "").strip()), "")
            if title:
                item.extra["cluster_title"] = title
            item.extra["minutes"] = read_minutes(item) + 1
    kept = [i for n, i in enumerate(items) if n not in members]
    counts = {t: sum(1 for i in kept if i.extra.get("priority") == t) for t in TIERS}
    print(f"[priority] {counts}; {len(members)} duplicate(s) folded into "
          f"{len(groups)} cluster(s)", flush=True)
    return kept


def read_minutes(item) -> int:
    """Estimated read time in whole minutes (images.py measures the article)."""
    m = item.extra.get("minutes")
    return m if isinstance(m, int) and not isinstance(m, bool) and m >= 1 else DEFAULT_MINUTES


def display_title(item) -> str:
    """The event-level headline for a cluster lead, else the item's own title."""
    return item.extra.get("cluster_title") or item.title


def _order_key(item):
    return (rank(item), item.extra.get("rank", float("inf")))


def order_themes(themes) -> list:
    """Within each theme, put higher-priority items first, then Claude's rank (stable)."""
    for theme in themes:
        theme["items"] = sorted(theme["items"], key=_order_key)
    return themes


def reading_list(themes) -> list:
    """The day's "Read first" items, most important first."""
    return sorted((i for t in themes for i in t["items"] if i.extra.get("priority") == "first"),
                  key=_order_key)


def triage(themes) -> tuple:
    """(reading order, skim). The reading order is every Read first item, then
    every Read today item, in Claude's rank order. Without any labels the lead
    story stands in as the whole reading order. Skim is [(theme, items)] for
    everything else, in theme order, leaving out empty sections."""
    items = [i for t in themes for i in t["items"]]
    order = sorted((i for i in items if i.extra.get("priority") in ("first", "today")),
                   key=_order_key)
    if not order and items:
        order = [items[0]]
    shown = {id(i) for i in order}
    skim = [(t, [i for i in t["items"] if id(i) not in shown]) for t in themes]
    return order, [(t, its) for t, its in skim if its]


def all_items(themes) -> list:
    """Every story in the edition, cluster members included (for counts)."""
    return [x for t in themes for i in t["items"] for x in [i] + list(i.extra.get("also") or [])]
