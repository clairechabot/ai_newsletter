import requests
from unittest.mock import patch, Mock
from briefing.sources._fetch import fetch, fetch_with_fallback, BROWSER_HEADERS

def test_browser_user_agent_present():
    assert "Mozilla/5.0" in BROWSER_HEADERS["User-Agent"]

def test_retries_then_succeeds():
    calls = {"n": 0}
    def side_effect(*a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            raise requests.ConnectionError("flaky")
        m = Mock(); m.raise_for_status = Mock(); return m
    with patch("briefing.sources._fetch.requests.request", side_effect=side_effect):
        fetch("http://x", retries=3, retry_delay=0)
    assert calls["n"] == 2

def test_raises_after_all_retries():
    with patch("briefing.sources._fetch.requests.request",
               side_effect=requests.ConnectionError("down")):
        try:
            fetch("http://x", retries=2, retry_delay=0)
            assert False, "expected RequestException"
        except requests.RequestException:
            pass

def _resp(status=200):
    m = Mock()
    if status >= 400:
        err = requests.HTTPError(response=Mock(status_code=status))
        m.raise_for_status = Mock(side_effect=err)
    else:
        m.raise_for_status = Mock()
    return m

def test_fallback_returns_direct_when_ok():
    with patch("briefing.sources._fetch.requests.request", return_value=_resp(200)) as req:
        fetch_with_fallback("http://x", retries=1, retry_delay=0)
    assert req.call_count == 1  # no relay needed

def test_fallback_uses_relay_on_403():
    seen = []
    def side_effect(method, url, **k):
        seen.append(url)
        return _resp(200) if "codetabs" in url else _resp(403)
    with patch("briefing.sources._fetch.requests.request", side_effect=side_effect):
        fetch_with_fallback("http://blocked/feed", retries=1, retry_delay=0)
    assert any("codetabs" in u for u in seen)  # fell through to a relay
    assert any("blocked%2Ffeed" in u for u in seen)  # target was url-encoded

def test_fallback_does_not_relay_on_404():
    with patch("briefing.sources._fetch.requests.request", return_value=_resp(404)) as req:
        try:
            fetch_with_fallback("http://x", retries=1, retry_delay=0)
            assert False, "expected HTTPError"
        except requests.HTTPError:
            pass
    assert req.call_count == 1  # 404 is a real miss, not a bot-wall

def test_fallback_tries_relay_when_200_fails_validation():
    good, challenge = _resp(200), _resp(200)
    challenge.text, good.text = "cf-challenge", "real feed"
    with patch("briefing.sources._fetch.requests.request",
               side_effect=[challenge, good]) as req:
        r = fetch_with_fallback("http://x", validate=lambda r: r.text == "real feed",
                                retries=1, retry_delay=0)
    assert r is good
    assert req.call_count == 2

def test_fallback_returns_direct_when_no_relay_validates():
    direct = _resp(200)
    with patch("briefing.sources._fetch.requests.request",
               side_effect=[direct, _resp(403), _resp(403)]):
        r = fetch_with_fallback("http://x", validate=lambda r: False,
                                retries=1, retry_delay=0)
    assert r is direct  # genuinely empty feed: keep the direct answer
