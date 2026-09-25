# Windy City Reaper: handoff for the next developer or model

Civic-accountability engine for Chicago IL, Denver CO, Aurora CO and Cheyenne WY.
Repo: github.com/therealwindycity/The-Real-Windy-City- (work arrives in `main` through PR #1).

## What it does
- **Ingests official sources** through a tiered chain: Socrata API → Legistar / Chicago eLMS APIs → RSS → HTML → Playwright (robots-gated) → legal channel.
- **Detects:**
  - silent edits to documents
  - watchlist hits, with verbatim quotes
  - permit/crime trends that outpace the whole city (seasonality-adjusted)
  - weekly news sentiment shifts
- **Drafts a public-records request** under the correct state statute whenever a source refuses automated access.
- **Records every finding** in a hash-chained public ledger.
- **Shows it all** in a Streamlit dashboard (`streamlit_app.py`), with an optional read-only FastAPI (`engine/api.py`).

## Hard design rules (keep these)
- Never bypass robots.txt, spoof user-agents or use stealth browsers. A refusal becomes a `blocked_source` event plus a drafted bulk records request (see LEGAL.md).
- Only the agency's own site or a known records platform can trigger a request. Refusals from third-party widgets are ignored.
- Nothing is sent to an agency automatically. Requests go draft → reviewed → sent (by a human) → due date → overdue.
- RSS stores summaries only. LLM output is kept only if its quotes match the source word for word.
- Demo data is synthetic and clearly labelled.

## Run it
```bash
pip install -r requirements.txt          # streamlit, pandas, pypdf (engine core is stdlib-only)
python run.py selftest                   # offline fixture world, 11/11 checks
python -m pytest -q tests                # 19 tests
python run.py cycle                      # live crawl → data/engine.db, ledger, digest
python run.py sources                    # health of every source
streamlit run streamlit_app.py           # dashboard (Live ledger / Demo toggle)
```

## Layout
- **`config/`**:
  - `jurisdictions.json`: jurisdictions and their sources
  - `statutes.json`: state records laws
  - `watchlist.json`: watchlist terms
- **`engine/`**:
  - `net.py`: legality gate
  - `ingest.py`: connectors
  - `extract.py`
  - `detect.py`: diffs
  - `analyze.py`: watchlist, trends, sentiment
  - `records.py`: records requests
  - `ledger.py`, `alerts.py`, `pipeline.py`
  - `db.py`: SQLite + FTS5
  - `api.py`, `fixtures.py`, `selftest.py`
- **`.github/workflows/`**:
  - `civic-cycle.yml`: runs every 6 hours plus hourly on Mon/Tue meeting nights, and commits the data
  - `tests.yml`: runs on every push
- **`data/`**: live output (`engine.db` is SQLite, plus `ledger/events.jsonl` and `out/digest-*.md`).
- **`supabase/schema.sql`**: a Postgres schema with the same table names, as a migration path. No sync code exists yet.

## Live status (verification run 2026-09-25 00:06Z)
All 12 enabled sources were OK:
- **Chicago:** 18 watchlist hits and 10 trend flags
- **Denver:** 7 hits
- **Aurora:** 1 hit
- **Cheyenne:** 8 hits, plus 1 drafted Wyoming records request for Granicus

## Open items
**Owner's tasks:**
- Merge PR #1.
- Set repo variables `REQUESTER_NAME` and `REQUESTER_CONTACT`.
- Point Streamlit Cloud at `main` / `streamlit_app.py`.
- Revoke the old GitHub token.

**Engineering:**
1. **Stop committing `data/engine.db` on every run.** The 5 MB file adds about 1 MB compressed per commit, roughly 2 GB of git history a year. Keep the ledger and digest in git and move the database to an artifact, a release file or Supabase. On Streamlit Cloud this also stops dashboard edits (request status) from being lost on each redeploy.
2. **Never run live:** alerts, the LLM pass and the Playwright tier. There were no credentials, and browsers couldn't be installed.
3. **Only Chicago has data trends.** Denver's open-data permits could be added.
4. **Aurora has no legislation API**, so the engine reads PDFs from its council page. Cheyenne's Granicus is reachable only through the records request.
5. **The Wyoming Tribune Eagle feed is disabled.**
6. **Watchlist terms are generic** outside Cheyenne.
7. **Documents received in reply** to records requests aren't ingested.
8. **Smaller gaps:** the API isn't hosted anywhere, and sentiment uses a simple word list.

## Known API facts
- **Chicago eLMS:** `GET https://api.chicityclerkelms.chicago.gov/matter` takes `filter`, `top` (≤500), `skip` and `sort`. `sort=recordCreateDate` is rejected.
- **Legistar Web API:** client `denver` works; `aurora` isn't a valid client.
- **Aurora eSCRIBE:** `pub-auroraon` is Aurora, Ontario, the wrong Aurora.
- **cheyenne.granicus.com:** robots.txt disallows crawling.
