from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from briefing.models import Item
from briefing.filter import apply_filter
from briefing.config import Config

def _items(n, source="s"):
    now = datetime.now(timezone.utc)
    return [Item.make(source=source, source_type="rss", title=f"T{i}",
                      url=f"http://x/{i}", summary=f"s{i}",
                      published=now - timedelta(minutes=i), id=str(i)) for i in range(n)]

def _cfg(mode, **kw):
    base = dict(title="t", filter_mode=mode, interests=["ai"], max_items=5,
                per_source_cap=2, recency_hours=24, sources=[])
    base.update(kw)
    return Config(**base)

def test_recent_caps_at_max_items():
    out = apply_filter(_items(10), _cfg("recent", max_items=5))
    assert len(out) == 5
    assert [i.id for i in out] == ["0", "1", "2", "3", "4"]  # newest-first, capped

def test_per_source_cap_limits_per_source():
    items = _items(3, "A") + _items(3, "B")
    out = apply_filter(items, _cfg("per_source_cap", per_source_cap=2, max_items=99))
    by = {}
    for i in out:
        by[i.source] = by.get(i.source, 0) + 1
    assert by == {"A": 2, "B": 2}

def test_claude_curate_keeps_only_picked_and_caps():
    items = _items(4)
    # _curate returns a subset; apply_filter then caps at max_items
    picked = [items[0], items[2], items[3]]
    with patch("briefing.filter._curate", return_value=picked):
        out = apply_filter(items, _cfg("claude_curate", max_items=2))
    assert [i.id for i in out] == ["0", "2"]  # _curate order preserved, capped to 2

def test_interests_keeps_high_scored_only(monkeypatch):
    items = _items(3)
    scores = {"0": 90, "1": 10, "2": 80}
    with patch("briefing.filter._score_items", return_value=scores):
        out = apply_filter(items, _cfg("interests", max_items=5))
    assert {i.id for i in out} == {"0", "2"}  # >= 50 threshold

def _client_returning(payload):
    import json
    from unittest.mock import MagicMock
    c = MagicMock(); block = MagicMock(); block.type = "text"; block.text = json.dumps(payload)
    msg = MagicMock(); msg.content = [block]; c.messages.create.return_value = msg
    return c

def test_interests_scores_by_index():
    items = _items(3)
    client = _client_returning({"scores": {"0": 20, "1": 95, "2": 70, "9": 100}})
    with patch("briefing.filter._client", return_value=client):
        out = apply_filter(items, _cfg("interests", max_items=5))
    assert [i.id for i in out] == ["1", "2"]

def test_interests_falls_back_to_recent_on_api_error():
    from unittest.mock import MagicMock
    boom = MagicMock(); boom.messages.create.side_effect = RuntimeError("429")
    with patch("briefing.filter._client", return_value=boom):
        out = apply_filter(_items(10), _cfg("interests", max_items=3))
    assert [i.id for i in out] == ["0", "1", "2"]

def test_claude_curate_by_index_and_falls_back():
    items = _items(4)
    with patch("briefing.filter._client", return_value=_client_returning({"keep": [3, 1, 3]})):
        assert [i.id for i in apply_filter(items, _cfg("claude_curate"))] == ["3", "1"]
    bad = _client_returning({"nope": 1}); bad.messages.create.return_value.content[0].text = "garbage"
    with patch("briefing.filter._client", return_value=bad):
        assert len(apply_filter(items, _cfg("claude_curate", max_items=2))) == 2


def test_interests_threshold_is_configurable():
    items = _items(3)
    scores = {"0": 90, "1": 45, "2": 30}
    with patch("briefing.filter._score_items", return_value=scores):
        assert {i.id for i in apply_filter(items, _cfg("interests"))} == {"0"}           # default 50
        assert {i.id for i in apply_filter(items, _cfg("interests", min_score=40))} == {"0", "1"}


def test_curate_prompt_asks_for_hot_topics_plus_interests_up_to_max_items():
    items = _items(3)
    client = _client_returning({"keep": [2, 0]})
    with patch("briefing.filter._client", return_value=client):
        out = apply_filter(items, _cfg("claude_curate", interests=["AI in banking"], max_items=12))
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "pick up to 12" in prompt and "hottest topics" in prompt
    assert "AI in banking" in prompt and "same news, keep only the best one" in prompt
    assert [i.id for i in out] == ["2", "0"]  # Claude's order, most important first
