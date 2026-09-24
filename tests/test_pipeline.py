from datetime import datetime, timezone
from unittest.mock import patch
from briefing.models import Item
from briefing.config import Config
from briefing.pipeline import run

def _cfg():
    return Config(title="B", filter_mode="recent", interests=[], max_items=5,
                  per_source_cap=2, recency_hours=24,
                  sources=[{"type": "rss", "name": "S", "url": "http://x"}])

def _item(uid):
    return Item.make(source="S", source_type="rss", title="T", url=f"http://x/{uid}",
                     summary="s", published=datetime.now(timezone.utc), id=uid)

def test_run_dedups_filters_and_sends(tmp_path):
    hist_path = str(tmp_path / "h.json")
    sent = {}
    with patch("briefing.pipeline.fetch_all", return_value=[_item("a"), _item("b")]), \
         patch("briefing.pipeline.load_history", return_value={"seen_ids": ["a"]}), \
         patch("briefing.pipeline.group_into_themes",
               side_effect=lambda items, voice=None: [{"name": "T", "emoji": "X", "items": items}]), \
         patch("briefing.pipeline.send_email",
               side_effect=lambda title, html, **kw: sent.update(title=title, html=html)), \
         patch("briefing.pipeline.save_history") as save:
        run(_cfg(), history_path=hist_path)
    assert "b" in sent["html"] or "T" in sent["html"]
    saved = save.call_args[0][1]["seen_ids"]
    assert "b" in saved and "a" in saved

def test_run_writes_web_edition_when_enabled(tmp_path):
    docs = tmp_path / "docs"
    cfg = Config(title="B", filter_mode="recent", interests=[], max_items=5,
                 per_source_cap=2, recency_hours=24,
                 sources=[{"type": "rss", "name": "S", "url": "http://x"}],
                 web={"enabled": True, "output_dir": str(docs)},
                 editions=[{"key": "morning", "label": "Morning", "until_hour": 12}])
    with patch("briefing.pipeline.fetch_all", return_value=[_item("a")]), \
         patch("briefing.pipeline.load_history", return_value={"seen_ids": []}), \
         patch("briefing.pipeline.group_into_themes",
               side_effect=lambda items, voice=None: [{"name": "T", "emoji": "X", "items": items}]), \
         patch("briefing.pipeline.send_email"), \
         patch("briefing.pipeline.save_history"):
        run(cfg, history_path=str(tmp_path / "h.json"),
            now=datetime(2026, 6, 29, 9, 0, 0))  # 09:00 -> morning edition
    assert (docs / "index.html").exists()
    assert (docs / "editions" / "2026-06-29-morning.html").exists()
    assert (docs / "archive.html").exists()
    assert "Morning" in (docs / "index.html").read_text()

def test_run_no_fresh_items_skips_send(tmp_path):
    with patch("briefing.pipeline.fetch_all", return_value=[_item("a")]), \
         patch("briefing.pipeline.load_history", return_value={"seen_ids": ["a"]}), \
         patch("briefing.pipeline.send_email") as send, \
         patch("briefing.pipeline.save_history"):
        run(_cfg(), history_path=str(tmp_path / "h.json"))
    send.assert_not_called()
