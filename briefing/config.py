from __future__ import annotations
from dataclasses import dataclass, field
import yaml

VALID_MODES = {"interests", "recent", "per_source_cap", "claude_curate"}
VALID_TYPES = {"rss", "site", "scrape", "claude_fetch", "youtube"}
VALID_EMAIL_MODES = {"full", "cover"}
VALID_SUBJECTS = {"date", "top_pick"}

class ConfigError(Exception):
    pass

@dataclass
class Config:
    title: str
    filter_mode: str
    interests: list
    max_items: int
    per_source_cap: int
    recency_hours: int
    sources: list
    min_score: int = 50                              # interests mode threshold (0-100)
    # Optional extensions — all default to "off" so a minimal config still works.
    voice: dict = field(default_factory=dict)       # editor persona (voice.py)
    priority: dict = field(default_factory=dict)    # reading-priority labels (priority.py)
    images: dict = field(default_factory=dict)      # preview images (images.py)
    summary: dict = field(default_factory=dict)     # "The day in 30 seconds" (summary.py)
    web: dict = field(default_factory=dict)          # web edition + archive (web.py)
    editions: list = field(default_factory=list)     # AM/PM schedule (editions.py)
    email_mode: str = "full"                         # "full" | "cover"
    email_subject: str = "date"                      # "date" | "top_pick"
    email_from_name: str = ""                        # inbox sender name; "" = account name
    email_unsubscribe: str = ""                      # cover footer link (URL or mailto:); "" = none
    email_address: str = ""                          # cover footer postal line; "" = none

def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    f = raw.get("filter", {})
    mode = f.get("mode", "recent")
    if mode not in VALID_MODES:
        raise ConfigError(f"filter.mode must be one of {sorted(VALID_MODES)}, got {mode!r}")
    sources = raw.get("sources", [])
    if not sources:
        raise ConfigError("config has no sources")
    for s in sources:
        t = s.get("type")
        if t not in VALID_TYPES:
            raise ConfigError(f"source has invalid/missing type: {s!r}")
    email = raw.get("email", {})
    email_mode = email.get("mode", "full")
    if email_mode not in VALID_EMAIL_MODES:
        raise ConfigError(f"email.mode must be one of {sorted(VALID_EMAIL_MODES)}, got {email_mode!r}")
    email_subject = email.get("subject", "date")
    if email_subject not in VALID_SUBJECTS:
        raise ConfigError(f"email.subject must be one of {sorted(VALID_SUBJECTS)}, got {email_subject!r}")
    return Config(
        title=raw.get("briefing", {}).get("title", "Daily Briefing"),
        filter_mode=mode,
        interests=f.get("interests", []),
        max_items=int(f.get("max_items", 25)),
        min_score=int(f.get("min_score", 50)),
        per_source_cap=int(f.get("per_source_cap", 5)),
        recency_hours=int(f.get("recency_hours", 24)),
        sources=sources,
        voice=raw.get("voice", {}) or {},
        priority=raw.get("priority", {}) or {},
        images=raw.get("images", {}) or {},
        summary=raw.get("summary", {}) or {},
        web=raw.get("web", {}) or {},
        editions=raw.get("editions", []) or [],
        email_mode=email_mode,
        email_subject=email_subject,
        email_from_name=str(email.get("from_name", "") or ""),
        email_unsubscribe=str(email.get("unsubscribe", "") or ""),
        email_address=str(email.get("address", "") or ""),
    )
