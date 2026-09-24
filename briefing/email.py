from __future__ import annotations
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape
from briefing.theme import css

_CSS = css(
    "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:$paper;"
    "color:$ink;margin:0}"
    ".wrapper{max-width:640px;margin:0 auto;padding:24px}"
    ".header{background:$black;border-bottom:4px solid $orange;border-radius:10px 10px 0 0;"
    "padding:20px 22px}"
    ".header h1{margin:0 0 4px;color:$white;letter-spacing:.5px}"
    ".date{color:$orange;font-size:13px;text-transform:uppercase;letter-spacing:1.5px}"
    ".theme-title{font-size:18px;font-weight:700;margin:24px 0 8px;color:$ink;"
    "border-left:4px solid $orange;padding-left:10px}"
    ".card{background:$white;border:1px solid $rule;border-radius:10px;padding:14px;"
    "margin:10px 0}"
    ".card a{color:$ink;text-decoration:none;font-weight:600}"
    ".card p{color:$muted}"
    ".src{color:$cobalt;font-size:12px;font-weight:700;text-transform:uppercase;"
    "letter-spacing:.5px}"
    ".footer{color:$muted;font-size:12px;margin-top:24px}"
    ".greeting{font-style:italic;color:$ink;background:$orange_tint;"
    "border-left:3px solid $cobalt;padding:12px 16px;margin:16px 0}"
    ".readmore{display:inline-block;margin:16px 0;padding:10px 18px;background:$orange;"
    "color:$black;border-radius:8px;text-decoration:none;font-weight:700}"
    ".toc{color:$ink;font-size:14px}.toc li{margin:2px 0}.toc li::marker{color:$cobalt}"
)

def _safe_url(url) -> str:
    """Only allow http(s) URLs into href/src; blank out anything else
    (e.g. javascript:, data:) to prevent script-URI injection."""
    url = (url or "").strip()
    return url if url.startswith(("http://", "https://")) else ""

def _card(item) -> str:
    href = escape(_safe_url(item.url), quote=True)
    if item.source_type == "youtube":
        thumb = escape(_safe_url(item.extra.get("thumbnail", "")), quote=True)
        media = f'<a href="{href}"><img src="{thumb}" width="100%" style="border-radius:8px"></a>'
    else:
        media = ""
    return (f'<div class="card"><div class="src">{escape(item.source)}</div>'
            f'<a href="{href}">{escape(item.title)}</a>'
            f'<p>{escape(item.summary)}</p>{media}</div>')

def _cover_body(themes, edition_url) -> str:
    """Short 'cover' email: today's opening item + a table of contents that
    links out to the full web edition. Used when email.mode == cover."""
    first = themes[0]["items"][0] if themes and themes[0]["items"] else None
    opening = _card(first) if first else ""
    toc = "".join(f'<li>{escape(t.get("emoji", ""))} {escape(t["name"])}</li>'
                  for t in themes)
    link = _safe_url(edition_url)
    button = (f'<a class="readmore" href="{escape(link, quote=True)}">'
              f'Read the full edition →</a>') if link else ""
    return (f'{opening}{button}'
            f'<p class="theme-title">In this edition</p><ul class="toc">{toc}</ul>')

def _preheader(text) -> str:
    """Hidden inbox-preview line (the grey snippet after the subject). Padded
    with zero-width spaces so clients don't pull body text in after it."""
    if not text:
        return ""
    pad = "&#8203;&nbsp;" * 60
    return ('<div style="display:none;max-height:0;overflow:hidden;opacity:0;'
            f'mso-hide:all">{escape(text[:140])}{pad}</div>')

def build_html_email(title, themes, *, greeting="", edition_url="", cover=False,
                     preheader="") -> str:
    now = datetime.now(timezone.utc).strftime("%A, %B %d")
    greet_html = f'<div class="greeting">{escape(greeting)}</div>' if greeting else ""
    if cover:
        body = _cover_body(themes, edition_url)
    else:
        body = ""
        for theme in themes:
            cards = "".join(_card(i) for i in theme["items"])
            body += (f'<p class="theme-title">{escape(theme.get("emoji", ""))} '
                     f'{escape(theme["name"])}</p>{cards}')
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<style>{_CSS}</style></head><body>{_preheader(preheader)}<div class="wrapper">'
            f'<div class="header"><h1>{escape(title)}</h1><div class="date">{now}</div></div>'
            f'{greet_html}{body}<div class="footer">Curated by Claude</div></div></body></html>')

def _recipients() -> list:
    """Recipients from EMAIL_RECIPIENT / EMAIL_RECIPIENTS / RECIPIENTS
    (whichever is set), comma-separated. Supports multiple readers."""
    raw = (os.environ.get("EMAIL_RECIPIENT")
           or os.environ.get("EMAIL_RECIPIENTS")
           or os.environ.get("RECIPIENTS", ""))
    return [a.strip() for a in raw.split(",") if a.strip()]

def top_pick_subject(title, themes, limit=60) -> str:
    """`Title | <lead headline>`, trimmed at a word boundary. Falls back to the
    plain title when there are no items."""
    first = next((t["items"][0] for t in themes if t.get("items")), None)
    if not first or not first.title.strip():
        return title
    lead = " ".join(first.title.split())
    if len(lead) > limit:
        lead = lead[:limit].rsplit(" ", 1)[0].rstrip(",;:-") + "…"
    return f"{title} | {lead}"

def send_email(title, html, subject=None, from_name="") -> None:
    """`subject` overrides the default "<title> - <date>" subject line.
    `from_name` is the sender name the inbox shows (e.g. "The Edge");
    blank shows the mailbox's own account name."""
    sender = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_PASSWORD"]
    recipients = _recipients()
    if not recipients:
        raise KeyError("EMAIL_RECIPIENT")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    subject = subject or f"{title} - {datetime.now(timezone.utc).strftime('%b %d, %Y')}"
    # One message per reader, each addressed only to them, so a multi-reader
    # list never exposes everyone's address in a shared To: header.
    with smtplib.SMTP(host, port) as server:
        server.ehlo(); server.starttls(); server.login(sender, password)
        for rcpt in recipients:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = formataddr((from_name, sender)) if from_name else sender
            msg["To"] = rcpt
            msg.attach(MIMEText(html, "html", "utf-8"))
            server.sendmail(sender, [rcpt], msg.as_string())
    print(f"[email] sent to {len(recipients)} recipient(s)", flush=True)
