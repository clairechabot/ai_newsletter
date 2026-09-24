from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from briefing.models import Item
from briefing.images import add_images, image_from_html, absolute_image_url

ON = {"enabled": True}

def _item(uid, url=None, **extra):
    return Item.make(source="S", source_type="rss", title=f"T{uid}", url=url or f"https://x.com/{uid}",
                     summary="s", published=datetime.now(timezone.utc), extra=extra or None)

def _page(html, ctype="text/html; charset=utf-8", url=""):
    return MagicMock(text=html, headers={"content-type": ctype}, url=url)

def test_og_image_preferred_and_resolved_relative():
    html = ('<head><meta name="twitter:image" content="https://cdn.x/tw.jpg">'
            '<meta property="og:image" content="/img/og.png"></head>')
    assert image_from_html(html, "https://x.com/a/b") == "https://x.com/img/og.png"

def test_falls_back_to_twitter_then_link_and_rejects_bad_schemes():
    assert image_from_html('<meta name="twitter:image" content="//cdn.x/t.jpg">', "https://x.com/") == "https://cdn.x/t.jpg"
    assert image_from_html('<link rel="image_src" href="https://x/i.jpg">', "https://x/") == "https://x/i.jpg"
    assert image_from_html('<meta property="og:image" content="javascript:alert(1)">', "") == ""
    assert image_from_html("<p>no preview</p>", "https://x/") == ""
    assert absolute_image_url("data:image/png;base64,AAA") == ""

def test_disabled_makes_no_requests():
    items = [_item(0)]
    with patch("briefing.images.http_get") as get:
        add_images(items, {})
    get.assert_not_called()
    assert "image" not in items[0].extra

def test_uses_known_images_without_fetching():
    feed = _item(0, image="https://cdn/feed.jpg")
    vid = _item(1, thumbnail="https://i.ytimg.com/v.jpg")
    with patch("briefing.images.http_get") as get:
        add_images([feed, vid], ON)
    get.assert_not_called()
    assert feed.extra["image"] == "https://cdn/feed.jpg"
    assert vid.extra["image"] == "https://i.ytimg.com/v.jpg"

def test_fetches_page_and_fails_soft_per_item():
    good, bad, pdf = _item(0), _item(1), _item(2)
    def fake_get(url, **kw):
        assert kw["retries"] == 1 and kw["timeout"] == 5
        if url.endswith("/1"):
            raise OSError("403 blocked")
        if url.endswith("/2"):
            return _page("%PDF", ctype="application/pdf")
        return _page('<meta property="og:image" content="https://cdn/good.jpg">', url=url)
    with patch("briefing.images.http_get", side_effect=fake_get):
        add_images([good, bad, pdf], {"enabled": True, "timeout": 5})
    assert good.extra["image"] == "https://cdn/good.jpg"
    assert "image" not in bad.extra and "image" not in pdf.extra

def test_skips_items_without_a_web_url():
    odd = _item(0, url="mailto:someone@example.com")
    with patch("briefing.images.http_get") as get:
        add_images([odd], ON)
    get.assert_not_called()
