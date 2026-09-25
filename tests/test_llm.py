from unittest.mock import patch
from briefing.llm import make_client

def test_workspace_header_only_when_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", " wrkspc_123 ")
    with patch("briefing.llm.anthropic.Anthropic") as A:
        make_client()
    assert A.call_args.kwargs["default_headers"] == {"anthropic-workspace-id": "wrkspc_123"}
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "")   # the workflow passes unset secrets as ""
    with patch("briefing.llm.anthropic.Anthropic") as A:
        make_client()
    assert A.call_args.kwargs["default_headers"] is None

def test_model_default_and_thinking_headroom():
    import json
    from unittest.mock import MagicMock
    from briefing import llm
    client = MagicMock(); block = MagicMock(); block.type = "text"; block.text = json.dumps({"ok": 1})
    msg = MagicMock(); msg.content = [block]; client.messages.create.return_value = msg
    assert llm.claude_json("p", max_tokens=900, client_factory=lambda: client) == {"ok": 1}
    kw = client.messages.create.call_args.kwargs
    assert kw["max_tokens"] == 900 + llm.THINKING_HEADROOM and kw["model"] == llm.MODEL
