"""Web edition — a browsable HTML page of the same themed items the email
carries, plus a permanent per-edition archive.

Three pieces, all pure-ish (filesystem only, no network, no API keys):

* `build_web_edition(title, themes, ...)` -> a self-contained HTML string
  (inline CSS, no assets) suitable for GitHub Pages.
* `save_edition(out_dir, html, date_str, slot_key)` writes that page to both
  `<out_dir>/index.html` (the "current" edition Pages serves) and
  `<out_dir>/editions/<date>-<slot>.html` (a permanent copy).
* `build_archive_index(out_dir, site_title)` scans `editions/` and (re)writes
  `<out_dir>/archive.html`, a dated index of every past edition.

Publish by pointing GitHub Pages at the `<out_dir>` folder (default `docs/`),
or by copying the folder into a separate Pages repo (see the workflow). The
email links to the current edition via `web.edition_url` in config.
"""
from __future__ import annotations
import os
import glob
import re
from datetime import datetime, timezone
from html import escape
from briefing.theme import css
from briefing.priority import LABELS, reading_list

_EDITION_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.html$")

_CSS = css(
    "*{box-sizing:border-box}"
    "body{font-family:Georgia,'Times New Roman',serif;color:$ink;"
    "background:$white;margin:0;line-height:1.55}"
    ".wrap{max-width:760px;margin:0 auto;padding:0 20px 64px}"
    "header.masthead{text-align:center;padding:40px 20px 24px;background:$black;"
    "color:$white;border-bottom:5px solid $orange}"
    ".masthead h1{font-size:40px;margin:0;letter-spacing:1px}"
    ".masthead .date{color:$orange;font-size:14px;margin-top:6px;"
    "text-transform:uppercase;letter-spacing:2px}"
    ".greeting{font-style:italic;color:$ink;background:$orange_tint;"
    "border-left:4px solid $cobalt;border-radius:0 10px 10px 0;padding:16px 20px;margin:24px 0}"
    ".theme-title{font-size:24px;font-weight:700;margin:36px 0 4px;"
    "padding-bottom:6px;border-bottom:3px solid $orange}"
    ".card{background:$white;border:1px solid $rule;border-radius:12px;padding:18px 20px;"
    "margin:16px 0}"
    ".card .src{color:$cobalt;font-size:12px;font-weight:700;text-transform:uppercase;"
    "letter-spacing:1px}"
    ".card h3{margin:4px 0 8px;font-size:19px}"
    ".card a{color:$ink;text-decoration:none}.card a:hover{color:$cobalt;text-decoration:underline}"
    ".card p{margin:0;color:$muted}"
    ".card .hero img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;"
    "border-radius:8px;margin:0 0 12px}"
    ".card.has-thumb{display:grid;grid-template-columns:132px minmax(0,1fr);gap:18px;"
    "align-items:start}"
    ".card.has-thumb:not(:has(>.thumb)){display:block}"
    ".card .thumb img{display:block;width:132px;height:88px;object-fit:cover;border-radius:6px}"
    "@media (max-width:560px){.card.has-thumb{grid-template-columns:88px minmax(0,1fr);gap:12px}"
    ".card .thumb img{width:88px;height:60px}}"
    "footer{text-align:center;color:$muted;font-size:13px;margin-top:48px}"
    "footer a{color:$cobalt}"
    # Reading-priority labels (priority.py): orange = read first, cobalt = today.
    ".badge{display:inline-block;font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
    "font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;"
    "padding:2px 8px;border-radius:4px;margin-right:8px;vertical-align:1px}"
    ".badge-first{background:$orange;color:$black}"
    ".badge-today{background:$white;color:$cobalt;border:1px solid $cobalt}"
    ".badge-later{background:$rule;color:$muted}"
    ".card.card-first{border-left:5px solid $orange}"
    ".card .why{color:$ink;margin:0 0 8px}"
    ".reading{border:2px solid $black;border-radius:12px;padding:18px 22px;margin:24px 0}"
    ".reading-title{display:inline-block;margin:0 0 10px;font-size:14px;font-weight:700;"
    "text-transform:uppercase;letter-spacing:2px;border-bottom:3px solid $orange}"
    ".reading ol{margin:0;padding-left:22px}.reading li{margin:10px 0}"
    ".reading li::marker{color:$orange;font-weight:700}"
    ".reading a{color:$ink;font-weight:700;text-decoration:none}"
    ".reading a:hover{color:$cobalt;text-decoration:underline}"
    ".reading .src{color:$cobalt;font-size:12px;text-transform:uppercase;letter-spacing:1px}"
    ".reading .why{margin:2px 0 0;color:$muted}"
)


def _safe_url(url) -> str:
    url = (url or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


def _badge(item) -> str:
    tier = item.extra.get("priority")
    return (f'<span class="badge badge-{tier}">{escape(LABELS[tier])}</span>'
            if tier in LABELS else "")


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
    return (f'<section class="reading"><p class="reading-title">Read first today</p>'
            f'<ol>{rows}</ol></section>')


def _card(item) -> str:
    href = escape(_safe_url(item.url), quote=True)
    img = escape(_safe_url(item.extra.get("image") or item.extra.get("thumbnail", "")), quote=True)
    first = " card-first" if item.extra.get("priority") == "first" else ""
    why = item.extra.get("why")
    why_html = f'<p class="why"><b>Why it matters:</b> {escape(why)}</p>' if why else ""
    text = (f'<div class="src">{_badge(item)}{escape(item.source)}</div>'
            f'<h3><a href="{href}">{escape(item.title)}</a></h3>{why_html}'
            f'<p>{escape(item.summary)}</p>')
    # Hotlinked, so a publisher can break an image later: drop it rather than
    # show a broken-image icon.
    pic = (f'<img src="{img}" alt="" loading="lazy" referrerpolicy="no-referrer" '
           f'onerror="this.parentNode.remove()">')
    if img and (first or item.source_type == "youtube"):
        return f'<div class="card{first}"><a class="hero" href="{href}">{pic}</a>{text}</div>'
    if img:
        return (f'<div class="card has-thumb{first}"><a class="thumb" href="{href}">{pic}</a>'
                f'<div>{text}</div></div>')
    return f'<div class="card{first}">{text}</div>'


def build_web_edition(title, themes, *, greeting="", edition_label="",
                      date_str=None, archive_link="archive.html") -> str:
    """Render the full browsable edition as a self-contained HTML string."""
    date_str = date_str or datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    eyebrow = escape(edition_label or date_str)
    greet_html = f'<div class="greeting">{escape(greeting)}</div>' if greeting else ""
    blocks = ""
    for theme in themes:
        cards = "".join(_card(i) for i in theme["items"])
        blocks += (f'<p class="theme-title">{escape(theme.get("emoji", ""))} '
                   f'{escape(theme["name"])}</p>{cards}')
    footer = (f'<footer>Curated by Claude · '
              f'<a href="{escape(archive_link, quote=True)}">The Archive</a></footer>')
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)}</title><style>{_CSS}</style></head><body>'
        f'<header class="masthead"><h1>{escape(title)}</h1>'
        f'<div class="date">{eyebrow}</div></header>'
        f'<div class="wrap">{greet_html}{_reading_list(themes)}{blocks}{footer}</div>'
        '</body></html>'
    )


def save_edition(out_dir, html, date_str, slot_key) -> dict:
    """Write `html` to <out_dir>/index.html and a permanent dated copy under
    <out_dir>/editions/. Returns the two paths written."""
    editions_dir = os.path.join(out_dir, "editions")
    os.makedirs(editions_dir, exist_ok=True)
    index_path = os.path.join(out_dir, "index.html")
    edition_path = os.path.join(editions_dir, f"{date_str}-{slot_key}.html")
    for path in (index_path, edition_path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
    return {"index": index_path, "edition": edition_path}


def _list_editions(out_dir) -> list:
    """[(date, slot, filename)] for every editions/*.html, newest first."""
    found = []
    for path in glob.glob(os.path.join(out_dir, "editions", "*.html")):
        m = _EDITION_RE.match(os.path.basename(path))
        if m:
            found.append((m.group(1), m.group(2), os.path.basename(path)))
    found.sort(reverse=True)  # ISO dates sort lexically; newest first
    return found


def build_archive_index(out_dir, site_title="The Archive") -> str:
    """(Re)build <out_dir>/archive.html from the editions/ folder and return it."""
    rows = ""
    for date_str, slot, fname in _list_editions(out_dir):
        label = f"{date_str} · {slot.replace('-', ' ').title()}"
        rows += (f'<li><a href="editions/{escape(fname, quote=True)}">'
                 f'{escape(label)}</a></li>')
    if not rows:
        rows = "<li>No past editions yet.</li>"
    style = css(
        "body{font-family:Georgia,serif;color:$ink;background:$white;"
        "margin:0;line-height:1.6}.wrap{max-width:680px;margin:0 auto;padding:40px 20px}"
        "h1{border-bottom:3px solid $orange;padding-bottom:8px}"
        "ul{list-style:none;padding:0}li{padding:8px 0;border-bottom:1px solid $rule}"
        "a{color:$cobalt;text-decoration:none}a:hover{text-decoration:underline}"
        "p.back a{color:$muted}"
    )
    html = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(site_title)} — Archive</title><style>{style}</style></head>'
        f'<body><div class="wrap"><h1>{escape(site_title)} — Archive</h1>'
        f'<ul>{rows}</ul><p class="back"><a href="index.html">← Latest edition</a>'
        '</p></div></body></html>'
    )
    with open(os.path.join(out_dir, "archive.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    return html
