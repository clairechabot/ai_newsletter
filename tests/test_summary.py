import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from briefing.models import Item
from briefing.summary import summarize, ref_target, is_enabled

def _item(n, **extra):
    return Item.make(source="S", source_type="rss", title=f"T{n}", url=f"http://x/{n}",
                     summary="s", published=datetime.now(timezone.utc), extra=extra)

def _themes():
    return [{"name": "Model Wars", "tab": "Models", "items": [_item(0, priority="first", rank=0),
                                                             _item(1, priority="later")]},
            {"name": "Follow the Money", "tab": "Money", "items": [_item(2, priority="today", rank=1),
                                                                   _item(3, priority="later")]}]

def _client(payload):
    c = MagicMock(); block = MagicMock(); block.type = "text"
    block.text = payload if isinstance(payload, str) else json.dumps(payload)
    msg = MagicMock(); msg.content = [block]; c.messages.create.return_value = msg
    return c

def _run(payload, cfg={"enabled": True}):
    client = _client(payload)
    with patch("briefing.summary._client", return_value=client):
        return summarize(_themes(), cfg), client

def test_off_by_default_makes_no_call():
    assert not is_enabled({}) and not is_enabled({"enabled": False})
    with patch("briefing.summary._client") as c:
        assert summarize(_themes(), {}) == []
    c.assert_not_called()

def test_takeaways_are_cleaned_and_refs_resolved():
    out, client = _run({"summary": [
        {"lead": "Price war", "text": "  Opus 5.5 and GPT-6\n cut prices. ", "short": "Prices fall.",
         "ref": {"stories": [2, 1, 1]}},
        {"lead": "Money moves.", "text": "Deals.", "ref": {"section": "money"}},
        {"lead": "", "text": "no lead"},
        {"lead": "Bad ref.", "text": "x", "ref": {"stories": [9]}},
        {"lead": "Extra.", "text": "over the limit"}]})
    assert out == [
        {"lead": "Price war.", "text": "Opus 5.5 and GPT-6 cut prices.", "short": "Prices fall.",
         "ref": {"stories": [1, 2]}},
        {"lead": "Money moves.", "text": "Deals.", "short": "", "ref": {"section": 1}},
        {"lead": "Bad ref.", "text": "x", "short": "", "ref": None}]
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Story 1: S | T0" in prompt and "Story 2: S | T2" in prompt
    assert 'Section "Models"' in prompt and 'Section "Money"' in prompt

def test_failure_gives_no_summary():
    out, client = _run("not json")
    assert out == [] and client.messages.create.call_count == 2
    assert _run({"summary": "nope"})[0] == []

def test_ref_target_labels_and_anchors():
    names = ["Models", "Money"]
    assert ref_target({"stories": [3]}, names) == ("Story 3", "order-2")
    assert ref_target({"stories": [1, 2]}, names) == ("Stories 1 and 2", "order-0")
    assert ref_target({"stories": [1, 2, 4]}, names) == ("Stories 1, 2 and 4", "order-0")
    assert ref_target({"section": 1}, names) == ("Skim: Money", "skim-1")
    assert ref_target(None, names) == ("", "") and ref_target({"section": 5}, names) == ("", "")


def test_prompt_is_written_for_the_priority_profile():
    profile = {"enabled": True, "org": "Khare", "context": "Khare builds AI screening for VCs."}
    client = _client({"summary": [{"lead": "A.", "text": "b"}]})
    with patch("briefing.summary._client", return_value=client):
        summarize(_themes(), {"enabled": True}, profile=profile)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "team at Khare" in prompt and "Khare builds AI screening for VCs." in prompt
    assert "Never invent a link" in prompt
    for off in (None, {"enabled": False, "context": "x"}, {"enabled": True, "context": " "}):
        with patch("briefing.summary._client", return_value=_client({"summary": []})) as c:
            summarize(_themes(), {"enabled": True}, profile=off)
        assert "The readers are" not in c.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
