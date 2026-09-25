# 🌪️ The Real Windy City: Windy City Reaper

**Civic Accountability Edition.** A multi-city civic intelligence engine. It
collects public records through the most official channel available, flags
what matters with verbatim quotes, catches silent edits, spots permit and
sentiment trends, and pushes alerts to Slack, Discord or email. When a source
refuses automated access, the engine drafts a statutory bulk-records request
for you to send instead of working around the refusal.

Example cycle log:

```
[06:00:01] jurisdiction=cheyenne_wy source=granicus_packets [pra_only] → LEGAL_CHANNEL · bulk request #1 (Wyo. Stat. §§ 16-4-201–205)
[06:00:09] jurisdiction=chicago_il source=building_permits [api] → OK · 212 aggregate buckets; 5000 rows scanned, 14 watchlist rows stored
[06:00:40] worked 31 jobs → new events {'silent_edit': 1, 'watchlist_hit': 9}
[06:00:55] trend: [chicago_il] building_permits:permits_per_month Community Area 31 = [12, 15, 22] → slope=+5.0 → FLAG
[06:00:57] sentiment: [chicago_il] “Pilsen” avg -0.83 (n=6) down from +0.05
[06:01:03] alerts dispatched: {'slack': 4, 'discord': 4, 'email': 1}
[06:01:05] ledger committed: +14 entries, head a13f0e02b9c1
```

## Try it in 30 seconds (no network, no API keys)

```bash
python run.py selftest            # full pipeline against a local fixture server: 11/11 checks
pip install -r requirements.txt
python run.py demo                # builds data/demo/ from synthetic fixtures
streamlit run streamlit_app.py    # command center; opens on the demo if no live data yet
```

The core engine uses only the Python standard library. Streamlit, pandas and
pypdf power the dashboard and PDF extraction.

## What it adds over the original (therealwindycity.streamlit.app)

| | Original Cheyenne watchdog | Windy City Reaper |
|---|---|---|
| Scope | One city, hard-coded Wyoming PRA | **Any city by config edit**: Cheyenne, Chicago, Denver and Aurora seeded; 27 state statute profiles plus federal FOIA |
| Blocked sources (e.g. Granicus) | Refused, then a dead end or manual PRA | **Auto-drafted bulk-access request** under the right state law, tracked to a due date |
| Ingestion | Polite HTML and RSS | **Tiered**: Socrata API → Legistar / Chicago eLMS APIs → RSS → HTML → Playwright render (robots-gated) → legal channel |
| Analysis | Keyword FTS5 + extractive summary | FTS5 + watchlist quotes + **permit/incident trend slopes** + **news sentiment shifts** + optional **LLM pass with verbatim-quote verification** |
| Alerts | Daily digest file | **Slack, Discord, webhook, email** push plus the digest |
| Records requests | Draft text | **Workflow**: draft → reviewed → sent → due date computed → overdue flagged; edit, download or open in your email client |
| Integrity | Hashes + diffs | Hashes + diffs + a **hash-chained public ledger** (tampering breaks the chain) |
| Access | Streamlit UI | Streamlit UI + **read-only JSON API** for journalists and developers |
| Storage | SQLite | SQLite (zero-ops) with a **Supabase/Postgres + pgvector** schema ready in `supabase/schema.sql` |

### What it deliberately does *not* do

It doesn't ignore `robots.txt`, spoof user-agents, run stealth browsers, or
automatically send anything to agencies. The records are public, so the legal
route to them always exists. Getting around a "no bots" rule only adds
terms-of-service and computer-access-law risk, and it gives an agency a reason
to discredit your findings. See [LEGAL.md](LEGAL.md).

## Dashboard tabs

The dashboard opens filtered to **Cheyenne, WY**, the project's home city.
Change `default_jurisdiction` in `config/jurisdictions.json` to use another city,
or clear the Jurisdictions filter in the sidebar to see all of them.

- **🗺️ Live Intel:** a map with pins colored by alert type, a sortable table of
  verbatim quotes and source links, and expandable detail with diffs for silent
  edits. Each event also shows the engine's **captured copy** of every stored
  version, so the evidence survives even if the agency edits or deletes the
  page. Any event has a one-click button to draft a records request about it.
- **🔎 Search:** full-text search across every captured document version.
- **📈 Trends:** sparklines for every ward or community area, with flagged
  groups first. Also shows weekly news sentiment by topic.
- **⚖️ Records Requests:** an editable status table (`st.data_editor`), a
  letter editor, `.txt` download, "open in my email client", and statutory due
  dates.
- **🛰️ Sources:** health of each source, and a "Run civic cycle now" button.
- **🔗 Ledger:** chain verification, recent entries and a JSONL download.

## CLI

```bash
python run.py cycle                      # crawl → analyze → trends → sentiment → alerts → ledger → digest
python run.py cycle -j chicago_il        # one jurisdiction
python run.py sources                    # status of every source
python run.py search "zoning variance"
python run.py request pra -j cheyenne_wy -r "All emails re: Ordinance No. 4687" --range "2026-01-01 to present"
python run.py request list
python run.py request sent 3             # you sent it → statutory due date computed
python run.py ledger verify
pip install -r requirements-extra.txt && python run.py api   # GET /events /search /requests /sources /metrics /ledger/verify
```

## Configuration

- `config/jurisdictions.json`: cities, custodians, map centers and sources.
  Each source's `method` is its tier. Add a city by copying a block.
- `config/watchlist.json`: regex terms with severity, optional per-city terms,
  and sentiment topics per city.
- `config/statutes.json`: public-records laws with citations and response
  deadlines. A state not listed gets a `[VERIFY]` placeholder instead of a
  made-up citation.

Environment and secrets (see `.env.example`): `SLACK_WEBHOOK_URL`,
`DISCORD_WEBHOOK_URL`, `ALERT_WEBHOOK_URL`, `SMTP_*`, `ALERT_EMAIL_TO`,
`ALERT_MIN_SEVERITY`, `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` (any
OpenAI-compatible endpoint), and `REQUESTER_NAME` / `REQUESTER_CONTACT` for the
letterhead.

## Deploy

1. **Streamlit Community Cloud:** point it at this repo with `streamlit_app.py`
   as the entry point. Paste `.streamlit/secrets.toml.example`, filled in, under
   *App settings → Secrets*. The app loads those keys (letterhead, alerts, LLM)
   automatically. The first visitor sees the demo until the Action has committed
   live data.
2. **GitHub Actions:** `.github/workflows/civic-cycle.yml` runs every 6 hours,
   plus hourly sweeps on Monday and Tuesday meeting nights. It runs the
   selftest first, then the cycle, verifies the ledger, and commits
   `data/engine.db`, `data/ledger/` and the digest. Add alert and LLM keys as
   repository **secrets**, and `REQUESTER_NAME` / `ALERT_MIN_SEVERITY` as
   **variables**.
3. `tests.yml` runs the selftest and pytest on every push.

## Seeded sources (endpoints checked 2026-09-24)

| City | Source | Tier | Status |
|---|---|---|---|
| Cheyenne, WY | Council minutes & agendas page | html | robots allows the page; Granicus packet links are refused and routed to a bulk request |
| Cheyenne, WY | Granicus agenda packets | pra_only | Wyoming PRA bulk-access request drafted automatically |
| Cheyenne, WY | City news, Cap City News | html, rss | as in the original project |
| Chicago, IL | Building permits `ydr8-5enu` | api | fields confirmed; grouped by **ward**; only permit type and work description are stored |
| Chicago, IL | Crimes `ijzp-q8t2` | api | confirmed; aggregate counts by ward only |
| Chicago, IL | City Council legislation | elms | official City Clerk eLMS API (replaced Legistar in 2023) |
| Chicago, IL | Block Club Chicago | rss | feed live; used for sentiment |
| Denver, CO | Council matters | legistar | Legistar Web API client `denver` confirmed |
| Denver, CO | Denverite | rss | feed live |
| Aurora, CO | Council Meetings page | html | Aurora isn't on Legistar (agendas are built in eSCRIBE); this official page links packets, minutes and votes |
| Aurora, CO | Sentinel Colorado | rss | feed live |

Linked documents are re-checked at most once every 24 hours per source
(`refetch_hours`), which is gentle on city servers and still catches silent
edits within a day.

### Noise controls (tuned on the first live run, 2026-09-24)

- **Trends are seasonality-adjusted.** A ward or area is flagged only if its growth
  beats the citywide total's growth over the same months by `min_excess_growth`
  (default 25%). The first live run flagged 31 wards before this rule because
  summer lifts every ward.
- **Only records hosts become records requests.** If the agency's own site or an
  agenda platform (Granicus, Legistar, CivicPlus, eSCRIBE, BoardDocs, …) refuses
  access, the engine drafts a bulk request. A refusal from a third-party widget,
  such as a text-to-speech service, is logged and ignored.
- **No duplicate pages.** Language-picker links are skipped, and linked documents
  with identical text are stored once.
- **Scoped news feeds.** `exclude_url_patterns` drops wire and national sections
  (Sentinel's `/nation-world/`). "Settlement" matches only legal settlements.
- **Complete Legistar pulls.** The engine paginates past the API's 1000-row page limit
  (`limit`, default 2000).

## Layout

```
run.py                  CLI
streamlit_app.py        command center
config/                 jurisdictions.json · watchlist.json · statutes.json
engine/
  net.py                legality gate: robots.txt, crawl-delay, rate limit, honest UA
  ingest.py             tiered fetchers (Socrata, Legistar, eLMS, RSS, HTML, Playwright) + blocked → request routing
  extract.py            HTML / PDF / OCR hook
  detect.py             SHA-256 drift + noise-filtered diffs (silent edits)
  analyze.py            watchlist, trend slopes, sentiment, LLM with quote verification
  records.py            multi-state request drafts, due dates, overdue tracking
  alerts.py             Slack / Discord / webhook / email
  ledger.py             hash-chained public ledger
  pipeline.py           orchestration + digest
  api.py                read-only FastAPI
  fixtures.py           offline fixture world (synthetic)
  selftest.py           end-to-end proof
supabase/schema.sql     Postgres + pgvector upgrade path
tests/                  pytest suite
```
