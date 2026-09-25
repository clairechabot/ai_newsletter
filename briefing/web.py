"""Web edition — the browsable version of the day's briefing, plus the Archive.

Layout (desktop first, works on a phone), built for triage:

* a sticky triage bar: jump links to Summary / Read first / Read today / Skim
  and a "2 of 4 read" progress bar;
* "The day in 30 seconds" (summary.py) beside a time budget (5 min, 15 min,
  +10 min), only when a summary exists;
* one numbered reading order: Read first, then Read today, in Claude's rank
  order, each with a read time, the why line, other sources for a cluster, a
  "Mark as read" toggle and (Read first by default) a picture;
* everything else as a skim list per section; tap a headline for its gist.

Without JavaScript the page still reads top to bottom: every gist is open
and every jump link is a plain anchor; the script only adds the read state
(kept in this browser's localStorage), the gist toggles and smooth scrolling.

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
from briefing.priority import LABELS, TIERS, triage, all_items, read_minutes, display_title
from briefing.summary import ref_target

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
    "#summary,#order,#skim,.item,.skim-col{scroll-margin-top:64px}"
    # Sticky triage bar: jump links on the left, reading progress on the right.
    ".tbar{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.95);"
    "-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border-bottom:1px solid $rule}"
    ".tbar-in{max-width:1180px;margin:0 auto;padding:0 40px;display:flex;align-items:center;"
    "justify-content:space-between;gap:0 24px;flex-wrap:wrap}"
    ".tjump{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}"
    ".tjump::-webkit-scrollbar{display:none}"
    ".tj{flex:none;white-space:nowrap;padding:15px 11px 13px;font:700 11.5px 'IBM Plex Sans',sans-serif;"
    "letter-spacing:.06em;text-transform:uppercase;color:$ink;text-decoration:none}"
    ".tj:hover{color:$cobalt}"
    ".tj .ix{font:500 12px 'IBM Plex Mono',monospace;color:$orange;margin-right:7px;letter-spacing:0}"
    ".tj .n{font:500 11px 'IBM Plex Mono',monospace;color:$muted;margin-left:6px;letter-spacing:0}"
    ".prog{display:flex;align-items:center;gap:10px;font:500 12px 'IBM Plex Mono',monospace;"
    "color:$muted;padding:8px 0}"
    ".prog b{color:$ink;font-weight:500}"
    ".track{display:block;width:96px;height:6px;background:$paper;border-radius:3px;overflow:hidden}"
    ".fill{display:block;height:100%;width:0;background:$orange;transition:width .25s ease}"
    # The day in 30 seconds + time budget.
    ".sum{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));"
    "gap:28px 40px;padding:26px 0 36px;align-items:start}"
    ".sum-main{grid-column:span 2;min-width:min(100%,340px)}"
    ".sum .h{margin:0 0 18px}"
    ".takeaways{list-style:none;margin:0;padding:0;display:grid;gap:18px}"
    ".takeaways li{display:grid;grid-template-columns:34px minmax(0,1fr);gap:6px}"
    ".takeaways .ix{font:500 13px/2.1 'IBM Plex Mono',monospace;color:$orange}"
    ".takeaways p{font:500 22px/1.32 Archivo,Arial,sans-serif;margin:0;text-wrap:pretty;"
    "letter-spacing:-.005em}"
    ".takeaways p b{font-weight:800}"
    ".jump{display:inline-block;padding:6px 0 0;font:500 11.5px 'IBM Plex Mono',monospace;"
    "letter-spacing:.06em;text-transform:uppercase;color:$cobalt;text-decoration:none}"
    ".jump:hover{text-decoration:underline}"
    ".budget{border:2px solid $black;border-radius:4px;padding:18px 20px 12px}"
    ".budget .bt{font:800 12.5px Archivo,Arial,sans-serif;font-stretch:112%;letter-spacing:.16em;"
    "text-transform:uppercase;margin:0 0 6px}"
    ".brow{display:grid;grid-template-columns:72px minmax(0,1fr);gap:10px;align-items:baseline;"
    "border-top:1px solid $rule;padding:12px 0;color:$ink;text-decoration:none}"
    ".brow:hover{color:$cobalt}"
    ".brow .time{font:500 16px 'IBM Plex Mono',monospace;color:$orange}"
    ".brow .what{font:600 14.5px/1.4 'IBM Plex Sans',sans-serif}"
    ".brow .what span{display:block;font-weight:400;font-size:13px;color:$muted}"
    # Reading order.
    ".order{padding:0 0 40px}.order .h{margin:0 0 4px}"
    ".sum+.order{padding-top:0}.dateline+.order,.greeting+.order{padding-top:26px}"
    ".item{display:grid;grid-template-columns:64px minmax(0,1fr) auto;gap:4px 20px;padding:22px 0;"
    "border-bottom:1px solid $rule;transition:opacity .2s ease}"
    ".item.read{opacity:.5}"
    ".num{font:900 40px/1 Archivo,Arial,sans-serif;font-stretch:112%;color:$orange;padding-top:2px}"
    ".item.today .num{color:$cobalt}.item.read .num{color:$muted}"
    ".item-body{display:grid;gap:9px;align-content:start;max-width:720px}"
    ".meta .quiet{color:$muted}"
    ".item h3{font:700 25px/1.18 Archivo,Arial,sans-serif;margin:0;text-wrap:balance}"
    ".whybox{background:$orange_tint;padding:9px 12px;border-radius:2px;font-size:14.5px;line-height:1.45}"
    ".whybox b{display:block;font:500 10.5px 'IBM Plex Mono',monospace;letter-spacing:.08em;"
    "text-transform:uppercase;color:#8A3207;margin-bottom:2px}"
    ".gist{color:$muted;font-size:14px;line-height:1.5;margin:0}"
    ".also{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13.5px;color:$muted}"
    ".also a{color:$cobalt}"
    ".acts{display:flex;gap:10px;align-items:center;padding-top:4px}"
    ".mark{appearance:none;cursor:pointer;white-space:nowrap;font:500 12.5px 'IBM Plex Sans',sans-serif;"
    "padding:5px 12px;border-radius:999px;border:1px solid $rule;background:$white;color:$ink}"
    ".mark[aria-pressed=true]{background:$black;border-color:$black;color:$white}"
    ".open-link{font:500 12.5px 'IBM Plex Sans',sans-serif;color:$cobalt}"
    ".item-pic{display:block;width:260px}"
    ".item-pic img{display:block;width:260px;aspect-ratio:16/9;object-fit:cover;border-radius:4px;"
    "border:1px solid $rule}"
    # Skim.
    ".skim{padding:0 0 48px}.skim .h{margin:0 0 6px}"
    ".skim-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));"
    "gap:8px 36px;align-items:start}"
    ".skim-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;"
    "padding:16px 0 8px;border-bottom:2px solid $black}"
    ".skim-head h3{font:800 19px/1.2 Archivo,Arial,sans-serif;margin:0}"
    ".skim-head span{font:12px 'IBM Plex Mono',monospace;color:$muted;white-space:nowrap}"
    ".srow{border-bottom:1px solid $rule}"
    ".stog{appearance:none;width:100%;text-align:left;background:none;border:0;cursor:pointer;"
    "padding:10px 0;display:grid;grid-template-columns:minmax(0,1fr) 16px;gap:10px;align-items:start;"
    "color:$ink;font:inherit}"
    ".stog:hover{color:$cobalt}"
    ".stog b{display:block;font:600 14.5px/1.3 Archivo,Arial,sans-serif}"
    ".stog .src{font:11px 'IBM Plex Mono',monospace;color:$muted}"
    ".stog .sign{font:500 14px/1.3 'IBM Plex Mono',monospace;color:$muted}"
    ".sgist{padding:0 26px 12px 0;font-size:13.5px;line-height:1.5;color:#333333;display:grid;gap:6px}"
    ".sgist a{color:$cobalt;font-weight:500;justify-self:start}"
    "@media (max-width:900px){.item{grid-template-columns:64px minmax(0,1fr)}"
    ".item-pic{grid-column:2;width:100%}.item-pic img{width:100%}}"
    "@media (max-width:760px){.sum-main{grid-column:auto}}"
    "@media (max-width:640px){.tbar-in{padding:0 16px}.tjump{margin-left:-11px}"
    ".item{grid-template-columns:44px minmax(0,1fr);gap:4px 12px}.num{font-size:30px}"
    ".item h3{font-size:21px}.takeaways p{font-size:19px}.takeaways li{grid-template-columns:28px minmax(0,1fr)}}"
)

# Progressive enhancement only: without it every section is open and every
# jump link is a plain anchor. Read state lives in this browser (localStorage).
_EDITION_JS = r"""
(function(){
  var order=document.getElementById('order'), key=order&&order.getAttribute('data-key');
  var read={};
  try{read=JSON.parse(localStorage.getItem(key)||'{}')||{};}catch(e){}
  function save(){try{localStorage.setItem(key,JSON.stringify(read));}catch(e){}}
  var items=[].slice.call(document.querySelectorAll('.item'));
  var done=document.getElementById('done'), fill=document.getElementById('fill');
  function paint(){
    var n=0;
    items.forEach(function(el){
      var r=!!read[el.getAttribute('data-n')]; if(r) n++;
      el.classList.toggle('read',r);
      var num=el.querySelector('.num'); num.textContent=r?'\u2713':num.getAttribute('data-num');
      var b=el.querySelector('.mark'); b.setAttribute('aria-pressed',String(r));
      b.textContent=r?'Read \u2713':'Mark as read';
    });
    if(done) done.textContent=n;
    if(fill) fill.style.width=(items.length?n/items.length*100:0)+'%';
  }
  items.forEach(function(el){
    var b=el.querySelector('.mark'); b.hidden=false;
    b.addEventListener('click',function(){
      var i=el.getAttribute('data-n'); if(read[i]) delete read[i]; else read[i]=true;
      save(); paint();
    });
  });
  var prog=document.querySelector('.prog'); if(prog) prog.hidden=false;
  paint();
  var skim=document.getElementById('skim'), openAll=skim&&skim.getAttribute('data-expanded')==='true';
  [].slice.call(document.querySelectorAll('.stog')).forEach(function(b){
    var g=document.getElementById(b.getAttribute('aria-controls'));
    function set(open){b.setAttribute('aria-expanded',String(open)); if(g) g.hidden=!open;
      b.querySelector('.sign').textContent=open?'\u2212':'+';}
    set(openAll);
    b.addEventListener('click',function(){set(b.getAttribute('aria-expanded')!=='true');});
  });
  var still=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  [].slice.call(document.querySelectorAll('a.go')).forEach(function(a){
    a.addEventListener('click',function(e){
      var id=a.getAttribute('href').slice(1), el=document.getElementById(id); if(!el) return;
      e.preventDefault();
      window.scrollTo({top:el.getBoundingClientRect().top+window.scrollY-64,behavior:still?'auto':'smooth'});
      try{history.replaceState(null,'','#'+id);}catch(x){}
    });
  });
})();
"""

_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
                 "nine", "ten")
READING_IMAGES = ("first", "all", "none")


def _safe_url(url) -> str:
    url = (url or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


def _image(item) -> str:
    return _safe_url(item.extra.get("image") or item.extra.get("thumbnail", ""))


def tab_label(name, limit=TAB_MAX) -> str:
    """A short label for a section when Claude didn't supply one: whole
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


def _words(n) -> str:
    return _NUMBER_WORDS[n] if 0 <= n < len(_NUMBER_WORDS) else str(n)


def _plural(n, one, many) -> str:
    return f"{n} {one if n == 1 else many}"


def _story_range(first, last) -> str:
    """"story 1", "stories 1 and 2", "stories 1–3"."""
    if first == last:
        return f"story {first}"
    if last == first + 1:
        return f"stories {first} and {last}"
    return f"stories {first}–{last}"


def _section_of(themes) -> dict:
    return {id(i): (t.get("tab") or tab_label(t["name"])) for t in themes for i in t["items"]}


def _triage_bar(summary, order, n_skim) -> str:
    firsts = [n for n, i in enumerate(order) if i.extra.get("priority") == "first"]
    todays = [n for n, i in enumerate(order) if i.extra.get("priority") == "today"]
    links = []
    if summary:
        links.append(("Summary", "", "summary"))
    if firsts:
        links.append(("Read first", str(len(firsts)), f"order-{firsts[0]}"))
    if todays:
        links.append(("Read today", str(len(todays)), f"order-{todays[0]}"))
    if order and not firsts and not todays:
        links.append(("Reading order", str(len(order)), "order"))
    if n_skim:
        links.append(("Skim", str(n_skim), "skim"))
    tabs = "".join(
        f'<a class="tj go" href="#{target}"><span class="ix">{n:02d}</span>{label}'
        + (f'<span class="n">{count}</span>' if count else "") + "</a>"
        for n, (label, count, target) in enumerate(links, 1))
    prog = (f'<div class="prog" hidden><span><b id="done">0</b> of {len(order)} read</span>'
            f'<span class="track"><span class="fill" id="fill"></span></span></div>' if order else "")
    return (f'<nav class="tbar" aria-label="Sections"><div class="tbar-in">'
            f'<div class="tjump">{tabs}</div>{prog}</div></nav>')


def _budget(order, n_skim, org) -> str:
    rows = []
    firsts = [i for i in order if i.extra.get("priority") == "first"]
    if firsts:
        who = f"what {escape(org)} does" if org else "what you do"
        n_first = len(firsts)
        rows.append((f"{sum(read_minutes(i) for i in firsts)} min",
                     f"Read {_story_range(1, n_first)}",
                     f"The one that changes {who} this quarter" if n_first == 1 else
                     f"The {_words(n_first)} that change {who} this quarter", "order-0"))
    if len(order) > len(firsts):
        n_today = len(order) - len(firsts)
        rows.append((f"{sum(read_minutes(i) for i in order)} min",
                     f"All {_words(len(order))} in the reading order" if len(order) > 1
                     else "The story in the reading order",
                     f"Adds the {_words(n_today) if n_today > 1 else 'one'} to read today"
                     if firsts else "The day's lead stories", "order-0"))
    if n_skim:
        rows.append((f"+{max(1, round(n_skim * 0.5))} min",
                     f"Skim the other {n_skim}" if order else f"Skim all {n_skim}",
                     "Headlines only; tap for a one-line gist", "skim"))
    if not rows:
        return ""
    body = "".join(
        f'<a class="brow go" href="#{target}"><span class="time">{time}</span>'
        f'<span class="what">{what}<span>{detail}</span></span></a>'
        for time, what, detail, target in rows)
    return f'<aside class="budget"><div class="bt">How much time do you have?</div>{body}</aside>'


def _summary_section(summary, order, skim, org) -> str:
    if not summary:
        return ""
    names = [t.get("tab") or tab_label(t["name"]) for t, _ in skim]
    lis = ""
    for n, s in enumerate(summary, 1):
        label, target = ref_target(s.get("ref"), names)
        jump = (f'<a class="jump go" href="#{target}">→ {escape(label)}</a>' if target else "")
        lis += (f'<li><span class="ix">{n:02d}</span><div><p><b>{escape(s["lead"])}</b> '
                f'{escape(s["text"])}</p>{jump}</div></li>')
    n_skim = sum(len(its) for _, its in skim)
    return (f'<section class="sum" id="summary"><div class="sum-main">'
            f'<h2 class="h">The day in 30 seconds</h2><ol class="takeaways">{lis}</ol></div>'
            f'{_budget(order, n_skim, org)}</section>')


def _order_item(n, item, section, org, reading_images) -> str:
    tier = item.extra.get("priority") or ""
    href = escape(_safe_url(item.url), quote=True)
    ext = 'target="_blank" rel="noopener"'
    also = item.extra.get("also") or []
    meta = (f'<div class="meta">{_badge(item)}<span>{escape(item.source)}</span>'
            f'<span class="quiet">{escape(section)} · {read_minutes(item)} min</span>'
            + (f'<span class="quiet">· {len(also) + 1} sources, 1 story</span>' if also else "")
            + "</div>")
    why = item.extra.get("why")
    why_html = (f'<div class="whybox"><b>Why it matters{escape(f" for {org}") if org else ""}</b>'
                f'{escape(why)}</div>' if why else "")
    gist = f'<p class="gist">{escape(item.summary)}</p>' if item.summary else ""
    also_html = ('<div class="also"><span>Also covered by</span>' + "".join(
        f'<a href="{escape(_safe_url(a.url), quote=True)}" {ext} '
        f'title="{escape(a.title, quote=True)}">{escape(a.source)}</a>' for a in also)
        + "</div>" if also else "")
    img = _image(item)
    show = reading_images == "all" or (reading_images == "first" and tier == "first")
    pic = (f'<a class="item-pic" href="{href}" {ext} tabindex="-1">'
           f'<img src="{escape(img, quote=True)}" alt="" loading="lazy" referrerpolicy="no-referrer" '
           f'onerror="this.parentNode.remove()"></a>' if img and show else "")
    return (f'<article class="item{" " + tier if tier else ""}" id="order-{n}" data-n="{n}">'
            f'<div class="num" data-num="{n + 1}">{n + 1}</div><div class="item-body">{meta}'
            f'<h3><a class="t" href="{href}" {ext}>{escape(display_title(item))}</a></h3>'
            f'{why_html}{gist}{also_html}<div class="acts">'
            f'<button class="mark" type="button" aria-pressed="false" hidden>Mark as read</button>'
            f'<a class="open-link" href="{href}" {ext}>Open article ↗</a></div></div>{pic}</article>')


def _order_section(order, themes, org, reading_images, read_key) -> str:
    if not order:
        return ""
    section = _section_of(themes)
    minutes = sum(read_minutes(i) for i in order)
    rows = "".join(_order_item(n, i, section.get(id(i), ""), org, reading_images)
                   for n, i in enumerate(order))
    return (f'<section class="order" id="order" data-key="{escape(read_key, quote=True)}">'
            f'<h2 class="h">Read in this order<span>{_plural(len(order), "story", "stories")} · '
            f'~{minutes} min</span></h2>{rows}</section>')


def _skim_section(skim, expanded) -> str:
    if not skim:
        return ""
    n_skim = sum(len(its) for _, its in skim)
    cols = ""
    for s, (theme, items) in enumerate(skim):
        rows = ""
        for r, i in enumerate(items):
            gid = f"gist-{s}-{r}"
            summary = escape(i.summary) if i.summary else \
                "No summary in the feed; open the article for the full story."
            rows += (f'<div class="srow"><button class="stog" type="button" aria-expanded="true" '
                     f'aria-controls="{gid}"><span><b>{escape(i.title)}</b>'
                     f'<span class="src">{escape(i.source)}</span></span>'
                     f'<span class="sign" aria-hidden="true">−</span></button>'
                     f'<div class="sgist" id="{gid}"><span>{summary}</span>'
                     f'<a href="{escape(_safe_url(i.url), quote=True)}" target="_blank" rel="noopener">'
                     f'Open article ↗</a></div></div>')
        cols += (f'<div class="skim-col" id="skim-{s}"><div class="skim-head">'
                 f'<h3 title="{escape(theme["name"], quote=True)}">'
                 f'{escape(theme.get("tab") or tab_label(theme["name"]))}</h3>'
                 f'<span>{_plural(len(items), "story", "stories")}</span></div>{rows}</div>')
    return (f'<section class="skim" id="skim" data-expanded="{"true" if expanded else "false"}">'
            f'<h2 class="h">Skim if you have time<span>{_plural(n_skim, "headline", "headlines")}'
            f' · tap one for the gist</span></h2><div class="skim-grid">{cols}</div></section>')


def _edition_data(themes, edition_date, slot_key) -> list:
    """What the Archive needs from this edition, one row per story (a cluster's
    other sources ride along in its lead's `also`)."""
    order, _ = triage(themes)
    in_order = {id(i) for i in order}
    rows = []
    for theme in themes:
        for i in theme["items"]:
            minutes = i.extra.get("minutes")
            rows.append({
                "title": i.title, "url": _safe_url(i.url), "source": i.source,
                "summary": (i.summary or "")[:280], "image": _image(i),
                "date": edition_date, "slot": slot_key,
                "p": i.extra.get("priority") or "", "why": i.extra.get("why") or "",
                "section": theme["name"], "tab": theme.get("tab") or tab_label(theme["name"]),
                "minutes": read_minutes(i) if id(i) in in_order else (
                    minutes if isinstance(minutes, int) else None),
                "cluster": i.extra.get("cluster_title") or "",
                "also": [{"title": a.title, "url": _safe_url(a.url), "source": a.source}
                         for a in i.extra.get("also") or []],
            })
    return rows


def _shell(title, page_title, body, extra_css, script, nav_on, top="") -> str:
    """The page frame. `top` sits between the masthead and <main> (the
    edition's sticky triage bar)."""
    nav = (f'<a class="{"on" if nav_on == "today" else ""}" href="index.html">Today</a>'
           f'<a class="{"on" if nav_on == "archive" else ""}" href="archive.html">Archive</a>')
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(page_title)}</title>{FONTS}<style>{_BASE_CSS}{extra_css}</style></head>'
        f'<body><header class="mast"><a class="word" href="index.html">{escape(title)}</a>'
        f'<nav class="nav">{nav}</nav></header>{top}<main>{body}</main>'
        f'<footer><span>{escape(title)} · curated by Claude</span>'
        f'<a href="{"archive.html" if nav_on == "today" else "index.html"}">'
        f'{"Browse the archive →" if nav_on == "today" else "← Today’s edition"}</a></footer>'
        f'{script}</body></html>'
    )


def build_web_edition(title, themes, *, greeting="", edition_label="", date_str=None,
                      edition_date=None, slot_key="edition", archive_link="archive.html",
                      summary=None, org="", reading_images="first", skim_expanded=False) -> str:
    """Render the full browsable edition as a self-contained HTML string.
    `summary` comes from summary.py; `org` names the reader in the why lines;
    `reading_images` is first|all|none (which reading-order stories get a
    picture); `skim_expanded` opens every skim gist by default."""
    now = datetime.now(timezone.utc)
    date_str = date_str or now.strftime("%A %d %B %Y")
    edition_date = edition_date or now.strftime("%Y-%m-%d")
    if reading_images not in READING_IMAGES:
        reading_images = "first"
    summary = summary or []
    order, skim = triage(themes)
    n_skim = sum(len(its) for _, its in skim)
    everything = all_items(themes)
    sources = len({i.source for i in everything})
    labelled = any(i.extra.get("priority") in ("first", "today") for i in order)
    dateline = (f'<div class="dateline"><span><b>{escape(date_str)}</b>'
                + (f' · {escape(edition_label)}' if edition_label else "")
                + f'</span><span>{_plural(len(everything), "story", "stories")} from '
                f'{_plural(sources, "source", "sources")}'
                + (f' · {len(order)} worth reading' if labelled else "") + '</span></div>')
    greet_html = f'<div class="greeting">{escape(greeting)}</div>' if greeting else ""
    read_key = f"edge-read-{edition_date}-{slot_key}"
    body = (f'<div class="wrap">{dateline}{greet_html}'
            f'{_summary_section(summary, order, skim, org)}'
            f'{_order_section(order, themes, org, reading_images, read_key)}'
            f'{_skim_section(skim, skim_expanded)}</div>')
    data = (f'<script id="edition-data" type="application/json">'
            f'{_json_for_html(_edition_data(themes, edition_date, slot_key))}</script>')
    script = data + f"<script>{_EDITION_JS}</script>"
    page_title = f"{title} — {edition_label}" if edition_label else title
    return _shell(title, page_title, body, _EDITION_CSS, script, "today",
                  top=_triage_bar(summary, order, n_skim))


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
