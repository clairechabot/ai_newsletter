"""Source adapter contract. Each adapter exposes fetch(source_cfg) -> list[Item]."""
from __future__ import annotations
import os

def _annotation(text) -> str:
    # GitHub Actions workflow commands must be one line; % and newlines are escaped.
    return str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

def safe_fetch(name, thunk, report=None):
    """Run a source's fetch; on ANY error log and return [] so one dead
    source never kills the briefing (Ellipsis fail-soft pattern).

    Failures are also emitted as a GitHub Actions ::warning:: so a dead
    source shows up on the run page instead of hiding in the log. If
    `report` (a dict) is given, it records name -> item count or error."""
    try:
        items = thunk()
    except Exception as e:  # boundary: external sites/APIs are untrusted
        print(f"[source:{name}] FAILED, skipping: {e}", flush=True)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning title=Source failed: {_annotation(name)}::{_annotation(e)}",
                  flush=True)
        if report is not None:
            report[name] = f"FAILED: {e}"
        return []
    if report is not None:
        report[name] = len(items)
    return items

def write_step_summary(report) -> None:
    """Per-source table on the Actions run page ($GITHUB_STEP_SUMMARY), so a
    source that silently returns 0 items for weeks is easy to spot."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path or not report:
        return
    rows = []
    for name, result in report.items():
        if isinstance(result, int):
            status = "⚠️ 0 items" if result == 0 else f"{result} items"
        else:
            status = "❌ " + str(result)[:200].replace("|", "\\|").replace("\n", " ")
        rows.append(f"| {str(name).replace('|', '/')} | {status} |")
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("### Sources\n\n| Source | Result |\n|---|---|\n" + "\n".join(rows) + "\n\n")
    except OSError as e:
        print(f"[summary] could not write step summary: {e}", flush=True)
