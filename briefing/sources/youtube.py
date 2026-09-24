"""YouTube adapter. Reads a channel's uploads playlist instead of calling
search.list: playlistItems.list costs 1 quota unit vs 100 for search, so a
10-channel briefing uses ~10-20 units a run instead of ~1,000 (the default
daily quota is 10,000)."""
from __future__ import annotations
import os
import re
from datetime import datetime, timezone
from googleapiclient.discovery import build
from briefing.models import Item

SHORTS_MAX_SECONDS = 120  # Newsletter's rule: <=2 min or tagged #shorts
_SKIP_TITLES = {"private video", "deleted video"}

def _parse_published(snip, details=None):
    raw = (details or {}).get("videoPublishedAt") or snip.get("publishedAt")
    if not raw:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))

def _duration_seconds(iso) -> int | None:
    """ISO-8601 duration (PT1H2M3S) -> seconds; None if unparseable."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m or not iso:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s

def _is_short(title, description, seconds) -> bool:
    text = f"{title} {description}".lower()
    if "#short" in text:
        return True
    return seconds is not None and seconds <= SHORTS_MAX_SECONDS

def _uploads_playlist(channel_id) -> str:
    # Every channel's uploads playlist is its id with UC -> UU; no API call needed.
    return "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id

def _thumb(snip) -> str:
    thumbs = snip.get("thumbnails") or {}
    for size in ("high", "medium", "default"):
        if thumbs.get(size, {}).get("url"):
            return thumbs[size]["url"]
    return ""

def _build_youtube():
    return build("youtube", "v3", developerKey=os.environ["YOUTUBE_API_KEY"])

def fetch_youtube(cfg, max_per_channel=2) -> list[Item]:
    yt = _build_youtube()
    skip_shorts = bool(cfg.get("skip_shorts"))
    # Over-fetch when filtering Shorts so a burst of them doesn't leave us empty.
    depth = 15 if skip_shorts else max_per_channel
    resp = yt.playlistItems().list(
        part="snippet,contentDetails", playlistId=_uploads_playlist(cfg["channel_id"]),
        maxResults=depth,
    ).execute()
    entries = [it for it in resp.get("items", [])
               if (it.get("snippet", {}).get("title", "").lower() not in _SKIP_TITLES)]
    durations = {}
    if skip_shorts and entries:
        ids = [it["contentDetails"]["videoId"] for it in entries]
        vids = yt.videos().list(part="contentDetails", id=",".join(ids)).execute()
        durations = {v["id"]: _duration_seconds(v.get("contentDetails", {}).get("duration"))
                     for v in vids.get("items", [])}
    out = []
    for it in entries:
        snip, details = it["snippet"], it.get("contentDetails", {})
        vid = details.get("videoId") or snip.get("resourceId", {}).get("videoId")
        if not vid:
            continue
        desc = snip.get("description", "")
        if skip_shorts and _is_short(snip["title"], desc, durations.get(vid)):
            continue
        out.append(Item.make(
            source=cfg["name"], source_type="youtube",
            title=snip["title"], url=f"https://www.youtube.com/watch?v={vid}",
            summary=desc, published=_parse_published(snip, details), id=vid,
            extra={
                "embed_url": f"https://www.youtube.com/embed/{vid}?rel=0",
                "thumbnail": _thumb(snip),
                "channel": snip.get("videoOwnerChannelTitle") or snip.get("channelTitle", ""),
            },
        ))
    out.sort(key=lambda i: i.published, reverse=True)
    return out[:max_per_channel]
