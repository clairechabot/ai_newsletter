from unittest.mock import patch
from briefing.sources import fetch_all
from briefing.config import Config

def _cfg(sources):
    return Config(title="t", filter_mode="recent", interests=[], max_items=10,
                  per_source_cap=5, recency_hours=24, sources=sources)

def test_dispatches_by_type_and_fails_soft():
    sources = [
        {"type": "rss", "name": "Good", "url": "http://x"},
        {"type": "rss", "name": "Bad", "url": "http://y"},
    ]
    def fake_rss(cfg, recency_hours):
        if cfg["name"] == "Bad":
            raise RuntimeError("boom")
        from briefing.models import Item
        from datetime import datetime, timezone
        return [Item.make(source="Good", source_type="rss", title="T",
                          url="http://x/1", summary="", published=datetime.now(timezone.utc))]
    with patch("briefing.sources.fetch_rss", side_effect=fake_rss):
        items = fetch_all(_cfg(sources))
    assert [i.source for i in items] == ["Good"]  # Bad failed soft, dropped
