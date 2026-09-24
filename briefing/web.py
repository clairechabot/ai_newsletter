"""Web edition — the browsable version of the day's briefing, plus the Archive.

Layout (desktop first, works on a phone):

* the opening is the reading list: "Read first" stories as image cards and
  "Read today" as a compact list, both only when priority labels exist;
* a sticky tab bar with one tab per section (short `theme["tab"]` label,
  story count, an orange pip when the section holds a Read first);
* a row of priority chips that filters every section at once;
* one panel per section holding a horizontally scrolling, snap-by-card deck
  of story cards (arrow buttons on desktop, swipe on touch).

Without JavaScript the page still reads top to bottom: every panel is
rendered and the decks scroll with plain CSS; the script only wires the tabs,
chips and arrows.

Each edition embeds its stories as JSON in `<script id="edition-data">`, so
`build_archive_index` can rebuild the Archive from the saved editions alone:
every story ever sent, searchable, filterable by priority and source, grouped
by week, keeping the label it got on the day.

Three entry points, all filesystem-only (no network, no API keys):

* `build_web_edition(title, themes, ...)` -> HTML string
* `save_edition(out_dir, html, date_str, slot_key)` -> writes index.html and
  editions/<date>-<slot>.html
* `build_archive_index(out_dir, site_title)` -> (re)writes archive.html

Publish by pointing GitHub Pages at `out_dir` (default `docs/`).
"""
from __future__ import annotations
import os
import glob
import json
import re
from datetime import datetime, timezone
from html import escape
from briefing.theme import css
from briefing.priority import LABELS, TIERS, rank

_EDITION_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.html$")
_DATA_RE = re.compile(r'<script id="edition-data" type="application/json">(.*?)</script>', re.S)

TAB_MAX = 20  # characters; long section names overflow the tab bar

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@'
         '62..125,400..900&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:ital,wght@'
         '0,400;0,500;0,600;0,700;1,400&display=swap">')

# Shared by the edition and the archive: palette, type, badges, cards.
_BASE_CSS = css(
    "*{box-sizing:border-box;min-width:0}"
    "[hidden]{display:none!important}"
    "html{overflow-x:clip}"
    "body{margin:0;background:$white;color:$ink;"
    "font:15px/1.55 'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif}"
    "a{color:inherit}"
    ":focus-visible{outline:2px solid $orange;outline-offset:2px}"
    "img{max-width:100%}"
    ".mono{font-family:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace}"
    ".mast{background:$black;color:$white;border-bottom:5px solid $orange;padding:18px 40px;"
    "display:flex;justify-content:space-between;align-items:center;gap:12px 24px;flex-wrap:wrap}"
    ".word{font:900 30px/1 Archivo,'Arial Narrow',Arial,sans-serif;font-stretch:125%;"
    "letter-spacing:.03em;color:$white;text-decoration:none}"
    ".nav{display:flex;gap:18px;font:500 12px 'IBM Plex Mono',monospace;letter-spacing:.08em;"
    "text-transform:uppercase}"
    ".nav a{color:#BDBDBD;text-decoration:none}.nav a.on{color:$orange}"
    ".wrap{max-width:1180px;margin:0 auto;padding:0 40px}"
    ".dateline{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 16px;"
    "font:500 12px 'IBM Plex Mono',monospace;letter-spacing:.08em;text-transform:uppercase;"
    "color:$muted;padding:22px 0 0}"
    ".dateline b{color:$ink;font-weight:500}"
    ".greeting{font-style:italic;background:$orange_tint;border-left:4px solid $cobalt;"
    "border-radius:0 8px 8px 0;padding:14px 18px;margin:20px 0 0}"
    ".h{display:flex;align-items:center;gap:12px;font:800 12.5px Archivo,Arial,sans-serif;"
    "font-stretch:112%;letter-spacing:.16em;text-transform:uppercase;margin:0 0 14px}"
    ".h::after{content:'';flex:1;height:2px;background:$black}"
    ".h span{font:500 11px 'IBM Plex Mono',monospace;letter-spacing:.06em;color:$muted}"
    ".meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;"
    "font:500 11px 'IBM Plex Mono',monospace;letter-spacing:.05em;text-transform:uppercase;"
    "color:$cobalt}"
    ".meta time{color:$muted}"
    ".badge{display:inline-block;font:700 10px/1.6 'IBM Plex Sans',Arial,sans-serif;"
    "letter-spacing:.08em;text-transform:uppercase;padding:1px 7px;border-radius:2px;"
    "white-space:nowrap}"
    ".badge-first{background:$orange;color:$black}"
    ".badge-today{color:$cobalt;box-shadow:inset 0 0 0 1px $cobalt;background:$white}"
    ".badge-later{background:$paper;color:$muted}"
    "a.t{color:$ink;text-decoration:none}a.t:hover{color:$cobalt;text-decoration:underline}"
    ".why{font-size:13.5px;line-height:1.4}.why b{color:$cobalt;font-weight:600}"
    ".preview{color:$muted;font-size:13.5px;line-height:1.5;margin:0;"
    "display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}"
    ".dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:5px}"
    ".dot.first{background:$orange}.dot.today{background:$cobalt}"
    ".chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center}"
    ".chips .lbl{font:500 11px 'IBM Plex Mono',monospace;letter-spacing:.08em;"
    "text-transform:uppercase;color:$muted;margin-right:4px}"
    ".chip{appearance:none;cursor:pointer;font:500 12.5px 'IBM Plex Sans',sans-serif;"
    "padding:5px 11px;border-radius:999px;border:1px solid $rule;background:$white;color:$ink}"
    ".chip em{font:400 11px 'IBM Plex Mono',monospace;font-style:normal;color:$muted;margin-left:4px}"
    ".chip[aria-pressed=true]{background:$black;border-color:$black;color:$white}"
    ".chip[aria-pressed=true] em{color:#BDBDBD}"
    "footer{background:$black;color:#BDBDBD;padding:20px 40px;margin-top:40px;"
    "font:12px 'IBM Plex Mono',monospace;letter-spacing:.04em;display:flex;flex-wrap:wrap;"
    "justify-content:space-between;gap:8px}"
    "footer a{color:$orange}"
    "@media (max-width:640px){.wrap{padding:0 16px}.mast{padding:14px 16px}"
    ".word{font-size:24px}footer{padding:18px 16px}}"
    "@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}"
)

_EDITION_CSS = css(
    ".open{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:32px;"
    "padding:22px 0 30px;align-items:start}"
    ".hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:20px}"
    ".hcard{display:flex;flex-direction:column;border:1px solid $rule;border-radius:4px;"
    "overflow:hidden;background:$white}"
    ".hcard>a>img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block}"
    ".hcard .body{padding:14px 16px 16px;display:grid;gap:8px}"
    ".hcard h3{font:700 21px/1.2 Archivo,Arial,sans-serif;margin:0;text-wrap:balance}"
    ".hcard .why{background:$orange_tint;padding:8px 10px;border-radius:2px;font-size:14px}"
    ".hcard .why b{display:block;font:500 10.5px 'IBM Plex Mono',monospace;letter-spacing:.08em;"
    "text-transform:uppercase;color:#8A3207;margin-bottom:1px}"
    ".tlist{display:grid;gap:10px}"
    ".trow{display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;padding:12px;"
    "border:1px solid $rule;border-radius:4px}"
    ".trow.noimg{grid-template-columns:minmax(0,1fr)}"
    ".trow>a>img{width:96px;height:72px;object-fit:cover;border-radius:2px;display:block}"
    ".trow h4{font:700 15.5px/1.25 Archivo,Arial,sans-serif;margin:3px 0 4px}"
    ".tabbar{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.94);"
    "backdrop-filter:blur(8px);border-top:2px solid $black;border-bottom:1px solid $rule}"
    ".tabbar-in{max-width:1180px;margin:0 auto;padding:0 40px;position:relative}"
    ".tabs{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}"
    ".tabs::-webkit-scrollbar{display:none}"
    ".tab{position:relative;flex:none;appearance:none;background:none;border:0;cursor:pointer;"
    "white-space:nowrap;padding:16px 11px 14px;font:700 11.5px 'IBM Plex Sans',sans-serif;"
    "letter-spacing:.06em;text-transform:uppercase;color:$muted}"
    ".tab .ix{font:500 12px 'IBM Plex Mono',monospace;color:$orange;margin-right:7px;letter-spacing:0}"
    ".tab .n{font:500 11px 'IBM Plex Mono',monospace;color:$muted;margin-left:6px;letter-spacing:0}"
    ".tab .pip{display:inline-block;width:7px;height:7px;border-radius:50%;background:$orange;"
    "margin-left:7px;vertical-align:1px}"
    ".tab:hover{color:$ink}.tab[aria-selected=true]{color:$black}"
    ".tab::after{content:'';position:absolute;left:11px;right:11px;bottom:-1px;height:3px;"
    "background:$orange;transform:scaleX(0);transition:transform .2s ease}"
    ".tab[aria-selected=true]::after{transform:scaleX(1)}"
    ".filter-row{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;align-items:center;"
    "padding:14px 0 0}"
    ".panel{padding:16px 0 40px}"
    ".sec-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;"
    "gap:8px 24px;margin-bottom:18px}"
    ".sec-head h2{font:900 clamp(26px,3.2vw,38px)/1.05 Archivo,Arial,sans-serif;margin:0;"
    "letter-spacing:-.005em}"
    ".sec-meta{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center;"
    "font:12px 'IBM Plex Mono',monospace;color:$muted}"
    ".deck-wrap{position:relative}"
    ".deck{display:flex;gap:22px;overflow-x:auto;overflow-y:hidden;scroll-snap-type:x mandatory;"
    "scroll-padding-inline:2px;padding:2px 2px 16px;scrollbar-width:thin;"
    "scrollbar-color:$rule transparent;-webkit-overflow-scrolling:touch}"
    ".deck::-webkit-scrollbar{height:8px}.deck::-webkit-scrollbar-thumb{background:$rule;"
    "border-radius:100px}.deck::-webkit-scrollbar-track{background:transparent}"
    ".dcard{flex:0 0 auto;width:312px;scroll-snap-align:start;display:flex;flex-direction:column;"
    "border:1px solid $rule;border-radius:4px;background:$white;overflow:hidden}"
    ".dcard.first{box-shadow:inset 0 4px 0 $orange}"
    ".dcard>a>img{width:100%;aspect-ratio:3/2;object-fit:cover;display:block}"
    ".dcard .body{padding:12px 14px 14px;display:grid;gap:7px;align-content:start}"
    ".dcard h3{font:700 18px/1.2 Archivo,Arial,sans-serif;margin:0;text-wrap:balance}"
    ".deck-nav{position:absolute;top:calc(50% - 30px);width:38px;height:38px;border-radius:50%;"
    "border:1px solid $rule;background:$white;box-shadow:0 2px 8px rgba(0,0,0,.12);"
    "display:grid;place-items:center;cursor:pointer;color:$ink;z-index:2;padding:0}"
    ".deck-nav svg{width:18px;height:18px}"
    ".deck-nav.prev{left:-19px}.deck-nav.next{right:-19px}"
    ".deck-nav[disabled]{opacity:0;pointer-events:none}"
    ".deck-count{font:12px 'IBM Plex Mono',monospace;color:$muted;margin-top:2px;min-height:1.2em}"
    ".empty-note{font-size:14px;color:$muted;padding:18px 0}"
    "@media (max-width:900px){.open{grid-template-columns:minmax(0,1fr);gap:24px}}"
    # Phone: opening stacks, tabs scroll with a fade hint, decks bleed to the
    # screen edge and swipe card by card; arrows go.
    "@media (max-width:640px){.tabbar-in{padding:0}"
    ".tabbar-in::after{content:'';position:absolute;top:0;right:0;bottom:0;width:36px;"
    "background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.96));pointer-events:none}"
    ".tab{padding:14px 12px 12px}.tabs{padding-left:6px;padding-right:36px}"
    ".deck{margin:0 -16px;padding:2px 16px 14px;gap:14px;scroll-padding-inline:16px}"
    ".dcard{width:min(300px,80vw)}.deck-nav{display:none}.filter-row{justify-content:flex-start}"
    ".hcard h3{font-size:19px}}"
)

_EDITION_JS = r"""
(function(){
  var tabs=[].slice.call(document.querySelectorAll('.tab'));
  var panels=[].slice.call(document.querySelectorAll('.panel'));
  var chips=[].slice.call(document.querySelectorAll('.filter-row .chip'));
  var filter='all', current=0;
  function layoutDeck(panel){
    var deck=panel.querySelector('.deck'); if(!deck) return;
    var cards=[].slice.call(deck.querySelectorAll('.dcard')), n=0;
    cards.forEach(function(c){var on=filter==='all'||c.getAttribute('data-p')===filter;c.hidden=!on;if(on)n++;});
    var empty=panel.querySelector('.empty-note'), wrap=panel.querySelector('.deck-wrap');
    if(empty) empty.hidden=n>0; if(wrap) wrap.hidden=n===0;
    var count=panel.querySelector('.sec-count');
    if(count) count.textContent=filter==='all'?cards.length+' stories':n+' of '+cards.length+' stories';
    var w=deck.clientWidth, total=deck.scrollWidth, first=cards.filter(function(c){return !c.hidden;})[0];
    var gap=parseFloat(getComputedStyle(deck).columnGap||getComputedStyle(deck).gap)||22;
    var per=first?Math.max(1,Math.floor((w+gap)/(first.offsetWidth+gap))):n;
    var dc=panel.querySelector('.deck-count');
    if(dc) dc.textContent=n>per?'Showing '+Math.min(per,n)+' of '+n+' \u00b7 scroll or use the arrows for the rest':'';
    var prev=panel.querySelector('.prev'), next=panel.querySelector('.next');
    function sync(){ if(prev) prev.disabled=deck.scrollLeft<=2; if(next) next.disabled=deck.scrollLeft+w>=total-2; }
    sync(); deck.onscroll=sync;
    if(prev) prev.onclick=function(){deck.scrollBy({left:-w*0.9,behavior:'smooth'});};
    if(next) next.onclick=function(){deck.scrollBy({left:w*0.9,behavior:'smooth'});};
  }
  function show(n){
    current=n;
    tabs.forEach(function(t){t.setAttribute('aria-selected',String(+t.getAttribute('data-n')===n));});
    panels.forEach(function(p){p.hidden=+p.getAttribute('data-n')!==n;});
    if(panels[n]) layoutDeck(panels[n]);
    try{history.replaceState(null,'','#s'+(n+1));}catch(e){}
  }
  tabs.forEach(function(t){t.addEventListener('click',function(){show(+t.getAttribute('data-n'));});});
  chips.forEach(function(b){b.addEventListener('click',function(){
    filter=b.getAttribute('data-f');
    chips.forEach(function(x){x.setAttribute('aria-pressed',String(x===b));});
    tabs.forEach(function(t,n){
      var has=filter==='all'||!!panels[n].querySelector('.dcard[data-p="'+filter+'"]');
      t.hidden=!has;
    });
    var firstVisible=tabs.map(function(t,n){return t.hidden?-1:n;}).filter(function(n){return n>=0;})[0];
    show(tabs[current]&&!tabs[current].hidden?current:(firstVisible==null?0:firstVisible));
  });});
  window.addEventListener('resize',function(){if(panels[current]) layoutDeck(panels[current]);});
  var m=/^#s(\d+)$/.exec(location.hash), start=m?Math.min(panels.length-1,Math.max(0,+m[1]-1)):0;
  if(panels.length) show(start);
})();
"""

_CHEV = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
         'aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>')
_CHEV_L = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
           'aria-hidden="true"><path d="m15 6-6 6 6 6"/></svg>')


def _safe_url(url) -> str:
    url = (url or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


def _image(item) -> str:
    return _safe_url(item.extra.get("image") or item.extra.get("thumbnail", ""))


def tab_label(name, limit=TAB_MAX) -> str:
    """A short label for the tab bar when Claude didn't supply one: whole
    words up to `limit` characters, then an ellipsis."""
    name = " ".join((name or "").split())
    if len(name) <= limit:
        return name
    cut = name[:limit].rsplit(" ", 1)[0].rstrip(",;:&-") or name[:limit]
    return cut + "…"


def _json_for_html(data) -> str:
    """JSON safe to embed in a <script> block."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # `<` as \u003c keeps "</script" and "<!--" out of the script block.
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _badge(item) -> str:
    tier = item.extra.get("priority")
    return (f'<span class="badge badge-{tier}">{escape(LABELS[tier])}</span>'
            if tier in LABELS else "")


def _meta(item, date_str) -> str:
    return (f'<div class="meta">{_badge(item)}<span>{escape(item.source)}</span>'
            f'<time>{escape(date_str)}</time></div>')


def _pic(item, cls="") -> str:
    """Linked image, or "" when the item has none. Hotlinked, so a broken
    image removes itself rather than showing an icon."""
    img = _image(item)
    if not img:
        return ""
    href = escape(_safe_url(item.url), quote=True)
    return (f'<a href="{href}" class="{cls}" tabindex="-1"><img src="{escape(img, quote=True)}" '
            f'alt="" loading="lazy" referrerpolicy="no-referrer" '
            f'onerror="this.parentNode.remove()"></a>')


def _title_link(item, tag="h3") -> str:
    href = escape(_safe_url(item.url), quote=True)
    return f'<{tag}><a class="t" href="{href}">{escape(item.title)}</a></{tag}>'


def _why(item, label="Why:") -> str:
    why = item.extra.get("why")
    return f'<div class="why"><b>{label}</b> {escape(why)}</div>' if why else ""


def _hcard(item, date_str) -> str:
    why = item.extra.get("why")
    why_html = (f'<div class="why"><b>Why it matters</b>{escape(why)}</div>' if why else "")
    return (f'<article class="hcard">{_pic(item)}<div class="body">{_meta(item, date_str)}'
            f'{_title_link(item)}{why_html}</div></article>')


def _trow(item, date_str) -> str:
    pic = _pic(item)
    return (f'<article class="trow{"" if pic else " noimg"}">{pic}<div>{_meta(item, date_str)}'
            f'{_title_link(item, "h4")}{_why(item)}</div></article>')


def _dcard(item, date_str) -> str:
    tier = item.extra.get("priority", "")
    preview = f'<p class="preview">{escape(item.summary)}</p>' if item.summary else ""
    return (f'<article class="dcard{" first" if tier == "first" else ""}" data-p="{escape(tier)}">'
            f'{_pic(item)}<div class="body">{_meta(item, date_str)}{_title_link(item)}'
            f'{_why(item)}{preview}</div></article>')


def _opening(themes, date_str) -> str:
    """The reading list: Read first as image cards, Read today as a list.
    Empty when nothing is labelled (priority off)."""
    items = [i for t in themes for i in t["items"]]
    firsts = [i for i in items if i.extra.get("priority") == "first"]
    todays = [i for i in items if i.extra.get("priority") == "today"]
    if not firsts and not todays:
        return ""
    cols = ""
    if firsts:
        cols += (f'<div><h2 class="h">Read first <span>{len(firsts)}</span></h2>'
                 f'<div class="hero">{"".join(_hcard(i, date_str) for i in firsts)}</div></div>')
    if todays:
        cols += (f'<div><h2 class="h">Read today <span>{len(todays)}</span></h2>'
                 f'<div class="tlist">{"".join(_trow(i, date_str) for i in todays)}</div></div>')
    return f'<div class="open">{cols}</div>'


def _filter_row(themes) -> str:
    items = [i for t in themes for i in t["items"]]
    if not any(i.extra.get("priority") in TIERS for i in items):
        return ""
    counts = {"all": len(items)}
    for tier in TIERS:
        counts[tier] = sum(1 for i in items if i.extra.get("priority") == tier)
    chips = "".join(
        f'<button class="chip" type="button" data-f="{k}" aria-pressed="{"true" if k == "all" else "false"}">'
        f'{"All" if k == "all" else escape(LABELS[k])}<em>{counts[k]}</em></button>'
        for k in ("all",) + TIERS)
    return f'<div class="wrap"><div class="filter-row chips"><span class="lbl">Show</span>{chips}</div></div>'


def _tabbar(themes) -> str:
    tabs = ""
    for n, theme in enumerate(themes):
        first = sum(1 for i in theme["items"] if i.extra.get("priority") == "first")
        label = theme.get("tab") or tab_label(theme["name"])
        tabs += (f'<button class="tab" role="tab" id="tab-{n}" aria-controls="panel-{n}" '
                 f'aria-selected="{"true" if n == 0 else "false"}" data-n="{n}" '
                 f'title="{escape(theme["name"], quote=True)}"><span class="ix">{n + 1:02d}</span>'
                 f'{escape(label)}<span class="n">{len(theme["items"])}</span>'
                 + (f'<span class="pip" title="{first} to read first"></span>' if first else "")
                 + "</button>")
    return (f'<nav class="tabbar" aria-label="Sections"><div class="tabbar-in">'
            f'<div class="tabs" role="tablist">{tabs}</div></div></nav>')


def _panel(n, theme, date_str) -> str:
    items = sorted(theme["items"], key=rank)
    first = sum(1 for i in items if i.extra.get("priority") == "first")
    today = sum(1 for i in items if i.extra.get("priority") == "today")
    dots = ((f'<span><i class="dot first"></i>{first} read first</span>' if first else "")
            + (f'<span><i class="dot today"></i>{today} read today</span>' if today else ""))
    cards = "".join(_dcard(i, date_str) for i in items)
    return (f'<section class="panel" id="panel-{n}" role="tabpanel" aria-labelledby="tab-{n}" '
            f'data-n="{n}"><div class="wrap"><div class="sec-head"><h2>{escape(theme["name"])}</h2>'
            f'<div class="sec-meta"><span class="sec-count">{len(items)} stories</span>{dots}</div></div>'
            f'<div class="deck-wrap"><button class="deck-nav prev" type="button" '
            f'aria-label="Previous cards">{_CHEV_L}</button><div class="deck" tabindex="0">{cards}</div>'
            f'<button class="deck-nav next" type="button" aria-label="Next cards">{_CHEV}</button></div>'
            f'<div class="deck-count"></div>'
            f'<p class="empty-note" hidden>No stories in this section match the filter.</p>'
            f'</div></section>')


def _edition_data(themes, edition_date, slot_key) -> list:
    """What the Archive needs from this edition, one row per story."""
    rows = []
    for theme in themes:
        for i in theme["items"]:
            rows.append({
                "title": i.title, "url": _safe_url(i.url), "source": i.source,
                "summary": (i.summary or "")[:280], "image": _image(i),
                "date": edition_date, "slot": slot_key,
                "p": i.extra.get("priority") or "", "why": i.extra.get("why") or "",
                "section": theme["name"], "tab": theme.get("tab") or tab_label(theme["name"]),
            })
    return rows


def _shell(title, page_title, body, extra_css, script, nav_on) -> str:
    nav = (f'<a class="{"on" if nav_on == "today" else ""}" href="index.html">Today</a>'
           f'<a class="{"on" if nav_on == "archive" else ""}" href="archive.html">Archive</a>')
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(page_title)}</title>{FONTS}<style>{_BASE_CSS}{extra_css}</style></head>'
        f'<body><header class="mast"><a class="word" href="index.html">{escape(title)}</a>'
        f'<nav class="nav">{nav}</nav></header><main>{body}</main>'
        f'<footer><span>{escape(title)} · curated by Claude</span>'
        f'<a href="{"archive.html" if nav_on == "today" else "index.html"}">'
        f'{"Browse the archive →" if nav_on == "today" else "← Today’s edition"}</a></footer>'
        f'{script}</body></html>'
    )


def build_web_edition(title, themes, *, greeting="", edition_label="", date_str=None,
                      edition_date=None, slot_key="edition", archive_link="archive.html") -> str:
    """Render the full browsable edition as a self-contained HTML string."""
    now = datetime.now(timezone.utc)
    date_str = date_str or now.strftime("%A %d %B %Y")
    edition_date = edition_date or now.strftime("%Y-%m-%d")
    short_date = escape(datetime.strptime(edition_date, "%Y-%m-%d").strftime("%d %b").lstrip("0"))
    items = [i for t in themes for i in t["items"]]
    sources = len({i.source for i in items})
    dateline = (f'<div class="dateline"><span><b>{escape(date_str)}</b>'
                + (f' · {escape(edition_label)}' if edition_label else "")
                + f'</span><span>{len(items)} stories from {sources} sources</span></div>')
    greet_html = f'<div class="greeting">{escape(greeting)}</div>' if greeting else ""
    panels = "".join(_panel(n, t, short_date) for n, t in enumerate(themes))
    body = (f'<div class="wrap">{dateline}{greet_html}{_opening(themes, short_date)}</div>'
            f'{_tabbar(themes)}{_filter_row(themes)}{panels}')
    data = (f'<script id="edition-data" type="application/json">'
            f'{_json_for_html(_edition_data(themes, edition_date, slot_key))}</script>')
    script = data + f"<script>{_EDITION_JS}</script>"
    page_title = f"{title} — {edition_label}" if edition_label else title
    return _shell(title, page_title, body, _EDITION_CSS, script, "today")


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


def _read_edition_data(path) -> list:
    """Stories embedded in a saved edition, or [] for pages without data."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            m = _DATA_RE.search(fh.read())
        rows = json.loads(m.group(1)) if m else []
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("url") and r.get("title")]


def collect_archive(out_dir) -> list:
    """Every story from every saved edition, oldest edition first, one row per
    URL (a story that ran twice keeps its first appearance, as in the Grove)."""
    seen, rows = set(), []
    for date_str, slot, fname in reversed(_list_editions(out_dir)):
        for r in _read_edition_data(os.path.join(out_dir, "editions", fname)):
            key = r["url"].split("#")[0].rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            r["date"], r["slot"], r["file"] = date_str, slot, fname
            rows.append(r)
    return rows


_ARCHIVE_CSS = css(
    ".a-head{padding:26px 0 6px;display:flex;flex-wrap:wrap;align-items:flex-end;"
    "justify-content:space-between;gap:8px 20px}"
    ".a-head h1{font:900 40px/1 Archivo,Arial,sans-serif;font-stretch:125%;margin:0;letter-spacing:.01em}"
    ".stats{font:12px 'IBM Plex Mono',monospace;color:$muted;letter-spacing:.04em}"
    ".tools{display:grid;gap:12px;margin:16px 0 8px;padding:16px;background:$paper;border-radius:4px}"
    ".search{position:relative}"
    ".search svg{position:absolute;left:12px;top:50%;transform:translateY(-50%);width:18px;height:18px;color:$muted}"
    ".search input{width:100%;font:16px 'IBM Plex Sans',sans-serif;padding:11px 14px 11px 40px;"
    "border:2px solid $black;border-radius:4px;background:$white;color:$ink}"
    ".row{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center}"
    ".row .lbl{font:500 11px 'IBM Plex Mono',monospace;letter-spacing:.08em;text-transform:uppercase;"
    "color:$muted;min-width:64px}"
    ".row select{font:14px 'IBM Plex Sans',sans-serif;padding:6px 10px;border:1px solid $rule;"
    "border-radius:999px;background:$white;color:$ink;max-width:100%}"
    ".count{display:flex;justify-content:space-between;align-items:center;"
    "font:12px 'IBM Plex Mono',monospace;color:$muted;margin:14px 0 2px}"
    ".linkbtn{appearance:none;background:none;border:0;cursor:pointer;color:$cobalt;"
    "font:500 13px 'IBM Plex Sans',sans-serif;text-decoration:underline;padding:4px}"
    "details.wk{border-bottom:1px solid $rule}"
    "details.wk>summary{list-style:none;display:grid;grid-template-columns:18px minmax(0,1fr) auto;"
    "gap:12px;align-items:center;padding:14px 0;cursor:pointer}"
    "details.wk>summary::-webkit-details-marker{display:none}"
    ".chev{width:18px;height:18px;transition:transform .18s ease}"
    "details[open]>summary .chev{transform:rotate(90deg)}"
    ".wk-name{font:800 19px/1.2 Archivo,Arial,sans-serif}"
    ".wk-meta{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;"
    "font:12px 'IBM Plex Mono',monospace;color:$muted;margin-top:3px}"
    ".thumbs{display:flex;padding-left:8px}"
    ".thumbs img{width:42px;height:42px;object-fit:cover;border-radius:3px;border:2px solid $white;"
    "margin-left:-10px;box-shadow:0 0 0 1px $rule}"
    "details[open]>summary .thumbs{display:none}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,210px),1fr));gap:16px;"
    "padding:4px 0 22px}"
    ".acard{display:flex;flex-direction:column;border:1px solid $rule;border-radius:4px;overflow:hidden;"
    "background:$white;text-decoration:none;color:$ink}"
    ".acard:hover h4{color:$cobalt;text-decoration:underline}"
    ".acard img{width:100%;aspect-ratio:16/10;object-fit:cover;display:block}"
    ".acard .body{padding:10px 12px 12px;display:grid;gap:6px;align-content:start}"
    ".acard h4{font:700 15px/1.25 Archivo,Arial,sans-serif;margin:0}"
    ".acard .tag{font:11px 'IBM Plex Mono',monospace;color:$muted}"
    ".acard .why{font-size:12.5px;color:#333}"
    "details.more{margin:-6px 0 20px}"
    "details.more>summary{list-style:none;cursor:pointer;display:inline-flex;gap:8px;align-items:center;"
    "font:500 13px 'IBM Plex Sans',sans-serif;color:$cobalt;padding:6px 0}"
    "details.more>summary::-webkit-details-marker{display:none}"
    "details.more>summary .chev{width:14px;height:14px}"
    ".mlist{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:0 24px;margin-top:6px}"
    ".mrow{display:grid;grid-template-columns:48px minmax(0,1fr);gap:10px;align-items:center;padding:8px 0;"
    "border-top:1px solid $rule;text-decoration:none;color:$ink}"
    ".mrow.noimg{grid-template-columns:minmax(0,1fr)}"
    ".mrow img{width:48px;height:36px;object-fit:cover;border-radius:2px}"
    ".mrow b{font:600 13.5px/1.3 Archivo,Arial,sans-serif;display:block}"
    ".mrow:hover b{color:$cobalt;text-decoration:underline}"
    ".mrow span{font:11px 'IBM Plex Mono',monospace;color:$muted}"
    ".empty{padding:28px 0;text-align:center;color:$muted}"
    ".editions{margin-top:36px;padding-top:18px;border-top:2px solid $black}"
    ".editions ul{list-style:none;margin:8px 0 0;padding:0;display:grid;"
    "grid-template-columns:repeat(auto-fill,minmax(min(100%,220px),1fr));gap:4px 20px}"
    ".editions li{padding:6px 0;border-bottom:1px solid $rule;font-size:14px}"
    ".editions a{color:$cobalt;text-decoration:none}.editions a:hover{text-decoration:underline}"
)

_ARCHIVE_JS = r"""
(function(){
  var all=JSON.parse(document.getElementById('archive-data').textContent);
  var LABEL={first:'Read first',today:'Read today',later:'Later'};
  var MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function safe(u){return /^https?:\/\//.test(u||'')?u:'#';}
  function day(d){return new Date(d+'T12:00:00Z');}
  function fmt(d){var x=day(d);return x.getUTCDate()+' '+MON[x.getUTCMonth()];}
  function monday(d){var x=day(d),wd=(x.getUTCDay()+6)%7;x.setUTCDate(x.getUTCDate()-wd);return x.toISOString().slice(0,10);}
  function img(i,cls){return i.image?'<img class="'+(cls||'')+'" src="'+esc(i.image)+'" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">':'';}
  function badge(p){return p&&LABEL[p]?'<span class="badge badge-'+p+'">'+LABEL[p]+'</span>':'';}
  var q=document.getElementById('q'), prio=document.getElementById('prio'), src=document.getElementById('src');
  var clear=document.getElementById('clear'), count=document.getElementById('count'), box=document.getElementById('groups');
  var st={q:'',p:'all',s:'all'};
  var sources=[]; all.forEach(function(i){if(sources.indexOf(i.source)<0)sources.push(i.source);}); sources.sort();
  src.innerHTML='<option value="all">All '+sources.length+' sources</option>'+sources.map(function(s){return '<option value="'+esc(s)+'">'+esc(s)+'</option>';}).join('');
  var latest=all.length?all.map(function(i){return i.date;}).sort().slice(-1)[0]:null;
  var thisWeek=latest?monday(latest):null, openWeeks={}; if(thisWeek) openWeeks[thisWeek]=true;
  var chev='<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';
  function weekLabel(m){
    var end=day(m); end.setUTCDate(end.getUTCDate()+6);
    var range=fmt(m)+' \u2013 '+fmt(end.toISOString().slice(0,10));
    var diff=thisWeek?Math.round((day(thisWeek)-day(m))/864e5/7):9;
    return [diff===0?'This week':diff===1?'Last week':'Week of '+fmt(m),range];
  }
  function render(){
    [].slice.call(prio.querySelectorAll('.chip')).forEach(function(b){b.setAttribute('aria-pressed',String(b.getAttribute('data-v')===st.p));});
    var hits=all.filter(function(i){return (st.p==='all'||i.p===st.p)&&(st.s==='all'||i.source===st.s)&&(!st.q||(i.title+' '+i.source+' '+i.why+' '+i.summary+' '+i.section).toLowerCase().indexOf(st.q)>=0);});
    var filtered=!!(st.q||st.p!=='all'||st.s!=='all');
    count.textContent=filtered?hits.length+' of '+all.length+' stories match':all.length+' stories';
    clear.hidden=!filtered;
    var groups={}, order=[];
    hits.forEach(function(i){var m=monday(i.date); if(!groups[m]){groups[m]=[];order.push(m);} groups[m].push(i);});
    order.sort().reverse();
    box.innerHTML=order.length?order.map(function(m){
      var list=groups[m].slice().sort(function(a,b){return b.date<a.date?-1:b.date>a.date?1:0;});
      var wl=weekLabel(m), f=list.filter(function(i){return i.p==='first';}).length;
      var top=filtered?list:list.filter(function(i){return i.p==='first'||i.p==='today';});
      var rest=filtered?[]:list.filter(function(i){return i.p!=='first'&&i.p!=='today';});
      var cards=top.map(function(i){return '<a class="acard" href="'+esc(safe(i.url))+'" target="_blank" rel="noopener">'+img(i)+'<div class="body"><div class="meta">'+badge(i.p)+'<span>'+esc(i.source)+'</span></div><h4>'+esc(i.title)+'</h4>'+(i.p==='first'&&i.why?'<div class="why">'+esc(i.why)+'</div>':'')+'<div class="tag">'+fmt(i.date)+' \u00b7 '+esc(i.tab||i.section)+'</div></div></a>';}).join('');
      var more=rest.length?'<details class="more"><summary>'+chev+'Show '+rest.length+' more '+(rest.length===1?'story':'stories')+'</summary><div class="mlist">'+rest.map(function(i){return '<a class="mrow'+(i.image?'':' noimg')+'" href="'+esc(safe(i.url))+'" target="_blank" rel="noopener">'+img(i)+'<div><b>'+esc(i.title)+'</b><span>'+esc(i.source)+' \u00b7 '+fmt(i.date)+'</span></div></a>';}).join('')+'</div></details>':'';
      var open=filtered||openWeeks[m];
      return '<details class="wk" data-m="'+m+'"'+(open?' open':'')+'><summary>'+chev+'<div><div class="wk-name">'+wl[0]+'</div><div class="wk-meta"><span>'+wl[1]+'</span><span>'+list.length+' stories</span>'+(f?'<span><i class="dot first"></i>'+f+' read first</span>':'')+'</div></div><div class="thumbs">'+list.slice(0,4).map(function(i){return img(i);}).join('')+'</div></summary>'+(cards?'<div class="grid">'+cards+'</div>':'')+more+'</details>';
    }).join(''):'<p class="empty">'+(all.length?'No stories match. Try a shorter search or clear the filters.':'No stories yet. The first edition fills this in.')+'</p>';
    [].slice.call(box.querySelectorAll('details.wk')).forEach(function(d){d.addEventListener('toggle',function(){if(!filtered){if(d.open)openWeeks[d.getAttribute('data-m')]=true;else delete openWeeks[d.getAttribute('data-m')];}});});
  }
  q.addEventListener('input',function(){st.q=q.value.trim().toLowerCase();render();});
  [].slice.call(prio.querySelectorAll('.chip')).forEach(function(b){b.addEventListener('click',function(){st.p=b.getAttribute('data-v');render();});});
  src.addEventListener('change',function(){st.s=src.value;render();});
  clear.addEventListener('click',function(){st={q:'',p:'all',s:'all'};q.value='';src.value='all';render();});
  render();
})();
"""


def build_archive_index(out_dir, site_title="The Archive") -> str:
    """(Re)build <out_dir>/archive.html from the saved editions and return it:
    every story ever sent, searchable and filterable, plus a list of editions."""
    rows = collect_archive(out_dir)
    editions = _list_editions(out_dir)
    dates = sorted({r["date"] for r in rows})
    stats = (f'{len(rows)} stories · {len(editions)} editions · '
             f'{escape(datetime.strptime(dates[0], "%Y-%m-%d").strftime("%d %b").lstrip("0"))} – '
             f'{escape(datetime.strptime(dates[-1], "%Y-%m-%d").strftime("%d %b %Y").lstrip("0"))}'
             if dates else f'{len(editions)} editions')
    chips = "".join(
        f'<button class="chip" type="button" data-v="{k}" aria-pressed="{"true" if k == "all" else "false"}">'
        f'{"All" if k == "all" else escape(LABELS[k])}</button>' for k in ("all",) + TIERS)
    ed_rows = "".join(
        f'<li><a href="editions/{escape(fname, quote=True)}">'
        f'{escape(date_str)} · {escape(slot.replace("-", " ").title())}</a></li>'
        for date_str, slot, fname in editions) or "<li>No past editions yet.</li>"
    body = (
        f'<div class="wrap"><div class="a-head"><h1>Archive</h1><div class="stats">{stats}</div></div>'
        '<div class="tools"><label class="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'
        '<input id="q" type="search" placeholder="Search headlines, sources and why lines" '
        'aria-label="Search the archive"></label>'
        f'<div class="row"><span class="lbl">Priority</span><div class="chips" id="prio">{chips}</div></div>'
        '<div class="row"><span class="lbl">Source</span><select id="src" aria-label="Filter by source"></select></div></div>'
        '<div class="count"><span id="count"></span><button class="linkbtn" id="clear" type="button" hidden>Clear filters</button></div>'
        '<div id="groups"></div>'
        f'<section class="editions"><h2 class="h">Editions <span>{len(editions)}</span></h2><ul>{ed_rows}</ul></section>'
        '</div>')
    script = (f'<script id="archive-data" type="application/json">{_json_for_html(rows)}</script>'
              f'<script>{_ARCHIVE_JS}</script>')
    html = _shell(site_title, f"{site_title} — Archive", body, _ARCHIVE_CSS, script, "archive")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "archive.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    return html
