"""Day summary — "The day in 30 seconds": three takeaways about the day's
biggest developments, each pointing at the story or section that backs it.

Optional and off by default. Enable in `config.yaml`:

    summary: { enabled: true }

One Claude call after priority and theming. Returns a list of
`{"lead": "Price war.", "text": "...", "short": "...", "ref": {...} | None}`
where `short` is the same point in at most 10 words (the cover email's inbox
preview) and `ref` is
`{"stories": [1, 2]}` (numbers in the reading order, 1-based) or
`{"section": 2}` (index into the skim sections). On any failure it returns
[] and the renderers leave the section out.
"""
from __future__ import annotations
from briefing.llm import claude_json, make_client
from briefing.priority import triage, display_title

MAX_TAKEAWAYS = 3


def _client():
    return make_client()


def is_enabled(cfg) -> bool:
    return bool(cfg) and bool(cfg.get("enabled"))


def _prompt(order, skim) -> str:
    stories = "\n".join(
        f"Story {n}: {i.source} | {display_title(i)} | {(i.summary or '')[:300]}"
        + (f" (also covered by {', '.join(a.source for a in i.extra.get('also') or [])})"
           if i.extra.get("also") else "")
        for n, i in enumerate(order, 1))
    sections = "\n".join(
        f'Section "{theme.get("tab") or theme["name"]}":\n'
        + "\n".join(f"- {i.source} | {i.title} | {(i.summary or '')[:160]}" for i in its)
        for theme, its in skim)
    return (
        "You write the top of a daily AI briefing: the day in 30 seconds.\n"
        f"Give exactly {MAX_TAKEAWAYS} takeaways about the day's biggest developments.\n"
        '- "lead": 2 or 3 words ending with a period, e.g. "Price war."\n'
        '- "text": at most 25 words. Concrete: name the companies and the numbers. '
        "No hype, no adjectives like groundbreaking.\n"
        '- "short": the same point in at most 10 words, for an inbox preview line.\n'
        '- "ref": what backs it up: {"stories": [<story numbers>]} for numbered stories, '
        'or {"section": "<section name exactly as given>"} for a section.\n'
        "Prefer the numbered stories; use a section when the takeaway sums one up.\n"
        "Return ONLY JSON:\n"
        '{"summary": [{"lead": "...", "text": "...", "short": "...", "ref": {"stories": [1]}}]}\n\n'
        f"Numbered stories (the reading order):\n{stories or '(none)'}\n\n"
        f"Other sections:\n{sections or '(none)'}"
    )


def _ref(raw, n_order, section_names) -> dict | None:
    if not isinstance(raw, dict):
        return None
    stories = raw.get("stories", raw.get("story"))
    if isinstance(stories, int) and not isinstance(stories, bool):
        stories = [stories]
    if isinstance(stories, list):
        nums = []
        for s in stories:
            if isinstance(s, int) and not isinstance(s, bool) and 1 <= s <= n_order and s not in nums:
                nums.append(s)
        if nums:
            return {"stories": sorted(nums)}
    name = raw.get("section")
    if isinstance(name, str):
        key = name.strip().lower()
        for n, section in enumerate(section_names):
            if section.lower() == key:
                return {"section": n}
    return None


def _clean(text, limit) -> str:
    return " ".join(str(text or "").split())[:limit]


def summarize(themes, cfg) -> list:
    """The day's takeaways (see module doc), or [] when off or on failure."""
    if not is_enabled(cfg):
        return []
    order, skim = triage(themes)
    if not order and not skim:
        return []
    data = claude_json(_prompt(order, skim), max_tokens=900, context="summary",
                       client_factory=lambda: _client())
    rows = data.get("summary") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        print("[summary] no summary; edition goes out without one", flush=True)
        return []
    names = [t.get("tab") or t["name"] for t, _ in skim]
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        lead, text = _clean(row.get("lead"), 40), _clean(row.get("text"), 280)
        if not lead or not text:
            continue
        if lead[-1] not in ".!?":
            lead += "."
        out.append({"lead": lead, "text": text, "short": _clean(row.get("short"), 90),
                    "ref": _ref(row.get("ref"), len(order), names)})
        if len(out) == MAX_TAKEAWAYS:
            break
    print(f"[summary] {len(out)} takeaway(s)", flush=True)
    return out


def ref_target(ref, skim_names) -> tuple:
    """(link text, anchor id) for a takeaway's `ref`, or ("", "") without one.
    Anchors match the web edition: order-<n> (0-based) and skim-<n>."""
    if not isinstance(ref, dict):
        return "", ""
    stories = ref.get("stories")
    if stories:
        if len(stories) == 1:
            label = f"Story {stories[0]}"
        else:
            label = ("Stories " + ", ".join(str(s) for s in stories[:-1])
                     + f" and {stories[-1]}")
        return label, f"order-{stories[0] - 1}"
    section = ref.get("section")
    if isinstance(section, int) and 0 <= section < len(skim_names):
        return f"Skim: {skim_names[section]}", f"skim-{section}"
    return "", ""
