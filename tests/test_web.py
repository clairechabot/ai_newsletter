from datetime import datetime, timezone
from pathlib import Path
from briefing.models import Item
from briefing.web import (build_web_edition, save_edition, build_archive_index,
                          collect_archive, tab_label)

def _item(t, st="rss", extra=None, url="http://x/1"):
    return Item.make(source="Src", source_type=st, title=t, url=url,
                     summary="a summary", published=datetime.now(timezone.utc),
                     extra=extra or {})

def _themes():
    return [{"name": "Theme A", "emoji": "*", "items": [_item("Headline One")]}]

def _body(html):
    return html.split("</style>")[1]

def test_build_web_edition_has_title_greeting_and_card():
    html = build_web_edition("Canopy", _themes(), greeting="Good morning.",
                             edition_label="Morning Edition", edition_date="2026-06-29")
    assert "Canopy" in html and "Good morning." in html
    assert "Theme A" in html and "Headline One" in html and "Morning Edition" in html
    assert "archive.html" in html  # footer + nav link to the archive
    assert "29 Jun" in _body(html)  # per-card date from edition_date

def test_web_edition_escapes_html():
    themes = [{"name": "A & B", "emoji": "*", "items": [_item("<script>x</script>")]}]
    html = build_web_edition("T & U", themes)
    assert "&amp;" in html
    assert "<script>x</script>" not in html  # raw markup must not leak

def test_embedded_data_cannot_close_the_script_block():
    themes = [{"name": "T", "emoji": "*", "items": [_item("</script><b>oops</b>", url="https://x/s")]}]
    html = build_web_edition("E", themes, edition_date="2026-06-29", slot_key="morning")
    data = html.split('<script id="edition-data" type="application/json">')[1].split("</script>")[0]
    assert "\\u003c/script>" in data and "</script" not in data
    import json
    row = json.loads(data)[0]
    assert row["title"] == "</script><b>oops</b>" and row["date"] == "2026-06-29"
    assert row["slot"] == "morning" and row["section"] == "T" and row["tab"] == "T"

def test_tab_label_shortens_on_word_boundary():
    assert tab_label("Price war") == "Price war"
    assert tab_label("Building on someone else's platform") == "Building on someone…"
    assert tab_label("Averyveryverylongsinglewordname") == "Averyveryverylongsin…"

def test_tabbar_uses_short_tab_label_and_counts():
    themes = [{"name": "Building on someone else's platform", "tab": "Platform risk", "emoji": "*",
               "items": [_item("A", extra={"priority": "first"}), _item("B", url="http://x/2")]},
              {"name": "Proof, not promises", "emoji": "*", "items": [_item("C", url="http://x/3")]}]
    body = _body(build_web_edition("E", themes))
    assert body.count('class="tab"') == 2 and body.count('class="panel"') == 2
    assert '<span class="ix">01</span>Platform risk<span class="n">2</span><span class="pip"' in body
    assert '<span class="ix">02</span>Proof, not promises<span class="n">1</span></button>' in body
    assert 'title="Building on someone else&#x27;s platform"' in body  # full name on hover

def test_youtube_thumbnail_rendered():
    yt = _item("Vid", st="youtube", extra={"thumbnail": "http://t/1.jpg"})
    html = build_web_edition("T", [{"name": "N", "emoji": "*", "items": [yt]}])
    assert "http://t/1.jpg" in html

def test_opening_and_chips_only_when_labelled():
    plain = _body(build_web_edition("E", _themes()))
    assert 'class="open"' not in plain and 'class="filter-row' not in plain
    it = _item("Hebbia raises", url="https://x/1", extra={"priority": "first", "why": "Competitor <funding>."})
    later = _item("Other", url="https://x/2", extra={"priority": "later"})
    body = _body(build_web_edition("E", [{"name": "T", "emoji": "X", "items": [later, it]}]))
    assert 'class="open"' in body and "Read first <span>1</span>" in body
    assert 'badge-first">Read first' in body and "Competitor &lt;funding&gt;." in body
    assert "<funding>" not in body.split('<script id="edition-data"')[0]
    assert 'data-f="first" aria-pressed="false">Read first<em>1</em>' in body
    # decks list Read first before Later
    deck = body.split('class="deck"')[1]
    assert deck.index("Hebbia raises") < deck.index("Other")

def test_deck_cards_carry_images_and_priority():
    mk = lambda t, **ex: Item.make(source="S", source_type="rss", title=t, url="https://x/" + t,
                                   summary="s", published=datetime.now(timezone.utc), extra=ex)
    items = [mk("a", priority="first", image="https://cdn/a.jpg"), mk("b", image="https://cdn/b.jpg"), mk("c")]
    body = _body(build_web_edition("E", [{"name": "T", "emoji": "X", "items": items}]))
    assert 'class="dcard first" data-p="first"' in body and 'class="dcard" data-p=""' in body
    assert body.count('src="https://cdn/a.jpg"') == 2  # opening hero card + deck card
    assert body.count('src="https://cdn/b.jpg"') == 1 and 'referrerpolicy="no-referrer"' in body

def test_save_edition_writes_index_and_dated_copy(tmp_path):
    out = str(tmp_path / "docs")
    paths = save_edition(out, "<html>hi</html>", "2026-06-29", "morning")
    assert Path(paths["index"]) == Path(out) / "index.html"
    assert Path(paths["edition"]) == Path(out) / "editions" / "2026-06-29-morning.html"
    assert Path(paths["index"]).read_text() == "<html>hi</html>"

def _edition(tmp_out, date, slot, items, section="Sec"):
    html = build_web_edition("E", [{"name": section, "emoji": "*", "items": items}],
                             edition_date=date, slot_key=slot)
    save_edition(str(tmp_out), html, date, slot)

def test_archive_merges_editions_dedups_and_lists_them(tmp_path):
    out = tmp_path / "docs"
    _edition(out, "2026-06-28", "evening",
             [_item("Old story", url="https://x/old", extra={"priority": "first", "why": "w"})])
    _edition(out, "2026-06-29", "morning",
             [_item("Old story again", url="https://x/old/"),  # same URL: first appearance wins
              _item("New story", url="https://x/new", extra={"priority": "today"})], section="Fresh")
    (out / "editions" / "2026-06-27-morning.html").write_text("legacy page without data")
    rows = collect_archive(str(out))
    assert [r["title"] for r in rows] == ["Old story", "New story"]
    assert rows[0]["date"] == "2026-06-28" and rows[0]["p"] == "first"
    assert rows[1]["section"] == "Fresh" and rows[1]["file"] == "2026-06-29-morning.html"
    html = build_archive_index(str(out), site_title="Canopy")
    assert (out / "archive.html").exists() and "Canopy — Archive" in html
    assert "2 stories · 3 editions" in html
    assert 'id="q"' in html and 'id="archive-data"' in html
    # every edition file is linked, newest first, including the legacy one
    assert html.index("2026-06-29") < html.index("2026-06-28") < html.index("2026-06-27")
    assert "editions/2026-06-27-morning.html" in html

def test_archive_index_empty(tmp_path):
    out = tmp_path / "docs"
    (out / "editions").mkdir(parents=True)
    html = build_archive_index(str(out))
    assert "No past editions yet." in html and "0 editions" in html

def test_palette_applied_to_web_and_archive(tmp_path):
    from briefing.theme import PALETTE
    page = build_web_edition("The Edge", [])
    archive = build_archive_index(str(tmp_path), site_title="The Edge")
    for html in (page, archive):
        style = html.split("<style>")[1].split("</style>")[0]
        assert PALETTE["orange"] in style and PALETTE["cobalt"] in style
        assert "$" not in style
