from __future__ import annotations
import os
import anthropic
from briefing.llm import claude_json

SCORE_THRESHOLD = 50

def _client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def _catalogue(items) -> str:
    # Short numeric indices, not 40-char sha1 ids: keeps the reply small enough
    # that a large batch doesn't get cut off at max_tokens.
    return "\n".join(f"[{n}] {i.title} :: {i.summary[:200]}" for n, i in enumerate(items))

def _max_tokens(items) -> int:
    return min(8000, 200 + 12 * len(items))

def _score_items(items, interests):
    """{item.id: score}, or None if Claude couldn't score this batch."""
    prompt = (
        f"Reader interests: {', '.join(interests)}.\n"
        "Score each numbered item 0-100 for how well it matches the interests.\n"
        "Return ONLY JSON: {\"scores\": {\"<index>\": <int>}}.\n\n" + _catalogue(items)
    )
    data = claude_json(prompt, max_tokens=_max_tokens(items), context="filter:score",
                       client_factory=lambda: _client())
    if data is None:
        return None
    out = {}
    for k, v in (data.get("scores") or {}).items():
        try:
            idx, score = int(k), int(v)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(items):
            out[items[idx].id] = score
    return out

def _curate(items, interests):
    """Claude's picks in its preferred order, or None on failure."""
    steer = f"Reader leans toward: {', '.join(interests)}.\n" if interests else ""
    prompt = (steer + "Pick the genuinely most interesting/important numbered items.\n"
              "Return ONLY JSON: {\"keep\": [<index>, ...]}.\n\n" + _catalogue(items))
    data = claude_json(prompt, max_tokens=_max_tokens(items), context="filter:curate",
                       client_factory=lambda: _client())
    if data is None:
        return None
    out, seen = [], set()
    for k in data.get("keep") or []:
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(items) and idx not in seen:
            seen.add(idx)
            out.append(items[idx])
    return out

def _recent(items, cfg) -> list:
    return sorted(items, key=lambda i: i.published, reverse=True)[:cfg.max_items]

def apply_filter(items, cfg) -> list:
    mode = cfg.filter_mode
    if mode == "recent":
        return _recent(items, cfg)
    if mode == "per_source_cap":
        counts, out = {}, []
        for i in sorted(items, key=lambda i: i.published, reverse=True):
            if counts.get(i.source, 0) < cfg.per_source_cap:
                counts[i.source] = counts.get(i.source, 0) + 1
                out.append(i)
        return out[:cfg.max_items]
    if mode == "interests":
        scores = _score_items(items, cfg.interests)
        if scores is None:
            # Never lose the edition to a bad LLM call: fall back to newest-first.
            print("[filter] scoring failed; falling back to 'recent'", flush=True)
            return _recent(items, cfg)
        kept = [i for i in items if scores.get(i.id, 0) >= SCORE_THRESHOLD]
        kept.sort(key=lambda i: scores.get(i.id, 0), reverse=True)
        return kept[:cfg.max_items]
    if mode == "claude_curate":
        picked = _curate(items, cfg.interests)
        if picked is None:
            print("[filter] curation failed; falling back to 'recent'", flush=True)
            return _recent(items, cfg)
        return picked[:cfg.max_items]
    raise ValueError(f"unknown filter mode {mode}")
