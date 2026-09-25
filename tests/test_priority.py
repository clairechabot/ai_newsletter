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

def _run_kept(items, payload, cfg=CFG):
    with patch("briefing.priority._client", return_value=_client(payload)):
        return prioritize(items, cfg)

def test_same_as_folds_duplicates_into_the_lead():
    items = [_item(n) for n in range(5)]
    items[1].extra["minutes"] = 5
    kept = _run_kept(items, {"items": [
        {"i": 3, "p": "first", "why": "Competitor."},
        {"i": 1, "p": "today", "why": "Prices fall for us.", "cluster_title": "Two labs ship on one day"},
        {"i": 2, "p": "first", "same_as": 1},          # duplicate ranked higher: lead inherits "first"
        {"i": 4, "p": "later", "same_as": 2},          # chain resolves to the lead
        {"i": 0, "p": "later"}]})
    assert kept == [items[0], items[1], items[3]]
    lead = items[1]
    assert lead.extra["also"] == [items[2], items[4]]
    assert lead.extra["priority"] == "first" and lead.extra["cluster_title"] == "Two labs ship on one day"
    assert lead.extra["why"] == "Prices fall for us." and lead.extra["minutes"] == 6  # 5 + 1
    # the group ranks where its highest member sat
    assert [items[3].extra["rank"], lead.extra["rank"], items[0].extra["rank"]] == [0, 1, 2]

def test_bad_same_as_is_ignored():
    items = [_item(n) for n in range(3)]
    kept = _run_kept(items, {"items": [
        {"i": 0, "p": "today", "same_as": 1}, {"i": 1, "p": "later", "same_as": 0},  # cycle
        {"i": 2, "p": "later", "same_as": 2}]})                                        # self
    assert kept == items and not any("also" in i.extra for i in items)
    assert _run_kept([_item(9)], {"items": [{"i": 0, "p": "first", "same_as": 7}]})[0].extra["priority"] == "first"

def test_cluster_counts_once_toward_first_cap():
    items = [_item(n) for n in range(4)]
    kept = _run_kept(items, {"items": [
        {"i": 0, "p": "first"}, {"i": 1, "p": "first", "same_as": 0},
        {"i": 2, "p": "first"}, {"i": 3, "p": "first"}]})
    assert [i.extra["priority"] for i in kept] == ["first", "first", "today"]  # cap of 2
    assert items[0].extra["minutes"] == 4  # unmeasured 3 + 1 for the cluster

def test_failure_returns_items_unclustered():
    items = [_item(0), _item(1)]
    with patch("briefing.priority._client", return_value=_client("nope")):
        assert prioritize(items, CFG) == items

def test_triage_orders_by_rank_and_skims_the_rest():
    from briefing.priority import triage, display_title, read_minutes
    a, b, c, d = (_item(n) for n in range(4))
    a.extra.update(priority="today", rank=2); b.extra.update(priority="first", rank=1)
    c.extra.update(priority="later", rank=3); d.extra.update(priority="first", rank=0)
    t1, t2 = {"name": "One", "items": [a, c]}, {"name": "Two", "items": [b, d]}
    order, skim = triage([t1, t2])
    assert order == [d, b, a] and skim == [(t1, [c])]
    plain = [{"name": "X", "items": [_item(5), _item(6)]}]
    order, skim = triage(plain)
    assert order == [plain[0]["items"][0]] and skim[0][1] == [plain[0]["items"][1]]
    # no labels: the lead story of each of the first three sections
    four = [{"name": f"S{n}", "items": [_item(10 * n), _item(10 * n + 1)]} for n in range(4)]
    four.insert(1, {"name": "Empty", "items": []})
    order, skim = triage(four)
    assert [i.url for i in order] == ["http://x/0", "http://x/10", "http://x/20"]
    assert [len(its) for _, its in skim] == [1, 1, 1, 2]
    d.extra["cluster_title"] = "Event"
    assert display_title(d) == "Event" and display_title(a) == a.title
    assert read_minutes(a) == 3 and read_minutes(_item(7)) == 3

def test_topics_are_assigned_and_validated():
    items = [_item(n) for n in range(4)]
    topics = ["Governed AI", "Frontier models"]
    client = _client({"items": [
        {"i": 0, "p": "first", "t": "governed ai"}, {"i": 1, "p": "later", "t": "Crypto"},
        {"i": 2, "p": "later"}, {"i": 3, "p": "later", "t": "Frontier models", "same_as": 2}]})
    with patch("briefing.priority._client", return_value=client):
        kept = prioritize(items, CFG, topics=topics)
    assert [i.extra["topic"] for i in kept] == ["Governed AI", "", "Frontier models"]  # lead takes member's
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert '"Governed AI", "Frontier models"' in prompt and '"t": "<topic>"' in prompt
    plain = [_item(9)]
    with patch("briefing.priority._client", return_value=_client({"items": [{"i": 0, "p": "later"}]})) as c:
        prioritize(plain, CFG)
    assert "topic" not in plain[0].extra
    assert '"t"' not in c.return_value.messages.create.call_args.kwargs["messages"][0]["content"]

def test_followups_of_recent_reading_orders_are_demoted():
    items = [_item(0), _item(1)]
    client = _client({"items": [{"i": 0, "p": "first", "why": "x", "followup": True},
                                {"i": 1, "p": "today", "why": "y"}]})
    with patch("briefing.priority._client", return_value=client):
        prioritize(items, CFG, recent=["Opus 5.5 ships"])
    assert items[0].extra["priority"] == "later" and items[0].extra["followup"] is True
    assert items[1].extra["priority"] == "today" and "followup" not in items[1].extra
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "- Opus 5.5 ships" in prompt and '"followup": true' in prompt
    # without recent headlines the flag is neither asked for nor honoured
    items = [_item(2)]
    client = _client({"items": [{"i": 0, "p": "first", "followup": True}]})
    with patch("briefing.priority._client", return_value=client):
        prioritize(items, CFG)
    assert items[0].extra["priority"] == "first" and "followup" not in items[0].extra
    assert "followup" not in client.messages.create.call_args.kwargs["messages"][0]["content"]
