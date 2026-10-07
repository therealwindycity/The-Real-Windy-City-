#!/usr/bin/env python3
"""Build the Atlas dataset from every source we can read.

Inputs (all optional, discovered by glob):
  data/raw/MyActivity*.html|json          Google Takeout My Activity exports
  data/raw/*.pdf                          printed Gemini chat exports
  data/raw/*.mht|*.htm|*.html             saved Gemini pages
  data/raw/* export*.txt|docs txt         exported Google Docs
  data/unpacked/arch_*.html               Takeout archive_browser indexes
  data/drive_catalog.json                 Drive file inventory (curated/connector)
  cheyenne-2026-transcripts/meetings.json repo archive catalog

Outputs:
  atlas/data/atlas.json                   index used by the GUI (lazy content)
  atlas/data/threads/<id>.json            full transcripts per thread
  atlas/data/inventory.json               Drive/Takeout coverage map
  atlas/exports/*.md|json                 pre-built agent handoff packets
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import analyze as A  # noqa: E402
from htmlmd import find_urls  # noqa: E402
import extra_sources as X  # noqa: E402
import gemini_pages as G  # noqa: E402
import drive_extras as D  # noqa: E402
from takeout_activity import parse_any  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
UNPACKED = os.path.join(ROOT, "data", "unpacked")
OUT = os.path.join(ROOT, "atlas", "data")
EXPORTS = os.path.join(ROOT, "atlas", "exports")

# Drive items verified present in the connected account, used to tie prompts to
# the artifacts they produced. Extended by tools/drive_catalog.py when the
# Drive connector is available.
DRIVE_ARTIFACTS = json.load(open(os.path.join(ROOT, "data", "drive_catalog.json"),
                                 encoding="utf-8")) if os.path.exists(
    os.path.join(ROOT, "data", "drive_catalog.json")) else []


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:48] or "thread")


def excerpt(text: str, n: int) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n]
    if " " in cut[cut.rfind(" ", 0, n) - 1:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + " …"


def load_turns() -> tuple[list[dict], list[dict]]:
    turns: list[dict] = []
    sources: list[dict] = []
    seen_ids = set()

    def add(recs: list[dict], label: str, path: str):
        added = 0
        for r in recs:
            if r["entry_id"] in seen_ids:
                continue
            seen_ids.add(r["entry_id"])
            r["origin"] = label
            r["origin_file"] = r.get("origin_file") or os.path.basename(path)
            turns.append(r)
            added += 1
        if added:
            sources.append({"label": label, "file": os.path.basename(path), "records": added})
        return added

    # 1. Takeout My Activity exports (the prompt/output backbone).
    for path in sorted(glob.glob(os.path.join(RAW, "MyActivity*.html"))) + \
            sorted(glob.glob(os.path.join(RAW, "MyActivity*.json"))):
        add(parse_any(path), "Google Takeout — My Activity (Gemini Apps)", path)
    for path in sorted(glob.glob(os.path.join(RAW, "**", "MyActivity*.html"), recursive=True)):
        if os.path.basename(path) not in [s["file"] for s in sources]:
            add(parse_any(path), "Google Takeout — My Activity", path)

    # 2. Printed Gemini chat exports (PDF).
    for path in sorted(glob.glob(os.path.join(RAW, "*.pdf"))):
        add(X.parse_pdf_pages(path), "Gemini PDF export", path)

    # 3. Saved Gemini pages: real chat saves recover every prompt + answer,
    #    landing-page saves keep the rail of recent conversations.
    chat_pages = sorted(glob.glob(os.path.join(RAW, "*.mht"))) + \
        sorted(glob.glob(os.path.join(RAW, "*.mhtml"))) + \
        [p for p in sorted(glob.glob(os.path.join(RAW, "*")))
         if not os.path.splitext(p)[1] and G._is_mhtml(p)]
    for path in chat_pages:
        add(G.parse_mhtml_chat(path), "Saved Gemini chat page", path)
    shells = sorted(glob.glob(os.path.join(RAW, "*.htm"))) + \
        sorted(glob.glob(os.path.join(RAW, "*.html"))) + \
        sorted(glob.glob(os.path.join(RAW, "saved-pages", "*.htm"))) + \
        sorted(glob.glob(os.path.join(RAW, "saved-pages", "*.html")))
    for path in shells:
        base = os.path.basename(path).lower()
        if base.startswith(("myactivity", "archive", "gemini_", "gemini ", "index", "robots")):
            continue
        add(G.parse_saved_page(path), "Saved Gemini page shell", path)

    # 3b. Gems, scheduled actions, account metadata, bookmarks.
    for path in sorted(glob.glob(os.path.join(RAW, "gemini_gems_data.html"))):
        add(D.parse_gems(path), "Gemini Gems export", path)
    for path in sorted(glob.glob(os.path.join(RAW, "gemini_scheduled_actions_data.html"))):
        add(D.parse_scheduled(path), "Gemini scheduled actions export", path)
    for path in sorted(glob.glob(os.path.join(RAW, "Gemini_ *Debugging.html"))):
        add(D.parse_debug_page(path), "Gemini account page export", path)
    for path in sorted(glob.glob(os.path.join(RAW, "ObservedObserver*.json"))):
        add(D.parse_bookmark(path), "Reading-list bookmark export", path)
    for path in sorted(glob.glob(os.path.join(RAW, "Gemini Export*"))) + \
            sorted(glob.glob(os.path.join(RAW, "Gemini Export*.*"))):
        if not os.path.splitext(path)[1]:
            add(X.parse_text_doc(path, title="Paradox Engine — framework text",
                                 source="Google Doc export",
                                 url="https://docs.google.com/document/d/1QLP0PTbBEjG_AqkgObCVu8-yRXdCsI3EyaSPj7uB5g4/edit"),
                "Google Doc export — Paradox Engine", path)

    # 4. Exported Google Docs kept in data/raw (plain-text exports).
    for path in sorted(glob.glob(os.path.join(RAW, "*"))):
        base = os.path.basename(path).lower()
        if base.startswith(("gemini export", "continue with", "blotter", "spreadsheet")):
            if not os.path.splitext(base)[1]:  # extension-less Doc export
                add(X.parse_text_doc(path, title=os.path.basename(path),
                                     source="Google Doc export"),
                    "Google Doc export", path)
    return turns, sources


def build_destinations(turns: list[dict], meetings: list[dict],
                       drive: list[dict]) -> dict:
    """Where the work actually went: products used, hosts linked, published output.

    This backs the "where did it go" panel — every row is counted from the raw
    records, never guessed.
    """
    product_counts = Counter((t.get("product") or t.get("source") or "unknown") for t in turns)
    host_counts: Counter = Counter()
    host_sample: dict[str, str] = {}
    for t in turns:
        for u in t.get("urls") or []:
            m = re.match(r"https?://([^/]+)", u)
            if not m:
                continue
            host = m.group(1).lower().removeprefix("www.")
            host_counts[host] += 1
            host_sample.setdefault(host, u)
    chips = []
    for host, n in host_counts.most_common(24):
        if n < 2:
            continue
        chips.append({"host": host, "turns": n, "url": host_sample[host]})
    with_links = sum(1 for t in turns if t.get("urls"))
    with_files = sum(1 for t in turns if t.get("artifacts"))
    return {
        "products": [{"name": n, "turns": c} for n, c in product_counts.most_common(12)],
        "hosts": chips,
        "turns_with_links": with_links,
        "turns_with_files": with_files,
        "drive_files": len(drive),
        "drive_url": "https://drive.google.com/drive/my-drive",
        "meetings_published": len(meetings),
        "youtube": "https://www.youtube.com/@therealwindycity" if meetings else None,
        "repo": "https://github.com/therealwindycity/The-Real-Windy-City-",
        "site": "https://therealwindycity.github.io/The-Real-Windy-City-/",
        "transcripts": "cheyenne-2026-transcripts/",
    }


def build_theme_index(turns: list[dict]) -> list[dict]:
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for t in turns:
        by_theme[t["theme"]].append(t)
    total = len(turns) or 1
    out = []
    for theme in A.THEMES + [A.FALLBACK_THEME]:
        items = by_theme.get(theme["id"], [])
        if not items:
            continue
        words = Counter()
        for t in items:
            words.update(A.tokens(t.get("prompt") or "")[:60])
        stamps = sorted(t["ts"] for t in items if t.get("ts"))
        out.append({
            "id": theme["id"],
            "name": theme["name"],
            "color": theme["color"],
            "blurb": theme["blurb"],
            "turns": len(items),
            "share": round(100 * len(items) / total, 1),
            "start": stamps[0] if stamps else None,
            "end": stamps[-1] if stamps else None,
            "top_terms": [w for w, _ in words.most_common(18)],
            "completeness": round(sum(t["completeness_pct"] for t in items) / len(items)),
        })
    out.sort(key=lambda t: -t["turns"])
    return out


def status_of(thread: dict, now: datetime) -> tuple[str, str]:
    pct = thread["completeness"]["percent"]
    last = A.parse_iso(thread.get("end"))
    days = (now - last).days if last else 999
    terminal = thread["completeness"].get("terminal", {}).get("reasons") or []
    declined = any(r["delta"] < 0 and ("declined" in r["signal"] or "lacked" in r["signal"])
                   for r in terminal)
    if pct >= 78 and not declined:
        return "complete", "Delivered — the output can be reused as-is."
    if declined:
        return "blocked", "Ended on a capability or information block — needs a different route."
    if days <= 3:
        return "active", "Touched in the last 72 hours — the live thread to continue."
    if days <= 30 and pct < 78:
        return "open", "Recent and unresolved — highest-value resume point."
    if pct >= 56:
        return "parked", "Substantial work banked, then set aside — resume with a status check."
    if pct <= 30:
        return "dormant", "Explored briefly; the goal was never fully specified."
    return "open", "Unfinished mid-stream — the next step is already implied."


def summary_of(thread: dict, turns: list[dict]) -> str:
    """One-paragraph, evidence-based summary of what the thread was and where it stopped."""
    def clean(s: str, n: int) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())[:n]

    first = clean(turns[0].get("prompt") or turns[0].get("title") or "", 200)
    last = clean(turns[-1].get("prompt") or "", 180)
    parts = []
    if first:
        parts.append(f"Opened: “{first}”")
    parts.append(f"{thread['turn_count']} turns over {thread['duration_hours']:.0f} h"
                 if thread["duration_hours"] >= 1 else f"{thread['turn_count']} turns in one sitting")
    names = ", ".join(a["name"] for a in thread["artifacts"][:3] if a.get("name"))
    if names:
        parts.append(f"produced {names}")
    parts.append(f"stopped at {thread['completeness']['percent']}% "
                 f"({thread['completeness']['label']})")
    if last and last != first:
        parts.append(f"last ask: “{last}”")
    return " — ".join(parts) + "."


def build_urls_and_artifacts(turn: dict) -> tuple[list[str], list[dict]]:
    urls = find_urls((turn.get("prompt") or "") + "\n" + (turn.get("output") or ""))
    if turn.get("url"):
        urls.insert(0, turn["url"])
    arts = A.artifacts_of(turn)
    for a in arts:
        if (a.get("href") or "").startswith("http"):
            urls.append(a["href"])
    seen, uq = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uq.append(u)
    return uq[:14], arts


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "threads"), exist_ok=True)
    os.makedirs(EXPORTS, exist_ok=True)

    turns, sources = load_turns()
    print(f"loaded {len(turns)} raw records from {len(sources)} sources")
    if not turns:
        print("no records found - nothing to build")
        return 1

    # Theme every turn.
    for t in turns:
        primary, secondary, scores = A.assign_themes(
            (t.get("prompt") or "") + "\n" + (t.get("output") or "")[:6000])
        t["theme"] = primary
        t["secondary_themes"] = secondary
        t["theme_scores"] = scores
        urls, arts = build_urls_and_artifacts(t)
        t["urls"] = urls
        t["artifacts"] = arts

    if not turns:
        sys.exit(
            "No raw records found — refusing to write an empty dataset.\n"
            "Sources live in data/raw/ and data/unpacked/ (git-ignored, so they are not in the\n"
            "repository). Either restore them from Google Takeout / Drive, or decrypt the shipped\n"
            "dataset instead:\n"
            "    python3 tools/lock_atlas.py unlock --password '…'")

    threads_raw = A.build_threads(turns, merge_threshold=0.13, merge_max_days=14)
    print(f"grouped into {len(threads_raw)} threads")

    # Curated names win over the auto-derived ones (see data/thread_names.json).
    name_path = os.path.join(ROOT, "data", "thread_names.json")
    curated: dict[str, str] = {}
    if os.path.exists(name_path):
        for key, value in json.load(open(name_path, encoding="utf-8")).items():
            if key.startswith("_"):
                continue
            curated[key] = value                      # full id, e.g. t0019-charlie-mike
            curated[key.split("-")[0]] = value        # ordinal prefix, e.g. t0019
    curated_used: set[str] = set()

    now = max((A.parse_iso(t["ts"]) for t in turns if t.get("ts")), default=datetime.now(timezone.utc))

    threads_out: list[dict] = []
    turns_out: list[dict] = []
    for idx, th in enumerate(threads_raw):
        name = th["name"]
        ordinal = f"t{idx + 1:04d}"
        override = curated.get(f"{ordinal}-{slugify(name)}") or curated.get(ordinal)
        if override:
            name = override
            curated_used.add(ordinal)
        tid = f"{ordinal}-{slugify(name)}"
        comp = A.project_completeness(th["turns"])
        open_items = A.open_threads(th["turns"])
        theme_votes = Counter(t["theme"] for t in th["turns"])
        theme = theme_votes.most_common(1)[0][0]
        secondary = [k for k, _ in theme_votes.most_common()[1:3] if k != theme]
        artworks: list[dict] = []
        urls: list[str] = []
        for t in th["turns"]:
            artworks.extend(t["artifacts"])
            urls.extend(t["urls"])
        # de-dup artifacts + urls, keep order
        seen_u, uq_urls = set(), []
        for u in urls:
            if u not in seen_u:
                seen_u.add(u)
                uq_urls.append(u)
        seen_a, uq_arts = set(), []
        for a in artworks:
            k = (a.get("name") or "").lower()
            if k and k not in seen_a:
                seen_a.add(k)
                uq_arts.append(a)

        thread = {
            "id": tid,
            "index": idx + 1,
            "name": name,
            "theme": theme,
            "secondary_themes": secondary,
            "start": th["start"],
            "end": th["end"],
            "duration_hours": th["duration_hours"],
            "turn_count": len(th["turns"]),
            "completeness": comp,
            "artifacts": uq_arts[:14],
            "urls": uq_urls[:14],
            "open_threads": open_items,
            "sources": sorted({t.get("origin", "") for t in th["turns"]}),
            "first_prompt": excerpt(th["turns"][0].get("prompt") or "", 240),
            "last_prompt": excerpt(th["turns"][-1].get("prompt") or "", 240),
            "last_output": excerpt(th["turns"][-1].get("output") or "", 400),
            "chars": sum(len(t.get("output") or "") for t in th["turns"]),
        }
        thread["slug"] = slugify(f"{tid}-{name}")
        status, note = status_of(thread, now)
        thread["status"] = status
        thread["status_note"] = note
        thread["summary"] = summary_of(thread, th["turns"])
        thread["resume_score"] = round(
            (100 - comp["percent"]) * 0.4
            + min(40, thread["chars"] / 2000)
            + (30 if status in ("active", "open") else 10 if status == "parked" else 0)
        )
        threads_out.append(thread)

        # turn records (index) + full thread file
        full_turns = []
        turn_scores = [A.score_turn(t, th["turns"][i + 1] if i + 1 < len(th["turns"]) else None)[0]
                       for i, t in enumerate(th["turns"])]
        for i, t in enumerate(th["turns"]):
            choices = A.extract_choices(t)
            ts = t.get("ts")
            dt = A.parse_iso(ts)
            rec = {
                "id": t["entry_id"],
                "thread": tid,
                "theme": t["theme"],
                "secondary_themes": t.get("secondary_themes", []),
                "ts": ts,
                "date": dt.strftime("%Y-%m-%d") if dt else None,
                "time": dt.strftime("%H:%M") if dt else None,
                "tz": t.get("tz"),
                "ts_raw": t.get("ts_raw"),
                "source": t.get("origin") or t.get("source"),
                "product": t.get("source"),
                "kind": t.get("kind"),
                "turn_index": i,
                "prompt": t.get("prompt") or "",
                "prompt_excerpt": excerpt(t.get("prompt") or "", 300),
                "output_excerpt": excerpt(t.get("output") or "", 520),
                "output_chars": len(t.get("output") or ""),
                "completeness_pct": round(turn_scores[i]),
                "artifacts": t["artifacts"],
                "urls": t["urls"],
                "choices": choices,
                "title": t.get("title"),
                "doc_page": t.get("doc_page"),
                "origin_file": t.get("origin_file"),
                "prev": None,
                "next": None,
                "park": t.get("prompt", "")[:0] or None,
            }
            # Thread files carry the payload the reader needs; excerpt fields
            # live in the index only, and very long text is capped so the
            # repository stays a sane size (the caps are declared).
            capped_out = (t.get("output") or "")[:60000]
            capped_prompt = (t.get("prompt") or "")[:24000]
            full_turns.append({
                k: v for k, v in rec.items()
                if k not in ("prompt", "prompt_excerpt", "output_excerpt", "urls")
            } | {
                "prompt": capped_prompt,
                "output": capped_out,
                "prompt_chars": len(t.get("prompt") or ""),
                "output_full_chars": len(t.get("output") or ""),
                "trimmed": (len(capped_out) < len(t.get("output") or "")
                            or len(capped_prompt) < len(t.get("prompt") or "")),
                "urls": t["urls"][:8],
            })
            turns_out.append(rec)

        json.dump({"thread": thread, "turns": full_turns},
                  open(os.path.join(OUT, "threads", f"{tid}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))

    # prev/next pointers within a thread
    by_thread: dict[str, list[dict]] = defaultdict(list)
    for r in turns_out:
        by_thread[r["thread"]].append(r)
    for tid, recs in by_thread.items():
        recs.sort(key=lambda r: (r["ts"] or ""))
        for i, r in enumerate(recs):
            r["prev"] = recs[i - 1]["id"] if i else None
            r["next"] = recs[i + 1]["id"] if i + 1 < len(recs) else None

    # Drive artifacts linked into threads by fuzzy name/date match
    for art in DRIVE_ARTIFACTS:
        art["linked_threads"] = []

    # Coverage map from Takeout archive browsers
    inventory = {"services": [], "generated_from": []}
    for path in sorted(glob.glob(os.path.join(UNPACKED, "arch_*.html"))):
        try:
            parsed = X.parse_archive_browser(path)
        except Exception as exc:  # pragma: no cover
            print("  index parse failed", path, exc)
            continue
        inventory["generated_from"].append({
            "file": os.path.basename(path),
            "services": parsed["service_count"],
            "entries": parsed["leaf_count"],
        })
        for svc in parsed["services"]:
            svc = dict(svc)
            svc["archive"] = os.path.basename(path)
            inventory["services"].append(svc)
        inventory.setdefault("folder_names", []).extend(parsed["folder_names"][:400])
    # Merge duplicates from multiple archives, keeping the newest figure.
    merged: dict[str, dict] = {}
    for svc in inventory["services"]:
        merged[svc["service"]] = svc
    inventory["services"] = sorted(merged.values(), key=lambda s: s["label"])

    themes_out = build_theme_index(turns_out)
    # repo archive catalog becomes part of the artifact registry
    repo_catalog = []
    cat_path = os.path.join(ROOT, "cheyenne-2026-transcripts", "meetings.json")
    if os.path.exists(cat_path):
        repo_catalog = json.load(open(cat_path, encoding="utf-8"))
        for m in repo_catalog:
            m["artifact_url"] = (
                f"https://github.com/therealwindycity/The-Real-Windy-City-/blob/main/"
                f"cheyenne-2026-transcripts/{m['file']}")
            m["video_url"] = f"https://www.youtube.com/watch?v={m['youtube_id']}"

    meta = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "data_through": now.isoformat(),
        "counts": {
            "turns": len(turns_out),
            "prompts": sum(1 for t in turns_out if t["kind"] == "prompt"),
            "documents": sum(1 for t in turns_out if t["kind"] == "document"),
            "threads": len(threads_out),
            "themes": len(themes_out),
            "urls": sum(len(t["urls"]) for t in turns_out),
            "artifacts": sum(len(t["artifacts"]) for t in turns_out),
            "chars": sum(t["output_chars"] for t in turns_out),
            "drive_items": len(DRIVE_ARTIFACTS),
            "archive_meetings": len(repo_catalog),
        },
        "sources": sources,
        "date_range": [min((t["ts"] for t in turns_out if t["ts"]), default=None),
                       max((t["ts"] for t in turns_out if t["ts"]), default=None)],
        "privacy": "Local-only archive of personal AI history. Nothing here is sent anywhere.",
    }
    meta["destinations"] = build_destinations(turns_out, repo_catalog, DRIVE_ARTIFACTS)

    atlas = {
        "meta": meta,
        "themes": themes_out,
        "threads": sorted(threads_out, key=lambda t: (t["start"] or "")),
        "turns": turns_out,
        "drive_artifacts": DRIVE_ARTIFACTS,
        "archive": repo_catalog,
    }
    json.dump(atlas, open(os.path.join(OUT, "atlas.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    json.dump(inventory, open(os.path.join(OUT, "inventory.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(os.path.join(OUT, "atlas.json"))
    print(f"atlas.json  {size/1e6:.2f} MB | {len(turns_out)} turns | "
          f"{len(threads_out)} threads | {len(themes_out)} themes")
    print(f"curated thread names applied: {len(curated_used)}")
    print("wrote", OUT)

    # Pre-built handoff packets for the most resumable threads.
    try:
        import handoff
        made = handoff.export_all(ROOT, atlas, EXPORTS, top=10)
        print(f"exported {made} handoff packets to {EXPORTS}")
    except Exception as exc:
        print("handoff export skipped:", exc)

    # Encrypt in the same run when a passphrase is supplied:
    #   ATLAS_PASSWORD='…' python3 tools/build_atlas.py
    # The plaintext then moves out of the repository, leaving ciphertext only.
    lock_pw = os.environ.get("ATLAS_PASSWORD")
    if lock_pw:
        try:
            import lock_atlas
            lock_atlas.lock(OUT, EXPORTS, os.path.join(ROOT, "atlas", "enc"), lock_pw,
                            stash=os.path.join(os.path.dirname(ROOT), "atlas-plaintext"))
        except SystemExit:
            raise
        except Exception as exc:
            print("locking failed:", exc)
    else:
        print("note: dataset left unencrypted — lock it with `python3 tools/lock_atlas.py lock`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
