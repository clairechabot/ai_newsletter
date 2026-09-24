"""Shared Claude JSON helper. Every LLM step in the pipeline is best-effort:
`claude_json` retries once and returns None instead of raising, so a timeout,
overload, or malformed reply degrades one step rather than killing the run."""
from __future__ import annotations
import os
import json
import re
import anthropic

MODEL = os.environ.get("BRIEFING_MODEL", "claude-sonnet-4-6")


def make_client():
    """The Anthropic client every step uses. A key that isn't scoped to one
    workspace must name the workspace on each request (Anthropic returns 400
    otherwise); set ANTHROPIC_WORKSPACE_ID (wrkspc_...) for such keys. Keys
    created for a single workspace need nothing extra."""
    headers = {}
    workspace = (os.environ.get("ANTHROPIC_WORKSPACE_ID") or "").strip()
    if workspace:
        headers["anthropic-workspace-id"] = workspace
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"],
                               default_headers=headers or None)


def _client():
    return make_client()


def strip_fences(text) -> str:
    return re.sub(r"^```[a-z]*\n?|```$", "", (text or "").strip(), flags=re.MULTILINE)


def claude_json(prompt, *, max_tokens=1000, context="llm", client_factory=None):
    """Ask Claude for a JSON object; return the parsed dict, or None if both
    attempts fail (API error, empty reply, unparseable or non-object JSON)."""
    make = client_factory or _client
    for attempt in (1, 2):
        try:
            msg = make().messages.create(model=MODEL, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}])
        except Exception as e:  # network, overload, rate limit, missing key
            print(f"[{context}] API call failed (attempt {attempt}): {e}", flush=True)
            continue
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if getattr(msg, "stop_reason", None) == "max_tokens":
            print(f"[{context}] reply hit max_tokens={max_tokens} (attempt {attempt})",
                  flush=True)
        try:
            data = json.loads(strip_fences(text))
        except (json.JSONDecodeError, TypeError):
            print(f"[{context}] reply was not valid JSON (attempt {attempt})", flush=True)
            continue
        if isinstance(data, dict):
            return data
        print(f"[{context}] reply was not a JSON object (attempt {attempt})", flush=True)
    return None
