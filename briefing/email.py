from __future__ import annotations
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

_CSS = (
    "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f5f5f7;margin:0}"
    ".wrapper{max-width:640px;margin:0 auto;padding:24px}"
    ".header h1{margin:0 0 4px}.date{color:#888;font-size:13px}"
    ".theme-title{font-size:18px;font-weight:700;margin:24px 0 8px}"
    ".card{background:#fff;border-radius:10px;padding:14px;margin:10px 0;"
    "box-shadow:0 1px 3px rgba(0,0,0,.08)}"
    ".card a{color:#1a1a1a;text-decoration:none;font-weight:600}"
    ".src{color:#999;font-size:12px}.footer{color:#aaa;font-size:12px;margin-top:24px}"
    ".greeting{font-style:italic;color:#444;margin:8px 0 16px}"
    ".readmore{display:inline-block;margin:16px 0;padding:10px 18px;background:#2f6f4f;"
    "color:#fff;border-radius:8px;text-decoration:none;font-weight:600}"
    ".toc{color:#666;font-size:14px}.toc li{margin:2px 0}"
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

def send_email(title, html, subject=None) -> None:
    """`subject` overrides the default "<title> - <date>" subject line."""
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
            msg["From"] = sender
            msg["To"] = rcpt
            msg.attach(MIMEText(html, "html", "utf-8"))
            server.sendmail(sender, [rcpt], msg.as_string())
    print(f"[email] sent to {len(recipients)} recipient(s)", flush=True)
