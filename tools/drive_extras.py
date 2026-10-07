#!/usr/bin/env python3
"""Small parsers for the odds and ends that arrived from Google Drive.

* ``gemini_gems_data.html`` — the custom Gems (reusable system prompts) on the
  account, exported from the Gemini settings page.
* ``gemini_scheduled_actions_data.html`` — scheduled prompts / automations.
* ``Gemini_ Search, Security, and Debugging.html`` — the account's
  search/security/debugging metadata page (kept as a document).
* ``*metada.json`` — the JSON that came with the page above.
* ``ObservedObserver…json`` — a Chrome-reading-list bookmark entry.
"""
from __future__ import annotations

import hashlib
import html as ihtml
import json
import os
import re

__all__ = ["parse_gems", "parse_scheduled", "parse_debug_page", "parse_bookmark"]


def _eid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?is)</(p|div|li|h[1-6]|tr)>", "\n", raw)
    txt = ihtml.unescape(re.sub(r"(?s)<[^>]+>", "", raw))
    txt = txt.replace("\u202f", " ").replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def parse_gems(path: str) -> list[dict]:
    """One record per custom Gem: its name and its full instruction text."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    body = _text(raw)
    # The export repeats "Name: … Instructions: …" blocks, one per Gem.
    blocks = re.split(r"(?m)^(?=Name:\s)", body)
    out: list[dict] = []
    for block in blocks:
        m = re.match(r"Name:\s*(.+?)\s*(?:\n|$)", block)
        if not m:
            continue
        name = m.group(1).strip()[:200]
        inst = re.search(r"(?s)Instructions:\s*(.*)", block)
        text = (inst.group(1).strip() if inst else block.strip())
        if not name:
            continue
        out.append({
            "source": "Gemini Gems export",
            "kind": "gem",
            "ts": None,
            "ts_raw": "Undated settings export",
            "tz": "UTC",
            "tz_offset_hours": 0,
            "prompt": text[:20000],
            "output": "",
            "title": f"Gem — {name}",
            "attachments": [],
            "products": ["Gemini Gems"],
            "url": "https://gemini.google.com/gems",
            "entry_id": _eid("gem", name),
            "origin_file": os.path.basename(path),
            "artifact_name": f"Gem: {name}",
        })
    return out


def parse_scheduled(path: str) -> list[dict]:
    raw = open(path, encoding="utf-8", errors="replace").read()
    body = _text(raw)
    out: list[dict] = []
    for block in re.split(r"(?m)^(?=Name:\s)", body):
        m = re.match(r"Name:\s*(.+?)\s*(?:\n|$)", block)
        if not m:
            continue
        name = m.group(1).strip()[:300]
        sched = re.search(r"Schedule:\s*(.+?)(?:\n|$)", block)
        state = re.search(r"State:\s*(.+?)(?:\n|$)", block)
        turns = re.search(r"Unread conversation turns:\s*(\d+)", block)
        out.append({
            "source": "Gemini scheduled actions export",
            "kind": "scheduled",
            "ts": None,
            "ts_raw": "Undated settings export",
            "tz": "UTC",
            "tz_offset_hours": 0,
            "prompt": name,
            "output": " · ".join(filter(None, [
                f"Schedule: {sched.group(1).strip()}" if sched else "",
                f"State: {state.group(1).strip()}" if state else "",
                f"{turns.group(1)} unread conversation turns" if turns else "",
            ])),
            "title": f"Scheduled action — {name[:80]}",
            "attachments": [],
            "products": ["Gemini Scheduled Actions"],
            "url": "https://gemini.google.com/scheduled",
            "entry_id": _eid("sched", name),
            "origin_file": os.path.basename(path),
        })
    return out


def parse_debug_page(path: str) -> list[dict]:
    raw = open(path, encoding="utf-8", errors="replace").read()
    body = _text(raw)
    if len(body) < 80:
        return []
    m = re.search(r"(?is)<title>(.*?)</title>", raw)
    title = _text(m.group(1)) if m else os.path.basename(path)
    return [{
        "source": "Gemini account page (exported)",
        "kind": "document",
        "ts": None,
        "ts_raw": "Undated export",
        "tz": "UTC",
        "tz_offset_hours": 0,
        "prompt": "",
        "output": body[:60000],
        "title": title or "Gemini — Search, Security and Debugging",
        "attachments": [],
        "products": ["Gemini"],
        "url": "https://gemini.google.com/",
        "entry_id": _eid("debug", os.path.basename(path)),
        "origin_file": os.path.basename(path),
    }]


def parse_bookmark(path: str) -> list[dict]:
    try:
        data = json.loads(open(path, encoding="utf-8", errors="replace").read())
    except Exception:
        return []
    title = data.get("title") or os.path.basename(path)
    meta = data.get("metadata") or {}
    added = (((meta.get("revisionData") or {}).get("dateAdded"))
             or meta.get("sourceAddedTimestamp"))
    url = None
    if "github" in title.lower():
        url = "https://github.com/ObservedObserver/ChatGPT-Jailbreak-Prompts"
    return [{
        "source": "Reading list / bookmark export",
        "kind": "bookmark",
        "ts": added,
        "ts_raw": f"added {added or 'unknown'}",
        "tz": "UTC",
        "tz_offset_hours": 0,
        "prompt": "",
        "output": f"Bookmarked reference kept in the archive: {title}",
        "title": title,
        "attachments": [],
        "products": ["Chrome reading list"],
        "url": url,
        "entry_id": _eid("bm", title),
        "origin_file": os.path.basename(path),
    }]


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        base = os.path.basename(p).lower()
        if "gems" in base:
            recs = parse_gems(p)
        elif "scheduled" in base:
            recs = parse_scheduled(p)
        elif base.endswith(".json"):
            recs = parse_bookmark(p)
        else:
            recs = parse_debug_page(p)
        print(f"{os.path.basename(p)}: {len(recs)} records")
        for r in recs[:3]:
            print("   ", (r.get("title") or r.get("prompt", ""))[:90])
