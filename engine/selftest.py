"""End-to-end proof of the pipeline against the offline fixture world.

`run_fixture_world(data_dir)` runs two civic cycles (with a silent edit
published between them) and returns the connection + a list of checks.
Used by `run.py selftest` (throwaway temp dir) and `run.py demo` (data/demo/).
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from . import db, ledger, pipeline
from .fixtures import FixtureWorld
from .net import Gate
from .util import load_config, now


@contextmanager
def _data_dir(path: Path):
    old = os.environ.get("REAPER_DATA_DIR")
    os.environ["REAPER_DATA_DIR"] = str(path)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("REAPER_DATA_DIR", None)
        else:
            os.environ["REAPER_DATA_DIR"] = old


def run_fixture_world(data_dir: Path, log=print):
    log = log or (lambda *_: None)
    data_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("engine.db", "engine.db-wal", "engine.db-shm", "ledger/events.jsonl"):
        (data_dir / stale).unlink(missing_ok=True)
    checks: list[tuple[str, bool, str]] = []
    with _data_dir(data_dir), FixtureWorld() as world:
        cfg = world.config(load_config())
        conn = db.connect(data_dir / "engine.db")
        gate = Gate(cfg["identity"], respect_robots=True)  # real robots gate, served locally

        # Last week's sentiment baseline (synthetic) so a week-over-week shift is observable.
        y, w, _ = (now() - dt.timedelta(days=7)).isocalendar()
        db.put_metric(conn, "demo_chicago", "sentiment", "Pilsen", f"{y}-W{w:02d}", 0.05, 41)
        conn.commit()

        log("── cycle 1 ─────────────────────────────────────────────")
        pipeline.cycle(conn, cfg, gate, log=log, dry_run_alerts=True)
        world.mutate()
        log("── agency silently edits Agenda Item 22-91 ─────────────")
        log("── cycle 2 ─────────────────────────────────────────────")
        pipeline.cycle(conn, cfg, gate, log=log, dry_run_alerts=True)

        def kinds(kind, **where):
            return [e for e in db.list_events(conn, kind=kind, limit=500)
                    if all(e.get(k) == v for k, v in where.items())]

        se = kinds("silent_edit")
        checks.append(("silent edit caught with removed line",
                       any("competitive bid" in " ".join(e["data"].get("removed", [])) for e in se),
                       f"{len(se)} silent_edit event(s)"))
        wl = kinds("watchlist_hit")
        labels = {l for e in wl for l in e["watchlist_hits"]}
        checks.append(("watchlist hits carry verbatim quotes",
                       {"no-bid contract", "zoning change", "annexation"} <= labels and all(e["quote"] for e in wl),
                       ", ".join(sorted(labels))))
        checks.append(("robots.txt honored (0 hits on disallowed path)", world.private_hits == 0,
                       f"{world.private_hits} requests to /private/"))
        reqs = conn.execute("SELECT * FROM requests WHERE kind='bulk_access'").fetchall()
        checks.append(("blocked sources → bulk records requests drafted",
                       any("5 ILCS 140" in r["body"] for r in reqs) and any("24-72" in r["body"] for r in reqs),
                       f"{len(reqs)} draft(s): " + ", ".join(f"#{r['id']} {r['state']}" for r in reqs)))
        tf = kinds("trend_flag")
        grps = {e["data"]["group"] for e in tf}
        checks.append(("permit trend flagged for area 31 only", grps == {"31"}, f"flagged groups: {sorted(grps)}"))
        ss = kinds("sentiment_shift")
        checks.append(("sentiment shift detected for Pilsen",
                       any(e["data"].get("topic") == "Pilsen" for e in ss), f"{len(ss)} shift event(s)"))
        leg = kinds("watchlist_hit", jurisdiction="demo_denver")
        checks.append(("legistar matters scanned (sole-source)",
                       any("sole-source award" in e["watchlist_hits"] for e in leg), f"{len(leg)} hit(s)"))
        el = [e for e in kinds("watchlist_hit", jurisdiction="demo_chicago") if "chicityclerkelms" in (e["source_url"] or "")]
        checks.append(("Chicago eLMS matters scanned (emergency procurement)",
                       any("emergency procurement" in e["watchlist_hits"] for e in el), f"{len(el)} hit(s)"))
        hits = db.search(conn, "variance")
        checks.append(("full-text search finds 'variance'", bool(hits), f"{len(hits)} result(s)"))
        ok, n, msg = ledger.verify()
        checks.append(("hash-chained ledger verifies", ok and n > 0, msg))
        dup = conn.execute("SELECT count(*) FROM events").fetchone()[0]
        checks.append(("cycle is idempotent (no duplicate events)",
                       dup == len({r[0] for r in conn.execute('SELECT id FROM events')}), f"{dup} events total"))
    return conn, checks


def selftest(log=print) -> bool:
    with tempfile.TemporaryDirectory(prefix="reaper-selftest-") as tmp:
        conn, checks = run_fixture_world(Path(tmp), log=log)
        conn.close()
    log("\n── selftest results ─────────────────────────────────────")
    for name, ok, detail in checks:
        log(f"  {'PASS' if ok else 'FAIL'}  {name}  ({detail})")
    all_ok = all(ok for _, ok, _ in checks)
    log(f"\n{'ALL CHECKS PASSED' if all_ok else 'SELFTEST FAILED'} ({sum(ok for _, ok, _ in checks)}/{len(checks)})")
    return all_ok
