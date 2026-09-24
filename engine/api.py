"""Public read-only API for journalists and developers.

    python run.py api            # or: uvicorn engine.api:app --host 0.0.0.0 --port 8000

GET /health · /events · /events/{id} · /search?q= · /requests · /sources
    /metrics/{jurisdiction}/{series} · /ledger/verify
Read-only by design: nothing here can send a request or modify the record.
Set REAPER_DATA_DIR=data/demo to serve the demo database.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, db, ledger

app = FastAPI(title="Windy City Reaper — Public Civic Ledger API", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def _conn():
    return db.connect()


@app.get("/health")
def health():
    conn = _conn()
    n = conn.execute("SELECT count(*) FROM events").fetchone()[0]
    return {"ok": True, "version": __version__, "events": n, "db": str(db.db_path())}


@app.get("/events")
def events(jurisdiction: str | None = None, kind: str | None = None, severity: str | None = None,
           since: str | None = None, q: str | None = None, limit: int = Query(100, le=1000)):
    return db.list_events(_conn(), jurisdiction, kind, severity, since, q, limit)


@app.get("/events/{event_id}")
def event(event_id: str):
    row = _conn().execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        raise HTTPException(404, "event not found")
    return db.event_dict(row)


@app.get("/search")
def search(q: str, jurisdiction: str | None = None, limit: int = Query(25, le=200)):
    return db.search(_conn(), q, jurisdiction, limit)


@app.get("/requests")
def requests_(jurisdiction: str | None = None, status: str | None = None):
    sql, args = "SELECT id, jurisdiction, state, kind, agency, subject, source_url, status, created_at, sent_at, due_at FROM requests WHERE 1=1", []
    if jurisdiction:
        sql += " AND jurisdiction=?"
        args.append(jurisdiction)
    if status:
        sql += " AND status=?"
        args.append(status)
    return [dict(r) for r in _conn().execute(sql + " ORDER BY id DESC", args)]


@app.get("/sources")
def sources():
    return [dict(r) for r in _conn().execute("SELECT * FROM sources ORDER BY key")]


@app.get("/metrics/{jurisdiction}/{series}")
def metrics(jurisdiction: str, series: str, group: str | None = None):
    return db.get_series(_conn(), jurisdiction, series, group)


@app.get("/ledger/verify")
def ledger_verify():
    ok, n, msg = ledger.verify()
    return {"ok": ok, "entries": n, "message": msg}
