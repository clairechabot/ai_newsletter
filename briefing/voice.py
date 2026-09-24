"""Editor voice — an optional persona that writes the briefing's daily
greeting and steers theme names. The persona is entirely user-defined.

Give your briefing an editor in `config.yaml`:

    voice:
      enabled: true
      name: "Your editor's name"          # invent a persona; it signs the greeting
      tone: "warm, cozy, slightly witty"  # describe personality + writing style

`tone` is the prompt: it is dropped verbatim into the requests below, so it is
the knob users turn to shape the voice (see the README "editor voice" section).
For deeper control, edit the prompt text in `compose_greeting` here and the
`theme_steer` clause that `enrich.py` folds into its theme-naming prompt.

When enabled, `compose_greeting` asks Claude for a one-or-two-sentence note in
that persona, referencing today's theme names. It always fails soft: any error
(or `enabled: false`, or no API key) returns "" and the briefing ships without
a greeting. `theme_steer` is folded into the enrich prompt so themes are named
in the same voice.

Variety: the pipeline keeps the last few greetings in history.json
(`recent_greetings`). They are passed back as an avoid-list, and any opening
phrase that keeps recurring is named explicitly as a habit to break, so the
voice doesn't settle into one stock opener. Replies that read like the model
thinking aloud ("Let me...", "Here's a greeting:") are discarded.
"""
from __future__ import annotations
from briefing.llm import make_client
import os
import re
from collections import Counter

RECENT_KEEP = 12  # how many past greetings to remember

# Openers that mean the model is narrating, not writing the greeting...
_REASONING_OPENERS = (
    "let me", "actually,", "wait,", "hmm", "i think", "i'll ", "i will ",
    "here's", "here is", "as an ai", "sure,", "okay,", "certainly",
)
# ...and phrases that give it away even mid-sentence.
_REASONING_ANYWHERE = ("let me think", "let me try", "here's a greeting",
                       "here is a greeting", "as an ai")

MODEL = os.environ.get("BRIEFING_MODEL", "claude-sonnet-4-6")


def _client():
    return make_client()


def is_enabled(voice) -> bool:
    return bool(voice) and bool(voice.get("enabled")) and bool(voice.get("name"))


def theme_steer(voice) -> str:
    """A clause appended to the enrich prompt so theme names match the voice."""
    if not is_enabled(voice):
        return ""
    return (f' Name the themes in the voice of {voice["name"]}, an editor who is '
            f'{voice.get("tone", "warm and witty")}.')


def looks_like_reasoning(text) -> bool:
    """True if the reply narrates (\"Let me...\") instead of being the greeting."""
    low = (text or "").strip().lower()
    return (any(low.startswith(m) for m in _REASONING_OPENERS)
            or any(m in low for m in _REASONING_ANYWHERE))


def opening_habits(greetings, n=3, min_count=2) -> list:
    """Opening n-word phrases used at least `min_count` times recently."""
    counts = Counter()
    for g in greetings or []:
        words = re.findall(r"[A-Za-z']+", g or "")[:n]
        if len(words) == n:
            counts[" ".join(words).lower()] += 1
    return [w for w, c in counts.most_common(6) if c >= min_count]


def _variety_clause(recent) -> str:
    recent = [g for g in (recent or []) if g][-RECENT_KEEP:]
    if not recent:
        return ""
    lines = "\n".join(f"- {g}" for g in recent)
    clause = (f"\n\nYour recent greetings are below. Don't reuse their openings, "
              f"structure, or stock phrases:\n{lines}")
    habits = opening_habits(recent)
    if habits:
        clause += ("\nYou keep opening with: " + "; ".join(f'"{h}"' for h in habits)
                   + ". Do not start with any of these.")
    return clause


def compose_greeting(voice, themes, recent=None) -> str:
    """Return a short editor's note for today, or "" if disabled / on any error.
    `recent` is the list of past greetings to steer away from."""
    if not is_enabled(voice) or not themes:
        return ""
    topics = ", ".join(t["name"] for t in themes)
    prompt = (
        f"You are {voice['name']}, the editor of a daily briefing. Your voice is "
        f"{voice.get('tone', 'warm and witty')}. Write a SHORT greeting (1-2 "
        f"sentences, no more than 40 words) welcoming the reader to today's "
        f"edition. Today's themes are: {topics}. Return only the greeting text, "
        f"no quotes, no preamble." + _variety_clause(recent)
    )
    try:
        msg = _client().messages.create(
            model=MODEL, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        text = text.strip().strip('"').strip()
        if looks_like_reasoning(text):
            print("[voice] greeting skipped: reply read like reasoning", flush=True)
            return ""
        return text
    except Exception as e:  # voice is a nice-to-have; never break the briefing
        print(f"[voice] greeting skipped: {e}", flush=True)
        return ""
