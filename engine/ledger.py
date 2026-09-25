"""Public, append-only, hash-chained event ledger (data/ledger/events.jsonl).

Each line carries prev_hash and entry_hash = sha256(prev_hash + canonical JSON),
so any retroactive edit or deletion breaks the chain — the engine holds itself
to the same silent-edit standard it holds governments to.
"""
from __future__ import annotations

import json
from pathlib import Path

from .util import data_dir, now_iso, sha256

GENESIS = "0" * 64
PUBLIC_FIELDS = ("id", "jurisdiction", "kind", "severity", "title", "quote", "source_url",
                 "method", "fetched_at", "created_at", "watchlist_hits", "hash")


def ledger_path() -> Path:
    return data_dir() / "ledger" / "events.jsonl"


def _last_hash(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return GENESIS
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 65536))
        last = [ln for ln in fh.read().splitlines() if ln.strip()][-1]
    return json.loads(last)["entry_hash"]


def canonical(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def commit(conn, path: Path | None = None) -> tuple[int, str]:
    path = path or ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute("SELECT * FROM events WHERE ledgered=0 ORDER BY created_at, id").fetchall()
    prev = _last_hash(path)
    n = 0
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            entry = {k: r[k] for k in PUBLIC_FIELDS}
            entry["watchlist_hits"] = json.loads(entry["watchlist_hits"] or "[]")
            entry_hash = sha256(prev + canonical(entry))
            fh.write(canonical({**entry, "prev_hash": prev, "entry_hash": entry_hash}) + "\n")
            conn.execute("INSERT INTO ledger(event_id, entry_hash, prev_hash, committed_at) VALUES(?,?,?,?)",
                         (r["id"], entry_hash, prev, now_iso()))
            conn.execute("UPDATE events SET ledgered=1 WHERE id=?", (r["id"],))
            prev = entry_hash
            n += 1
    conn.commit()
    return n, prev


def verify(path: Path | None = None) -> tuple[bool, int, str]:
    """Returns (ok, entries_checked, message)."""
    path = path or ledger_path()
    if not path.exists():
        return True, 0, "ledger empty"
    prev = GENESIS
    n = 0
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            eh, ph = rec.pop("entry_hash"), rec.pop("prev_hash")
            if ph != prev:
                return False, n, f"line {i}: prev_hash mismatch (chain broken)"
            if sha256(prev + canonical(rec)) != eh:
                return False, n, f"line {i}: entry_hash mismatch (entry altered)"
            prev = eh
            n += 1
    return True, n, f"{n} entries verified; head {prev[:12]}…"
