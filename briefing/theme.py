"""The Edge palette: orange, black and white with cobalt accents.

One place for every colour the email (`email.py`) and web edition (`web.py`)
use. CSS strings there reference these as `$orange`, `$cobalt`, ... and are
filled in with `css()`, so changing the look means editing this file only.

Contrast notes (WCAG): black text on orange is ~6.5:1 and orange on black is
the same, so orange works as a fill or on the black masthead. White on orange
is only ~3:1, so buttons use black text. Cobalt on white is ~8.4:1 (good for
links and labels) but too dark on black, so it never sits on the masthead.
"""
from __future__ import annotations
from string import Template

PALETTE = {
    "orange": "#FF5F15",       # brand: masthead rule, section markers, buttons
    "orange_tint": "#FFF3EC",  # soft orange wash behind the greeting
    "black": "#0B0B0B",        # masthead band, button text
    "ink": "#111111",          # body text and headlines
    "muted": "#5A5A5A",        # dates, summaries, footer
    "rule": "#E4E4E4",         # hairlines and card borders
    "paper": "#F4F4F4",        # page background behind white cards (email)
    "white": "#FFFFFF",
    "cobalt": "#0047AB",       # accents: source labels, links, TOC
}


def css(template: str) -> str:
    """Fill `$name` placeholders in a CSS string from PALETTE."""
    return Template(template).substitute(PALETTE)
