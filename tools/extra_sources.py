"""Extra source loaders: PDF chat exports, saved MHTML/HTML chat pages,
Drive/Docs text, and Takeout archive-browser inventories.

Stdlib + pypdf (only used when a PDF is present).
"""
from __future__ import annotations

import base64
import email
import hashlib
import json
import os
import quopri
import re
from datetime import datetime, timezone

from htmlmd import html_to_markdown, text_of, find_urls

# --------------------------------------------------------------------------- PDF


def _eid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8", "replace")).hexdigest()[:16]


def parse_pdf_pages(path: str, *, title: str | None = None) -> list[dict]:
    """One record per page: these exports are long print-runs of AI sessions."""
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        return []
    reader = PdfReader(path)
    created = None
    try:
        meta = reader.metadata or {}
        raw = str(meta.get("/CreationDate", ""))
        m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", raw)
        if m:
            created = datetime(*[int(g) for g in m.groups()], tzinfo=timezone.utc).isoformat()
    except Exception:
        pass
    base = title or os.path.basename(path).rsplit(".", 1)[0]
    out = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        if len(text) < 80:
            continue
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        heading = lines[0][:120] if lines else f"Page {i}"
        body = html_to_markdown(text)
        out.append({
            "source": "Gemini PDF export",
            "kind": "document",
            "ts": created,
            "ts_raw": created or "",
            "tz": "UTC",
            "tz_offset_hours": 0,
            "prompt": "",  # printed output only - no prompt side available
            "output": body,
            "title": f"{base} — p.{i}: {heading}",
            "attachments": [],
            "products": ["Gemini"],
            "entry_id": _eid("pdf", base, str(i)),
            "doc_page": i,
            "origin_file": os.path.basename(path),
        })
    return out


# --------------------------------------------------------------------------- MHT


def parse_mhtml(path: str) -> list[dict]:
    """Saved Gemini pages (.mht). Keeps the real conversation URL."""
    raw = open(path, "rb").read()
    msg = email.message_from_bytes(raw)
    html_part, url, saved = None, None, None
    url = msg.get("Snapshot-Content-Location")
    saved = msg.get("Date")
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            html_part = payload.decode("utf-8", "replace")
            url = part.get("Content-Location") or url
            break
    if not html_part:
        return []
    ts = None
    if saved:
        try:
            ts = email.utils.parsedate_to_datetime(saved).astimezone(timezone.utc).isoformat()
        except Exception:
            ts = None
    body = html_to_markdown(html_part)
    title = None
    m = re.search(r"<title>(.*?)</title>", html_part, re.S | re.I)
    if m:
        title = text_of(m.group(1)) or None
    return [{
        "source": "Saved Gemini page",
        "kind": "document",
        "ts": ts,
        "ts_raw": saved or "",
        "tz": "UTC",
        "tz_offset_hours": 0,
        "prompt": "",
        "output": body,
        "title": title or os.path.basename(path),
        "attachments": [],
        "products": ["Gemini"],
        "url": url,
        "entry_id": _eid("mht", os.path.basename(path)),
        "origin_file": os.path.basename(path),
    }]


# --------------------------------------------------------------------------- HTML


def parse_saved_html(path: str, *, title: str | None = None, ts: str | None = None) -> list[dict]:
    raw = open(path, encoding="utf-8", errors="replace").read()
    body = html_to_markdown(raw)
    if len(body) < 200:
        return []
    m = re.search(r"<title>(.*?)</title>", raw, re.S | re.I)
    name = title or (text_of(m.group(1)) if m else None) or os.path.basename(path)
    urls = [u for u in find_urls(raw[:20000]) if "gemini" in u or "docs.google" in u]
    return [{
        "source": "Saved Gemini page",
        "kind": "document",
        "ts": ts,
        "ts_raw": ts or "",
        "tz": "UTC",
        "tz_offset_hours": 0,
        "prompt": "",
        "output": body,
        "title": name,
        "attachments": [],
        "products": ["Gemini"],
        "url": urls[0] if urls else None,
        "entry_id": _eid("html", os.path.basename(path)),
        "origin_file": os.path.basename(path),
    }]


def parse_text_doc(path: str, *, title: str | None = None, ts: str | None = None,
                   source: str = "Drive document", url: str | None = None) -> list[dict]:
    raw = open(path, encoding="utf-8", errors="replace").read()
    body = html_to_markdown(raw) if raw.lstrip().startswith("<") else raw
    if len(body) < 120:
        return []
    first = next((l.strip("# ").strip() for l in body.splitlines() if l.strip()), "")
    return [{
        "source": source,
        "kind": "document",
        "ts": ts,
        "ts_raw": ts or "",
        "tz": "UTC",
        "tz_offset_hours": 0,
        "prompt": "",
        "output": body,
        "title": title or first[:120] or os.path.basename(path),
        "attachments": [],
        "products": [source],
        "url": url,
        "entry_id": _eid("doc", os.path.basename(path), (title or "")[:80]),
        "origin_file": os.path.basename(path),
    }]


# --------------------------------------------------------------------------- Takeout index

_SVC = re.compile(
    r'data-english-name="([^"]+)"\s+data-folder-name="([^"]+)">([^<]*)</h1>\s*</div>\s*'
    r'(?:<div[^>]*>)?([\d,\.]+ files?[^<]*)',
    re.S,
)
_FOLDER = re.compile(r'class="extracted-folder-name">([^<]*)<')
_LEAF = re.compile(r'class="file-leaf"><div class="extracted-file-name">([^<]*)<')
_TOKEN = re.compile(r"<[^>]+>|\"[^\"]*\"|'[^']*'")


def parse_archive_browser(path: str) -> dict:
    """Turn a Takeout `archive_browser.html` into a coverage map.

    The page is a nested list of folders and files; we walk the tag stream to
    rebuild paths and aggregate counts/sizes per top-level service.
    """
    raw = open(path, encoding="utf-8", errors="replace").read()
    services = []
    for en, folder, label, summary in _SVC.findall(raw):
        services.append({
            "service": en,
            "label": (label or folder).strip(),
            "summary": summary.strip(),
        })
    # Stream walk: folder opens push, closes pop.
    events = []
    for m in re.finditer(r'class="extracted-(folder-name|child|file-name)"|class="file-leaf"', raw):
        events.append((m.start(), m.group(0)))
    paths: dict[str, int] = {}
    stack: list[str] = []
    for m in _FOLDER.finditer(raw):
        # nearest preceding open/close context is ambiguous in a flat scan, so
        # we keep it simple: names only, aggregated by top-level section.
        stack.append(html_text(m.group(1)))
    leaves = [_html_unescape_text(x) for x in _LEAF.findall(raw)]
    counts: dict[str, int] = {}
    for name in stack:
        counts[name] = counts.get(name, 0)
    return {
        "services": services,
        "service_count": len(services),
        "total_files": sum(int(re.sub(r"[^\d]", "", s["summary"].split(" file")[0]) or 0)
                           for s in services if "file" in s["summary"]),
        "folder_names": sorted(set(stack)),
        "leaf_sample": leaves[:400],
        "leaf_count": len(leaves),
    }


def html_text(s: str) -> str:
    return text_of(s)


def _html_unescape_text(s: str) -> str:
    import html as h
    return h.unescape(s).strip()


def load_drive_inventory(path: str) -> dict:
    """Google Drive file inventory captured from the Drive connector."""
    return json.load(open(path, encoding="utf-8"))
