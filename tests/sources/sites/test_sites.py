from pathlib import Path
from unittest.mock import patch, Mock
from briefing.sources.sites import discover, get
import briefing.sources.sites.seedcamp as seedcamp

def test_discover_finds_seedcamp_not_example():
    mods = discover()
    assert "seedcamp" in mods
    assert "_example" not in mods  # underscore-prefixed are templates

def test_get_returns_callable():
    assert callable(get("seedcamp"))

def test_seedcamp_parses_fixture():
    html = (Path(__file__).parents[2] / "fixtures" / "seedcamp.html").read_text(encoding="utf-8")
    resp = Mock(); resp.text = html
    with patch("briefing.sources.sites.seedcamp.http_get", return_value=resp):
        items = seedcamp.fetch({"type": "site", "name": "Seedcamp", "module": "seedcamp"})
    assert {i.title for i in items} == {"Acme AI", "Beta Co"}
    assert all(i.source_type == "site" for i in items)
    assert items[0].url.startswith("https://")
