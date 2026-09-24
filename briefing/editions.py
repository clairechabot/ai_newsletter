"""Editions: which named edition (e.g. Morning / Evening) is running now.

A briefing can ship more than once a day. `config.yaml` lists editions in
chronological order, each with an `until_hour` boundary:

    editions:
      - { key: morning, label: "Morning Edition", until_hour: 12 }
      - { key: evening, label: "Evening Edition" }   # no boundary = catch-all

`pick_edition` chooses the first edition whose `until_hour` is still ahead of
the current local hour (the last edition is the implicit catch-all). With no
editions configured it returns a single unnamed "daily" edition, so the rest
of the pipeline never has to special-case the simple setup.

Everything here is pure (hour in, dict out) so it is trivially testable.
"""
from __future__ import annotations

DAILY = {"key": "daily", "label": ""}


def pick_edition(editions, hour) -> dict:
    """Return {"key", "label"} for the edition covering `hour` (0-23)."""
    if not editions:
        return dict(DAILY)
    for ed in editions:
        until = ed.get("until_hour")
        if until is None or hour < int(until):
            return {"key": ed.get("key", "edition"), "label": ed.get("label", "")}
    last = editions[-1]
    return {"key": last.get("key", "edition"), "label": last.get("label", "")}


def edition_filename(date_str, slot_key) -> str:
    """Permanent archive filename for an edition, e.g. 2026-06-29-morning.html."""
    return f"{date_str}-{slot_key}.html"
