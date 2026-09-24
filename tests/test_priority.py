import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from briefing.models import Item
from briefing.priority import prioritize, order_themes, reading_list, is_enabled, rank

CFG = {"enabled": True, "org": "Khare", "max_first": 2,
       "context": "Khare builds AI screening for private capital."}

def _item(uid, title=None):
    return Item.make(source="S", source_type="rss", title=title or f"T{uid}",
                     url=f"http://x/{uid}", summary="s", published=datetime.now(timezone.utc))

def _client(payload):
    c = MagicMock(); block = MagicMock(); block.type = "text"
    block.text = payload if isinstance(payload, str) else json.dumps(payload)
    msg = MagicMock(); msg.content = [block]; c.messages.create.return_value = msg
    return c

def _run(items, payload, cfg=CFG):
    client = _client(payload)
    with patch("briefing.priority._client", return_value=client):
        prioritize(items, cfg)
    return client

def test_disabled_or_no_context_makes_no_call():
    assert not is_enabled({}) and not is_enabled({"enabled": True, "context": "  "})
    items = [_item(0)]
    with patch("briefing.priority._client") as c:
        prioritize(items, {"enabled": False, "context": "x"})
    c.assert_not_called()
    assert "priority" not in items[0].extra

def test_labels_and_why_applied():
    items = [_item(0), _item(1), _item(2)]
    _run(items, {"items": [
        {"i": 1, "p": "first", "why": "Hebbia moves down-market into our lane."},
        {"i": 0, "p": "today", "why": "Eval technique we could use."},
        {"i": 2, "p": "later", "why": "ignored for later"}]})
    assert [i.extra["priority"] for i in items] == ["today", "first", "later"]
    assert items[1].extra["why"].startswith("Hebbia")
    assert "why" not in items[2].extra  # no reason shown for "later"

def test_first_is_capped_in_claude_order():
    items = [_item(n) for n in range(4)]
    _run(items, {"items": [{"i": 3, "p": "first", "why": "a"}, {"i": 0, "p": "first", "why": "b"},
                           {"i": 1, "p": "first", "why": "c"}, {"i": 2, "p": "later"}]})
    assert items[3].extra["priority"] == "first" and items[0].extra["priority"] == "first"
    assert items[1].extra["priority"] == "today"  # over the cap of 2: demoted, keeps its why
    assert items[1].extra["why"] == "c"

def test_skipped_and_bad_rows_default_to_later():
    items = [_item(0), _item(1), _item(2)]
    _run(items, {"items": [{"i": 0, "p": "first"}, {"i": 0, "p": "later"}, {"i": 9, "p": "first"},
                           {"i": "1", "p": "first"}, {"i": 2, "p": "urgent"}, "junk"]})
    assert [i.extra["priority"] for i in items] == ["first", "later", "later"]

def test_failure_leaves_items_unlabeled():
    items = [_item(0)]
    client = _run(items, "not json")
    assert client.messages.create.call_count == 2  # retried once via claude_json
    assert "priority" not in items[0].extra

def test_prompt_carries_profile_and_cap():
    items = [_item(0)]
    client = _run(items, {"items": [{"i": 0, "p": "later"}]})
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Khare builds AI screening" in prompt and "at most 2" in prompt

def test_order_themes_and_reading_list():
    a, b, c, d = (_item(n) for n in range(4))
    a.extra["priority"], b.extra["priority"], c.extra["priority"] = "later", "first", "today"
    themes = order_themes([{"name": "X", "items": [a, d, c, b]}])
    assert themes[0]["items"] == [b, c, a, d]  # unlabeled sorts last
    assert reading_list(themes) == [b]
    assert rank(d) > rank(a)
