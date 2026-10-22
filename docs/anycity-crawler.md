# Any-city crawler: design and terminology

## The technical term

The tool described — *first go out and map a site's different
infrastructures, then design its own scraper from that map, then keep
returning for new PDFs/content* — already has established names in the
web-crawling literature. It is not one word; it is a three-part class:

> **Adaptive focused incremental crawler with platform fingerprinting
> and automatic wrapper induction.**

| Phase | Established term | What it means here |
|---|---|---|
| Point it at a topic, not the whole web | **Focused crawling** (a.k.a. topical crawling) — Chakrabarti, van den Berg & Dom, *Focused crawling: a new approach to topic-specific Web resource discovery* (WWW 1999) | Every discovered URL is scored for civic-record relevance (agenda, minutes, packet, ordinance…) and the fetch budget is spent best-first. Jobs pages and photo galleries lose; agenda listings win. |
| Map the infrastructure first | **Exploratory / reconnaissance crawl** + **web-application (platform) fingerprinting** | A bounded first pass reads `robots.txt`/sitemaps, headers, `<meta name="generator">`, asset URLs, outbound links and URL shapes, and matches them against known municipal platforms (CivicPlus, Granicus, Legistar, BoardDocs, PrimeGov, NovusAGENDA, CivicClerk, Municode, Laserfiche, IQM2, Simbli, OnBase, WordPress, Drupal, plus YouTube/Vimeo as linked video infrastructure). |
| The tool designing its own scraper | **Automatic wrapper generation / wrapper induction** (e.g. RoadRunner, Crescenzi et al., VLDB 2001; DEPTA, Zhai & Liu 2005) | A *wrapper* is the technical term for a site-specific extraction program/configuration. Instead of hand-writing selectors per city, the crawler induces one: URL templates (`/AgendaCenter/ViewFile/Item/{id}`, `/wp-content/uploads/{year}/{id}/agenda-{date}.pdf`), listing pages (high density of document links), document-kind and date classifiers. The wrapper is emitted as a reviewable `site-profile.json` rather than hidden inside code. |
| Come back for only what's new | **Incremental crawling** — Cho & Garcia-Molina, *The evolution of the web and implications for an incremental crawler* (VLDB 2000) | Re-visits use conditional GET (`If-None-Match` / `If-Modified-Since`) and SHA-256 comparison. Unchanged documents are not re-downloaded; changed/new ones are logged with before/after hashes. |
| (Not yet) listings behind JS/search forms | **Deep / hidden-Web crawling** (Raghavan & Garcia-Molina 2001) | Fingerprinted and recorded (BoardDocs is the classic case) but requires a headless-browser stage; deliberately out of scope for this stdlib-only tool. |

Related terms you will see used for the same architecture: *site-agnostic /
template-independent crawler*, *self-configuring spider*, and (in the
municipal-scraping world, e.g. City Scrapers / Open Civic Data) a
*platform-adapter spider* — one adapter per vendor platform instead of one
scraper per city. If you are searching literature or vendors, search:
**“adaptive focused incremental web crawler wrapper induction.”**

## Why the existing Cheyenne tool is not this

`tools/sync_city.py` is a **site-specific mirror**: it hard-codes
`https://www.cheyennecity.org` (`Mirror.__init__` rejects any other
origin) and refuses every external host. That is correct for a defensive
mirror of one city, but it cannot be re-pointed: in most towns the agendas
do not live on the city hall homepage's host at all — they live on
`*.granicus.com`, `go.boarddocs.com`, `*.civicclerk.com`, a Laserfiche
WebLink subdomain, etc. A single-host crawler pointed at such a town
succeeds politely and archives almost nothing important.

`tools/anycity_crawler.py` generalises the same safety machinery
(stdlib-only, per-host robots that fail closed, per-host delay, byte/page/time
budgets, PDF signature checks, hash change-log, resumable pending queue)
into the adaptive form:

```
                ┌──────────────────────── Phase 1: recon ────────────────────────┐
 seed URL ─────▶ robots.txt + sitemaps ─▶ bounded best-first exploratory crawl  │
 (any town)     per-host, fail-closed     │  • fingerprint platforms            │
                                           │  • cluster URLs into templates    │
                                           │  • find document listing pages    │
                                           ▼                                     │
                                  site-profile.json  ◀── the induced wrapper, │
                                  (review / edit it)     human-reviewable      │
                └────────────────────────────────────────────────────────────────┘
                                           │
                ┌─────────────────────── Phase 2: harvest ───────────────────────┐
 profile ─────▶ focused priority queue (civic score, best-first)                 │
                │  seed-domain + subdomains + fingerprinted vendor hosts only  │
                │  conditional GET + SHA-256 ─▶ only new/changed PDFs stored   │
                ▼                                                                 │
   out/catalog.json · out/documents.jsonl · out/documents/*.pdf · out/status.json│
   state/state.json (records, changes, pending queue — resumable)               │
                └────────────────────────────────────────────────────────────────┘
        Re-run Phase 2 on a schedule for incremental updates.
        Re-run Phase 1 when the city re-platforms (profile diff = migration evidence).
```

## Usage

```sh
# Both phases, one workdir per town:
python3 tools/anycity_crawler.py run https://www.exampleville.gov \
    --workdir towns/exampleville

# Or separately, so you can inspect/edit the induced wrapper first:
python3 tools/anycity_crawler.py recon https://www.exampleville.gov \
    --out towns/exampleville/site-profile.json
python3 tools/anycity_crawler.py crawl \
    --profile towns/exampleville/site-profile.json \
    --state-dir towns/exampleville/state --output towns/exampleville/out

# A city parks agendas on a non-vendor partner domain? Admit it explicitly:
python3 tools/anycity_crawler.py run https://www.exampleville.gov \
    --workdir towns/exampleville --allow-host agendas.partner-county.gov

python3 -m unittest tests.test_anycity_crawler -v   # offline fixture towns
```

Outputs per town: `documents.jsonl` rows carry `doc_kind`
(`agenda`, `minutes`, `agenda-packet`, `ordinance`, …), `meeting_date`
(extracted from anchor text/URL), source/final URL, SHA-256, ETag,
`discovered_from`, and the local PDF path. `status.json` carries the
run report and the full hash change-log.

## Scope rule (how “wherever I point it” stays safe)

A URL is crawlable only if it is (a) on the seed's bare domain or a
subdomain of it, (b) on a host fingerprinted as a known municipal
**content** platform, or (c) on an explicitly `--allow-host`ed domain.
Video platforms are recorded as linked infrastructure but never crawled
(captions are `tools/fetch_transcripts.py`'s job). Every admitted host
gets its own `robots.txt` check — a robots failure closes that host,
not silently the whole run — and every redirect is re-checked against
scope and robots on the destination host. Login/admin/payment paths and
binary asset extensions are excluded. No form is ever submitted.

## Honest limits

- **JavaScript-only listings** (BoardDocs especially) and
  **search-form archives** are fingerprinted, not enumerated. Adding a
  headless stage is a per-*platform* job (one adapter serves every city
  on that platform) — do it when a target town needs it, keyed off
  `platforms_detected[].id` in the profile.
- **Fingerprint ≠ proof.** `confidence: high` means redundant evidence
  (vendor host + URL shape + body marker), not a verified contract, and
  a platform the recon budget never reached will be missed. Raise
  `--recon-max-pages` for big counties.
- **Completed ≠ complete.** It means the discovered priority queue was
  processed within budget. Coverage claims still need the same care as
  the Cheyenne archive uses.
- State is local JSON; for evidentiary use, back up `state/` and the
  harvested PDFs to durable storage (same warning as `city/SYNC.md`).
- This design was verified offline against three fixture towns
  (CivicPlus+BoardDocs, Granicus, generic WordPress — see
  `tests/test_anycity_crawler.py`). Pointing it at a real town needs
  real network access and a review of the generated profile before the
  first harvest.

## Adding a platform

Add one entry to `PLATFORMS` in `tools/anycity_crawler.py`: vendor host
regex, a distinctive URL-path regex, lowercase body markers, and
`crawlable`. Prefer two or more independent signals per platform so a
coincidental body-word match stays `medium` confidence. Add a fixture
town to the tests in the same change.
