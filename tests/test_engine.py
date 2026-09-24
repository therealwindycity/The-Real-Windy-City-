import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import analyze, db, detect, ledger, records  # noqa: E402
from engine.fixtures import FixtureWorld  # noqa: E402
from engine.ingest import parse_feed  # noqa: E402
from engine.net import Blocked, Gate  # noqa: E402
from engine.selftest import run_fixture_world  # noqa: E402


@pytest.fixture(scope="module")
def world_run(tmp_path_factory):
    conn, checks = run_fixture_world(tmp_path_factory.mktemp("reaper"), log=None)
    yield conn, checks
    conn.close()


def test_end_to_end_selftest_checks_all_pass(world_run):
    _, checks = world_run
    failed = [(n, d) for n, ok, d in checks if not ok]
    assert not failed, failed


def test_robots_gate_refuses_disallowed_path():
    with FixtureWorld() as w:
        gate = Gate({"user_agent": "TestBot/1.0", "delay_seconds_per_host": 0})
        assert gate.get(f"{w.base}/agendas").status == 200
        with pytest.raises(Blocked):
            gate.get(f"{w.base}/private/packet.pdf")
        assert w.private_hits == 0


def test_every_event_is_traceable(world_run):
    conn, _ = world_run
    for e in db.list_events(conn, limit=1000):
        assert e["quote"], e["id"]
        assert e["fetched_at"], e["id"]
        if e["kind"] in ("watchlist_hit", "silent_edit", "blocked_source", "trend_flag"):
            assert e["source_url"], e["id"]


def test_watchlist_quotes_are_verbatim(world_run):
    conn, _ = world_run
    for e in db.list_events(conn, kind="watchlist_hit", limit=1000):
        doc = conn.execute("SELECT id FROM documents WHERE url=?", (e["source_url"],)).fetchone()
        texts = " ".join(r[0] for r in conn.execute("SELECT text FROM versions WHERE document_id=?", (doc["id"],)))
        assert " ".join(e["quote"].split()) in " ".join(texts.split())


def test_ledger_detects_tampering(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for i in range(3):
        db.add_event(conn, {"id": f"evt_{i}", "jurisdiction": "x", "kind": "watchlist_hit",
                            "severity": "low", "title": f"t{i}", "quote": "q", "fetched_at": "now"})
    path = tmp_path / "ledger.jsonl"
    n, _ = ledger.commit(conn, path)
    assert n == 3 and ledger.verify(path)[0]
    lines = path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["quote"] = "altered"
    lines[1] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n")
    ok, _, msg = ledger.verify(path)
    assert not ok and "altered" in msg


def test_llm_quote_verification_drops_hallucinations():
    src = "The council approved a no-bid contract with Acme Paving for $2 million."
    ok, rejected = analyze.verify_quotes(
        [{"quote": "approved a no-bid contract with Acme Paving"},
         {"quote": "the mayor received a kickback from Acme"}], src)
    assert len(ok) == 1 and len(rejected) == 1


def test_trend_slope_and_partial_month():
    assert analyze.slope([12, 15, 22]) == pytest.approx(5.0)
    rows = [{"grp": "31", "bucket": b, "value": v}
            for b, v in [("2026-06", 12), ("2026-07", 15), ("2026-08", 22), ("2026-09", 3)]]
    flags = list(analyze.trend_flags(rows, 3.0, current_bucket="2026-09"))
    assert flags and flags[0][1] == [12, 15, 22]


def test_sentiment_direction():
    assert analyze.sentiment("Residents protest evictions and displacement") < 0
    assert analyze.sentiment("Neighbors welcome the new park and praise the investment") > 0


def test_statutes_and_business_day_deadlines():
    assert "16-4-201" in records.statute("WY")["cite"]
    assert "5 ILCS 140" in records.statute("IL")["cite"]
    assert "VERIFY" in records.statute("ZZ")["cite"]  # never silently invent a citation
    friday = dt.datetime(2026, 9, 25, tzinfo=dt.timezone.utc)
    assert records.add_days(friday, 3, business=True).date() == dt.date(2026, 9, 30)
    assert records.add_days(friday, 30, business=False).date() == dt.date(2026, 10, 25)


def test_mark_sent_sets_due_date_and_overdue(tmp_path):
    conn = db.connect(tmp_path / "r.db")
    rid, created = records.save_request(conn, jurisdiction="denver_co", jcfg={"state": "CO", "agency": "Denver"},
                                        kind="pra", records_description="All emails about X")
    assert created
    due = records.mark_sent(conn, rid, sent_at=dt.datetime(2020, 1, 6, tzinfo=dt.timezone.utc))
    assert due == "2020-01-09"
    assert records.refresh_overdue(conn) == 1


def test_atom_and_rss_parsing():
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A</title>'
            '<link href="https://x/a"/><summary>&lt;p&gt;Hi&lt;/p&gt;</summary></entry></feed>')
    items = parse_feed(atom)
    assert items[0]["link"] == "https://x/a" and items[0]["summary"] == "Hi"


def test_diff_ignores_timestamp_noise():
    d = detect.diff("Agenda\nPage generated 10:01 AM\nItem 1", "Agenda\nPage generated 10:05 AM\nItem 1")
    assert not d["removed"] and not d["added"]


def test_linked_documents_not_refetched_within_window(tmp_path):
    from engine import pipeline
    from engine.util import load_config
    with FixtureWorld() as w:
        cfg = w.config(load_config())
        src = cfg["jurisdictions"]["demo_chicago"]["sources"][0]
        src["refetch_hours"] = 24
        conn = db.connect(tmp_path / "f.db")
        gate = Gate(cfg["identity"])
        first = pipeline.crawl(conn, cfg, gate, ["demo_chicago"], ["council_agendas"], log=None)[0]
        second = pipeline.crawl(conn, cfg, gate, ["demo_chicago"], ["council_agendas"], log=None)[0]
        assert "2 linked documents fetched" in first["detail"]
        assert "0 linked documents fetched, 2 recently checked" in second["detail"]


def test_elms_connector_paginates_and_stores(tmp_path):
    from engine import pipeline
    from engine.util import load_config
    with FixtureWorld() as w:
        cfg = w.config(load_config())
        conn = db.connect(tmp_path / "e.db")
        r = pipeline.crawl(conn, cfg, Gate(cfg["identity"]), ["demo_chicago"], ["city_council_elms"], log=None)[0]
        assert r["status"] == "ok" and r["items"] == 1
        doc = conn.execute("SELECT * FROM documents WHERE url LIKE '%chicityclerkelms%'").fetchone()
        assert doc["method"] == "elms_api" and "O2026-0031001" in doc["title"]
