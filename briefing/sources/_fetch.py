"""Hardened HTTP fetch, ported from Ellipsis athena/scrapers/__init__.py.
Retries with backoff, browser User-Agent, timeout, raise_for_status."""
from __future__ import annotations
import time
from urllib.parse import quote
import requests

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Status codes that signal a bot-wall (Cloudflare etc.) rather than a real
# outage — worth retrying through a public read-through relay.
BLOCK_STATUSES = {401, 403, 429, 451, 503}

# Public CORS/read-through proxies. Some publishers (Atlas Obscura, Science
# News, ...) 403 datacenter IPs like GitHub Actions runners; routing the same
# request through one of these relays usually returns the real page. Tried in
# order, only after a direct fetch is blocked. {url} is the encoded target.
RELAYS = (
    "https://api.codetabs.com/v1/proxy/?quest={url}",
    "https://api.allorigins.win/raw?url={url}",
)

def fetch(url, method="GET", headers=None, timeout=60, retries=3,
          retry_delay=5, **kwargs):
    hdrs = {**BROWSER_HEADERS, **(headers or {})}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(method, url, headers=hdrs, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(retry_delay)
    raise last_err


def _is_block(err) -> bool:
    status = getattr(getattr(err, "response", None), "status_code", None)
    # No response at all (timeout/connection error) is also worth a relay retry.
    return status is None or status in BLOCK_STATUSES


def fetch_with_fallback(url, validate=None, **kwargs):
    """Like `fetch`, but if the direct request is blocked (bot-wall / network
    error) retry through the public RELAYS in order. Returns the first good
    `requests.Response`; re-raises the last error if every path fails. Use this
    for feeds/pages from publishers that block datacenter IPs.

    `validate(resp) -> bool` catches bot-walls that answer 200 with a challenge
    page instead of the content (e.g. a feed that parses to zero entries). A
    direct response that fails validation is treated as blocked; if no relay
    does better, that direct response is still returned (it may be genuinely
    empty)."""
    direct = None
    try:
        direct = fetch(url, **kwargs)
        if validate is None or validate(direct):
            return direct
        print(f"[fetch] {url} answered but failed validation; trying relays", flush=True)
        last_err = None
    except requests.RequestException as direct_err:
        if not _is_block(direct_err):
            raise
        last_err = direct_err
    for tmpl in RELAYS:
        try:
            resp = fetch(tmpl.format(url=quote(url, safe="")), **kwargs)
        except requests.RequestException as e:
            last_err = e
            continue
        if validate is None or validate(resp):
            return resp
    if direct is not None:
        return direct
    raise last_err
