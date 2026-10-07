"""Parse Google Takeout "My Activity" exports into structured turns.

Handles both shapes Google ships:

  * HTML  (`My Activity/<Product>/MyActivity.html`) - the layout used by the
    2026 exports, where each entry is an `outer-cell` block holding the
    prompt, the timestamp, the model response, and any attachments.
  * JSON  (`My Activity/<Product>/MyActivity.json`) - the newer Takeout shape
    with `title`, `time`, `subtitles` and (for Gemini) `details`.

Output record:
    {
      "source": "Gemini Apps",
      "kind": "prompt" | "event",
      "ts": "2026-04-03T07:59:27Z",        # UTC, best effort
      "ts_raw": "Apr 3, 2026, 3:59:27 AM EDT",
      "tz": "EDT",
      "prompt": "markdown text",
      "output": "markdown text",
      "attachments": [{"name": ..., "href": ...}],
      "products": [...],
      "entry_id": stable hash
    }
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
from datetime import datetime, timedelta, timezone

from htmlmd import html_to_markdown, text_of

MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

_DATE_RE = re.compile(
    r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4}), (\d{1,2}):(\d{2}):(\d{2})[\s\u202f\u00a0]*([AP]M) (\w{2,4})"
)

# Rough fixed offsets so we can emit a UTC instant for sorting. DST is not
# modelled; the local wall-clock string is always preserved alongside it.
TZ_OFFSET = {
    "EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6, "MST": -7,
    "PDT": -7, "PST": -8, "AKDT": -8, "AKST": -9, "HST": -10, "UTC": 0, "GMT": 0,
}


def parse_stamp(raw: str):
    m = _DATE_RE.search(raw or "")
    if not m:
        return None, None
    mon, day, year, hh, mm, ss, ap, tz = m.groups()
    hour = int(hh) % 12 + (12 if ap == "PM" else 0)
    naive = datetime(int(year), MONTHS[mon], int(day), hour, int(mm), int(ss))
    off = TZ_OFFSET.get(tz, 0)
    utc = naive - timedelta(hours=off)
    return utc.replace(tzinfo=timezone.utc), off


def _eid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8", "replace")).hexdigest()[:16]


# --------------------------------------------------------------------------- HTML

_OUTER = re.compile(r'<div class="outer-cell.*?(?=<div class="outer-cell|</body>)', re.S)
_TITLE = re.compile(r'mdl-typography--title">(.*?)</p>', re.S)
_CELLS = re.compile(
    r'<div class="content-cell[^"]*?mdl-typography--body-1[^"]*">(.*?)</div>\s*(?=<div class="content-cell|<div class="mdl-grid|</div>)',
    re.S,
)
_CAPTION = re.compile(r'mdl-typography--caption">(.*?)$', re.S)


def parse_activity_html(path: str, product_hint: str | None = None) -> list[dict]:
    raw = open(path, encoding="utf-8", errors="replace").read()
    raw = raw.replace("\u202f", " ").replace("\u00a0", " ")
    out: list[dict] = []
    for block in _OUTER.findall(raw):
        title_m = _TITLE.search(block)
        product = text_of(title_m.group(1)) if title_m else (product_hint or "Google")
        cells = _CELLS.findall(block)
        left = cells[0] if cells else ""
        right = cells[1] if len(cells) > 1 else ""
        stamp_m = _DATE_RE.search(left) or _DATE_RE.search(right)
        ts_raw = stamp_m.group(0) if stamp_m else ""
        if not left.strip():
            continue

        # The Takeout layout is:
        #   Prompted <prompt text><br><timestamp><br><p>response …</p>
        # so the timestamp is the split point between question and answer.
        head = left[: stamp_m.start()] if stamp_m else left
        tail = left[stamp_m.end():] if stamp_m else ""
        attachments = [
            {"name": _html.unescape(text_of(a) or "attachment"), "href": h}
            for h, a in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', head, re.S)
        ]

        text_copy = html_to_markdown(head)
        kind = "event"
        m = re.match(r"^(Prompted|Asked|Said)\s+(.*)$", text_copy, re.S | re.I)
        if m:
            kind = "prompt"
            prompt = m.group(2).strip()
        elif text_copy.lower().startswith("searched for"):
            kind = "search"
            prompt = re.sub(r"(?i)^searched for\s*", "", text_copy).strip()
        else:
            prompt = text_copy

        # The response usually sits after the timestamp in the left cell; some
        # exports put it in the right-hand cell instead.
        output = html_to_markdown(tail)
        if len(output) < 40 and right.strip():
            output = html_to_markdown(right)
        # Remove trailing "Products:" chatter that Takeout appends.
        output = re.sub(r"(?is)\n*Products:.*$", "", output).strip()

        utc, off = parse_stamp(ts_raw)
        caption = _CAPTION.search(block)
        products = []
        if caption:
            cap = text_of(caption.group(1))
            pm = re.search(r"Products:\s*(.*?)(?:Why is this here|$)", cap, re.S)
            if pm:
                products = [p.strip() for p in re.split(r"[\n,]", pm.group(1)) if p.strip()]

        out.append({
            "source": product,
            "kind": kind,
            "ts": utc.isoformat() if utc else None,
            "ts_raw": ts_raw,
            "tz": (stamp_m.group(8) if stamp_m else None),
            "tz_offset_hours": off,
            "prompt": prompt,
            "output": output,
            "attachments": attachments,
            "products": products or [product],
            "entry_id": _eid(product, ts_raw, prompt[:200]),
        })
    return out


# --------------------------------------------------------------------------- JSON

def parse_activity_json(path: str, product_hint: str | None = None) -> list[dict]:
    data = json.load(open(path, encoding="utf-8", errors="replace"))
    if isinstance(data, dict):
        data = data.get("items", data.get("activity", [data]))
    out: list[dict] = []
    for item in data:
        title = item.get("title") or product_hint or "Google"
        subtitles = item.get("subtitles") or []
        prompt = ""
        for sub in subtitles:
            name = sub.get("name") if isinstance(sub, dict) else str(sub)
            if name:
                prompt += ("\n" if prompt else "") + text_of(name)
        output = ""
        details = item.get("details")
        if isinstance(details, list):
            output = "\n\n".join(text_of(d) if not isinstance(d, str) else d for d in details)
        header = item.get("header") or ""
        raw_time = item.get("time") or ""
        utc = None
        try:
            utc = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except Exception:
            utc = None
        out.append({
            "source": header or product_hint or "Google",
            "kind": "prompt" if prompt else "event",
            "ts": utc.isoformat() if utc else None,
            "ts_raw": raw_time,
            "tz": None,
            "tz_offset_hours": None,
            "prompt": prompt,
            "output": output,
            "attachments": [],
            "products": [header] if header else [],
            "entry_id": _eid(title, raw_time, prompt[:200]),
        })
    return out


def parse_any(path: str) -> list[dict]:
    product = None
    parts = path.replace("\\", "/").split("/")
    for p in reversed(parts[:-1]):
        if p and p.lower() not in ("my activity", "takeout"):
            product = p
            break
    if path.lower().endswith((".json", ".jsonl")):
        return parse_activity_json(path, product)
    return parse_activity_html(path, product)


if __name__ == "__main__":
    import sys

    total = 0
    for p in sys.argv[1:]:
        recs = parse_any(p)
        prompts = [r for r in recs if r["kind"] == "prompt"]
        with_out = [r for r in prompts if len(r["output"]) > 80]
        total += len(recs)
        print(f"{os.path.basename(p)}: {len(recs)} records, {len(prompts)} prompts, "
              f"{len(with_out)} with responses")
        if recs:
            r = recs[0]
            print("   first:", r["ts_raw"], "|", r["prompt"][:90].replace("\n", " "))
    print("total records:", total)
