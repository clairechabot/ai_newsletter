from unittest.mock import patch, MagicMock
from briefing.sources.youtube import fetch_youtube, _duration_seconds, _uploads_playlist

def _entry(vid, title, published="2026-06-04T00:00:00Z", desc=""):
    return {"snippet": {"title": title, "description": desc, "channelTitle": "Chan",
                        "publishedAt": published,
                        "thumbnails": {"high": {"url": f"http://t/{vid}.jpg"}}},
            "contentDetails": {"videoId": vid, "videoPublishedAt": published}}

def _fake_yt(entries, durations=None):
    yt = MagicMock()
    yt.playlistItems().list().execute.return_value = {"items": entries}
    yt.videos().list().execute.return_value = {"items": [
        {"id": v, "contentDetails": {"duration": d}} for v, d in (durations or {}).items()]}
    yt.search.side_effect = AssertionError("search.list costs 100 units; must not be used")
    return yt

def test_youtube_maps_to_items():
    cfg = {"type": "youtube", "name": "Chan", "channel_id": "UC1"}
    with patch("briefing.sources.youtube._build_youtube",
               return_value=_fake_yt([_entry("v1", "Vid")])):
        items = fetch_youtube(cfg, max_per_channel=2)
    assert items[0].id == "v1"
    assert items[0].source_type == "youtube"
    assert items[0].extra["embed_url"].endswith("v1?rel=0")
    assert items[0].published.year == 2026
    assert items[0].published.tzinfo is not None

def test_uploads_playlist_derived_from_channel_id():
    assert _uploads_playlist("UCabc") == "UUabc"

def test_duration_parse():
    assert _duration_seconds("PT1M5S") == 65
    assert _duration_seconds("PT1H") == 3600
    assert _duration_seconds("P0D") == 0
    assert _duration_seconds("") is None

def test_skip_shorts_drops_short_and_tagged_videos():
    entries = [_entry("s1", "Quick one"), _entry("s2", "Big news #shorts"),
               _entry("l1", "Long talk"), _entry("p", "Private video")]
    yt = _fake_yt(entries, {"s1": "PT45S", "s2": "PT10M", "l1": "PT20M"})
    cfg = {"type": "youtube", "name": "Chan", "channel_id": "UC1", "skip_shorts": True}
    with patch("briefing.sources.youtube._build_youtube", return_value=yt):
        items = fetch_youtube(cfg, max_per_channel=5)
    assert [i.id for i in items] == ["l1"]

def test_shorts_kept_when_not_opted_in():
    yt = _fake_yt([_entry("s1", "Quick #shorts")])
    cfg = {"type": "youtube", "name": "Chan", "channel_id": "UC1"}
    with patch("briefing.sources.youtube._build_youtube", return_value=yt):
        assert [i.id for i in fetch_youtube(cfg)] == ["s1"]
