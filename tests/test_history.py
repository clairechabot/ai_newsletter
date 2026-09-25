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

def test_load_corrupt_file_starts_fresh(tmp_path):
    p = tmp_path / "h.json"
    p.write_text("<<<<<<< HEAD\n{not json")
    assert load_history(str(p)) == {"seen_ids": []}

def test_load_non_object_starts_fresh(tmp_path):
    p = tmp_path / "h.json"
    p.write_text("[1, 2]")
    assert load_history(str(p)) == {"seen_ids": []}

def test_save_leaves_no_temp_file(tmp_path):
    p = tmp_path / "h.json"
    save_history(str(p), {"seen_ids": []})
    assert [f.name for f in tmp_path.iterdir()] == ["h.json"]

from briefing.history import mark_seen
from briefing.models import legacy_url_id

def _titled(url, title):
    return Item.make(source="s", source_type="rss", title=title, url=url,
                     summary="", published=datetime.now(timezone.utc))

def test_drop_seen_collapses_same_story_within_batch():
    a = _titled("https://a.com/story?utm_source=rss", "Europe passes the AI Act today")
    b = _titled("https://b.com/other", "Europe passes the AI Act today!")
    c = _titled("https://www.a.com/story/", "Different headline for same link")
    assert drop_seen([a, b, c], {"seen_ids": []}) == [a]

def test_drop_seen_honours_legacy_ids_and_title_marks():
    old = _titled("http://x/1", "A long enough headline here")
    assert drop_seen([old], {"seen_ids": [legacy_url_id("http://x/1")]}) == []
    hist = mark_seen({"seen_ids": []}, [old])
    repost = _titled("http://elsewhere/2", "A long enough headline here")
    assert drop_seen([repost], hist) == []

def test_recent_order_keeps_two_past_days_and_replaces_reruns():
    from briefing.history import recent_titles, remember_order
    hist = {}
    remember_order(hist, ["Mon A", "Mon B"], "2026-09-21")
    remember_order(hist, ["Tue A"], "2026-09-22")
    remember_order(hist, ["Wed old"], "2026-09-23")
    remember_order(hist, ["Wed A", ""], "2026-09-23")      # a rerun replaces the day
    assert recent_titles(hist, "2026-09-24") == ["Wed A", "Tue A"]
    assert recent_titles(hist, "2026-09-23") == ["Tue A", "Mon A", "Mon B"]
    remember_order(hist, ["Thu A"], "2026-09-24")
    assert {r["date"] for r in hist["recent_order"]} == {"2026-09-22", "2026-09-23", "2026-09-24"}
    assert recent_titles({}, "2026-09-24") == [] and recent_titles({"recent_order": ["junk"]}, "x") == []
