#!/usr/bin/env python3
"""Windy City Reaper — command line.

  python run.py selftest                 prove the whole pipeline offline (no installs, no network)
  python run.py demo                     build data/demo/ from synthetic fixtures for the dashboard
  python run.py cycle [-j chicago_il]    crawl -> analyze -> trends/sentiment -> alerts -> ledger -> digest
  python run.py crawl | work | digest    individual stages
  python run.py sources                  list configured sources + last status
  python run.py search "zoning variance"
  python run.py request pra -j cheyenne_wy -r "All emails re: Ordinance 4687" [--range "..."]
  python run.py request sent 3           mark request #3 as sent -> statutory due date computed
  python run.py ledger verify
  python run.py api                      serve the public read API (needs fastapi + uvicorn)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine import alerts, db, ledger, pipeline, records
from engine.util import data_dir, load_config


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Windy City Reaper — civic accountability engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    sub.add_parser("demo")
    sub.add_parser("init")
    for name in ("cycle", "crawl"):
        p = sub.add_parser(name)
        p.add_argument("-j", "--jurisdiction", action="append")
        p.add_argument("-s", "--source", action="append")
    sub.add_parser("work")
    sub.add_parser("alerts")
    p = sub.add_parser("digest")
    p.add_argument("--hours", type=int, default=24)
    sub.add_parser("sources")
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("-j", "--jurisdiction")
    p = sub.add_parser("request")
    rs = p.add_subparsers(dest="rcmd", required=True)
    pr = rs.add_parser("pra")
    pr.add_argument("-j", "--jurisdiction", required=True)
    pr.add_argument("-r", "--records", required=True, help="description of the records sought")
    pr.add_argument("--range", default="January 1, 2025 to present")
    pr.add_argument("--fee-limit", default="$50")
    ps = rs.add_parser("sent")
    ps.add_argument("id", type=int)
    rs.add_parser("list")
    p = sub.add_parser("ledger")
    p.add_argument("action", choices=["verify", "commit"])
    p = sub.add_parser("api")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    if a.cmd == "selftest":
        from engine.selftest import selftest
        return 0 if selftest() else 1
    if a.cmd == "demo":
        from engine.selftest import run_fixture_world
        conn, checks = run_fixture_world(data_dir() / "demo")
        print(f"\nDemo database ready: {data_dir() / 'demo' / 'engine.db'} "
              f"({sum(ok for _, ok, _ in checks)}/{len(checks)} checks passed)")
        return 0
    if a.cmd == "api":
        import uvicorn
        uvicorn.run("engine.api:app", host=a.host, port=a.port)
        return 0

    cfg = load_config()
    conn = db.connect()
    for jkey, src in pipeline.iter_sources(cfg, include_disabled=True):
        db.upsert_source(conn, jkey, src)
    conn.commit()

    if a.cmd == "init":
        print(f"initialized {db.db_path()} with {len(list(pipeline.iter_sources(cfg, include_disabled=True)))} sources")
    elif a.cmd == "cycle":
        r = pipeline.cycle(conn, cfg, jurisdictions=a.jurisdiction, sources=a.source)
        return 0 if any(c["status"] != "error" for c in r["crawl"]) or not r["crawl"] else 2
    elif a.cmd == "crawl":
        pipeline.crawl(conn, cfg, jurisdictions=a.jurisdiction, sources=a.source)
    elif a.cmd == "work":
        pipeline.work(conn, cfg)
        pipeline.trends(conn, cfg)
        pipeline.sentiment(conn, cfg)
    elif a.cmd == "alerts":
        print(json.dumps(alerts.dispatch(conn), indent=2))
    elif a.cmd == "digest":
        print(pipeline.write_digest(conn, cfg, a.hours))
    elif a.cmd == "sources":
        for r in conn.execute("SELECT * FROM sources ORDER BY key"):
            flag = "" if r["enabled"] else " (disabled)"
            print(f"{r['key']:<42} {r['method']:<10} {str(r['last_status'] or '-'):<13} "
                  f"{r['last_run'] or '':<21} {r['last_detail'] or ''}{flag}")
    elif a.cmd == "search":
        for h in db.search(conn, a.query, a.jurisdiction):
            print(f"[{h['jurisdiction']}] {h['title']}\n  {h['url']}\n  …{h['snippet']}…\n")
    elif a.cmd == "request":
        if a.rcmd == "pra":
            jcfg = cfg["jurisdictions"][a.jurisdiction]
            rid, _ = records.save_request(conn, jurisdiction=a.jurisdiction, jcfg=jcfg, kind="pra",
                                          records_description=a.records, date_range=a.range,
                                          fee_limit=a.fee_limit, identity=cfg.get("identity"))
            row = conn.execute("SELECT body FROM requests WHERE id=?", (rid,)).fetchone()
            print(f"Draft request #{rid} saved (status=draft). Review, sign and send it yourself.\n")
            print(row["body"])
        elif a.rcmd == "sent":
            due = records.mark_sent(conn, a.id)
            print(f"request #{a.id} marked sent; response due {due or '(no fixed statutory deadline)'}")
        else:
            for r in conn.execute("SELECT * FROM requests ORDER BY id"):
                print(f"#{r['id']:<4} {r['status']:<9} {r['jurisdiction']:<13} {r['kind']:<12} "
                      f"due={r['due_at'] or '-':<11} {r['subject'][:90]}")
    elif a.cmd == "ledger":
        if a.action == "commit":
            n, head = ledger.commit(conn)
            print(f"+{n} entries, head {head}")
        else:
            ok, n, msg = ledger.verify()
            print(("OK  " if ok else "BROKEN  ") + msg)
            return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
