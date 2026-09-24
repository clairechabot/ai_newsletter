from __future__ import annotations
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape
from briefing.theme import css
from briefing.priority import LABELS, reading_list

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
    # Reading-priority labels (priority.py): orange = read first, cobalt = today.
    ".badge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.8px;"
    "text-transform:uppercase;padding:2px 7px;border-radius:4px;margin-right:6px;"
    "vertical-align:1px}"
    ".badge-first{background:$orange;color:$black}"
    ".badge-today{background:$white;color:$cobalt;border:1px solid $cobalt}"
    ".badge-later{background:$paper;color:$muted}"
    ".card-first{border-left:4px solid $orange}"
    ".card img.hero{display:block;width:100%;height:auto;border-radius:6px;margin:0 0 10px}"
    ".card td.thumb{padding-right:12px}"
    ".card td.thumb img{display:block;width:88px;height:auto;border-radius:4px}"
    ".why{color:$ink;font-size:14px;margin:6px 0}"
    ".reading{background:$white;border:2px solid $black;border-radius:10px;"
    "padding:14px 18px;margin:16px 0}"
    ".reading-title{display:inline-block;margin:0 0 8px;font-size:13px;font-weight:700;"
    "text-transform:uppercase;letter-spacing:1px;color:$black;"
    "border-bottom:3px solid $orange}"
    ".reading ol{margin:0;padding-left:20px}.reading li{margin:8px 0}"
    ".reading li::marker{color:$orange;font-weight:700}"
    ".reading a{color:$ink;font-weight:700;text-decoration:none}"
    ".reading .why{margin:2px 0 0;color:$muted}"
    # Cover mode (email.mode: cover): short email that links to the web edition.
    ".e-counts{color:#CFCFCF;font-size:12px;line-height:1.6;text-align:right}"
    ".e-counts b{color:$white}"
    ".e-label{display:block;font-size:11px;font-weight:700;letter-spacing:1.4px;"
    "text-transform:uppercase;color:$black;border-bottom:2px solid $black;"
    "padding-bottom:6px;margin:22px 0 12px}"
    ".e-label span{float:right;color:$muted;letter-spacing:.5px;font-weight:400}"
    ".e-card{margin:0 0 20px}"
    ".e-card img.hero{display:block;width:100%;height:auto;border-radius:4px;margin:0 0 10px}"
    ".e-meta{font-size:11px;letter-spacing:.8px;text-transform:uppercase;color:$cobalt;"
    "font-weight:700;margin:0 0 4px}"
    ".e-title{font-size:18px;line-height:1.3;font-weight:700;color:$ink;text-decoration:none}"
    ".e-row .e-title{font-size:15px}"
    ".e-why{font-size:14px;line-height:1.45;color:$ink;margin:6px 0 0}"
    ".e-row{border-top:1px solid $rule;padding:12px 0}"
    ".e-row td.thumb{padding-right:12px;width:84px}"
    ".e-row td.thumb img{display:block;width:84px;height:63px;object-fit:cover;border-radius:3px}"
    ".e-also h5{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:$cobalt;"
    "margin:16px 0 4px}"
    ".e-also ul{margin:0;padding-left:16px}.e-also li{font-size:14px;line-height:1.4;margin:5px 0}"
    ".e-also li a{color:$ink;text-decoration:none}.e-also li span{color:$muted;font-size:12px}"
    ".e-cta{display:block;text-align:center;background:$orange;color:$black;font-size:15px;"
    "font-weight:700;padding:14px;border-radius:4px;margin:24px 0 8px;text-decoration:none}"
    ".e-foot{font-size:12px;color:$muted;line-height:1.6;margin-top:16px}"
    ".e-foot a{color:$cobalt}"
)

def _safe_url(url) -> str:
    """Only allow http(s) URLs into href/src; blank out anything else
    (e.g. javascript:, data:) to prevent script-URI injection."""
    url = (url or "").strip()
    return url if url.startswith(("http://", "https://")) else ""

def _badge(item) -> str:
    tier = item.extra.get("priority")
    return (f'<span class="badge badge-{tier}">{escape(LABELS[tier])}</span>'
            if tier in LABELS else "")

def _why(item) -> str:
    why = item.extra.get("why")
    return f'<p class="why"><b>Why it matters:</b> {escape(why)}</p>' if why else ""

def _reading_list(themes) -> str:
    """'Read first today' box at the top: the day's must-reads and why."""
    items = reading_list(themes)
    if not items:
        return ""
    rows = "".join(
        f'<li><a href="{escape(_safe_url(i.url), quote=True)}">{escape(i.title)}</a>'
        f' <span class="src">{escape(i.source)}</span>'
        + (f'<p class="why">{escape(i.extra["why"])}</p>' if i.extra.get("why") else "")
        + "</li>" for i in items)
    return f'<div class="reading"><p class="reading-title">Read first today</p><ol>{rows}</ol></div>'

def _image_url(item) -> str:
    return _safe_url(item.extra.get("image") or item.extra.get("thumbnail", ""))

def _card(item) -> str:
    href = escape(_safe_url(item.url), quote=True)
    img = escape(_image_url(item), quote=True)
    first = " card-first" if item.extra.get("priority") == "first" else ""
    text = (f'<div class="src">{_badge(item)}{escape(item.source)}</div>'
            f'<a href="{href}">{escape(item.title)}</a>{_why(item)}'
            f'<p>{escape(item.summary)}</p>')
    if img and (first or item.source_type == "youtube"):
        # The big picture goes to what to read first (and videos) only.
        return (f'<div class="card{first}"><a href="{href}"><img class="hero" src="{img}" '
                f'alt="" width="100%"></a>{text}</div>')
    if img:
        # A small thumbnail beside the text. A table, because Gmail ignores
        # floats, flex and grid.
        return (f'<div class="card{first}"><table role="presentation" width="100%" '
                f'cellpadding="0" cellspacing="0"><tr><td class="thumb" width="100" valign="top">'
                f'<a href="{href}"><img src="{img}" alt="" width="88"></a></td>'
                f'<td valign="top">{text}</td></tr></table></div>')
    return f'<div class="card{first}">{text}</div>'

def _split_by_priority(themes) -> tuple:
    """(read first, read today, [(section name, remaining items)]). Without
    any labels the lead story stands in for Read first."""
    items = [i for t in themes for i in t["items"]]
    firsts = [i for i in items if i.extra.get("priority") == "first"]
    todays = [i for i in items if i.extra.get("priority") == "today"]
    if not firsts and not todays and items:
        firsts = [items[0]]
    shown = {id(i) for i in firsts + todays}
    rest = [(t.get("tab") or t["name"], [i for i in t["items"] if id(i) not in shown])
            for t in themes]
    return firsts, todays, [(name, its) for name, its in rest if its]

def _e_card(item) -> str:
    href = escape(_safe_url(item.url), quote=True)
    img = escape(_image_url(item), quote=True)
    pic = f'<a href="{href}"><img class="hero" src="{img}" alt="" width="100%"></a>' if img else ""
    return (f'<div class="e-card">{pic}<div class="e-meta">{_badge(item)}{escape(item.source)}</div>'
            f'<a class="e-title" href="{href}">{escape(item.title)}</a>{_e_why(item, True)}</div>')

def _e_why(item, label=False) -> str:
    why = item.extra.get("why")
    if not why:
        return ""
    return f'<p class="e-why">{"<b>Why it matters:</b> " if label else ""}{escape(why)}</p>'

def _e_row(item) -> str:
    href = escape(_safe_url(item.url), quote=True)
    img = escape(_image_url(item), quote=True)
    text = (f'<div class="e-meta">{_badge(item)}{escape(item.source)}</div>'
            f'<a class="e-title" href="{href}">{escape(item.title)}</a>{_e_why(item)}')
    thumb = (f'<td class="thumb" valign="top"><a href="{href}"><img src="{img}" alt="" width="84"></a></td>'
             if img else "")
    return (f'<table class="e-row" role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{thumb}<td valign="top">{text}</td></tr></table>')

def _cover_body(themes, edition_url) -> str:
    """Short 'cover' email: Read first as image cards, Read today as thumbnail
    rows, everything else as one headline per line grouped by section, and a
    button to the full web edition. Used when email.mode == cover."""
    firsts, todays, rest = _split_by_priority(themes)
    n_rest = sum(len(its) for _, its in rest)
    out = ""
    if firsts:
        out += (f'<span class="e-label">Read first <span>{len(firsts)} '
                f'{"story" if len(firsts) == 1 else "stories"}</span></span>'
                + "".join(_e_card(i) for i in firsts))
    if todays:
        out += (f'<span class="e-label">Read today <span>{len(todays)} '
                f'{"story" if len(todays) == 1 else "stories"}</span></span>'
                + "".join(_e_row(i) for i in todays))
    if rest:
        lists = "".join(
            f'<h5>{escape(name)}</h5><ul>' + "".join(
                f'<li><a href="{escape(_safe_url(i.url), quote=True)}">{escape(i.title)}</a> '
                f'<span>{escape(i.source)}</span></li>' for i in its) + "</ul>"
            for name, its in rest)
        out += (f'<span class="e-label">Also in today\'s edition <span>{n_rest} '
                f'{"headline" if n_rest == 1 else "headlines"}</span></span>'
                f'<div class="e-also">{lists}</div>')
    link = _safe_url(edition_url)
    if link:
        out += f'<a class="e-cta" href="{escape(link, quote=True)}">Open the full edition →</a>'
    return out

def cover_preheader(themes, greeting="") -> str:
    """Inbox preview line for a cover email: the day's shape, then the lead titles."""
    items = [i for t in themes for i in t["items"]]
    firsts = [i for i in items if i.extra.get("priority") == "first"]
    todays = [i for i in items if i.extra.get("priority") == "today"]
    if not firsts and not todays:
        return greeting or (items[0].title if items else "")
    rest = len(items) - len(firsts) - len(todays)
    shape = f"{len(firsts)} to read first · {len(todays)} today · {rest} more."
    return shape + (" " + " · ".join(i.title for i in firsts) if firsts else "")

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
    counts = ""
    reading = _reading_list(themes)
    footer = '<div class="footer">Curated by Claude</div>'
    if cover:
        reading = ""  # the cover's Read first block replaces the list
        items = [i for t in themes for i in t["items"]]
        f = sum(1 for i in items if i.extra.get("priority") == "first")
        t = sum(1 for i in items if i.extra.get("priority") == "today")
        if f or t:
            counts = (f'<td class="e-counts" valign="bottom"><b>{f}</b> to read first<br>'
                      f'<b>{t}</b> for today · <b>{len(items) - f - t}</b> more</td>')
        link = _safe_url(edition_url)
        sources = len({i.source for i in items})
        footer = (f'<div class="e-foot">{escape(title)} is curated by Claude from {sources} sources.'
                  + (f'<br><a href="{escape(link, quote=True)}">Read on the web</a> · '
                     f'<a href="{escape(link.rstrip("/") + "/archive.html", quote=True)}">'
                     f'Search the archive</a>' if link else "") + '</div>')
    header = (f'<div class="header"><table role="presentation" width="100%" cellpadding="0" '
              f'cellspacing="0"><tr><td valign="bottom"><h1>{escape(title)}</h1>'
              f'<div class="date">{now}</div></td>{counts}</tr></table></div>')
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<style>{_CSS}</style></head><body>{_preheader(preheader)}<div class="wrapper">'
            f'{header}{greet_html}{reading}{body}{footer}</div></body></html>')

def _recipients() -> list:
    """Recipients from EMAIL_RECIPIENT / EMAIL_RECIPIENTS / RECIPIENTS
    (whichever is set), comma-separated. Supports multiple readers."""
    raw = (os.environ.get("EMAIL_RECIPIENT")
           or os.environ.get("EMAIL_RECIPIENTS")
           or os.environ.get("RECIPIENTS", ""))
    return [a.strip() for a in raw.split(",") if a.strip()]

def top_pick_subject(title, themes, limit=60) -> str:
    """`Title | <lead headline>`, trimmed at a word boundary. The lead is the
    first "Read first" item when priority labels are on, else the first item.
    Falls back to the plain title when there are no items."""
    must = reading_list(themes)
    first = must[0] if must else next((t["items"][0] for t in themes if t.get("items")), None)
    if not first or not first.title.strip():
        return title
    lead = " ".join(first.title.split())
    if len(lead) > limit:
        lead = lead[:limit].rsplit(" ", 1)[0].rstrip(",;:-") + "…"
    return f"{title} | {lead}"

def _smtp_settings() -> tuple:
    """(sender, password, host, port) from the environment. A secret that isn't
    set arrives from the workflow as "", not as missing."""
    sender = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_PASSWORD"]
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or 587)
    return sender, password, host, port


def _login(server, sender, password) -> None:
    try:
        server.login(sender, password)
    except smtplib.SMTPAuthenticationError as e:
        hint = ""
        if b"Application-specific password" in e.smtp_error or e.smtp_code == 534:
            hint = (" Gmail needs a 16-character App Password in EMAIL_PASSWORD, not the "
                    "account password: https://myaccount.google.com/apppasswords")
        raise RuntimeError(f"SMTP login failed for {sender}: {e.smtp_code} "
                           f"{e.smtp_error.decode(errors='replace')}.{hint}") from e


def check_login() -> bool:
    """Log in to the mail server and disconnect, so a bad password fails the
    run before any fetching or Claude spend. Skipped (returns False) when
    the email settings aren't configured at all."""
    if not os.environ.get("EMAIL_SENDER") or not os.environ.get("EMAIL_PASSWORD"):
        return False
    sender, password, host, port = _smtp_settings()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo(); server.starttls(); _login(server, sender, password)
    print(f"[email] login ok as {sender} via {host}:{port}", flush=True)
    return True


def send_email(title, html, subject=None, from_name="") -> None:
    """`subject` overrides the default "<title> - <date>" subject line.
    `from_name` is the sender name the inbox shows (e.g. "The Edge");
    blank shows the mailbox's own account name."""
    sender, password, host, port = _smtp_settings()
    recipients = _recipients()
    if not recipients:
        raise KeyError("EMAIL_RECIPIENT")
    subject = subject or f"{title} - {datetime.now(timezone.utc).strftime('%b %d, %Y')}"
    # One message per reader, each addressed only to them, so a multi-reader
    # list never exposes everyone's address in a shared To: header.
    with smtplib.SMTP(host, port) as server:
        server.ehlo(); server.starttls(); _login(server, sender, password)
        for rcpt in recipients:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = formataddr((from_name, sender)) if from_name else sender
            msg["To"] = rcpt
            msg.attach(MIMEText(html, "html", "utf-8"))
            server.sendmail(sender, [rcpt], msg.as_string())
    print(f"[email] sent to {len(recipients)} recipient(s)", flush=True)
