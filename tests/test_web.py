from datetime import datetime, timezone
from pathlib import Path
from briefing.models import Item
from briefing.web import build_web_edition, save_edition, build_archive_index

def _item(t, st="rss", extra=None):
    return Item.make(source="Src", source_type=st, title=t, url="http://x/1",
                     summary="a summary", published=datetime.now(timezone.utc),
                     extra=extra or {})

def _themes():
    return [{"name": "Theme A", "emoji": "*", "items": [_item("Headline One")]}]

def test_build_web_edition_has_title_greeting_and_card():
    html = build_web_edition("Canopy", _themes(), greeting="Good morning.",
                             edition_label="Morning Edition")
    assert "Canopy" in html
    assert "Good morning." in html
    assert "Theme A" in html
    assert "Headline One" in html
    assert "Morning Edition" in html
    assert "archive.html" in html  # footer links to the archive

def test_web_edition_escapes_html():
    themes = [{"name": "A & B", "emoji": "*", "items": [_item("<script>x</script>")]}]
    html = build_web_edition("T & U", themes)
    assert "&amp;" in html
    assert "<script>x</script>" not in html  # raw markup must not leak

def test_youtube_thumbnail_rendered():
    yt = _item("Vid", st="youtube", extra={"thumbnail": "http://t/1.jpg"})
    html = build_web_edition("T", [{"name": "N", "emoji": "*", "items": [yt]}])
    assert "http://t/1.jpg" in html

def test_save_edition_writes_index_and_dated_copy(tmp_path):
    out = str(tmp_path / "docs")
    paths = save_edition(out, "<html>hi</html>", "2026-06-29", "morning")
    assert Path(paths["index"]) == Path(out) / "index.html"
    assert Path(paths["edition"]) == Path(out) / "editions" / "2026-06-29-morning.html"
    assert Path(paths["index"]).read_text() == "<html>hi</html>"
    assert Path(paths["edition"]).read_text() == "<html>hi</html>"

def test_archive_index_lists_editions_newest_first(tmp_path):
    out = tmp_path / "docs"
    (out / "editions").mkdir(parents=True)
    for name in ("2026-06-28-evening.html", "2026-06-29-morning.html"):
        (out / "editions" / name).write_text("x")
    html = build_archive_index(str(out), site_title="Canopy")
    assert "Canopy — Archive" in html
    assert (out / "archive.html").exists()
    # newest edition appears before the older one
    assert html.index("2026-06-29") < html.index("2026-06-28")
    assert "editions/2026-06-29-morning.html" in html

def test_archive_index_empty(tmp_path):
    out = tmp_path / "docs"
    (out / "editions").mkdir(parents=True)
    html = build_archive_index(str(out))
    assert "No past editions yet." in html

def test_palette_applied_to_web_and_archive(tmp_path):
    from briefing.theme import PALETTE
    from briefing.web import build_web_edition, build_archive_index
    page = build_web_edition("The Edge", [])
    archive = build_archive_index(str(tmp_path), site_title="The Edge")
    for html in (page, archive):
        style = html.split("<style>")[1].split("</style>")[0]
        assert PALETTE["orange"] in style and PALETTE["cobalt"] in style
        assert "$" not in style
