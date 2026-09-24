from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from briefing.sources.rss import fetch_rss

def _fake_parsed():
    now = datetime.now(timezone.utc)
    return type("P", (), {"entries": [
        {"title": "Fresh", "link": "http://x/1",
         "summary": "s1", "published_parsed": (now).timetuple()},
        {"title": "Old", "link": "http://x/2",
         "summary": "s2", "published_parsed": (now - timedelta(days=10)).timetuple()},
    ]})()

def test_rss_maps_and_respects_recency():
    cfg = {"type": "rss", "name": "BBC", "url": "http://x/rss"}
    with patch("briefing.sources.rss.fetch", return_value=MagicMock(content=b"")), \
         patch("briefing.sources.rss.feedparser.parse", return_value=_fake_parsed()):
        items = fetch_rss(cfg, recency_hours=24)
    assert len(items) == 1
    assert items[0].title == "Fresh"
    assert items[0].source == "BBC"
    assert items[0].source_type == "rss"

def test_proxy_feed_uses_validated_fallback():
    cfg = {"type": "rss", "name": "AO", "url": "http://x/rss", "proxy": True}
    with patch("briefing.sources.rss.fetch_with_fallback",
               return_value=MagicMock(content=b"")) as fwf, \
         patch("briefing.sources.rss.feedparser.parse", return_value=_fake_parsed()):
        items = fetch_rss(cfg, recency_hours=24)
    assert len(items) == 1
    assert fwf.call_args.kwargs["validate"] is not None

def test_per_feed_timeout_passed_through():
    cfg = {"type": "rss", "name": "Slow", "url": "http://x/rss", "timeout": 60}
    with patch("briefing.sources.rss.fetch", return_value=MagicMock(content=b"")) as f, \
         patch("briefing.sources.rss.feedparser.parse", return_value=_fake_parsed()):
        fetch_rss(cfg)
    assert f.call_args.kwargs["timeout"] == 60
