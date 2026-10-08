# Civic Legal Research Red-Team Engine

A conservative, auditable research workflow for case packets and source records. The engine combines transparent issue-spotting rules, page/time-preserving document ingestion, pluggable primary-source and case-law discovery connectors, a researcher-reviewed fact/authority graph, an optional case-law treatment search, and strictly allowlisted optional LLM drafting.

It is a **research aid, not legal advice, a legal-outcome predictor, or a substitute for counsel**. No single issue catalog or provider covers every jurisdiction or source. Search results are leads; facts, source status, legal meaning, controlling force, and remedies require human verification.

## Quick start

Python 3.11 or newer:

```bash
python -m legal_redteam analyze legal_redteam/examples/synthetic_inspection_matter.json
python -m legal_redteam analyze path/to/matter.json --format json --output /secure/location/matter-report.json
python -m legal_redteam analyze /path/to/source-bundle --format markdown --output /secure/location/source-bundle-review.md
```

Analysis is deterministic and offline. It does not call an LLM or a legal database. A directory input is recursively ingested as one source bundle, with a separate record, SHA-256, filename, extraction status, and uniquely linked facts for each readable file. Supported inputs include normalized `.json` case packets (passed directly), UTF-8 `.txt`, `.md`, `.markdown`, `.rst`; text-layer `.pdf`; `.docx`; timestamped `.vtt` and `.srt`; and Markdown transcripts with `[HH:MM:SS]` markers. A folder bundle intentionally skips JSON files and requires a JSON case packet to be passed directly. Hidden/cache directories are excluded; unsupported and unreadable files are reported as ingestion warnings. Every extracted passage remains `unclassified`; no source is promoted to an established fact.

### Private upload preview

Start a browser-based upload-and-analyze page inside the Arena workspace:

```bash
python -m legal_redteam.upload_preview --host 0.0.0.0 --port 8000
```

The page accepts individual files or a folder upload and saves each batch under `.legal_redteam_private/uploads/<batch-id>/`, which is ignored by Git. It runs the same offline analyzer and offers Markdown/JSON report downloads. The batch remains in the sandbox until you use **Delete batch**. Uploads are limited to 512 MiB and 500 files per batch; OCR is opt-in. This is a workspace convenience, not a confidentiality or retention guarantee—upload sensitive material only if appropriate for the workspace, and do not treat the ignored folder as a secure records archive.

For PDF and DOCX support, install optional Python dependencies:

```bash
python -m pip install -r legal_redteam/requirements-optional.txt
```

OCR is **opt-in**. Install the system Tesseract executable and dependencies, then run:

```bash
python -m legal_redteam analyze scan.pdf --ocr --ocr-language eng
```

The original input is never changed or embedded. By default it is not copied; to archive verified, SHA-256-named copies outside the source directory (preferably outside the repository), use `--preserve-sources-dir "$HOME/legal-redteam-source-archive"` (choose a secure location appropriate for the matter). Each packet/report record retains its relative filename, optional archive filename, byte size, SHA-256, ingestion capture time (not the source's own creation/effective date), extractor, categorical extraction status, and warnings. Markdown headings are kept as section context in line locators; explicit `Page N` labels in Markdown are marked as source labels, not independently verified page numbers. Names ending in `.pdf.md` or `.docx.md` are ingested as Markdown exports with a warning that the original binary/layout is absent. A filename identifying Gemini Notebook material also receives a derivative/AI-notes warning. PDF facts receive page/line locators. DOCX has layout-dependent pagination, so it uses paragraph/table-row locators and warns that page layout, headers/footers, comments, footnotes, and tracked changes may need separate review. OCR status is explicitly unreviewed; the label is process metadata, not a probability of accuracy. Scanned pages without OCR are retained as warnings, not silently discarded or treated as readable.

The repository's Cheyenne meeting transcript archive is supported directly: its timestamped Markdown and raw WebVTT files preserve timestamps as fact locators.

### Issue packs

Append a custom JSON issue pack to the 24-rule starter catalog:

```bash
python -m legal_redteam analyze matter.json \
  --rules legal_redteam/examples/custom_issue_pack.json
```

Rules need inspectable triggers, elements/questions, authority lanes, evidence needs, opposing questions, and research queries. Custom IDs cannot overwrite built-ins. See [`schema/issue-pack.schema.json`](schema/issue-pack.schema.json). The built-ins cover constitutional and administrative issues, choice of law/sovereign jurisdiction, public records, criminal procedure, contracts/torts, employment/labor, environmental/public health, procurement, tax/fiscal issues, elections, speech, housing, consumer matters, immigration, and bankruptcy. This is a non-exhaustive starter set, not a universal law taxonomy.

## Research providers

Providers run only through the explicit `research` command. Each has an interface and injectable HTTP transport; tests use mock transports. Provider results retain source URLs, dates, snippets, hashes where available, provenance warnings, and the provider's own source classification. They do not automatically create verified authorities or determine bindingness/currentness.

The default query searches eCFR and the Federal Register:

```bash
python -m legal_redteam research "administrative inspection warrant" --as-of 2026-10-06
```

Select providers explicitly as needed:

```bash
# National Archives Constitution transcription
python -m legal_redteam research "free exercise" --provider us-constitution

# Exact citation lookup at the official House Office of the Law Revision Counsel (OLRC)
python -m legal_redteam research "42 U.S.C. § 1983" --provider uscode

# Official Wyoming Constitution/statute PDF download page; select the needed title(s)
python -m legal_redteam research "inspection authority" \
  --provider wyoming-statutes --wyoming-titles 15,16,18
python -m legal_redteam research "search and seizure" --provider wyoming-statutes --wyoming-titles 97

# Local city/county enacted records, official opinions, tribal codes, or other source files
python -m legal_redteam research "public notice hearing" \
  --provider local-folder --local-corpus ./official-sources \
  --local-manifest ./official-sources-manifest.json

# Court-law discovery through CourtListener (secondary index, not the official opinion)
export LEGAL_REDTEAM_COURTLISTENER_TOKEN='configured-in-your-local-environment'
python -m legal_redteam research "administrative inspection warrant" --provider courtlistener
```

Provider notes:

- **U.S. Constitution:** searches the National Archives transcription. This is a text-search starting point; constitutional interpretation comes from the exact provision and applicable jurisprudence.
- **U.S. Code:** exact section lookup only at the official OLRC site, e.g. `42 U.S.C. § 1983`. The connector does not pretend to offer arbitrary subject searching. `--uscode-edition prelim` is the default; a four-digit edition can be selected. Check currency, classification tables, and session laws for the event date.
- **eCFR:** uses the official eCFR search API. `--as-of` requests a historical date where available. The eCFR is a continuously updated editorial compilation; verify official CFR/Federal Register history and the effective text.
- **Federal Register:** uses the public official search API. A publication-date filter is not a reconstruction of when a rule was legally effective.
- **Wyoming statutes/constitution:** reads the official Legislature's [State Statutes — Files in Download Format](https://www.wyoleg.gov/stateStatutes/StatutesDownload) index, then downloads only explicitly selected official title PDFs. The site currently describes its downloadable edition as reflecting the 2026 Budget Session and text existing as of July 1, 2026; the provider parses the edition note from the index rather than hard-coding it. It caches PDFs outside the repository under `~/.cache/legal-redteam/wyoming-statutes` for up to 24 hours (override with `--cache-dir`). No title selection means no Wyoming PDF search; this avoids silently treating a partial set as complete. Inspect the PDF, neighboring provisions, definitions, session laws, and historical version.
- **Local folder:** searches user-supplied files without deciding whether they are official. An optional JSON manifest maps relative file paths to user-entered citation, layer, jurisdiction, source URL, and primary-source-status labels. Use [`examples/local_sources_manifest.example.json`](examples/local_sources_manifest.example.json) as a template and [`schema/local-source-manifest.schema.json`](schema/local-source-manifest.schema.json) for the schema. This is the connector for official county/municipal enacted records and other jurisdictions whose portals do not expose a common API. A manifest label is not independent verification.
- **CourtListener:** requires `LEGAL_REDTEAM_COURTLISTENER_TOKEN` for API access. It is a discovery index. Its case snippets/citation graph are not the official opinion or a citator guarantee; preserve/open the official opinion, docket, reporter citation, pinpoint, and capture date.

Network/TLS access from this development sandbox was unavailable during implementation. The provider adapters are covered by mocked-transport tests; no live API call is represented as verified in this build.

## Case packet and evidence review

The complete packet definition is in [`schema/case.schema.json`](schema/case.schema.json). The fictional sample is [`examples/synthetic_inspection_matter.json`](examples/synthetic_inspection_matter.json).

Facts carry status, source ID, locator, optional exact `source_quote`, extraction metadata, and an optional person-entered `evidence_assessment`. Qualitative dimensions are `strength`, `authenticity`, `directness`, and `corroboration`. If any dimension is assessed, a reviewer and rationale are required. The engine never calculates, ranks, or auto-populates evidence strength. Those fields are reviewer notes, not admissibility rulings or fact-finding.

Authorities preserve layer, jurisdiction, citation, pinpoint, proposition, source excerpt, official opinion/source URL, docket number/URL, reporter citation, precedential status, decision/effective dates, capture time/hash, and independent citation, primary-text, currentness, and subsequent-history checks. Checks and characterization are entered by a researcher; the program does not silently promote them to verified status.

### Researcher-reviewed graph

Add edges in `research_links` to the case packet. Element IDs are deterministic and follow rule order as `<issue_id>::e<ordinal>`:

```json
{
  "research_links": [
    {
      "id": "link-fact-1",
      "from_type": "fact",
      "from_id": "fact-1",
      "to_type": "element",
      "to_id": "administrative_search::e1",
      "relation": "supports",
      "review_status": "reviewed",
      "reviewer": "Researcher initials",
      "reviewed_at": "2026-10-06",
      "rationale": "The cited record passage bears on the place and conduct element."
    },
    {
      "id": "link-authority-1",
      "from_type": "authority",
      "from_id": "authority-1",
      "to_type": "element",
      "to_id": "administrative_search::e1",
      "relation": "undercuts",
      "review_status": "reviewed",
      "reviewer": "Researcher initials",
      "rationale": "The opinion appears to limit this theory; verify the holding and procedural posture."
    }
  ]
}
```

A `reviewed` or `rejected` edge needs a reviewer and rationale. Proposed edges stay proposed and do not count as reviewed mappings. The analysis report shows resolved/dangling edges and provides separate element/fact/authority maps. It does not turn a link into proof or decide that a cited authority controls.

## Case-law treatment search

Run an explicitly requested case-law search against entered case authorities:

```bash
python -m legal_redteam cite-check matter.json --limit 100 --output reports/citator-leads.json
```

The adapter finds indexed opinions citing a matched case and flags snippets containing configured terms such as *overruled*, *abrogated*, *vacated*, *limited*, *questioned*, or *distinguished*. A phrase hit may concern another case, a party's argument, or a different issue. The output marks candidates for manual review; no hit is not a clean bill of health, and **no authority verification field is changed automatically**. Verify the opinion, court, citation, docket, official source, exact treatment passage, and later history. An unavailable token/provider is an explicit error, not a pass.

## Optional source-grounded drafting

Normal `analyze` never uses a model. Drafting is a separate explicit command. Configure an OpenAI-compatible chat-completions endpoint through environment variables; a local endpoint is also possible:

```bash
export LEGAL_REDTEAM_LLM_ENDPOINT='https://your-configured-endpoint/v1'
export LEGAL_REDTEAM_LLM_MODEL='your-model-name'
export LEGAL_REDTEAM_LLM_API_KEY='your-key-if-the-endpoint-requires-one'
python -m legal_redteam draft matter.json --issue-id administrative_search --output reports/draft.json
```

Drafting is refused unless at least one authority mapped to the issue has a source excerpt, official URL, and researcher-entered citation/primary-text/currentness checks (plus subsequent-history check for a case). Only the selected issue, linked facts, verified-source excerpts/metadata, issue elements, counterquestions, and procedural gates are sent. Raw source documents, absolute local paths, and unrelated case fields are not sent by default. The model must use source IDs, provide a full element analysis, bridge **and** disanalogy for a novel theory, the strongest opposing account/legal argument, procedural/remedy gates, and open research gaps. Unknown IDs and free-form legal citations are rejected; citations in output are formatted by the program from the verified records.

A model-drafted memo is not a verified legal analysis. Review the source record, currentness, adverse treatment, citations, every fact, and every argument independently. Do not send confidential or privileged information to an external model unless the user has approved that endpoint and data handling.

## What the offline analysis returns

- Five-vector intake adapted from the prior Paradox Engine work.
- Candidate issue prompts from inspectable, extensible text-trigger rules.
- Provenance-linked fact leads, extraction warnings, and user-entered evidence reviews.
- Element questions and a distinction between keyword leads, proposed graph edges, and researcher-reviewed mappings.
- Supplied supporting/contrary authorities, unresolved verification checks, and an explicit authority inventory.
- Opposing-side questions, procedural gates, completeness warnings, and an ordered research queue.
- Novel/analogical hypothesis prompts even when no exact fact-pattern match is present, while requiring existing-rule support, bridge, disanalogy, adverse search, remedy, and falsifier.

No match is not proof no issue exists. The catalog does not cover every subject, jurisdiction, treaty, tribal/foreign-law rule, ordinance, or procedural doctrine. Providers can fail, omit coverage, or return stale/irrelevant material; research is not complete until a human resolves the gap.

## Tests

```bash
python -m unittest discover -s legal_redteam/tests -v
```

Tests use synthetic packets and mocked network transports; they do not call live legal databases. The fictional example contains no private case facts.
