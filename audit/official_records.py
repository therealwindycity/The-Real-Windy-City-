"""
OFFICIAL RECORDS EXTRACT
========================

Builds ``audit/reference/official_records.json``, the official-record layer the
reconciliation engine checks the transcripts against. It contains, for every
City of Cheyenne governing-body meeting in the CivicWatch database:

* the meeting itself (date, kind, Granicus clip, agenda and minutes URLs)
* the published agenda items (number, title, recommended action, sponsor, consent flag)
* the full text of the official minutes ("Record of Proceedings"), page by page

Source: ``civic.db`` from the CivicWatch pipeline in
``bartimoussmith-oss/therealwindycity`` (``2026-09-14-council/civicwatch/data``).
That database holds text extracted from the city's own Granicus PDFs. This
script copies the public-record fields verbatim and records where each one came
from, so the 55 MB database doesn't have to be shipped.

Usage
-----
    python audit/official_records.py --db /path/to/civic.db [--since 2025-01-01]
    python audit/official_records.py --fetch          # sparse-clone the source repo into a temp dir first
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "reference" / "official_records.json"
SOURCE_REPO = "https://github.com/bartimoussmith-oss/therealwindycity"
DB_PATH_IN_REPO = "2026-09-14-council/civicwatch/data/civic.db"
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
_DATE_LINE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|"
                        r"November|December)\s+(\d{1,2}),\s+(\d{4})\b")


def minutes_date(text: str) -> str | None:
    """Meeting date as printed in the minutes header. Granicus listing dates
    are sometimes off by a day (for example, the June 22 meeting is listed as June 23)."""
    m = _DATE_LINE.search(text[:600])
    if not m:
        return None
    return f"{int(m.group(3)):04d}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"


def extract(db_path: Path, since: str, source_commit: str | None) -> dict:
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    meetings = []
    for m in c.execute("SELECT * FROM meetings WHERE date >= ? ORDER BY date, kind", (since,)):
        items = [dict(item_no=r["item_no"], title=re.sub(r"\s+", " ", r["title"] or "").strip(),
                      action=r["action"] or "", sponsor=r["sponsor"] or "", consent=bool(r["consent"]))
                 for r in c.execute("SELECT * FROM items WHERE meeting_id=? ORDER BY id", (m["id"],))]
        minutes = []
        for d in c.execute("SELECT * FROM docs WHERE meeting_id=? AND role='minutes' ORDER BY id", (m["id"],)):
            pages = [r["text"] for r in c.execute(
                "SELECT page, text FROM pages WHERE doc_id=? ORDER BY page", (d["id"],))]
            text = "\f".join(pages)
            minutes.append({"doc_id": d["id"], "url": d["url"], "sha1": d["sha1"], "pages": len(pages),
                            "ocr": bool(d["ocr"]), "printed_date": minutes_date(text), "text": text})
        printed = next((x["printed_date"] for x in minutes if x["printed_date"]), None)
        meetings.append({
            "meeting_key": f"{printed or m['date']}|{m['kind']}",
            "date": printed or m["date"],
            "listing_date": m["date"],
            "kind": m["kind"],
            "special": "special" in m["kind"].lower(),
            "clip_id": m["clip_id"],
            "agenda_url": m["agenda_url"],
            "minutes_url": m["minutes_url"],
            "items": items,
            "minutes": minutes,
        })
    return {
        "generated_from": {"repo": SOURCE_REPO, "path": DB_PATH_IN_REPO, "commit": source_commit,
                           "extracted_at": datetime.now().date().isoformat(), "since": since},
        "note": "Verbatim public-record fields from City of Cheyenne Granicus agendas and minutes, "
                "via CivicWatch text extraction. Verify against the linked PDF before quoting.",
        "meetings": meetings,
    }


def fetch_db(workdir: Path) -> tuple[Path, str]:
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse",
                    SOURCE_REPO, str(workdir)], check=True)
    subprocess.run(["git", "-C", str(workdir), "sparse-checkout", "set", "--no-cone", "/" + DB_PATH_IN_REPO],
                   check=True)
    sha = subprocess.run(["git", "-C", str(workdir), "rev-parse", "HEAD"], check=True,
                         capture_output=True, text=True).stdout.strip()
    return workdir / DB_PATH_IN_REPO, sha


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path)
    ap.add_argument("--fetch", action="store_true", help="sparse-clone the source repo to get civic.db")
    ap.add_argument("--commit", help="source commit to record (auto when --fetch)")
    ap.add_argument("--since", default="2025-01-01")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    commit = a.commit
    if a.fetch:
        tmp = Path(tempfile.mkdtemp(prefix="civicwatch-"))
        db, commit = fetch_db(tmp / "repo")
    elif a.db:
        db = a.db
        if not commit:
            r = subprocess.run(["git", "-C", str(db.parent), "rev-parse", "HEAD"], capture_output=True, text=True)
            commit = r.stdout.strip() or None
    else:
        ap.error("--db or --fetch required")
    data = extract(db, a.since, commit)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    n_items = sum(len(m["items"]) for m in data["meetings"])
    n_min = sum(len(m["minutes"]) for m in data["meetings"])
    print(f"[+] {len(data['meetings'])} meetings, {n_items} agenda items, {n_min} minutes docs -> {a.out} "
          f"({a.out.stat().st_size/1e6:.1f} MB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
