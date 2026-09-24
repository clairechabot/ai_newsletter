"""Bespoke per-site parsers (the Ellipsis model). Each <site>.py module exposes
fetch(source_cfg) -> list[Item]. Underscore-prefixed files are templates, not sources."""
from __future__ import annotations
import importlib
import pkgutil

def discover() -> dict:
    out = {}
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        out[mod.name] = mod.name
    return out

def get(module_name):
    mod = importlib.import_module(f"{__name__}.{module_name}")
    return mod.fetch
