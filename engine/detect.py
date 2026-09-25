"""Silent-edit detection: SHA-256 drift + line diffs between stored versions."""
from __future__ import annotations

import difflib
import re

from .util import short_id

# Lines that change on every page load and are not substantive edits.
_NOISE = re.compile(
    r"(copyright|©|\blast updated\b|\bpage generated\b|\bvisitors?\b|csrf|__viewstate|"
    r"\b\d{1,2}:\d{2}(:\d{2})?\s?(am|pm)?\b)", re.I)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines()
            if ln.strip() and not _NOISE.search(ln)]


def diff(old: str, new: str) -> dict:
    a, b = _lines(old), _lines(new)
    removed, added = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            removed += a[i1:i2]
        if tag in ("replace", "insert"):
            added += b[j1:j2]
    unified = "\n".join(difflib.unified_diff(a, b, "previous", "current", lineterm="", n=1))
    return {"removed": removed, "added": added, "unified": unified[:20000]}


def silent_edit_event(*, jurisdiction: str, url: str, title: str, prev_version, new_text: str,
                      new_hash: str, fetched_at: str, method: str, lat=None, lon=None) -> dict | None:
    """Build a silent_edit event if the change is substantive; else None."""
    d = diff(prev_version["text"] or "", new_text)
    if not d["removed"] and not d["added"]:
        return None
    # Removing text from a published record is more alarming than appending.
    severity = "high" if d["removed"] else "medium"
    quote = ("Removed: " + d["removed"][0]) if d["removed"] else ("Added: " + d["added"][0])
    return {
        "id": short_id("silent_edit", url, prev_version["hash"], new_hash),
        "jurisdiction": jurisdiction,
        "kind": "silent_edit",
        "severity": severity,
        "title": f"Silent edit detected — {title or url}",
        "quote": quote[:600],
        "source_url": url,
        "method": method,
        "fetched_at": fetched_at,
        "hash": new_hash,
        "lat": lat, "lon": lon,
        "data": {
            "previous_hash": prev_version["hash"],
            "previous_fetched_at": prev_version["fetched_at"],
            "removed": d["removed"][:50],
            "added": d["added"][:50],
            "unified_diff": d["unified"],
        },
    }
