from __future__ import annotations
import json
import os
from briefing.models import legacy_url_id, title_key

def load_history(path) -> dict:
    if not os.path.exists(path):
        return {"seen_ids": []}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("history is not a JSON object")
    except (OSError, ValueError) as e:  # JSONDecodeError is a ValueError
        # A corrupt history (bad merge, truncated write) must not stop the
        # edition; worst case a few items repeat once.
        print(f"::warning::history {path} unreadable ({e}); starting fresh", flush=True)
        return {"seen_ids": []}
    data.setdefault("seen_ids", [])
    return data

def save_history(path, hist) -> None:
    # Write-then-rename so a crash mid-write can't leave a truncated file.
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(hist, fh, indent=2)
    os.replace(tmp, path)

def _title_mark(item) -> str:
    key = title_key(item.title)
    return f"title::{key}" if key else ""

def drop_seen(items, hist) -> list:
    """Drop items already sent (by id, legacy raw-URL id, or title fingerprint)
    and collapse duplicates within this batch (same story from two feeds)."""
    seen = set(hist.get("seen_ids", []))
    out = []
    for i in items:
        marks = {i.id, legacy_url_id(i.url)}
        tm = _title_mark(i)
        if tm:
            marks.add(tm)
        if marks & seen:
            continue
        seen |= marks
        out.append(i)
    return out

def mark_seen(hist, items) -> dict:
    """Record items (ids + title fingerprints) as sent."""
    marks = set(hist.get("seen_ids", []))
    for i in items:
        marks.add(i.id)
        tm = _title_mark(i)
        if tm:
            marks.add(tm)
    hist["seen_ids"] = sorted(marks)
    return hist

RECENT_ORDER_DAYS = 2  # how many past editions' reading orders count as "already covered"

def recent_titles(hist, today) -> list:
    """Headlines from the reading order of the last RECENT_ORDER_DAYS dates
    before `today` (ISO date), newest first: what readers were already told
    to read, so a follow-up can be recognised as one."""
    rows = [r for r in hist.get("recent_order") or []
            if isinstance(r, dict) and r.get("title") and str(r.get("date", "")) < today]
    dates = sorted({r["date"] for r in rows}, reverse=True)[:RECENT_ORDER_DAYS]
    return [r["title"] for d in dates for r in rows if r["date"] == d]

def remember_order(hist, titles, today) -> dict:
    """Record today's reading-order headlines, replacing an earlier run of the
    same date, and keep only the last few dates."""
    rows = [r for r in hist.get("recent_order") or []
            if isinstance(r, dict) and r.get("date") != today]
    rows += [{"date": today, "title": t} for t in titles if t]
    dates = sorted({r["date"] for r in rows}, reverse=True)[:RECENT_ORDER_DAYS + 1]
    hist["recent_order"] = [r for r in rows if r["date"] in dates]
    return hist
