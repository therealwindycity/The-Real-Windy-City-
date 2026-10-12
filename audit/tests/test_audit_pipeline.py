"""Run with:  python -m pytest audit/tests -q"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_ingest_node as node  # noqa: E402

SAMPLE = ("Vehicle operator detained under municipal code dispute; field verification "
          "prolonged past standard inspection timeline awaiting secondary unit.")


@pytest.fixture()
def pipe(tmp_path):
    return node.RegulatoryAuditPipeline(output_path=tmp_path / "out.jsonl")


def test_reference_sample_matches_original_contract(pipe):
    c = pipe.classify_record_deterministic(SAMPLE)
    assert c["procedural_deviations"] == ["timeline", "prolonged"]
    assert c["statutory_reference_points"] == ["municipal code"]
    assert c["enforcement_classification"] == ["detained"]
    assert c["compliance_friction_score"] == 5.0  # 2 * 1.5 + 1 * 2.0
    assert c["remediation_status"] == "Eligible for Administrative Review"
    for key in ("entity_mapping", "procedural_deviations", "rhetorical_alignment_profile", "remediation_pathway"):
        assert key in c


def test_deterministic(pipe):
    a = json.dumps(pipe.classify_record_deterministic(SAMPLE), sort_keys=True)
    b = json.dumps(pipe.classify_record_deterministic(SAMPLE), sort_keys=True)
    assert a == b


def test_whole_word_matching_and_plurals(pipe):
    c = pipe.classify_record_deterministic("The warranty expired; the ordinances and warrants were reviewed.")
    assert "warrant" in c["procedural_deviations"] and "ordinance" in c["procedural_deviations"]
    c2 = pipe.classify_record_deterministic("The warranty expired.")
    assert c2["procedural_deviations"] == ["None identified"]


def test_entities(pipe):
    em = pipe.extract_entities("Wyoming statute section 35-7-1046 and W.S. 16-4-405(a). Ordinance No. 4524. "
                               "Councilman Tom Crave asked Mr. Chairman. LEADS spoke; the item leads nowhere. "
                               "The Board of Adjustment met.")
    assert em["statutory_citations"] == ["W.S. 35-7-1046", "W.S. 16-4-405(a)"]
    assert em["instruments"] == ["Ordinance 4524"]
    assert em["officials"] == ["Councilman Tom Crave"]
    assert em["agencies"] == ["Board of Adjustment", "LEADS"]


def test_rhetoric_and_remediation(pipe):
    c = pipe.classify_record_deterministic(
        "I think this went into executive session without notice, and I believe that's wrong.")
    rh = c["rhetorical_alignment_profile"]
    assert rh["subjective"] == 2 and rh["dominant_mode"] == "subjective" and rh["objectivity_ratio"] == 0.0
    assert any("Public Meetings Act" in p["authority"] for p in c["remediation_pathway"])


def test_persist_append_dedupes_and_rebuild_is_atomic(pipe, tmp_path):
    recs = [{"id": 1, "notes": SAMPLE}, {"id": 2, "notes": ""}, {"id": 3, "notes": "routine item"}]
    s1 = pipe.process_and_persist(recs, "notes", source={"type": "test"})
    assert s1["written"] == 2 and s1["skipped_empty"] == 1 and s1["review_flagged"] == 1
    s2 = pipe.process_and_persist(recs, "notes", source={"type": "test"})
    assert s2["written"] == 0 and s2["skipped_duplicate"] == 2
    s3 = pipe.process_and_persist(recs, "notes", source={"type": "test"}, mode="rebuild")
    assert s3["written"] == 2
    lines = (tmp_path / "out.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert not list(tmp_path.glob(".audit-*"))
    assert json.loads((tmp_path / "out.manifest.json").read_text())["runs"][-1]["mode"] == "rebuild"


def test_dead_letter_zero_loss(pipe, tmp_path):
    class Boom(dict):
        def get(self, *a, **k):
            raise RuntimeError("bad record")
    s = pipe.process_and_persist([Boom(notes="x"), {"notes": SAMPLE}], "notes")
    assert s["dead_lettered"] == 1 and s["written"] == 1
    dl = (tmp_path / "out.deadletter.jsonl").read_text().splitlines()
    assert "bad record" in json.loads(dl[0])["error"]


def test_arcgis_attributes_and_dotted_fields(pipe):
    rec = node.flatten_feature({"attributes": {"NOTES": "citation issued"}, "geometry": {"x": 1}})
    assert node.extract_text(rec, "NOTES") == "citation issued"
    assert node.extract_text({"a": {"b": "x"}, "c": "y"}, "a.b,c") == "x\n\ny"


def test_transcript_chunking(tmp_path):
    (tmp_path / "cc").mkdir()
    long_run = " ".join(["word"] * 900)  # no punctuation, ~4.5k chars, with an inline timestamp
    (tmp_path / "cc" / "m.md").write_text(
        "# Title\n\nheader\n\n---\n[00:00:05] Call to order. Roll call.\n\n"
        f"[00:01:00] {long_run} [00:09:59] Adjourned.\n")
    (tmp_path / "meetings.json").write_text(json.dumps([
        {"date": "2026-01-01", "body": "cc", "youtube_id": "abc", "file": "cc/m.md"},
        {"date": "2026-01-02", "body": "cc", "youtube_id": "zzz", "file": None, "note": "no captions"}]))
    out = list(node.iter_transcripts(tmp_path, chunk_chars=1200))
    assert all(len(r["text"]) <= 2 * 1200 + 50 for r in out)
    assert out[0]["start"] == "00:00:05" and out[0]["url"].endswith("&t=5s")
    assert out[-1]["text"].endswith("Adjourned.")
    assert sum(len(r["text"]) for r in out) >= len(long_run)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path.startswith("/resource/"):
            rows = [{"id": i, "description": f"row {i} citation"} for i in range(5)]
            off, lim = int(q["$offset"]), int(q["$limit"])
            body = rows[off:off + lim]
        elif u.path.endswith("/query"):
            feats = [{"attributes": {"OBJECTID": i, "NOTES": f"seizure {i}"}} for i in range(5)]
            off, n = int(q["resultOffset"]), int(q["resultRecordCount"])
            page = feats[off:off + n]
            body = {"features": page, "exceededTransferLimit": off + n < len(feats)}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_socrata_paging(pipe, server):
    rows = list(pipe.iter_socrata(server, "abcd-1234", page_size=2))
    assert [r["id"] for r in rows] == [0, 1, 2, 3, 4]


def test_arcgis_paging_end_to_end(pipe, server, tmp_path):
    feats = list(pipe.iter_arcgis(server + "/arcgis/rest/services/X/FeatureServer/0", page_size=2))
    assert [f["OBJECTID"] for f in feats] == [0, 1, 2, 3, 4]
    s = pipe.process_and_persist(iter(feats), "NOTES", source={"type": "arcgis"})
    assert s["written"] == 5


def test_fetch_endpoint_stream_returns_empty_on_failure(pipe):
    assert pipe.fetch_endpoint_stream("http://127.0.0.1:9/nothing") == []
