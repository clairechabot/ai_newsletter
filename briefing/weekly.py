"""Week in 5 — the Friday edition: the five stories of the week that matter
most, picked from Monday–Thursday's reading orders (read back from the
archive) plus Friday's own news, with "The week in 30 seconds" on top.
Friday's other stories still run as the skim list.

Optional and off by default. Configure in `config.yaml`:

    schedule:
      weekly_day: friday     # this day's edition becomes the Week in 5
      weekly_picks: 5
      skip_weekends: true    # no edition on Saturday or Sunday

One Claude call picks the stories and writes the week's takeaways. If it
fails, the picks fall back to the week's Read first stories, newest first,
and the edition goes out without a summary.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from briefing.llm import claude_json, make_client
from briefing.models import Item
from briefing.priority import triage, display_title, read_minutes, _RANK
from briefing.summary import MAX_TAKEAWAYS, _clean, _reader

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEKLY_LABEL = "Week in 5"
WEEKLY_SLOT = "weekly"


def _client():
    return make_client()


def weekly_day(schedule) -> int | None:
    """Weekday index (Monday 0) of the weekly edition, or None when off."""
    day = str((schedule or {}).get("weekly_day") or "").strip().lower()
    return DAYS.index(day) if day in DAYS else None


def is_weekly(schedule, now) -> bool:
    return weekly_day(schedule) == now.weekday()


def skips_today(schedule, now) -> bool:
    """True on Saturday and Sunday when `schedule.skip_weekends` is on."""
    return bool((schedule or {}).get("skip_weekends")) and now.weekday() >= 5


def picks_wanted(schedule) -> int:
    try:
        return max(1, min(10, int((schedule or {}).get("weekly_picks", 5))))
    except (TypeError, ValueError):
        return 5


def _row_item(row) -> Item:
    """An archive row (web.py edition-data) back as an Item."""
    date = str(row.get("date") or "")
    try:
        published = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        published = datetime.now(timezone.utc)
    also = [Item.make(source=a.get("source", ""), source_type="rss", title=a.get("title", ""),
                      url=a.get("url", ""), summary="", published=published)
            for a in row.get("also") or [] if isinstance(a, dict) and a.get("url")]
    extra = {k: v for k, v in {
        "priority": row.get("p") or "", "why": row.get("why") or "",
        "image": row.get("image") or "", "topic": row.get("topic") or "",
        "cluster_title": row.get("cluster") or "", "also": also,
        "minutes": row.get("minutes") if isinstance(row.get("minutes"), int) else None,
    }.items() if v}
    extra["day"] = date
    return Item.make(source=row.get("source", ""), source_type="rss", title=row.get("title", ""),
                     url=row.get("url", ""), summary=row.get("summary") or "",
                     published=published, extra=extra)


def week_candidates(rows, themes, now) -> list:
    """This week's Read first / Read today stories: archive rows dated Monday
    up to yesterday, then today's reading order. Duplicate URLs keep the first."""
    today = now.strftime("%Y-%m-%d")
    monday = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    out, seen = [], set()
    past = [r for r in rows if monday <= str(r.get("date", "")) < today
            and r.get("p") in ("first", "today") and r.get("url")]
    past.sort(key=lambda r: (r["date"], _RANK.get(r["p"], 9), r.get("n") or 99))
    order, _ = triage(themes)
    fresh = [i for i in order if i.extra.get("priority") in ("first", "today")]
    for item in fresh:
        item.extra.setdefault("day", today)
    for item in [_row_item(r) for r in past] + fresh:
        key = item.url.split("#")[0].rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _day_name(iso) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%a")
    except ValueError:
        return ""


def _prompt(candidates, n, profile) -> str:
    rows = "\n".join(
        f"[{k}] {_day_name(i.extra.get('day', ''))} | {i.extra.get('priority', '')} | {i.source} | "
        f"{display_title(i)} | {(i.extra.get('why') or i.summary or '')[:200]}"
        for k, i in enumerate(candidates))
    return (
        "You edit the Friday edition of a daily AI briefing: the week in "
        f"{n}.\n" + _reader(profile)
        + f"From this week's most important stories, pick the {n} that matter most looking "
        "back over the whole week, most important first. Prefer lasting significance over "
        "the day's noise; pick at most one story per event.\n"
        'For each pick give "why": one plain sentence, at most 22 words, on why it matters '
        "this week. Then give exactly "
        f'{MAX_TAKEAWAYS} takeaways about the week: "lead" (2-3 words ending with a period), '
        '"text" (at most 25 words, concrete, names companies and numbers, no hype), "short" '
        '(the same in at most 10 words) and "ref": {"stories": [<pick numbers, 1-based>]}.\n'
        "Return ONLY JSON:\n"
        '{"picks": [{"i": <index>, "why": "..."}], "summary": [{"lead": "...", "text": "...", '
        '"short": "...", "ref": {"stories": [1]}}]}\n\n' + rows)


def _fallback(candidates, n) -> list:
    """Read first before Read today; within a tier, the newest day first."""
    newest = sorted(candidates, key=lambda i: i.extra.get("day", ""), reverse=True)
    return sorted(newest, key=lambda i: _RANK.get(i.extra.get("priority"), 9))[:n]


def pick_week(candidates, n, profile=None) -> tuple:
    """(picks, summary). Picks are Items with `extra["rank"]` set; summary is
    summary.py's shape with story refs into the picks, or [] on failure."""
    if not candidates:
        return [], []
    data = claude_json(_prompt(candidates, n, profile), max_tokens=1500, context="weekly",
                       client_factory=lambda: _client())
    picks, seen = [], set()
    for row in (data or {}).get("picks") or []:
        if not isinstance(row, dict):
            continue
        idx = row.get("i")
        if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(candidates) \
                and idx not in seen:
            seen.add(idx)
            item = candidates[idx]
            why = _clean(row.get("why"), 240)
            if why:
                item.extra["why"] = why
            picks.append(item)
        if len(picks) == n:
            break
    summary = []
    if picks:
        for row in (data or {}).get("summary") or []:
            if not isinstance(row, dict):
                continue
            lead, text = _clean(row.get("lead"), 40), _clean(row.get("text"), 280)
            if not lead or not text:
                continue
            if lead[-1] not in ".!?":
                lead += "."
            stories = (row.get("ref") or {}).get("stories") if isinstance(row.get("ref"), dict) else None
            nums = sorted({s for s in stories or [] if isinstance(s, int)
                           and not isinstance(s, bool) and 1 <= s <= len(picks)})
            summary.append({"lead": lead, "text": text, "short": _clean(row.get("short"), 90),
                            "ref": {"stories": nums} if nums else None})
            if len(summary) == MAX_TAKEAWAYS:
                break
    else:
        print("[weekly] picking failed; using the week's Read first stories", flush=True)
        picks = _fallback(candidates, n)
    for k, item in enumerate(picks):
        item.extra["priority"] = "first"
        item.extra["rank"] = k
        item.extra["minutes"] = read_minutes(item)
        item.extra["day_label"] = _day_name(item.extra.get("day", ""))
        item.extra["weekly_pick"] = True  # renderers drop the (redundant) Read first badge
    print(f"[weekly] {len(picks)} picks from {len(candidates)} candidates", flush=True)
    return picks, summary


def weekly_themes(picks, themes) -> list:
    """The Friday edition's themes: a pinned "Week in 5" section holding the
    picks (triage uses it as the whole reading order), then today's sections
    without any story that was picked."""
    picked = {id(i) for i in picks}
    rest = [dict(t, items=[i for i in t["items"] if id(i) not in picked]) for t in themes]
    return [{"name": WEEKLY_LABEL, "tab": WEEKLY_LABEL, "emoji": "*", "pinned": True,
             "items": list(picks)}] + [t for t in rest if t["items"]]
