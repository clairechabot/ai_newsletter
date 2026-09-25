import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from briefing.models import Item
from briefing.priority import triage, reading_list
from briefing.weekly import (weekly_day, is_weekly, skips_today, picks_wanted, week_candidates,
                             pick_week, weekly_themes, WEEKLY_LABEL)

FRI = datetime(2026, 9, 25, 6, 13)
SCHED = {"weekly_day": "friday", "skip_weekends": True}

def _row(day, title, p="first", **kw):
    return dict({"date": day, "title": title, "url": f"https://x/{title}", "source": "S",
                 "summary": "s", "p": p, "why": "w", "image": "", "n": 1}, **kw)

def _item(title, p=None, rank=0):
    extra = {"priority": p, "rank": rank} if p else {}
    return Item.make(source="Today", source_type="rss", title=title, url=f"https://t/{title}",
                     summary="s", published=datetime.now(timezone.utc), extra=extra)

def _client(payload):
    c = MagicMock(); block = MagicMock(); block.type = "text"
    block.text = payload if isinstance(payload, str) else json.dumps(payload)
    msg = MagicMock(); msg.content = [block]; c.messages.create.return_value = msg
    return c

def test_schedule_helpers():
    assert weekly_day(SCHED) == 4 and weekly_day({}) is None and weekly_day({"weekly_day": "funday"}) is None
    assert is_weekly(SCHED, FRI) and not is_weekly(SCHED, datetime(2026, 9, 24)) and not is_weekly({}, FRI)
    assert skips_today(SCHED, datetime(2026, 9, 26)) and skips_today(SCHED, datetime(2026, 9, 27))
    assert not skips_today(SCHED, FRI) and not skips_today({}, datetime(2026, 9, 26))
    assert picks_wanted({}) == 5 and picks_wanted({"weekly_picks": 3}) == 3 and picks_wanted({"weekly_picks": "x"}) == 5

def test_candidates_are_this_weeks_top_stories_plus_today():
    rows = [_row("2026-09-18", "Last week"), _row("2026-09-21", "Mon lead"),
            _row("2026-09-22", "Tue later", p="later"), _row("2026-09-23", "Wed today", p="today",
            also=[{"title": "Dup", "url": "https://d/1", "source": "Other"}], minutes=5, cluster="Wed event"),
            _row("2026-09-25", "Today's row"), _row("2026-09-24", "Thu lead", url="https://t/Fresh")]
    themes = [{"name": "T", "items": [_item("Fresh", "first"), _item("Meh", "later", 1)]}]
    cands = week_candidates(rows, themes, FRI)
    assert [c.title for c in cands] == ["Mon lead", "Wed today", "Thu lead"]  # Fresh = Thu's URL: kept once
    wed = cands[1]
    assert wed.extra["day"] == "2026-09-23" and wed.extra["minutes"] == 5
    assert wed.extra["cluster_title"] == "Wed event" and wed.extra["also"][0].source == "Other"
    assert week_candidates([], themes, FRI)[0].extra["day"] == "2026-09-25"

def test_pick_week_uses_claude_and_marks_picks():
    cands = week_candidates([_row("2026-09-21", "A"), _row("2026-09-22", "B", p="today"),
                             _row("2026-09-23", "C")], [], FRI)
    client = _client({"picks": [{"i": 2, "why": "Biggest."}, {"i": 0}, {"i": 2}, {"i": 9}],
                      "summary": [{"lead": "Big week", "text": "Things.", "ref": {"stories": [1, 5]}}]})
    with patch("briefing.weekly._client", return_value=client):
        picks, summary = pick_week(cands, 5, profile={"enabled": True, "org": "Khare", "context": "ctx"})
    assert [p.title for p in picks] == ["C", "A"]
    assert picks[0].extra["why"] == "Biggest." and picks[1].extra["why"] == "w"
    assert [p.extra["rank"] for p in picks] == [0, 1] and all(p.extra["priority"] == "first" for p in picks)
    assert picks[0].extra["day_label"] == "Wed" and picks[0].extra["minutes"] == 3
    assert summary == [{"lead": "Big week.", "text": "Things.", "short": "", "ref": {"stories": [1]}}]
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "the week in 5" in prompt and "team at Khare" in prompt and "[2] Wed | first | S | C" in prompt

def test_pick_week_falls_back_to_read_first_newest_first():
    cands = week_candidates([_row("2026-09-21", "Mon"), _row("2026-09-22", "Tue", p="today"),
                             _row("2026-09-23", "Wed")], [], FRI)
    with patch("briefing.weekly._client", return_value=_client("nope")):
        picks, summary = pick_week(cands, 2)
    assert [p.title for p in picks] == ["Wed", "Mon"] and summary == []
    assert pick_week([], 5) == ([], [])

def test_weekly_themes_pin_the_picks_as_the_reading_order():
    a, b, c = _item("A", "first"), _item("B", "today", 1), _item("C", "later", 2)
    old = _row("2026-09-22", "Old")
    picks, _ = (lambda cs: (cs, None))(week_candidates([old], [], FRI))
    picks = [picks[0], a]
    themes = weekly_themes(picks, [{"name": "T", "items": [a, b, c]}, {"name": "Empty", "items": [a]}])
    assert themes[0]["name"] == WEEKLY_LABEL and themes[0]["pinned"]
    order, skim = triage(themes)
    assert order == picks and [its for _, its in skim] == [[b, c]]  # b keeps its label but goes to skim
    assert reading_list(themes) == picks
