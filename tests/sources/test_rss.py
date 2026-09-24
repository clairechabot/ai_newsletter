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

def test_feed_images_and_plain_text_summaries():
    now = datetime.now(timezone.utc).timetuple()
    parsed = type("P", (), {"entries": [
        {"title": "Using the  <details> element", "link": "http://x/1", "published_parsed": now,
         "summary": "<p>First &amp; <b>best</b></p>\n<p>line</p>",
         "media_content": [{"url": "https://cdn/v.mp4", "type": "video/mp4"},
                           {"url": "https://cdn/pic.jpg", "medium": "image"}]},
        {"title": "B", "link": "http://x/2", "published_parsed": now, "summary": "x",
         "enclosures": [{"href": "https://cdn/enc.png", "type": "image/png"}]},
        {"title": "C", "link": "http://x/3", "published_parsed": now, "summary": "x",
         "media_thumbnail": [{"url": "https://cdn/thumb.jpg"}]},
        {"title": "D", "link": "http://x/4", "published_parsed": now, "summary": "x" * 900,
         "enclosures": [{"href": "https://cdn/ep.mp3", "type": "audio/mpeg"}]},
    ]})()
    cfg = {"type": "rss", "name": "F", "url": "http://x/rss"}
    with patch("briefing.sources.rss.fetch", return_value=MagicMock(content=b"")), \
         patch("briefing.sources.rss.feedparser.parse", return_value=parsed):
        a, b, c, d = fetch_rss(cfg, recency_hours=24)
    assert a.summary == "First & best line"            # HTML stripped, entities decoded
    assert a.title == "Using the <details> element"     # titles are text: kept, whitespace tidied
    assert a.extra["image"] == "https://cdn/pic.jpg"    # video media skipped
    assert b.extra["image"] == "https://cdn/enc.png"
    assert c.extra["image"] == "https://cdn/thumb.jpg"
    assert "image" not in d.extra and d.summary.endswith("…") and len(d.summary) <= 501

def test_wordpress_footer_removed():
    from briefing.sources.rss import _plain
    html = "<p>UBS may need US$16B more.</p><p>The post UBS Capital Rule appeared first on Fintech Schweiz - FintechNewsCH.</p>"
    assert _plain(html) == "UBS may need US$16B more."
    assert _plain("The post office reopened today.") == "The post office reopened today."
