from datetime import datetime, timezone
from briefing.models import Item

def test_item_has_stable_id_from_url_when_not_given():
    a = Item.make(source="BBC", source_type="rss", title="T",
                  url="https://x.com/a", summary="s",
                  published=datetime(2026, 6, 4, tzinfo=timezone.utc))
    b = Item.make(source="BBC", source_type="rss", title="T2",
                  url="https://x.com/a", summary="s2",
                  published=datetime(2026, 6, 4, tzinfo=timezone.utc))
    assert a.id == b.id  # same url -> same id

def test_item_make_uses_explicit_id_when_given():
    it = Item.make(source="YT", source_type="youtube", title="V",
                   url="https://youtu.be/x", summary="",
                   published=datetime(2026, 6, 4, tzinfo=timezone.utc),
                   id="vid123")
    assert it.id == "vid123"
    assert it.extra == {}

from briefing.models import normalize_url, title_key, legacy_url_id

def test_normalize_url_strips_tracking_www_fragment_slash():
    assert normalize_url("http://WWW.Example.com/a/?utm_source=x&fbclid=1#top") == \
        "https://example.com/a"

def test_normalize_url_keeps_identifying_query():
    assert normalize_url("https://blog.com/?p=123&utm_medium=rss") == "https://blog.com?p=123"

def test_tracking_variants_share_an_id():
    mk = lambda u: Item.make(source="s", source_type="rss", title="t", url=u, summary="",
                             published=datetime(2026, 6, 4, tzinfo=timezone.utc))
    assert mk("https://x.com/a?utm_source=rss").id == mk("https://www.x.com/a/").id

def test_title_key_ignores_short_titles():
    assert title_key("News") == ""
    assert title_key("Europe passes the AI Act, finally!") == "europe passes the ai act finally"

def test_legacy_id_is_raw_sha1():
    import hashlib
    assert legacy_url_id("http://x/1") == hashlib.sha1(b"http://x/1").hexdigest()
