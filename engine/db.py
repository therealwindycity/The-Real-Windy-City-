"""Storage: SQLite + FTS5 (zero services). Supabase/Postgres upgrade path in
supabase/schema.sql — table and column names are identical so the swap is
mechanical.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .util import data_dir, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    key            TEXT PRIMARY KEY,          -- jurisdiction/name
    jurisdiction   TEXT NOT NULL,
    name           TEXT NOT NULL,
    url            TEXT,
    method         TEXT NOT NULL,
    enabled        INTEGER NOT NULL DEFAULT 1,
    last_run       TEXT,
    last_status    TEXT,
    last_detail    TEXT,
    items_last_run INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS documents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key     TEXT NOT NULL,
    jurisdiction   TEXT NOT NULL,
    url            TEXT NOT NULL UNIQUE,
    title          TEXT,
    content_type   TEXT,
    method         TEXT,
    published_at   TEXT,
    first_seen     TEXT NOT NULL,
    last_fetched   TEXT NOT NULL,
    current_hash   TEXT,
    version_count  INTEGER NOT NULL DEFAULT 0,
    lat            REAL,
    lon            REAL
);

CREATE TABLE IF NOT EXISTS versions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id    INTEGER NOT NULL REFERENCES documents(id),
    hash           TEXT NOT NULL,
    fetched_at     TEXT NOT NULL,
    size           INTEGER,
    text           TEXT
);
CREATE INDEX IF NOT EXISTS ix_versions_doc ON versions(document_id);

CREATE TABLE IF NOT EXISTS events (
    id             TEXT PRIMARY KEY,
    jurisdiction   TEXT NOT NULL,
    kind           TEXT NOT NULL,   -- watchlist_hit | silent_edit | trend_flag | sentiment_shift | blocked_source | llm_flag
    severity       TEXT NOT NULL,   -- high | medium | low | info
    title          TEXT NOT NULL,
    quote          TEXT,
    source_url     TEXT,
    method         TEXT,
    fetched_at     TEXT,
    created_at     TEXT NOT NULL,
    watchlist_hits TEXT,            -- JSON list
    hash           TEXT,
    lat            REAL,
    lon            REAL,
    data           TEXT,            -- JSON blob (diffs, series, etc.)
    alerted        INTEGER NOT NULL DEFAULT 0,
    ledgered       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_events_created ON events(created_at);

CREATE TABLE IF NOT EXISTS metrics (
    jurisdiction   TEXT NOT NULL,
    series         TEXT NOT NULL,   -- e.g. building_permits:permits_per_month
    grp            TEXT NOT NULL,   -- e.g. ward 25 / topic Pilsen
    bucket         TEXT NOT NULL,   -- e.g. 2026-09 or cycle timestamp
    value          REAL NOT NULL,
    n              INTEGER,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (jurisdiction, series, grp, bucket)
);

CREATE TABLE IF NOT EXISTS jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT NOT NULL,
    payload        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'queued',
    attempts       INTEGER NOT NULL DEFAULT 0,
    error          TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key     TEXT UNIQUE,
    jurisdiction   TEXT NOT NULL,
    state          TEXT NOT NULL,
    kind           TEXT NOT NULL,   -- pra | bulk_access
    agency         TEXT,
    subject        TEXT NOT NULL,
    body           TEXT NOT NULL,
    source_url     TEXT,
    status         TEXT NOT NULL DEFAULT 'draft',  -- draft | reviewed | sent | answered | denied | overdue
    created_at     TEXT NOT NULL,
    sent_at        TEXT,
    due_at         TEXT,
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS ledger (
    seq            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id       TEXT NOT NULL,
    entry_hash     TEXT NOT NULL,
    prev_hash      TEXT NOT NULL,
    committed_at   TEXT NOT NULL
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5(
    title, text, url UNINDEXED, jurisdiction UNINDEXED, document_id UNINDEXED,
    tokenize = 'porter unicode61'
);
"""


def db_path() -> Path:
    return Path(os.getenv("REAPER_DB", data_dir() / "engine.db"))


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init(conn)
    return conn


def has_fts(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='doc_fts'").fetchone())


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    try:
        conn.executescript(FTS_SCHEMA)
    except sqlite3.OperationalError:
        pass  # FTS5 not compiled in: search degrades to LIKE
    conn.commit()


# ---------------------------------------------------------------- sources
def upsert_source(conn, jurisdiction: str, src: dict) -> str:
    key = f"{jurisdiction}/{src['name']}"
    conn.execute(
        """INSERT INTO sources(key, jurisdiction, name, url, method, enabled)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET url=excluded.url, method=excluded.method,
                                          enabled=excluded.enabled""",
        (key, jurisdiction, src["name"], src.get("url"), src["method"],
         1 if src.get("enabled", True) else 0))
    return key


def mark_source(conn, key: str, status: str, detail: str = "", items: int = 0):
    conn.execute(
        "UPDATE sources SET last_run=?, last_status=?, last_detail=?, items_last_run=? WHERE key=?",
        (now_iso(), status, detail[:500], items, key))
    conn.commit()


# ---------------------------------------------------------------- documents
def get_document(conn, url: str):
    return conn.execute("SELECT * FROM documents WHERE url=?", (url,)).fetchone()


def latest_version(conn, document_id: int):
    return conn.execute(
        "SELECT * FROM versions WHERE document_id=? ORDER BY id DESC LIMIT 1",
        (document_id,)).fetchone()


def store_version(conn, *, source_key: str, jurisdiction: str, url: str, title: str,
                  text: str, content_hash: str, content_type: str, method: str,
                  published_at: str | None = None, lat=None, lon=None,
                  fetched_at: str | None = None):
    """Insert/refresh a document. Returns (document_id, previous_version_row|None, changed:bool)."""
    ts = fetched_at or now_iso()
    doc = get_document(conn, url)
    if doc is None:
        cur = conn.execute(
            """INSERT INTO documents(source_key, jurisdiction, url, title, content_type, method,
                   published_at, first_seen, last_fetched, current_hash, version_count, lat, lon)
               VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)""",
            (source_key, jurisdiction, url, title, content_type, method, published_at,
             ts, ts, content_hash, lat, lon))
        doc_id = cur.lastrowid
        prev, changed = None, True
    else:
        doc_id = doc["id"]
        prev = latest_version(conn, doc_id)
        changed = doc["current_hash"] != content_hash
        conn.execute(
            """UPDATE documents SET last_fetched=?, title=COALESCE(?, title),
                   current_hash=?, version_count=version_count+? WHERE id=?""",
            (ts, title, content_hash, 1 if changed else 0, doc_id))
    if changed:
        conn.execute(
            "INSERT INTO versions(document_id, hash, fetched_at, size, text) VALUES(?,?,?,?,?)",
            (doc_id, content_hash, ts, len(text), text))
        if has_fts(conn):
            conn.execute("DELETE FROM doc_fts WHERE document_id=?", (doc_id,))
            conn.execute(
                "INSERT INTO doc_fts(title, text, url, jurisdiction, document_id) VALUES(?,?,?,?,?)",
                (title or "", text, url, jurisdiction, doc_id))
    conn.commit()
    return doc_id, prev, changed


# ---------------------------------------------------------------- events
def add_event(conn, ev: dict) -> bool:
    """Insert an event; returns True if new (idempotent on id)."""
    row = {
        "id": ev["id"], "jurisdiction": ev["jurisdiction"], "kind": ev["kind"],
        "severity": ev.get("severity", "info"), "title": ev["title"],
        "quote": ev.get("quote"), "source_url": ev.get("source_url"),
        "method": ev.get("method"), "fetched_at": ev.get("fetched_at"),
        "created_at": ev.get("created_at") or now_iso(),
        "watchlist_hits": json.dumps(ev.get("watchlist_hits") or []),
        "hash": ev.get("hash"), "lat": ev.get("lat"), "lon": ev.get("lon"),
        "data": json.dumps(ev.get("data") or {}),
    }
    cur = conn.execute(
        f"INSERT OR IGNORE INTO events({','.join(row)}) VALUES({','.join('?' * len(row))})",
        tuple(row.values()))
    conn.commit()
    return cur.rowcount == 1


def event_dict(row) -> dict:
    d = dict(row)
    for k in ("watchlist_hits", "data"):
        try:
            d[k] = json.loads(d.get(k) or ("[]" if k == "watchlist_hits" else "{}"))
        except (TypeError, json.JSONDecodeError):
            pass
    return d


def list_events(conn, jurisdiction: str | None = None, kind: str | None = None,
                severity: str | None = None, since: str | None = None,
                q: str | None = None, limit: int = 200) -> list[dict]:
    sql, args = "SELECT * FROM events WHERE 1=1", []
    for col, val in (("jurisdiction", jurisdiction), ("kind", kind), ("severity", severity)):
        if val:
            sql += f" AND {col}=?"
            args.append(val)
    if since:
        sql += " AND created_at>=?"
        args.append(since)
    if q:
        sql += " AND (title LIKE ? OR quote LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY created_at DESC, id LIMIT ?"
    args.append(limit)
    return [event_dict(r) for r in conn.execute(sql, args)]


# ---------------------------------------------------------------- search
def search(conn, query: str, jurisdiction: str | None = None, limit: int = 50) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    if has_fts(conn):
        fts_q = " ".join(f'"{t}"' for t in query.replace('"', " ").split())
        sql = """SELECT d.id, d.url, d.title, d.jurisdiction, d.last_fetched, d.method,
                        snippet(doc_fts, 1, '[[', ']]', ' … ', 24) AS snippet, bm25(doc_fts) AS score
                 FROM doc_fts JOIN documents d ON d.id = doc_fts.document_id
                 WHERE doc_fts MATCH ?"""
        args: list = [fts_q]
        if jurisdiction:
            sql += " AND d.jurisdiction=?"
            args.append(jurisdiction)
        sql += " ORDER BY score LIMIT ?"
        args.append(limit)
        try:
            return [dict(r) for r in conn.execute(sql, args)]
        except sqlite3.OperationalError:
            pass
    sql = """SELECT d.id, d.url, d.title, d.jurisdiction, d.last_fetched, d.method,
                    substr(v.text, max(1, instr(lower(v.text), lower(?)) - 80), 240) AS snippet
             FROM documents d JOIN versions v ON v.id = (SELECT max(id) FROM versions WHERE document_id=d.id)
             WHERE lower(v.text) LIKE ?"""
    args = [query, f"%{query.lower()}%"]
    if jurisdiction:
        sql += " AND d.jurisdiction=?"
        args.append(jurisdiction)
    sql += " LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args)]


# ---------------------------------------------------------------- metrics
def put_metric(conn, jurisdiction, series, grp, bucket, value, n=None):
    conn.execute(
        """INSERT INTO metrics(jurisdiction, series, grp, bucket, value, n, updated_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(jurisdiction, series, grp, bucket)
           DO UPDATE SET value=excluded.value, n=excluded.n, updated_at=excluded.updated_at""",
        (jurisdiction, series, str(grp), bucket, float(value), n, now_iso()))


def get_series(conn, jurisdiction, series, grp=None) -> list[dict]:
    sql = "SELECT * FROM metrics WHERE jurisdiction=? AND series=?"
    args = [jurisdiction, series]
    if grp is not None:
        sql += " AND grp=?"
        args.append(str(grp))
    sql += " ORDER BY grp, bucket"
    return [dict(r) for r in conn.execute(sql, args)]


# ---------------------------------------------------------------- jobs
def enqueue(conn, kind: str, payload: dict) -> int:
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO jobs(kind, payload, status, created_at, updated_at) VALUES(?,?,?,?,?)",
        (kind, json.dumps(payload), "queued", ts, ts))
    conn.commit()
    return cur.lastrowid


def claim_jobs(conn, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status='queued' AND attempts < 3 ORDER BY id LIMIT ?",
        (limit,)).fetchall()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


def finish_job(conn, job_id: int, error: str | None = None):
    conn.execute(
        """UPDATE jobs SET attempts=attempts+1, error=?, updated_at=?,
               status=CASE WHEN ? IS NULL THEN 'done'
                           WHEN attempts+1 >= 3 THEN 'failed' ELSE 'queued' END
           WHERE id=?""",
        (error, now_iso(), error, job_id))
    conn.commit()
