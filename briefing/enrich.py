from __future__ import annotations
import os
import anthropic
from briefing.llm import claude_json
from briefing.voice import theme_steer
from briefing.web import tab_label

def _client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def group_into_themes(items, voice=None) -> list:
    """Cluster items into 3-4 magazine-style themes. Returns
    [{"name", "emoji", "items": [Item, ...]}]. If `voice` is an enabled editor
    persona, themes are named in that voice. Every input item appears exactly
    once: items Claude repeats are kept in their first theme, and items it
    leaves out go into a trailing catch-all theme."""
    if not items:
        return []
    catalogue = "\n".join(
        f"[{idx}] {i.source} | {i.title} | {i.summary[:200]}"
        for idx, i in enumerate(items)
    )
    prompt = (
        "You are the editor of a witty daily briefing.\n"
        "Group the numbered items into 3-4 creative theme names. Every item "
        "belongs to exactly one theme." + theme_steer(voice) + " Give each theme "
        "a short \"tab\" label too (at most 20 characters, plain words, no emoji) for "
        "a navigation bar. Return ONLY JSON, no fences:\n"
        '{"themes": [{"name": "Theme", "tab": "Short label", "emoji": "X", "indices": [0,3]}]}\n\n'
        + catalogue
    )
    data = claude_json(prompt, max_tokens=min(4000, 400 + 8 * len(items)),
                       context="enrich", client_factory=lambda: _client())
    # Theming is best-effort: never drop the briefing over a bad LLM response.
    fallback = [{"name": "Today", "emoji": "*", "tab": "Today", "items": list(items)}]
    if data is None:
        return fallback
    out, used = [], set()
    for theme in data.get("themes") or []:
        if not isinstance(theme, dict) or not theme.get("name"):
            continue
        chosen = []
        for idx in theme.get("indices") or []:
            if isinstance(idx, int) and 0 <= idx < len(items) and idx not in used:
                used.add(idx)
                chosen.append(items[idx])
        if chosen:
            out.append({"name": str(theme["name"]), "emoji": str(theme.get("emoji") or "*"),
                        "tab": tab_label(str(theme.get("tab") or theme["name"])),
                        "items": chosen})
    leftovers = [i for n, i in enumerate(items) if n not in used]
    if not out:
        return fallback
    if leftovers:
        out.append({"name": "Also Today", "emoji": "*", "tab": "Also today", "items": leftovers})
    return out
