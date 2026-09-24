import json
from unittest.mock import patch, MagicMock
from briefing.sources.claude_fetch import fetch_claude

def _fake_client(payload):
    client = MagicMock()
    block = MagicMock(); block.type = "text"; block.text = json.dumps(payload)
    msg = MagicMock(); msg.content = [block]
    client.messages.create.return_value = msg
    return client

def test_claude_fetch_parses_items():
    cfg = {"type": "claude_fetch", "name": "NoFeed", "url": "https://nf.com"}
    payload = {"items": [
        {"title": "A", "url": "https://nf.com/a", "summary": "sa"},
        {"title": "B", "url": "https://nf.com/b", "summary": "sb"},
    ]}
    with patch("briefing.sources.claude_fetch._client", return_value=_fake_client(payload)), \
         patch("briefing.sources.claude_fetch.http_get", side_effect=OSError("offline")):
        items = fetch_claude(cfg)
    assert [i.title for i in items] == ["A", "B"]
    assert items[0].source_type == "claude_fetch"

def _page(*hrefs):
    html = "".join(f'<a href="{h}">x</a>' for h in hrefs)
    return MagicMock(text=f"<html><body>{html}</body></html>")

def _run(payload, page):
    cfg = {"type": "claude_fetch", "name": "NoFeed", "url": "https://nf.com/news"}
    with patch("briefing.sources.claude_fetch._client", return_value=_fake_client(payload)), \
         patch("briefing.sources.claude_fetch.http_get", return_value=page):
        return fetch_claude(cfg)

def test_invented_links_are_dropped():
    payload = {"items": [{"title": "Real", "url": "/a"},
                         {"title": "Made up", "url": "https://nf.com/invented"}]}
    items = _run(payload, _page("https://www.nf.com/a/", "/b"))
    assert [(i.title, i.url) for i in items] == [("Real", "https://nf.com/a")]

def test_js_shell_page_keeps_claude_list():
    payload = {"items": [{"title": "A", "url": "https://nf.com/a"}]}
    assert [i.title for i in _run(payload, _page("/about"))] == ["A"]
