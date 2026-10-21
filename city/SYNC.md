# City website mirror and sync service

## What is implemented

- `tools/sync_city.py`: standard-library crawler and static renderer.
- `mirror-config.json`: explicit host allowlist, crawl budgets, robots-aware user
  agent, document MIME types, and excluded paths.
- `/city/mirror/`: searchable directory of mirrored pages and documents;
  internally mirrored links stay local. Other links go to their source.
- `/city/mirror/status.html`: run status, coverage limitations, errors, source
  hashes, and observed change history. JSON versions support other tools.
- The existing Pages workflow runs the sync before publishing, daily at **09:17
  UTC**, on existing publishing-branch pushes, and on manual dispatch. Scheduled
  workflows only run after this change reaches the default branch.

**This is a readable content mirror, not a pixel-identical city-site clone.**
Upstream CSS, scripts, forms, cookies, authentication and transactional systems are
not copied. The existing municipal-style presentation is used consistently.
No requests are submitted, no credentials collected, and no payments processed.

## Supported scope

The only crawled host is `https://www.cheyennecity.org`. The crawler discovers
URLs from robots-declared sitemaps (or `/sitemap.xml`), links, pending work and
previously archived records. It checks robots rules before each content request,
including redirects. Robots errors fail closed; HTTP 404 for robots means no
published rules. External redirects are rejected, not silently followed.

Public HTML is extracted to escaped plain text and a link list. PDF and plain-text
files are retained. PDF signatures are checked, but PDFs are **not malware-scanned**.
Use an updated viewer. Embedded widgets, JavaScript-only content, images, videos,
other office formats and externally hosted services are not mirrored. Links to
these services are preserved when present in source HTML. This deliberately does
not promise to clone all of the city's internet infrastructure.

Default limits: at least 3 seconds between requests (longer when robots specifies
it), 1,500 page/document attempts, 30 sitemaps, 20 MB per file, 250 MB of response
bodies and 90 minutes per run. A 400 MB cumulative source-byte budget bounds the
current archive; an exhausted budget is reported, not silently discarded. HTTP 429/503 responses receive bounded retries.
An unfinished page queue is persisted for subsequent runs. Sitemap discovery
is bounded; no completion claim means every possible URL has been discovered.

## Local use

From the repository root, with Python 3.10 or newer:

```sh
python3 -m unittest discover -s tests -v
python3 tools/sync_city.py                    # real network access required
python3 tools/sync_city.py --render-only      # no network; render cached state
python3 -m http.server 8000 --bind 0.0.0.0
```

Visit `/city/`, `/city/mirror/` and `/city/mirror/status.html`.
A first render without crawl data explicitly says no content has been fetched.
The restricted Arena workspace cannot reach the city host; fixture tests do not
constitute live-source verification.

## Deployment and activation

1. Review and merge this working branch into the repository's default publishing
   branch. This does not change the separate `/therealwindycity/` repository or
   the Streamlit deployment.
2. Ensure repository Settings → Pages uses **GitHub Actions**, Actions is enabled,
   and the `github-pages` environment permits the publishing branch.
3. The push starts the existing **Deploy site** workflow. Alternatively run it
   from Actions → Deploy site → Run workflow on the publishing branch.
4. Check both the Actions job summary and the public sync status page. A successful
   Pages deployment is **not** proof that the source crawl succeeded: failures are
   published visibly alongside any available last-known copies.

Expected location:
`https://therealwindycity.github.io/The-Real-Windy-City-/city/mirror/`

The workflow uses the built-in Pages token; no city login, API key, or PAT is
needed. Tests run before sync. Existing encrypted Atlas safeguards remain in place.
Cache, tests and build directories are excluded from the public site artifact.
No generated crawl corpus is committed to Git.

## Persistence and integrity limits

Crawl state and current document bytes are stored in `.cache/city-mirror/` and
saved/restored using branch-scoped GitHub Actions caches. Pages receives only the
rendered public mirror. Caches can be evicted; loss causes a fresh crawl and loss
of accumulated hash history. This is **not durable evidentiary storage**. Back up
that state to durable storage if long-term preservation is required.

Each record includes source/final URL, fetch and check time, content type,
ETag/Last-Modified when provided, and SHA-256 of the fetched response bytes.
Conditional requests avoid repeat downloads. Hash changes log both old and new
hashes, but old document bodies are not kept. This is observation-to-observation
change detection, not instant monitoring, a textual diff service, proof of intent,
or a guarantee against changes between crawls.

If a source disappears, the last copy is retained with its observed error status.
A robots block also labels an existing copy; it is not fetched again. Check the
run-level status for network errors. No automated takedown decision is made.

## Troubleshooting

- **failed / robots error:** respect the restriction; use official access or request
  records manually. Do not disable robots enforcement.
- **partial / pending URLs:** normal for a site larger than a run budget; later
  runs resume pending work. Adjust budgets cautiously to avoid overloading the city.
- **HTTP errors:** inspect the per-URL status report. The archive does not imply
  that unavailable pages were removed intentionally.
- **not yet run:** no sync state exists; run the workflow with city network access.
- **No scheduled run:** the workflow must be on the default branch; GitHub may delay
  schedules or disable inactive public-repository schedules. It is not an uptime SLA.
