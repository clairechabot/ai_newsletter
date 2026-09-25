from __future__ import annotations
from datetime import datetime
from briefing.sources import fetch_all
from briefing.history import load_history, save_history, drop_seen, mark_seen
from briefing.filter import apply_filter
from briefing.enrich import group_into_themes
from briefing.priority import prioritize, order_themes, reading_list
from briefing.images import add_images
from briefing.summary import summarize
from briefing.voice import compose_greeting, RECENT_KEEP
from briefing.editions import pick_edition
from briefing.email import build_html_email, send_email, top_pick_subject, check_login, cover_preheader
from briefing.web import build_web_edition, save_edition, build_archive_index

def run(cfg, history_path="history.json", now=None) -> None:
    now = now or datetime.now()  # local time decides which edition (AM/PM) runs
    slot = pick_edition(cfg.editions, now.hour)
    title = f"{cfg.title} — {slot['label']}" if slot.get("label") else cfg.title

    check_login()  # fail fast on a bad mail password, before fetching or paying for Claude
    raw = fetch_all(cfg)
    print(f"[pipeline] fetched {len(raw)} items", flush=True)
    hist = load_history(history_path)
    fresh = drop_seen(raw, hist)
    print(f"[pipeline] {len(fresh)} fresh after dedup", flush=True)
    if not fresh:
        print("[pipeline] nothing new; skipping edition", flush=True)
        return
    selected = apply_filter(fresh, cfg)
    print(f"[pipeline] {len(selected)} after filter ({cfg.filter_mode})", flush=True)

    add_images(selected, cfg.images)    # optional: preview image + read time per item
    # optional: labels read first / today / later and folds duplicate coverage
    # of one event into its lead story (the others ride along in extra["also"])
    selected = prioritize(selected, cfg.priority)
    themes = order_themes(group_into_themes(selected, cfg.voice))
    summary = summarize(themes, cfg.summary)  # optional: "The day in 30 seconds"
    greeting = compose_greeting(cfg.voice, themes, recent=hist.get("recent_greetings"))
    org = cfg.priority.get("org", "") if cfg.priority.get("enabled") else ""

    # Web edition (optional): write the browsable page + permanent archive copy.
    if cfg.web.get("enabled"):
        out_dir = cfg.web.get("output_dir", "docs")
        page = build_web_edition(title, themes, greeting=greeting,
                                 edition_label=slot.get("label", ""),
                                 date_str=now.strftime("%A %d %B %Y").replace(" 0", " "),
                                 edition_date=now.strftime("%Y-%m-%d"), slot_key=slot["key"],
                                 summary=summary, org=org,
                                 reading_images=cfg.web.get("reading_images", "first"),
                                 skim_expanded=bool(cfg.web.get("skim_expanded", False)))
        paths = save_edition(out_dir, page, now.strftime("%Y-%m-%d"), slot["key"])
        build_archive_index(out_dir, site_title=cfg.title)
        print(f"[pipeline] web edition -> {paths['edition']}", flush=True)

    must = reading_list(themes)
    lead = must[0].title if must else next(
        (t["items"][0].title for t in themes if t.get("items")), "")
    cover = cfg.email_mode == "cover"
    html = build_html_email(title, themes, greeting=greeting,
                            edition_url=cfg.web.get("edition_url", ""), cover=cover,
                            preheader=(cover_preheader(themes, greeting, summary) if cover
                                       else (greeting or lead)),
                            summary=summary, org=org, now=now,
                            unsubscribe=cfg.email_unsubscribe, address=cfg.email_address)
    subject = top_pick_subject(title, themes) if cfg.email_subject == "top_pick" else None
    send_email(title, html, subject=subject, from_name=cfg.email_from_name)

    mark_seen(hist, fresh)
    if greeting:
        hist["recent_greetings"] = (hist.get("recent_greetings", []) + [greeting])[-RECENT_KEEP:]
    save_history(history_path, hist)
