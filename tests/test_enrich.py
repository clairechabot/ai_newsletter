import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from briefing.models import Item
from briefing.enrich import group_into_themes

def _item(uid):
    return Item.make(source="s", source_type="rss", title=f"T{uid}",
                     url=f"http://x/{uid}", summary="sum", published=datetime.now(timezone.utc), id=uid)

def _client(payload):
    c = MagicMock(); block = MagicMock(); block.type = "text"; block.text = json.dumps(payload)
    msg = MagicMock(); msg.content = [block]; c.messages.create.return_value = msg
    return c

def test_group_into_themes_maps_indices():
    items = [_item("0"), _item("1")]
    payload = {"themes": [{"name": "Theme A", "emoji": "X", "indices": [0, 1]}]}
    with patch("briefing.enrich._client", return_value=_client(payload)):
        themes = group_into_themes(items)
    assert themes[0]["name"] == "Theme A"
    assert len(themes[0]["items"]) == 2

def test_group_into_themes_empty_returns_empty():
    assert group_into_themes([]) == []

def test_group_into_themes_bad_json_falls_back_to_single_theme():
    items = [_item("0"), _item("1")]
    bad = MagicMock(); blk = MagicMock(); blk.type = "text"; blk.text = "not json at all"
    bad_msg = MagicMock(); bad_msg.content = [blk]
    bad_client = MagicMock(); bad_client.messages.create.return_value = bad_msg
    with patch("briefing.enrich._client", return_value=bad_client):
        themes = group_into_themes(items)
    assert len(themes) == 1
    assert themes[0]["name"] == "Today"
    assert len(themes[0]["items"]) == 2

def test_items_left_out_by_claude_are_kept_in_catch_all():
    items = [_item("0"), _item("1"), _item("2")]
    payload = {"themes": [{"name": "A", "emoji": "X", "indices": [0]}]}
    with patch("briefing.enrich._client", return_value=_client(payload)):
        themes = group_into_themes(items)
    assert [t["name"] for t in themes] == ["A", "Also Today"]
    assert [i.id for i in themes[1]["items"]] == ["1", "2"]

def test_item_in_two_themes_appears_once():
    items = [_item("0"), _item("1")]
    payload = {"themes": [{"name": "A", "emoji": "X", "indices": [0, 1]},
                          {"name": "B", "emoji": "Y", "indices": [1, 99, "x"]}]}
    with patch("briefing.enrich._client", return_value=_client(payload)):
        themes = group_into_themes(items)
    assert [t["name"] for t in themes] == ["A"]  # B ended up empty
    assert sum(len(t["items"]) for t in themes) == 2

def test_api_error_falls_back_to_single_theme():
    boom = MagicMock(); boom.messages.create.side_effect = RuntimeError("overloaded")
    with patch("briefing.enrich._client", return_value=boom):
        themes = group_into_themes([_item("0")])
    assert themes[0]["name"] == "Today"
    assert boom.messages.create.call_count == 2  # retried once


def test_tab_label_from_claude_or_shortened_name():
    items = [_item("0"), _item("1")]
    payload = {"themes": [{"name": "Building on someone else's platform", "tab": "Platform risk",
                           "emoji": "X", "indices": [0]},
                          {"name": "A very long theme name that overflows", "emoji": "Y", "indices": [1]}]}
    with patch("briefing.enrich._client", return_value=_client(payload)):
        themes = group_into_themes(items)
    assert themes[0]["tab"] == "Platform risk"
    assert themes[1]["tab"] == "A very long theme…"
