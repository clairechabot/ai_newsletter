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
