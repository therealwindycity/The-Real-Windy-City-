#!/usr/bin/env python3
"""Extract conversations out of saved Gemini web pages.

Two shapes show up in the archive:

* ``.mht`` / ``.mhtml`` files — real saves of a chat tab. Google's SPA marks the
  exchange up with ``<user-query>`` / ``<model-response>`` custom elements, so the
  prompt and the answer are both recoverable, along with the tab URL from the
  ``Snapshot-Content-Location`` header and the save time from ``Date``.
* ``.htm`` files — "Save page as" of the Gemini landing screen. There is no
  conversation body in them (the chat area is rendered client-side), but the left
  rail still lists recent conversation titles, which is useful context.

Everything is best-effort; a page that holds nothing yields nothing.
"""
from __future__ import annotations

import email
import email.utils
import hashlib
import html as ihtml
import os
import re
from datetime import timezone

__all__ = ["parse_mhtml_chat", "parse_saved_page"]

CHROME_LINES = {
    "Copy", "Copy code", "Share", "More", "Edit", "Thumbs up", "Thumbs down",
    "Good response", "Bad response", "Show drafts", "Google it", "Sources",
    "Stop", "Regenerate", "Listen", "Pin", "Save", "Report", "Export to Docs",
    "Modify response", "Collapse", "Show more lines", "Canvas", "Suggested",
    "Show thinking", "Hide thinking", "Search related", "Ask Gemini",
    "Volume up", "Volume down", "Skip", "New chat", "Search", "Settings",
    "Activity", "Help", "Send feedback", "Upgrade", "Sign in", "Menu",
    "Main menu", "Google apps", "Google Account", "Use microphone", "Use camera",
    "Add files", "Tools", "Deep research", "Video", "Images", "Gems", "Chats",
    "Recent", "Show more", "Temporary chat",
}


def _is_mhtml(path: str) -> bool:
    """True for .mht/.mhtml and for MHTML saved under another name (no extension)."""
    if path.lower().endswith((".mht", ".mhtml")):
        return True
    try:
        with open(path, "rb") as fh:
            head = fh.read(2048)
    except OSError:
        return False
    return head.lstrip().startswith((b"From: <", b"From: \n")) or b"MIME-Version:" in head


def _html_part(path: str) -> tuple[str, str | None, str | None]:
    """Return (html, snapshot_url, saved_iso) from an .mht or a plain .htm."""
    if _is_mhtml(path):
        with open(path, "rb") as fh:
            msg = email.message_from_binary_file(fh)
        url = msg.get("Snapshot-Content-Location")
        saved = msg.get("Date")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True) or b""
                return payload.decode("utf-8", "replace"), url, saved
        return "", url, saved
    raw = open(path, encoding="utf-8", errors="replace").read()
    url = None
    m = re.search(r'(?is)<meta[^>]+name=["\']?og:url["\']?[^>]+content=["\']([^"\']+)', raw)
    if m:
        url = m.group(1)
    return raw, url, None


def _inner_text(fragment: str, *, keep_lines: bool = True) -> str:
    fragment = re.sub(r"(?is)<(script|style|svg|noscript)\b.*?</\1>", " ", fragment)
    fragment = re.sub(r"(?is)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|pre|code|blockquote)>", "\n", fragment)
    fragment = re.sub(r"(?is)<li\b[^>]*>", "\n• ", fragment)
    text = re.sub(r"(?s)<[^>]+>", "", fragment)
    text = ihtml.unescape(text)
    text = text.replace("\u202f", " ").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln and ln not in CHROME_LINES]
    if not keep_lines:
        return " ".join(lines)
    out: list[str] = []
    for ln in lines:
        if out and out[-1] == ln:
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _saved_iso(saved: str | None) -> str | None:
    if not saved:
        return None
    try:
        return email.utils.parsedate_to_datetime(saved).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _eid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _rail_titles(html_text: str, limit: int = 40) -> list[str]:
    """Recent-conversation titles from the left rail of a landing-page save."""
    titles: list[str] = []
    for m in re.finditer(r'(?is)<(?:a|button|div|span)[^>]*class="[^"]*'
                         r'(?:conversation|chat-history|recent-item)[^"]*"[^>]*>(.*?)</', html_text):
        t = _inner_text(m.group(1), keep_lines=False)
        if 8 < len(t) < 160 and t not in titles:
            titles.append(t)
        if len(titles) >= limit:
            break
    if not titles:
        # fall back to the visible aria-labels of rail entries
        for m in re.finditer(r'aria-label="([^"]{10,160})"', html_text):
            t = _inner_text(m.group(1), keep_lines=False)
            if t and t not in titles and not t.lower().startswith(("google account", "open menu", "toggle")):
                titles.append(t)
            if len(titles) >= limit:
                break
    return titles


def parse_mhtml_chat(path: str) -> list[dict]:
    """Split a saved Gemini chat into prompt/output records (one per exchange)."""
    page, url, saved = _html_part(path)
    if not page:
        return []
    ts = _saved_iso(saved)
    title = None
    m = re.search(r"(?is)<title>(.*?)</title>", page)
    if m:
        title = _inner_text(m.group(1), keep_lines=False) or None

    events: list[tuple[str, str]] = []
    for m in re.finditer(r"(?is)<(user-query|model-response)\b[^>]*>(.*?)</\1>", page):
        role, frag = m.group(1), m.group(2)
        if role == "model-response":
            mc = re.search(r"(?is)<message-content\b[^>]*>(.*?)</message-content>", frag)
            if mc:
                frag = mc.group(1)
        text = _inner_text(frag)
        if len(text) < 8:
            continue
        if events and events[-1][0] == role and events[-1][1] == text:
            continue  # same node rendered twice (chat + side panel)
        events.append((role, text))

    records: list[dict] = []
    pending_prompt: str | None = None
    for role, text in events:
        if role == "user-query":
            if pending_prompt is not None:
                records.append(_record(path, url, ts, title, pending_prompt, "", len(records)))
            pending_prompt = text
        else:
            if pending_prompt is None:
                records.append(_record(path, url, ts, title, "", text, len(records)))
            else:
                records.append(_record(path, url, ts, title, pending_prompt, text, len(records)))
            pending_prompt = None
    if pending_prompt is not None:
        records.append(_record(path, url, ts, title, pending_prompt, "", len(records)))
    return records


def _record(path: str, url: str | None, ts: str | None, title: str | None,
            prompt: str, output: str, idx: int) -> dict:
    return {
        "source": "Saved Gemini chat page",
        "kind": "prompt" if output or prompt else "document",
        "ts": ts,
        "ts_raw": f"saved file (no per-turn stamp) — page save time {ts or 'unknown'}",
        "tz": "UTC",
        "tz_offset_hours": 0,
        "prompt": prompt,
        "output": output,
        "title": title or os.path.basename(path),
        "attachments": [],
        "products": ["Gemini"],
        "url": url,
        "entry_id": _eid("mht", os.path.basename(path), str(idx)),
        "origin_file": os.path.basename(path),
        "ts_source": "page-save",
    }


def parse_saved_page(path: str) -> list[dict]:
    """Landing-page saves: keep the shell text and the recent-conversation rail."""
    page, url, saved = _html_part(path)
    if not page:
        return []
    ts = _saved_iso(saved)
    title = None
    m = re.search(r"(?is)<title>(.*?)</title>", page)
    if m:
        title = _inner_text(m.group(1), keep_lines=False) or None
    rail = _rail_titles(page)
    body = _inner_text(re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page))
    notes = ["Saved Gemini page shell — the chat body is rendered client-side and is not in the file."]
    if rail:
        notes.append("Recent conversations listed on the page:")
        notes += [f"• {t}" for t in rail]
    if body:
        notes.append("")
        notes.append(body[:4000])
    return [{
        "source": "Saved Gemini page shell",
        "kind": "document",
        "ts": ts,
        "ts_raw": f"page saved {ts or 'unknown'}",
        "tz": "UTC",
        "tz_offset_hours": 0,
        "prompt": "",
        "output": "\n".join(notes),
        "title": title or os.path.basename(path),
        "attachments": [],
        "products": ["Gemini"],
        "url": url or ("https://gemini.google.com/app" if "gemini" in (title or "").lower() else None),
        "entry_id": _eid("htm", os.path.basename(path)),
        "origin_file": os.path.basename(path),
        "ts_source": "page-save",
    }]


if __name__ == "__main__":  # quick manual check: python3 tools/gemini_pages.py FILE...
    import sys
    for p in sys.argv[1:]:
        recs = parse_mhtml_chat(p) if _is_mhtml(p) else parse_saved_page(p)
        pairs = sum(1 for r in recs if r["prompt"] and r["output"])
        print(f"{os.path.basename(p)}: {len(recs)} turns ({pairs} prompt+output), "
              f"{sum(len(r['output']) for r in recs):,} output chars")
        for r in recs[:2]:
            print("   P:", r["prompt"][:90].replace("\n", " "))
            print("   O:", r["output"][:90].replace("\n", " "))
