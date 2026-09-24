from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query params that only track the click, never identify the page.
_TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|"
                       r"ref|ref_src|cmpid|guccounter|_hsenc|_hsmi|igshid)$", re.I)

def normalize_url(url) -> str:
    """Canonical form for dedup: lowercase scheme/host, no `www.`, no fragment,
    no tracking params, no trailing slash. Other query params are kept because
    some sites identify articles by them (?p=123)."""
    url = (url or "").strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.netloc:
        return url
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not _TRACKING.match(k)])
    path = parts.path.rstrip("/") or ""
    scheme = "https" if parts.scheme.lower() in ("http", "https") else parts.scheme.lower()
    return urlunsplit((scheme, host, path, query, ""))

def url_id(url) -> str:
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()

def legacy_url_id(url) -> str:
    """The pre-normalisation id (sha1 of the raw URL), still honoured by
    history so upgrading doesn't resend recently seen items."""
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()

def title_key(title) -> str:
    """Fingerprint for catching the same story under different URLs. Returns
    "" for short/generic titles, which are too collision-prone to dedup on."""
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    key = " ".join(words)
    return key if len(words) >= 4 and len(key) >= 20 else ""

@dataclass
class Item:
    source: str
    source_type: str
    title: str
    url: str
    summary: str
    published: datetime
    id: str
    extra: dict = field(default_factory=dict)

    @classmethod
    def make(cls, *, source, source_type, title, url, summary, published,
             id=None, extra=None):
        if id is None:
            id = url_id(url)
        return cls(source=source, source_type=source_type, title=title,
                   url=url, summary=summary, published=published, id=id,
                   extra=extra or {})
