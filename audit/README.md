# Audit pipeline: ingest node + compliance dashboard

Deterministic indexing of public meeting records into a four-part audit schema,
plus a Streamlit review matrix.

| File | Role |
|---|---|
| `audit_ingest_node.py` | `RegulatoryAuditPipeline`: source readers, classifier, JSONL persistence, CLI |
| `lexicon.json` | every marker term, agency, title and scoring weight (versioned and hashed) |
| `ui_adapter.py` | `load_audit_data()` / `render_compliance_dashboard()` |
| `app.py` | standalone entry point: `streamlit run audit/app.py` |
| `streamlit_page.py` | drop-in page for the TheReelWindyCity multipage app |
| `tests/` | `python -m pytest audit/tests -q` (12 tests, including mock Socrata/ArcGIS servers) |

## Quick start

```bash
pip install -r audit/requirements.txt
python3 audit/audit_ingest_node.py --mode rebuild transcripts   # ~10 s, writes audit/output/audit_records.jsonl
streamlit run audit/app.py
```

`audit/output/` is git-ignored because it is derived data and rebuilds in seconds.
On a fresh checkout the dashboard also has a **Build index** button.

## Data targets

```bash
# this repo's 2026 transcripts (84 meetings -> ~5,900 timestamped passages)
python3 audit/audit_ingest_node.py transcripts [--dir PATH] [--chunk-chars 1200]

# local files (--text-field accepts dotted paths and comma lists: "title,attributes.NOTES")
python3 audit/audit_ingest_node.py csv   docket.csv    --text-field description
python3 audit/audit_ingest_node.py jsonl records.jsonl --text-field text
python3 audit/audit_ingest_node.py textdir ../cheyenne-archives-2025-2026/text --glob "*.txt"

# open-data portals (paged; retries with backoff on 429/5xx)
python3 audit/audit_ingest_node.py discover "code enforcement" --domain data.example.gov
python3 audit/audit_ingest_node.py socrata data.example.gov abcd-1234 --text-field description --where "date > '2026-01-01'"
python3 audit/audit_ingest_node.py arcgis https://host/arcgis/rest/services/Svc/FeatureServer/0 --text-field NOTES
```

Global options: `--out FILE`, `--mode append|rebuild`, `--lexicon FILE`, `--max-records N`.
Set `SOCRATA_APP_TOKEN` for higher Socrata rate limits.

## Output record

```jsonc
{
  "record_id": "…16 hex…",              // sha256(source + text); append mode skips IDs it has already written
  "schema_version": "1.0",
  "lexicon_version": "2026.10.1", "lexicon_sha256": "…",
  "source": {"type": "transcript", "file": "city-council/2026-01-12-city-council.md", "youtube_id": "…", "start": "01:10:56"},
  "raw_source": {"text": "…", "date": "2026-01-12", "body": "city-council", "start": "01:10:56", "url": "https://www.youtube.com/watch?v=…&t=4256s"},
  "audit_classification": {
    "entity_mapping": {"agencies": [], "officials": [], "statutory_citations": [], "instruments": []},
    "procedural_deviations": ["statute", "ordinance"],
    "rhetorical_alignment_profile": {"objective": 1, "subjective": 0, "deferral": 0, "authority_appeal": 0,
                                     "objectivity_ratio": 1.0, "dominant_mode": "objective"},
    "remediation_pathway": [{"pathway": "…", "authority": "…", "triggered_by": "…"}],
    "statutory_reference_points": ["wyoming statute", "W.S. 35-7-1046"],
    "enforcement_classification": ["Routine/Informational"],
    "compliance_friction_score": 7.5,
    "remediation_status": "Eligible for Administrative Review",
    "evidence": [{"category": "procedural_deviation", "term": "statute", "count": 2, "snippet": "…"}]
  }
}
```

Every run also writes two side files:

* `<out>.manifest.json`: per-run counts (written, duplicate, empty, dead-lettered, flagged) and the lexicon hash.
* `<out>.deadletter.jsonl`: written only if a record fails. It holds the original record and the error, so nothing is silently dropped.

## Rules (deterministic)

* **Matching:** case-insensitive whole words or phrases, with an optional plural. `warrant` matches
  "warrants" but not "warranty". All-caps acronyms such as `LEADS` and `BOPU` are case-sensitive.
* **Score:** `1.5 × unique deviation terms + 2.0 × unique statutory terms`. Explicit
  `W.S. nn-n-nnn` citations count as statutory terms. A score above `3.0` sets status to
  *Eligible for Administrative Review*. The weights and threshold live in `lexicon.json → scoring`.
* **Remediation pathways:** a fixed table in `REMEDIATION_RULES` (Public Meetings Act,
  Public Records Act, WAPA review, municipal-code appeal, parliamentary objection,
  suppression/due-process motion, expungement). Each rule fires on specific trigger terms.
* **Transcript chunking:** timestamps are honoured wherever they appear, including mid-paragraph.
  Passages are about 1,200 characters, and over-long caption runs are split at sentence or word
  boundaries. Every passage links to its moment in the video.

## Limits: read before you cite anything

* A keyword hit means **a word appeared**. It does not establish a deviation, violation or
  misconduct. The score ranks passages for a human to read. It is not a veracity metric.
* The transcripts are auto-captions. Names are often wrong ("Aldrich" / "Aldridge", "Crave" / "Seager"),
  so the officials list reflects caption spellings. Verify against the linked video.
* Remediation pathways are general research pointers. They are not legal advice. Check the current
  statute text and deadlines, or ask a Wyoming attorney.

## Adding it to the TheReelWindyCity app

The multipage Streamlit app lives in `bartimoussmith-oss/therealwindycity`:

1. Copy `audit/` next to `streamlit_app.py`.
2. Copy `audit/streamlit_page.py` to `pages/21_Compliance_Matrix.py`.
3. Make the data available. Either commit a built `audit/output/audit_records.jsonl` there
   (about 15 MB), or set `AUDIT_RECORDS_PATH` to wherever the file lives.
4. `requests` is only needed for remote sources. The dashboard needs only `streamlit` and `pandas`,
   which that app already pins.
