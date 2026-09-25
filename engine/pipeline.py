"""Orchestration: crawl -> work (analyze jobs) -> correlate (trends, sentiment,
overdue requests) -> alert -> ledger -> digest.
"""
from __future__ import annotations

import datetime as dt

from . import alerts, analyze, db, ledger, records
from .detect import silent_edit_event
from .ingest import SILENT_EDIT_METHODS, crawl_source
from .net import Gate
from .util import data_dir, now, now_iso, short_id


def _log(msg: str, log=print):
    if log:
        log(f"[{now().strftime('%H:%M:%S')}] {msg}")


def iter_sources(cfg, jurisdictions=None, sources=None, include_disabled=False):
    for jkey, jcfg in cfg["jurisdictions"].items():
        if jurisdictions and jkey not in jurisdictions:
            continue
        for src in jcfg.get("sources", []):
            if sources and src["name"] not in sources:
                continue
            if src.get("enabled", True) or include_disabled:
                yield jkey, src


def find_source(cfg, source_key: str) -> dict:
    jkey, _, name = source_key.partition("/")
    for src in cfg["jurisdictions"].get(jkey, {}).get("sources", []):
        if src["name"] == name:
            return src
    return {}


# ------------------------------------------------------------------ crawl
def crawl(conn, cfg, gate: Gate | None = None, jurisdictions=None, sources=None, log=print) -> list[dict]:
    gate = gate or Gate(cfg["identity"])
    results = []
    for jkey, src in iter_sources(cfg, jurisdictions, sources):
        r = crawl_source(conn, gate, cfg, jkey, src)
        _log(f"jurisdiction={jkey} source={src['name']} [{src['method']}] → "
             f"{r['status'].upper()} · {r['detail']}", log)
        results.append(r)
    return results


# ------------------------------------------------------------------ work
def analyze_document(conn, cfg, document_id: int, prev_version_id: int | None) -> list[str]:
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if doc is None:
        return []
    cur = db.latest_version(conn, document_id)
    if cur is None:
        return []
    jkey, text = doc["jurisdiction"], cur["text"] or ""
    compiled = analyze.compile_watchlist(cfg["watchlist"], jkey)
    created: list[str] = []
    base = dict(jurisdiction=jkey, url=doc["url"], title=doc["title"], fetched_at=cur["fetched_at"],
                method=doc["method"], lat=doc["lat"], lon=doc["lon"])

    # 1. silent edits (published documents only; feeds/API metadata legitimately change)
    if prev_version_id and doc["method"] in SILENT_EDIT_METHODS:
        prev = conn.execute("SELECT * FROM versions WHERE id=?", (prev_version_id,)).fetchone()
        if prev is not None:
            ev = silent_edit_event(prev_version=prev, new_text=text, new_hash=cur["hash"], **base)
            if ev and db.add_event(conn, ev):
                created.append("silent_edit")

    # 2. watchlist
    ev = analyze.watchlist_event(text=text, content_hash=cur["hash"], compiled=compiled, **base)
    if ev and db.add_event(conn, ev):
        created.append("watchlist_hit")

    # 3. optional LLM pass — only on documents that already matter, to bound cost
    if analyze.llm_configured() and (ev or doc["method"] in SILENT_EDIT_METHODS):
        flags, method = analyze.llm_flags(text, [t.get("label", t["term"]) for _, t in compiled])
        for f in flags:
            sev = f.get("severity") if f.get("severity") in analyze.SEV_RANK else "medium"
            if db.add_event(conn, {
                "id": short_id("llm", doc["url"], cur["hash"], f["quote"][:80]),
                "jurisdiction": jkey, "kind": "llm_flag", "severity": sev,
                "title": f"{f.get('title', 'AI red flag')} — {doc['title'] or doc['url']}"[:300],
                "quote": f["quote"][:600], "source_url": doc["url"], "method": method,
                "fetched_at": cur["fetched_at"], "hash": cur["hash"], "lat": doc["lat"], "lon": doc["lon"],
                "data": {"why": f.get("why", "")},
            }):
                created.append("llm_flag")
    return created


def work(conn, cfg, log=print, limit: int = 5000) -> dict:
    counts: dict[str, int] = {}
    jobs = db.claim_jobs(conn, limit)
    for job in jobs:
        try:
            if job["kind"] == "analyze":
                p = job["payload"]
                for kind in analyze_document(conn, cfg, p["document_id"], p.get("prev_version_id")):
                    counts[kind] = counts.get(kind, 0) + 1
            db.finish_job(conn, job["id"])
        except Exception as e:  # keep the queue moving; job retried up to 3x
            db.finish_job(conn, job["id"], error=f"{type(e).__name__}: {e}")
    _log(f"worked {len(jobs)} jobs → new events {counts or '{}'}", log)
    return {"jobs": len(jobs), "events": counts}


# ------------------------------------------------------------------ correlate
def trends(conn, cfg, log=print) -> int:
    n = 0
    current = now().strftime("%Y-%m")
    for jkey, src in iter_sources(cfg):
        t = src.get("trend")
        if src.get("method") != "api" or not t:
            continue
        series = f"{src['name']}:{t['series']}"
        rows = db.get_series(conn, jkey, series)
        min_excess = float(t.get("min_excess_growth", 0.25))
        for grp, vals, buckets, s in analyze.trend_flags(
                rows, float(t.get("min_slope", 3)), int(t.get("min_points", 3)),
                int(t.get("window", 3)), current_bucket=current):
            # Seasonality control: a group must outgrow the whole city over the same buckets.
            ok, grp_ratio, city_ratio = analyze.outpaces_city(rows, vals, buckets, min_excess)
            if not ok:
                continue
            label = src.get("group_label", src.get("group_field", "group"))
            pretty = src["name"].replace("_", " ").capitalize()
            if db.add_event(conn, {
                "id": short_id("trend", jkey, series, str(grp), buckets[-1]),
                "jurisdiction": jkey, "kind": "trend_flag", "severity": "medium",
                "title": f"{pretty} up {100 * (grp_ratio - 1):.0f}% vs citywide {100 * (city_ratio - 1):+.0f}% — {label} {grp}",
                "quote": f"Monthly counts {' → '.join(str(int(v)) for v in vals)} "
                         f"({', '.join(buckets)}); slope +{s:.1f}/mo. Citywide change over the same months: "
                         f"{100 * (city_ratio - 1):+.0f}%.",
                "source_url": src["url"], "method": "official_api+trend",
                "fetched_at": now_iso(),
                "data": {"series": series, "group": grp, "values": vals, "buckets": buckets, "slope": s,
                         "group_ratio": grp_ratio, "city_ratio": city_ratio},
            }):
                n += 1
                _log(f"trend: [{jkey}] {series} {label} {grp} = {vals} → ×{grp_ratio:.2f} vs city ×{city_ratio:.2f} → FLAG", log)
    return n


def _week(d: dt.datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def sentiment(conn, cfg, log=print, days: int = 7) -> int:
    topics_by_j = cfg["watchlist"].get("sentiment_topics", {})
    threshold = float(cfg["watchlist"].get("sentiment_shift_threshold", 0.15))
    since = (now() - dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")
    bucket = _week(now())
    n = 0
    for jkey, topics in topics_by_j.items():
        src_keys = [f"{jkey}/{s['name']}" for j, s in iter_sources(cfg, [jkey]) if s.get("sentiment")]
        if not src_keys:
            continue
        rows = conn.execute(
            f"""SELECT d.url, v.text FROM documents d
                JOIN versions v ON v.id = (SELECT max(id) FROM versions WHERE document_id=d.id)
                WHERE d.source_key IN ({','.join('?' * len(src_keys))}) AND d.first_seen >= ?""",
            (*src_keys, since)).fetchall()
        for topic in topics:
            scores = [analyze.sentiment(s) for r in rows for s in analyze.topic_mentions(r["text"], topic)]
            if not scores:
                continue
            avg = sum(scores) / len(scores)
            db.put_metric(conn, jkey, "sentiment", topic, bucket, avg, len(scores))
            conn.commit()
            hist = db.get_series(conn, jkey, "sentiment", topic)
            prev = [h for h in hist if h["bucket"] < bucket]
            if prev and len(scores) >= 3:
                delta = avg - prev[-1]["value"]
                if abs(delta) >= threshold:
                    direction = "down" if delta < 0 else "up"
                    if db.add_event(conn, {
                        "id": short_id("sentiment", jkey, topic, bucket, direction),
                        "jurisdiction": jkey, "kind": "sentiment_shift",
                        "severity": "medium" if delta < 0 else "low",
                        "title": f"News sentiment on “{topic}” {direction} {abs(delta):.2f}",
                        "quote": f"Average polarity {avg:+.2f} over {len(scores)} mentions this week "
                                 f"(was {prev[-1]['value']:+.2f} in {prev[-1]['bucket']}).",
                        "method": "rss+lexicon_sentiment", "fetched_at": now_iso(),
                        "data": {"topic": topic, "avg": avg, "n": len(scores), "prev": prev[-1]["value"]},
                    }):
                        n += 1
                        _log(f"sentiment: [{jkey}] “{topic}” avg {avg:+.2f} (n={len(scores)}) "
                             f"{direction} from {prev[-1]['value']:+.2f}", log)
    return n


# ------------------------------------------------------------------ digest
def write_digest(conn, cfg, hours: int = 24) -> str:
    since = (now() - dt.timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
    evs = db.list_events(conn, since=since, limit=1000)
    out = data_dir() / "out"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"digest-{now().date().isoformat()}.md"
    lines = [f"# Civic digest — {now().date().isoformat()}", "",
             f"_Window: last {hours}h · generated {now_iso()} · every item carries a verbatim quote, "
             "source URL and fetch timestamp._", ""]
    if not evs:
        lines += ["**True quiet:** no new events in this window. Nothing is manufactured to fill space.", ""]
    for jkey, jcfg in cfg["jurisdictions"].items():
        jev = [e for e in evs if e["jurisdiction"] == jkey]
        if not jev:
            continue
        lines += [f"## {jcfg.get('label', jkey)} ({len(jev)})", ""]
        for e in sorted(jev, key=lambda e: -analyze.SEV_RANK.get(e["severity"], 0)):
            lines.append(f"- **[{e['severity'].upper()}] {alerts.LABEL.get(e['kind'], e['kind'])}** — {e['title']}")
            if e.get("quote"):
                lines.append(f"  > {e['quote']}")
            if e.get("source_url"):
                lines.append(f"  <{e['source_url']}> · fetched {e.get('fetched_at')} · `{e.get('method')}`")
        lines.append("")
    pending = conn.execute(
        "SELECT id, jurisdiction, kind, subject, status, due_at FROM requests "
        "WHERE status IN ('draft','reviewed','sent','overdue') ORDER BY id").fetchall()
    if pending:
        lines += ["## Records requests awaiting action", ""]
        lines += [f"- #{r['id']} [{r['status']}] {r['jurisdiction']} · {r['subject']}"
                  f"{' · due ' + r['due_at'] if r['due_at'] else ''}" for r in pending]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------ full cycle
def cycle(conn, cfg, gate: Gate | None = None, jurisdictions=None, sources=None, log=print,
          dry_run_alerts: bool = False) -> dict:
    results = crawl(conn, cfg, gate, jurisdictions, sources, log)
    w = work(conn, cfg, log)
    t = trends(conn, cfg, log)
    s = sentiment(conn, cfg, log)
    overdue = records.refresh_overdue(conn)
    if overdue:
        _log(f"records: {overdue} request(s) now OVERDUE", log)
    a = alerts.dispatch(conn, dry_run=dry_run_alerts)
    _log(f"alerts dispatched: {a['sent']}{' (dry run)' if a.get('dry_run') else ''}"
         f"{' errors=' + str(a['errors']) if a['errors'] else ''}", log)
    n, head = ledger.commit(conn)
    _log(f"ledger committed: +{n} entries, head {head[:12]}", log)
    digest = write_digest(conn, cfg)
    _log(f"digest written → {digest}", log)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return {"crawl": results, "work": w, "trends": t, "sentiment": s, "overdue": overdue,
            "alerts": a, "ledger": {"added": n, "head": head}, "digest": digest}
