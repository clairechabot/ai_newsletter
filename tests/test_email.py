from datetime import datetime, timezone
from briefing.models import Item
from briefing.email import build_html_email, _recipients

def _item(t, st="rss", extra=None):
    return Item.make(source="Src", source_type=st, title=t, url="http://x/1",
                     summary="a summary", published=datetime.now(timezone.utc), extra=extra or {})

def test_build_html_contains_title_and_cards():
    themes = [{"name": "Theme A", "emoji": "X", "items": [_item("Headline One")]}]
    html = build_html_email("Claire's Briefing", themes)
    assert "Claire" in html  # title present (apostrophe may be escaped)
    assert "Theme A" in html
    assert "Headline One" in html
    assert "http://x/1" in html

def test_youtube_item_renders_embed():
    yt = _item("Vid", st="youtube", extra={"embed_url": "http://e/v1", "thumbnail": "http://t/1"})
    html = build_html_email("B", [{"name": "T", "emoji": "X", "items": [yt]}])
    assert "http://e/v1" in html or "http://t/1" in html

def test_titles_are_html_escaped():
    it = _item("AI raises $10M & acquires <Startup>")
    html = build_html_email("B", [{"name": "T & U", "emoji": "X", "items": [it]}])
    assert "&amp;" in html
    assert "&lt;Startup&gt;" in html
    assert "<Startup>" not in html  # raw angle brackets must not leak through

def test_javascript_url_is_blocked():
    it = _item("Click me")
    it.url = "javascript:alert(1)"
    html = build_html_email("B", [{"name": "T", "emoji": "X", "items": [it]}])
    assert "javascript:" not in html
    assert 'href=""' in html  # scheme-rejected url renders empty

def test_greeting_is_rendered():
    themes = [{"name": "T", "emoji": "X", "items": [_item("H")]}]
    html = build_html_email("B", themes, greeting="Welcome back.")
    assert "Welcome back." in html

def test_cover_mode_is_short_and_links_to_edition():
    themes = [{"name": "Theme A", "emoji": "X", "items": [_item("Opening")]},
              {"name": "Theme B", "emoji": "Y", "items": [_item("Second")]}]
    html = build_html_email("B", themes, edition_url="https://site/ed", cover=True)
    assert "Opening" in html            # the hero item is included
    assert "Second" not in html         # but not every item — it's a cover
    assert "Theme B" in html            # table of contents lists all themes
    assert "https://site/ed" in html    # links out to the full edition

def test_recipients_parsing(monkeypatch):
    monkeypatch.delenv("EMAIL_RECIPIENTS", raising=False)
    monkeypatch.delenv("RECIPIENTS", raising=False)
    monkeypatch.setenv("EMAIL_RECIPIENT", "a@x.com, b@y.com ,")
    assert _recipients() == ["a@x.com", "b@y.com"]

def test_recipients_fallback_env_names(monkeypatch):
    monkeypatch.delenv("EMAIL_RECIPIENT", raising=False)
    monkeypatch.delenv("EMAIL_RECIPIENTS", raising=False)
    monkeypatch.setenv("RECIPIENTS", "only@z.com")
    assert _recipients() == ["only@z.com"]

def test_theme_emoji_is_escaped():
    html = build_html_email("B", [{"name": "T", "emoji": "<img src=x>", "items": [_item("H")]}])
    assert "<img src=x>" not in html

def test_each_recipient_gets_own_message(monkeypatch):
    from unittest.mock import patch, MagicMock
    from briefing.email import send_email
    monkeypatch.setenv("EMAIL_SENDER", "me@x.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    monkeypatch.setenv("EMAIL_RECIPIENT", "a@x.com,b@y.com")
    server = MagicMock()
    with patch("briefing.email.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = server
        send_email("B", "<p>hi</p>")
    calls = server.sendmail.call_args_list
    assert [c.args[1] for c in calls] == [["a@x.com"], ["b@y.com"]]
    assert "b@y.com" not in calls[0].args[2]  # a never sees b's address

def test_preheader_is_hidden_and_escaped():
    html = build_html_email("B", [{"name": "T", "emoji": "X", "items": [_item("H")]}],
                            preheader="Today <b>big</b> news")
    assert "display:none" in html
    assert "Today &lt;b&gt;big&lt;/b&gt; news" in html

def test_top_pick_subject_trims_at_word():
    from briefing.email import top_pick_subject
    it = _item("European regulators finally agree on the long awaited artificial intelligence rulebook")
    subj = top_pick_subject("Brief", [{"name": "T", "emoji": "X", "items": [it]}], limit=40)
    assert subj.startswith("Brief | European regulators")
    assert subj.endswith("…") and len(subj) <= len("Brief | ") + 41
    assert top_pick_subject("Brief", []) == "Brief"

def test_send_email_uses_subject_override(monkeypatch):
    from unittest.mock import patch, MagicMock
    from briefing.email import send_email
    for k, v in {"EMAIL_SENDER": "me@x.com", "EMAIL_PASSWORD": "pw",
                 "EMAIL_RECIPIENT": "a@x.com"}.items():
        monkeypatch.setenv(k, v)
    server = MagicMock()
    with patch("briefing.email.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = server
        send_email("B", "<p/>", subject="B | Lead story")
    assert "Subject: B | Lead story" in server.sendmail.call_args.args[2]

def test_palette_applied_to_email():
    from briefing.theme import PALETTE
    html = build_html_email("The Edge", [{"name": "T", "emoji": "X", "items": [_item("H")]}])
    for key in ("orange", "black", "cobalt"):
        assert PALETTE[key] in html
    assert "$" not in html.split("<style>")[1].split("</style>")[0]  # every placeholder filled

def test_from_name_sets_sender_display_name(monkeypatch):
    from unittest.mock import patch, MagicMock
    from briefing.email import send_email
    for k, v in {"EMAIL_SENDER": "me@x.com", "EMAIL_PASSWORD": "pw",
                 "EMAIL_RECIPIENT": "a@x.com"}.items():
        monkeypatch.setenv(k, v)
    server = MagicMock()
    with patch("briefing.email.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = server
        send_email("The Edge", "<p/>", from_name="The Edge")
        send_email("The Edge", "<p/>")
    first, second = (c.args[2] for c in server.sendmail.call_args_list)
    assert "From: The Edge <me@x.com>" in first
    assert "From: me@x.com" in second
    assert server.sendmail.call_args_list[0].args[0] == "me@x.com"  # envelope stays bare
