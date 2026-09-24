from unittest.mock import patch, Mock
from briefing.sources.scrape import fetch_scrape

HTML = """<html><body>
<div class="post"><h2><a href="https://s/1">First</a></h2><p class="excerpt">e1</p></div>
<div class="post"><h2><a href="https://s/2">Second</a></h2><p class="excerpt">e2</p></div>
</body></html>"""

def test_scrape_uses_selectors():
    cfg = {"type": "scrape", "name": "Static", "url": "http://s",
           "item_selector": ".post", "title_selector": "h2 a",
           "link_selector": "h2 a", "summary_selector": "p.excerpt"}
    resp = Mock(); resp.text = HTML
    with patch("briefing.sources.scrape.fetch", return_value=resp):
        items = fetch_scrape(cfg)
    assert [i.title for i in items] == ["First", "Second"]
    assert items[0].url == "https://s/1"
    assert items[0].summary == "e1"
    assert items[0].source_type == "scrape"
