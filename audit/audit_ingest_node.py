"""
AUDIT INGESTION & NORMALIZATION NODE
====================================

Deterministic extractor/classifier for municipal records, dockets and
transparency streams. Every ingested record is normalised into the four-part
audit schema:

    entity_mapping                agencies, officials, statute citations, instruments
    procedural_deviations         lexicon hits signalling timeline / procedure variance
    rhetorical_alignment_profile  objective vs. subjective / deferral / authority framing
    remediation_pathway           procedural remedies keyed to the triggers that fired

What the scores mean
--------------------
Everything here is keyword matching against ``lexicon.json``. A hit means a
term appears in the text. It does NOT mean a violation happened. Records with a
``compliance_friction_score`` above the threshold are queued for a person to
read the passage, nothing more. Every hit carries its snippet (and, for
transcripts, a timestamped video link) so a reviewer can check it at the source.
``remediation_pathway`` lists general procedural avenues for reference. It is
not legal advice.

Determinism
-----------
* Same text + same lexicon produces the same classification, byte for byte.
  No clocks, randomness or models are involved.
* ``record_id`` = sha256(source key + text)[:16]. Re-running in ``append`` mode
  skips records already in the output file.
* Each record is stamped with ``lexicon_version`` and ``lexicon_sha256``.

Zero-loss handling
------------------
A record that fails to classify or serialise goes to ``<out>.deadletter.jsonl``
along with its error. ``rebuild`` mode writes to a temporary file and then swaps
it in atomically, so a crash never leaves half a file behind.

Data targets (CLI)
------------------
    python audit/audit_ingest_node.py transcripts            # this repo's 2026 meeting transcripts
    python audit/audit_ingest_node.py csv FILE --text-field description
    python audit/audit_ingest_node.py jsonl FILE --text-field text
    python audit/audit_ingest_node.py textdir DIR --glob "*.txt"
    python audit/audit_ingest_node.py socrata data.cityofchicago.org ijzp-q8t2 --text-field description
    python audit/audit_ingest_node.py arcgis https://host/arcgis/rest/services/X/FeatureServer/0 --text-field NOTES
    python audit/audit_ingest_node.py discover "code enforcement" --domain data.example.gov
    python audit/audit_ingest_node.py demo

Only the standard library is needed for local sources. ``requests`` is
imported lazily for the remote ones (socrata / arcgis / discover).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

SCHEMA_VERSION = "1.0"
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
DEFAULT_LEXICON = HERE / "lexicon.json"
DEFAULT_OUTPUT = HERE / "output" / "audit_records.jsonl"
DEFAULT_TRANSCRIPTS = REPO_ROOT / "cheyenne-2026-transcripts"
USER_AGENT = "EnterpriseComplianceAuditor/2.1 (+https://github.com/therealwindycity/The-Real-Windy-City-)"

NONE_IDENTIFIED = ["None identified"]
STANDARD_REVIEW = ["Standard review"]
ROUTINE = ["Routine/Informational"]
STATUS_REVIEW = "Eligible for Administrative Review"
STATUS_NOMINAL = "Nominal"

# ----------------------------------------------------------------------------
# Remediation rules: trigger terms -> procedural avenue.
# The rules are evaluated in this order and each fires at most once. The
# citations are starting points for research; check the current text first.
# ----------------------------------------------------------------------------
REMEDIATION_RULES: List[Dict[str, Any]] = [
    {
        "pathway": "Open-meetings review (notice, agenda, executive-session limits)",
        "authority": "Wyoming Public Meetings Act, W.S. 16-4-401 et seq.",
        "triggers": ["executive session", "open meetings", "public meetings act",
                     "without notice", "no notice", "not on the agenda"],
    },
    {
        "pathway": "Public-records request / review of a records denial",
        "authority": "Wyoming Public Records Act, W.S. 16-4-201 et seq.",
        "triggers": ["public records act", "unverified"],
    },
    {
        "pathway": "Administrative appeal, then judicial review of agency action",
        "authority": "Wyoming Administrative Procedure Act, W.S. 16-3-101 et seq. (review: W.S. 16-3-114; W.R.A.P. 12)",
        "triggers": ["administrative procedure", "title 16", "appeal", "non-compliant", "failed to"],
    },
    {
        "pathway": "Municipal-code appeal (Board of Adjustment / governing body, as the code provides)",
        "authority": "Cheyenne Municipal Code & Unified Development Code",
        "triggers": ["municipal code", "city code", "ordinance", "unified development code", "udc",
                     "code enforcement", "nuisance abatement", "lien", "emergency ordinance"],
    },
    {
        "pathway": "Parliamentary objection / motion to reconsider under council rules",
        "authority": "Governing-body rules of procedure",
        "triggers": ["point of order", "out of order", "suspend the rules", "waive the rules",
                     "without a second"],
    },
    {
        "pathway": "Suppression / due-process motion in the underlying case",
        "authority": "U.S. Const. amend. IV & XIV; Wyo. Const. art. 1, §§ 4, 6; W.R.Cr.P. 12",
        "triggers": ["warrant", "seizure", "fourth amendment", "due process", "detention",
                     "detained", "pretext", "prolonged"],
    },
    {
        "pathway": "Records expungement petition (eligibility depends on disposition)",
        "authority": "W.S. 7-13-1401 (non-conviction records); W.S. 7-13-1501 (misdemeanor convictions)",
        "triggers": ["arrest", "citation", "misdemeanor", "felony"],
    },
]

_STATUTE_RE = re.compile(
    r"(?:\bW\.?\s?S\.?|Wyo(?:ming)?\.?\s+Stat(?:\.|ute)?s?|§)\s*(?:section\s+|sec\.\s*)?§?\s*(\d{1,2}-\d{1,2}-\d{2,4}(?:\([a-z0-9]+\))*)",
    re.IGNORECASE,
)
_INSTRUMENT_RE = re.compile(
    r"\b(Ordinance|Resolution|Council Bill|Bill)\s+(?:No\.?|Number|#)?\s*(\d{1,2}-\d{2,5}|\d{2,5})\b",
    re.IGNORECASE,
)
_NAME_TOKEN = r"[A-Z][a-zA-Z'\-]{1,}"
_NAME_STOP = {
    "The", "And", "But", "So", "If", "We", "I", "It", "This", "That", "Thank", "Thanks",
    "Yes", "No", "Okay", "All", "Second", "Motion", "Mayor", "President", "Chair", "Council",
    "City", "Madam", "Madame", "Sir", "Please", "Any", "Are", "Is", "Do", "Can", "Would",
    "Members", "Member", "Clerk", "Director", "Chief", "Chairman", "Chairwoman", "Mr", "Mrs",
    "Ms", "Dr", "Vice", "Commissioner", "Councilman", "Councilwoman", "Attorney", "Sheriff",
}
_TS_SPLIT_RE = re.compile(r"\[(\d{2}:\d{2}:\d{2})\]")
_SENTENCE_RE = re.compile(r"(?<=[.?!])\s+")


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------
def _term_pattern(term: str, case_sensitive: bool = False) -> re.Pattern:
    """Whole-word/phrase, whitespace-tolerant pattern with an optional plural
    suffix. Case-insensitive unless the term is an all-caps acronym ("LEADS" is
    an agency, "leads" is not)."""
    parts = [re.escape(p) for p in term.split()]
    plural = r"(?:s|es)?" if term[-1].isalpha() and not case_sensitive else ""  # warrant -> warrants
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + plural + r"(?!\w)",
                      0 if case_sensitive else re.IGNORECASE)


def _compile_terms(terms: Iterable[str]) -> List[tuple]:
    """(term, cheap lowercase prefilter token, compiled pattern). The prefilter
    is a plain substring test that rules out most terms before any regex runs."""
    return [(t, t.lower().split()[0], _term_pattern(t, case_sensitive=t.isupper() and len(t) > 1))
            for t in terms]


def _snippet(text: str, start: int, end: int, radius: int = 90) -> str:
    a, b = max(0, start - radius), min(len(text), end + radius)
    s = re.sub(r"\s+", " ", text[a:b]).strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def _dedupe(seq: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for x in seq:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def _get_path(record: Dict[str, Any], dotted: str) -> Any:
    cur: Any = record
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def extract_text(record: Dict[str, Any], text_field: str) -> str:
    """``text_field`` may be dotted (``attributes.NOTES``) or comma-separated
    (``title,description``); the values found are joined with blank lines."""
    vals = []
    for f in [f.strip() for f in text_field.split(",") if f.strip()]:
        v = _get_path(record, f)
        if v is not None and str(v).strip():
            vals.append(str(v).strip())
    return "\n\n".join(vals)


def flatten_feature(rec: Any) -> Any:
    """ArcGIS features nest their fields under ``attributes`` (or GeoJSON
    ``properties``). Lift them up so text fields can be addressed directly."""
    if isinstance(rec, dict):
        for key in ("attributes", "properties"):
            if isinstance(rec.get(key), dict):
                flat = dict(rec[key])
                if "geometry" in rec:
                    flat.setdefault("_geometry", rec["geometry"])
                return flat
    return rec


def hms_to_seconds(ts: str) -> int:
    h, m, s = (int(x) for x in ts.split(":"))
    return h * 3600 + m * 60 + s


# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
class RegulatoryAuditPipeline:
    def __init__(self, output_path: str | os.PathLike = DEFAULT_OUTPUT,
                 lexicon_path: str | os.PathLike = DEFAULT_LEXICON,
                 dead_letter_path: Optional[str | os.PathLike] = None,
                 timeout: int = 30):
        self.output_path = Path(output_path)
        self.dead_letter_path = Path(dead_letter_path) if dead_letter_path else \
            self.output_path.with_suffix(".deadletter.jsonl")
        self.timeout = timeout
        raw = Path(lexicon_path).read_bytes()
        self.lexicon: Dict[str, Any] = json.loads(raw)
        self.lexicon_version = self.lexicon.get("version", "unversioned")
        self.lexicon_sha256 = hashlib.sha256(raw).hexdigest()
        sc = self.lexicon.get("scoring", {})
        self.w_dev = float(sc.get("deviation_weight", 1.5))
        self.w_stat = float(sc.get("statutory_weight", 2.0))
        self.threshold = float(sc.get("review_threshold", 3.0))

        # Kept for compatibility with the original interface.
        self.classification_markers = {
            "procedural_deviation": self.lexicon["procedural_deviation"],
            "statutory_nexus": self.lexicon["statutory_nexus"],
            "enforcement_tier": self.lexicon["enforcement_tier"],
        }
        self._patterns = {cat: _compile_terms(terms) for cat, terms in self.classification_markers.items()}
        self._rhetoric = {mode: _compile_terms(terms)
                          for mode, terms in self.lexicon.get("rhetoric", {}).items()}
        self._agencies = _compile_terms(self.lexicon.get("agencies", []))
        titles = sorted(self.lexicon.get("titles", []), key=len, reverse=True)
        title_alt = "|".join(re.escape(t) for t in titles)
        self._official_re = re.compile(
            r"(?<![\w.])(" + title_alt + r")\s+(" + _NAME_TOKEN + r")(?:\s+(" + _NAME_TOKEN + r"))?")
        self._session = None

    # ------------------------------------------------------------------ network
    def _http(self):
        if self._session is None:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            s = requests.Session()
            retry = Retry(total=4, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504),
                          allowed_methods=("GET",), respect_retry_after_header=True)
            s.mount("http://", HTTPAdapter(max_retries=retry))
            s.mount("https://", HTTPAdapter(max_retries=retry))
            s.headers["User-Agent"] = USER_AGENT
            self._session = s
        return self._session

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None,
                  headers: Optional[Dict[str, str]] = None) -> Any:
        r = self._http().get(url, params=params, headers=headers or {}, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and isinstance(data.get("error"), dict):  # ArcGIS reports errors with HTTP 200
            raise RuntimeError(f"endpoint error: {data['error']}")
        return data

    def fetch_endpoint_stream(self, endpoint_url: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Single GET against a structured public endpoint (ArcGIS / REST).
        Returns [] on failure, as the original did; use iter_arcgis/iter_socrata to page through results."""
        try:
            data = self._get_json(endpoint_url, params)
        except Exception as e:  # noqa: BLE001 - logged, caller gets []
            print(f"[!] Endpoint acquisition error: {e}", file=sys.stderr)
            return []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("features", data.get("results", [data]))
        else:
            rows = []
        return [flatten_feature(r) for r in rows]

    def iter_socrata(self, domain: str, dataset_id: str, where: Optional[str] = None,
                     page_size: int = 1000, max_records: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Page through a Socrata (SODA 2) dataset in stable ``:id`` order."""
        base = domain if domain.startswith("http") else f"https://{domain}"
        url = f"{base.rstrip('/')}/resource/{dataset_id}.json"
        headers = {}
        if os.environ.get("SOCRATA_APP_TOKEN"):
            headers["X-App-Token"] = os.environ["SOCRATA_APP_TOKEN"]
        offset, n = 0, 0
        while True:
            params = {"$limit": page_size, "$offset": offset, "$order": ":id"}
            if where:
                params["$where"] = where
            rows = self._get_json(url, params, headers)
            if not rows:
                return
            for row in rows:
                yield row
                n += 1
                if max_records and n >= max_records:
                    return
            if len(rows) < page_size:
                return
            offset += page_size

    def iter_arcgis(self, layer_url: str, where: str = "1=1", page_size: int = 1000,
                    max_records: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Page through an ArcGIS FeatureServer/MapServer layer with resultOffset."""
        url = layer_url.rstrip("/")
        if not url.endswith("/query"):
            url += "/query"
        offset, n = 0, 0
        while True:
            params = {"where": where, "outFields": "*", "returnGeometry": "false", "f": "json",
                      "resultOffset": offset, "resultRecordCount": page_size}
            data = self._get_json(url, params)
            feats = data.get("features", []) if isinstance(data, dict) else []
            for f in feats:
                yield flatten_feature(f)
                n += 1
                if max_records and n >= max_records:
                    return
            if not feats or not data.get("exceededTransferLimit"):
                return
            offset += len(feats)

    def socrata_discover(self, query: str, domain: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Search the Socrata Discovery API for candidate datasets."""
        params: Dict[str, Any] = {"q": query, "limit": limit, "only": "dataset"}
        if domain:
            params["domains"] = domain
        data = self._get_json("https://api.us.socrata.com/api/catalog/v1", params)
        out = []
        for r in data.get("results", []):
            res = r.get("resource", {})
            out.append({"name": res.get("name"), "id": res.get("id"),
                        "domain": r.get("metadata", {}).get("domain"),
                        "updated": res.get("updatedAt"),
                        "description": (res.get("description") or "")[:200]})
        return out

    # ------------------------------------------------------------ classification
    def _hits(self, text: str, compiled, lowered: Optional[str] = None) -> List[Dict[str, Any]]:
        lowered = text.lower() if lowered is None else lowered
        out = []
        for term, key, pat in compiled:
            if key not in lowered:
                continue
            m = pat.search(text)
            if m:
                out.append({"term": term, "count": len(pat.findall(text)),
                            "snippet": _snippet(text, m.start(), m.end())})
        return out

    def extract_entities(self, text: str, lowered: Optional[str] = None) -> Dict[str, List[str]]:
        lowered = text.lower() if lowered is None else lowered
        agencies = [a for a, key, p in self._agencies if key in lowered and p.search(text)]
        officials = []
        for m in self._official_re.finditer(text):
            title, first, second = m.group(1), m.group(2), m.group(3)
            if first in _NAME_STOP:
                continue
            name = first if (not second or second in _NAME_STOP) else f"{first} {second}"
            officials.append(f"{title} {name}")
        statutes = [f"W.S. {m.group(1)}" for m in _STATUTE_RE.finditer(text)]
        instruments = [f"{m.group(1).title()} {m.group(2)}" for m in _INSTRUMENT_RE.finditer(text)]
        return {"agencies": _dedupe(agencies), "officials": _dedupe(officials),
                "statutory_citations": _dedupe(statutes), "instruments": _dedupe(instruments)}

    def rhetorical_profile(self, text: str, lowered: Optional[str] = None) -> Dict[str, Any]:
        lowered = text.lower() if lowered is None else lowered
        counts = {mode: sum(len(p.findall(text)) for _, key, p in compiled if key in lowered)
                  for mode, compiled in self._rhetoric.items()}
        obj, subj = counts.get("objective", 0), counts.get("subjective", 0)
        total = sum(counts.values())
        if total == 0:
            dominant = "procedural/neutral"
        else:
            # ties break in lexicon order, which keeps this deterministic
            dominant = max(counts, key=lambda k: (counts[k], -list(counts).index(k)))
        return {**counts,
                "objectivity_ratio": round(obj / (obj + subj), 3) if (obj + subj) else None,
                "dominant_mode": dominant}

    def remediation_pathways(self, fired_terms: Iterable[str]) -> List[Dict[str, str]]:
        fired = {t.lower() for t in fired_terms}
        out = []
        for rule in REMEDIATION_RULES:
            trig = [t for t in rule["triggers"] if t in fired]
            if trig:
                out.append({"pathway": rule["pathway"], "authority": rule["authority"],
                            "triggered_by": ", ".join(trig)})
        return out

    def classify_record_deterministic(self, text_payload: str) -> Dict[str, Any]:
        """Turn one passage into the structured audit schema. Pure function of
        (text, lexicon)."""
        text = text_payload or ""
        low = text.lower()
        dev = self._hits(text, self._patterns["procedural_deviation"], low)
        stat = self._hits(text, self._patterns["statutory_nexus"], low)
        enf = self._hits(text, self._patterns["enforcement_tier"], low)
        entities = self.extract_entities(text, low)
        # explicit citations such as "W.S. 16-4-405" count as statutory nexus too
        stat_terms = [h["term"] for h in stat] + entities["statutory_citations"]
        dev_terms = [h["term"] for h in dev]
        enf_terms = [h["term"] for h in enf]

        friction = len(dev_terms) * self.w_dev + len(_dedupe(stat_terms)) * self.w_stat
        evidence = ([{"category": "procedural_deviation", **h} for h in dev]
                    + [{"category": "statutory_nexus", **h} for h in stat]
                    + [{"category": "enforcement_tier", **h} for h in enf])

        return {
            # --- four-part enterprise audit schema ---
            "entity_mapping": entities,
            "procedural_deviations": dev_terms or list(NONE_IDENTIFIED),
            "rhetorical_alignment_profile": self.rhetorical_profile(text, low),
            "remediation_pathway": self.remediation_pathways(dev_terms + stat_terms + enf_terms),
            # --- original fields, kept so existing consumers keep working ---
            "statutory_reference_points": _dedupe(stat_terms) or list(STANDARD_REVIEW),
            "enforcement_classification": enf_terms or list(ROUTINE),
            "compliance_friction_score": round(friction, 2),
            "remediation_status": STATUS_REVIEW if friction > self.threshold else STATUS_NOMINAL,
            # --- traceability ---
            "evidence": evidence,
        }

    # -------------------------------------------------------------- persistence
    def _existing_ids(self) -> set:
        ids = set()
        if self.output_path.exists():
            with self.output_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        ids.add(json.loads(line)["record_id"])
                    except Exception:  # noqa: BLE001 - tolerate foreign/corrupt lines
                        continue
        return ids

    def build_entry(self, record: Dict[str, Any], text: str, source: Dict[str, Any]) -> Dict[str, Any]:
        key = json.dumps(source, sort_keys=True) + "\x00" + text
        return {
            "record_id": hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
            "schema_version": SCHEMA_VERSION,
            "lexicon_version": self.lexicon_version,
            "lexicon_sha256": self.lexicon_sha256,
            "source": source,
            "raw_source": record,
            "audit_classification": self.classify_record_deterministic(text),
        }

    def process_and_persist(self, raw_records: Iterable[Dict[str, Any]], text_field: str,
                            source: Optional[Dict[str, Any]] = None, mode: str = "append",
                            max_records: Optional[int] = None, progress_every: int = 0) -> Dict[str, int]:
        """Stream records through the classifier into JSONL.

        mode="append"   add to the existing file, skipping record_ids already present
        mode="rebuild"  write a fresh file to a temp path, then swap it in atomically
        """
        if mode not in ("append", "rebuild"):
            raise ValueError("mode must be 'append' or 'rebuild'")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        stats = {"seen": 0, "written": 0, "skipped_empty": 0, "skipped_duplicate": 0,
                 "dead_lettered": 0, "review_flagged": 0}
        known = self._existing_ids() if mode == "append" else set()
        base_source = dict(source or {})

        if mode == "rebuild":
            fd, tmp = tempfile.mkstemp(prefix=".audit-", suffix=".jsonl.tmp", dir=self.output_path.parent)
            out = os.fdopen(fd, "w", encoding="utf-8")
        else:
            tmp = None
            out = self.output_path.open("a", encoding="utf-8")
        dead = None
        try:
            for record in raw_records:
                stats["seen"] += 1
                try:
                    rec = flatten_feature(record)
                    text = extract_text(rec, text_field) if isinstance(rec, dict) else str(rec)
                    if not text.strip():
                        stats["skipped_empty"] += 1
                        continue
                    src = {**base_source, **(rec.pop("_source", {}) if isinstance(rec, dict) else {})}
                    entry = self.build_entry(rec, text, src)
                    if entry["record_id"] in known:
                        stats["skipped_duplicate"] += 1
                        continue
                    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
                    out.write(line + "\n")
                    known.add(entry["record_id"])
                    stats["written"] += 1
                    if entry["audit_classification"]["remediation_status"] == STATUS_REVIEW:
                        stats["review_flagged"] += 1
                except Exception as e:  # noqa: BLE001 - zero-loss: park it, keep going
                    if dead is None:
                        self.dead_letter_path.parent.mkdir(parents=True, exist_ok=True)
                        dead = self.dead_letter_path.open("a", encoding="utf-8")
                    dead.write(json.dumps({"error": f"{type(e).__name__}: {e}", "source": base_source,
                                           "record": record}, ensure_ascii=False, default=str) + "\n")
                    stats["dead_lettered"] += 1
                if progress_every and stats["seen"] % progress_every == 0:
                    print(f"[.] {stats['seen']} seen / {stats['written']} written", file=sys.stderr)
                if max_records and stats["seen"] >= max_records:
                    break
            out.flush()
            os.fsync(out.fileno())
            out.close()
            if tmp:
                os.chmod(tmp, 0o644)
                os.replace(tmp, self.output_path)
        except BaseException:
            out.close()
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
            raise
        finally:
            if dead:
                dead.close()
        self._write_manifest(stats, base_source, mode)
        print(f"[+] {stats['written']} written, {stats['skipped_duplicate']} duplicate, "
              f"{stats['skipped_empty']} empty, {stats['dead_lettered']} dead-lettered "
              f"-> {self.output_path}", file=sys.stderr)
        return stats

    def _write_manifest(self, stats: Dict[str, int], source: Dict[str, Any], mode: str) -> None:
        manifest_path = self.output_path.with_suffix(".manifest.json")
        runs = []
        if manifest_path.exists() and mode == "append":
            try:
                runs = json.loads(manifest_path.read_text()).get("runs", [])
            except Exception:  # noqa: BLE001
                runs = []
        runs.append({"finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "mode": mode, "source": source, **stats})
        manifest_path.write_text(json.dumps({
            "schema_version": SCHEMA_VERSION, "lexicon_version": self.lexicon_version,
            "lexicon_sha256": self.lexicon_sha256, "output": self.output_path.name,
            "runs": runs[-50:]}, indent=2))


# ----------------------------------------------------------------------------
# Local source readers
# ----------------------------------------------------------------------------
def _split_long(text: str, limit: int) -> List[str]:
    """Split an over-long segment at sentence ends, falling back to word
    boundaries for caption runs that have no punctuation."""
    pieces, cur = [], ""
    for sent in _SENTENCE_RE.split(text):
        while len(sent) > limit:  # no usable punctuation: break on whitespace
            cut = sent.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if cur and len(cur) + len(sent) + 1 > limit:
            pieces.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        pieces.append(cur)
    return [p for p in pieces if p]


def _timestamped_segments(markdown: str, chunk_chars: int) -> List[tuple]:
    """[(HH:MM:SS, text)] from a transcript body. Timestamps are honoured
    wherever they appear, including mid-paragraph. Segments longer than
    2 x chunk_chars are split, and every piece keeps the timestamp it started at."""
    body = markdown.split("\n---\n", 1)[1] if "\n---\n" in markdown else markdown
    parts = _TS_SPLIT_RE.split(body)
    out = []
    for i in range(1, len(parts) - 1, 2):
        ts, txt = parts[i], re.sub(r"\s+", " ", parts[i + 1]).strip()
        if not txt:
            continue
        if len(txt) > 2 * chunk_chars:
            out.extend((ts, piece) for piece in _split_long(txt, chunk_chars))
        else:
            out.append((ts, txt))
    return out


def iter_transcripts(transcripts_dir: str | os.PathLike = DEFAULT_TRANSCRIPTS,
                     chunk_chars: int = 1200) -> Iterator[Dict[str, Any]]:
    """Yield timestamped passages from the meeting transcripts.

    Consecutive ``[HH:MM:SS]`` paragraphs are merged until a passage reaches
    ``chunk_chars``, which gives units small enough to review by hand. Each
    passage carries a deep link to the moment it starts in the video.
    """
    root = Path(transcripts_dir)
    catalog = json.loads((root / "meetings.json").read_text(encoding="utf-8"))
    for meeting in sorted(catalog, key=lambda m: (m.get("date", ""), m.get("body", ""))):
        if not meeting.get("file"):
            print(f"[i] no transcript for {meeting.get('date')} {meeting.get('body')}: "
                  f"{meeting.get('note', 'no file listed')}", file=sys.stderr)
            continue
        path = root / meeting["file"]
        if not path.exists():
            print(f"[!] missing transcript {path}", file=sys.stderr)
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"[!] unreadable transcript {path}: {e}", file=sys.stderr)
            continue
        paras = _timestamped_segments(body, chunk_chars)
        buf: List[tuple] = []

        def emit(seq: int):
            start, end = buf[0][0], buf[-1][0]
            secs = hms_to_seconds(start)
            return {
                "text": " ".join(t for _, t in buf),
                "date": meeting["date"], "body": meeting["body"],
                "start": start, "end": end, "passage": seq,
                "url": f"https://www.youtube.com/watch?v={meeting['youtube_id']}&t={secs}s",
                "_source": {"type": "transcript", "file": meeting["file"],
                            "youtube_id": meeting["youtube_id"], "start": start},
            }

        seq, size = 0, 0
        for ts, txt in paras:
            buf.append((ts, txt))
            size += len(txt) + 1
            if size >= chunk_chars:
                yield emit(seq)
                seq, buf, size = seq + 1, [], 0
        if buf:
            yield emit(seq)


def iter_csv(path: str | os.PathLike) -> Iterator[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f)):
            row["_source"] = {"type": "csv", "file": str(path), "row": i}
            yield row


def iter_jsonl(path: str | os.PathLike) -> Iterator[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if line.strip():
                rec = json.loads(line)
                if isinstance(rec, dict):
                    rec["_source"] = {"type": "jsonl", "file": str(path), "line": i}
                yield rec


def iter_text_dir(directory: str | os.PathLike, glob: str = "*.txt") -> Iterator[Dict[str, Any]]:
    for p in sorted(Path(directory).rglob(glob)):
        yield {"text": p.read_text(encoding="utf-8", errors="replace"), "path": str(p),
               "_source": {"type": "textdir", "file": str(p)}}


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=str(DEFAULT_OUTPUT), help="output JSONL (default: audit/output/audit_records.jsonl)")
    p.add_argument("--lexicon", default=str(DEFAULT_LEXICON))
    p.add_argument("--mode", choices=["append", "rebuild"], default="append")
    p.add_argument("--max-records", type=int, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("transcripts", help="this repo's meeting transcripts")
    t.add_argument("--dir", default=str(DEFAULT_TRANSCRIPTS))
    t.add_argument("--chunk-chars", type=int, default=1200)

    for name in ("csv", "jsonl"):
        s = sub.add_parser(name)
        s.add_argument("path")
        s.add_argument("--text-field", required=True, help="field(s); dotted paths and commas allowed")

    d = sub.add_parser("textdir")
    d.add_argument("directory")
    d.add_argument("--glob", default="*.txt")

    so = sub.add_parser("socrata", help="Socrata SODA dataset")
    so.add_argument("domain")
    so.add_argument("dataset_id")
    so.add_argument("--text-field", required=True)
    so.add_argument("--where")

    a = sub.add_parser("arcgis", help="ArcGIS FeatureServer/MapServer layer")
    a.add_argument("layer_url")
    a.add_argument("--text-field", required=True)
    a.add_argument("--where", default="1=1")

    disc = sub.add_parser("discover", help="search the Socrata Discovery API")
    disc.add_argument("query")
    disc.add_argument("--domain")

    sub.add_parser("demo", help="classify the built-in sample and print it")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    auditor = RegulatoryAuditPipeline(output_path=args.out, lexicon_path=args.lexicon)

    if args.cmd == "demo":
        sample_text = ("Vehicle operator detained under municipal code dispute; field verification "
                       "prolonged past standard inspection timeline awaiting secondary unit.")
        print(json.dumps(auditor.classify_record_deterministic(sample_text), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "discover":
        for row in auditor.socrata_discover(args.query, args.domain):
            print(json.dumps(row, ensure_ascii=False))
        return 0

    t0 = time.time()
    if args.cmd == "transcripts":
        records, field = iter_transcripts(args.dir, args.chunk_chars), "text"
        source = {"type": "transcript", "collection": Path(args.dir).name}
    elif args.cmd == "csv":
        records, field, source = iter_csv(args.path), args.text_field, {"type": "csv"}
    elif args.cmd == "jsonl":
        records, field, source = iter_jsonl(args.path), args.text_field, {"type": "jsonl"}
    elif args.cmd == "textdir":
        records, field, source = iter_text_dir(args.directory, args.glob), "text", {"type": "textdir"}
    elif args.cmd == "socrata":
        records = auditor.iter_socrata(args.domain, args.dataset_id, args.where, max_records=args.max_records)
        field, source = args.text_field, {"type": "socrata", "domain": args.domain, "dataset": args.dataset_id}
    elif args.cmd == "arcgis":
        records = auditor.iter_arcgis(args.layer_url, args.where, max_records=args.max_records)
        field, source = args.text_field, {"type": "arcgis", "layer": args.layer_url}
    else:  # pragma: no cover
        raise SystemExit(f"unknown command {args.cmd}")

    stats = auditor.process_and_persist(records, field, source=source, mode=args.mode,
                                        max_records=args.max_records, progress_every=2000)
    print(json.dumps({**stats, "seconds": round(time.time() - t0, 1)}))
    return 0 if stats["dead_lettered"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
