#!/usr/bin/env python3
"""Agent handoff packets: everything another agent needs to resume a thread.

Markdown for humans/paste, JSON for machines.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone


def _fmt(ts: str | None) -> str:
    if not ts:
        return "unknown"
    return ts.replace("T", " ").replace("+00:00", " UTC")[:19] + " UTC"


def _load_thread(root: str, tid: str) -> dict | None:
    path = os.path.join(root, "atlas", "data", "threads", f"{tid}.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path, encoding="utf-8"))


def resume_prompt(thread: dict, turns: list[dict]) -> str:
    """A paste-ready prompt that puts a fresh agent exactly where you left off."""
    arts = "\n".join(
        f"- {a.get('name')}" + (f" — {a['href']}" if a.get("href") else "")
        for a in thread.get("artifacts", [])[:8]) or "- (none recorded)"
    urls = "\n".join(f"- {u}" for u in thread.get("urls", [])[:8]) or "- (none recorded)"
    opens = "\n".join(f"- {o}" for o in thread.get("open_threads", [])) or "- (none detected)"
    last = turns[-1] if turns else {}
    return f"""You are resuming an existing work thread. Absorb the state below, then continue — do not restart from scratch.

## Thread
{thread['name']}  ·  theme: {thread['theme']}  ·  {thread['turn_count']} turns
Window: {_fmt(thread.get('start'))} → {_fmt(thread.get('end'))}
Progress when paused: {thread['completeness']['percent']}% ({thread['completeness']['label']})
Status: {thread['status']} — {thread.get('status_note','')}

## Objective as last stated by the user
"{thread.get('last_prompt','')}"

## Where it stopped (final assistant output)
{(last.get('output_excerpt') or last.get('output') or '')[:1200]}

## Open threads to resolve first
{opens}

## Artifacts produced so far
{arts}

## Source URLs
{urls}

## Completeness evidence
{chr(10).join('- ' + r['signal'] + f" ({r['delta']:+d})" for r in thread['completeness'].get('reasons', [])[:6])}

## Your task
1. Confirm in one paragraph what state you have absorbed.
2. Resolve the open threads above in priority order.
3. Continue the work to completion, matching the established voice and formats.
4. End with a short changelog of what you added and the new completeness estimate.
"""


def packet_markdown(thread: dict, turns: list[dict], *, include_transcript: bool = True) -> str:
    lines: list[str] = []
    add = lines.append
    add(f"# Handoff — {thread['name']}")
    add("")
    add(f"- **Thread id:** `{thread['id']}`")
    add(f"- **Theme:** {thread['theme']}" +
        (f" (+ {', '.join(thread['secondary_themes'])})" if thread.get("secondary_themes") else ""))
    add(f"- **Turns:** {thread['turn_count']}  ·  **Chars produced:** {thread['chars']:,}")
    add(f"- **Window:** {_fmt(thread.get('start'))} → {_fmt(thread.get('end'))}"
        f"  ({thread.get('duration_hours', 0)} h)")
    add(f"- **Completeness:** {thread['completeness']['percent']}% "
        f"({thread['completeness']['label']})")
    add(f"- **Status:** {thread['status']} — {thread.get('status_note','')}")
    add(f"- **Sources:** {', '.join(thread.get('sources', []))}")
    add("")
    add("## Resume prompt (paste into any capable agent)")
    add("")
    add("```text")
    add(resume_prompt(thread, turns))
    add("```")
    add("")
    if thread.get("open_threads"):
        add("## Open threads")
        for o in thread["open_threads"]:
            add(f"- [ ] {o}")
        add("")
    if thread.get("artifacts"):
        add("## Artifacts")
        for a in thread["artifacts"]:
            href = f" — <{a['href']}>" if a.get("href") else ""
            add(f"- `{a.get('name')}`{href}")
        add("")
    if thread.get("urls"):
        add("## URLs")
        for u in thread["urls"]:
            add(f"- {u}")
        add("")
    add("## Completeness evidence")
    for r in thread["completeness"].get("reasons", []):
        add(f"- {r['signal']} ({r['delta']:+d})")
    add("")
    add("## Decision / turn timeline")
    for t in turns:
        stamp = _fmt(t.get("ts"))
        kind = t.get("kind") or "turn"
        add(f"### {t.get('turn_index', 0)+1:03d} · {stamp} · {kind}")
        prompt = (t.get("prompt") or "").strip()
        if prompt:
            add(f"**Prompt**")
            add("")
            add("> " + prompt.replace("\n", "\n> ")[:2000])
            add("")
        out = (t.get("output") or "").strip()
        if out:
            if include_transcript:
                add("**Output**")
                add("")
                add(out[:6000])
                if len(out) > 6000:
                    add(f"\n*…{len(out)-6000:,} characters trimmed from this turn "
                        f"(see `atlas/data/threads/{thread['id']}.json` for the full text).*")
            else:
                add("**Output (excerpt)**")
                add("")
                add((t.get("output_excerpt") or "")[:600])
            add("")
        if t.get("choices"):
            add("**Branches offered:**")
            for c in t["choices"]:
                add(f"- {c['label']}")
            add("")
    add("---")
    add(f"Generated {datetime.now(timezone.utc).isoformat()} by the Paradox Atlas "
        f"handoff exporter. Source: local archive, no external calls.")
    return "\n".join(lines)


def export_all(root: str, atlas: dict, out_dir: str, *, top: int = 12) -> int:
    os.makedirs(out_dir, exist_ok=True)
    made = 0
    ranked = sorted(atlas["threads"], key=lambda t: -t.get("resume_score", 0))[:top]
    for thread in ranked:
        data = _load_thread(root, thread["id"])
        if not data:
            continue
        turns = data["turns"]
        # Pre-built packets stay light: transcript trimmed, full text lives in
        # atlas/data/threads/*.json (or regenerate in-app with the export tab).
        md = packet_markdown(thread, turns, include_transcript=False)
        with open(os.path.join(out_dir, f"{thread['slug']}.md"), "w", encoding="utf-8") as fh:
            fh.write(md)
        json.dump({
            "generated": datetime.now(timezone.utc).isoformat(),
            "kind": "agent-handoff",
            "version": 1,
            "thread": thread,
            "resume_prompt": resume_prompt(thread, turns),
            "turns": [{**t, "output": (t.get("output") or "")[:3000]} for t in turns],
        }, open(os.path.join(out_dir, f"{thread['slug']}.json"), "w", encoding="utf-8"),
            ensure_ascii=False, indent=1)
        made += 2

    # Global index packet
    idx = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "kind": "atlas-index",
        "meta": atlas["meta"],
        "themes": [{k: t[k] for k in ("id", "name", "turns", "share", "completeness", "blurb")}
                   for t in atlas["themes"]],
        "threads": [{k: t[k] for k in ("id", "name", "theme", "status", "turn_count",
                                       "completeness", "start", "end", "resume_score")}
                    for t in atlas["threads"]],
    }
    json.dump(idx, open(os.path.join(out_dir, "atlas-index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# Handoff packets\n\n"
                 "One Markdown + one JSON packet per high-value thread, plus "
                 "`atlas-index.json` describing the whole archive. Paste a packet's "
                 "*Resume prompt* into any capable agent to continue the work.\n\n")
        for thread in ranked:
            fh.write(f"- **{thread['name']}** — {thread['completeness']['percent']}% "
                     f"({thread['status']}) · `{thread['slug']}.md`\n")
    return made + 2


if __name__ == "__main__":
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    atlas = json.load(open(os.path.join(root, "atlas", "data", "atlas.json"), encoding="utf-8"))
    n = export_all(root, atlas, os.path.join(root, "atlas", "exports"))
    print("files written:", n)
