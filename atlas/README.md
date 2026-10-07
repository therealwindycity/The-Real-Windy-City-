# Paradox Atlas — personal AI & Google history explorer

A mind map **and** a choose-your-own-adventure reader over a personal AI history
archive. Every prompt, every output, when it happened, what it produced, how
complete it was, which theme it belongs to, and a one-click handoff packet so
another agent can pick the work up exactly where it stopped.

Everything is local. The browser never sends a byte anywhere: the dataset is
decrypted in-page, imports are parsed in-page, exports are generated in-page.

## Run it

```bash
# from the repository root
python3 -m http.server 8000
# open http://localhost:8000/atlas/

# or behind a password prompt (nothing is served without it):
python3 tools/serve_locked.py --port 8000
```

It needs to be served over HTTP (browsers block `fetch` on `file://`).

## Live on GitHub Pages

**https://therealwindycity.github.io/The-Real-Windy-City-/atlas/**

The whole site — the meeting transcripts and the Atlas — is published by
`.github/workflows/pages.yml`, which assembles the artifact instead of serving
the branch directly:

* `rsync` excludes `.git`, `.github`, `tools/`, `data/` and `*.zip`, so build
  tooling and sources never reach the web;
* a **guard step refuses to publish plaintext** — it fails the build if
  `atlas/data`, `atlas/exports`, `data/raw` or `data/unpacked` appear, requires
  the encrypted dataset (manifest + ≥100 blobs), and spot-checks blobs for
  readable content. A rebuild that somehow left the dataset decrypted cannot
  reach the public site.

The published Atlas is the **encrypted** build: visitors get the lock screen and
need the passphrase, exactly like a local copy. Crawlers are kept out of the
ciphertext by `robots.txt` (`Disallow: /atlas/enc/`) and the page carries
`noindex,nofollow`.

One operational note: the `github-pages` environment has a deployment branch
policy, so the branch that publishes must be listed under
**Settings → Environments → github-pages → Deployment branches and tags**
(`main` is listed by default; add others to publish from them).

## Password protection

**The shipped dataset is ciphertext.** `atlas/enc/` holds AES-256-GCM blobs;
only `atlas/enc/manifest.json` is readable, and it reveals a file count, a size
and a KDF iteration count — no names, no content. The passphrase is never
written to disk anywhere, in any form. Your browser derives the key with
PBKDF2-HMAC-SHA256 (600,000 iterations) and decrypts in memory; the plaintext
never lands in storage.

```bash
python3 tools/lock_atlas.py newpass                     # generate a strong passphrase
python3 tools/lock_atlas.py lock                        # atlas/data → atlas/enc, plaintext leaves the repo
python3 tools/lock_atlas.py unlock                      # put a working copy back in atlas/data
python3 tools/lock_atlas.py verify                      # decrypt + hash-check every blob
python3 tools/lock_atlas.py seal --src data/raw --enc sealed/raw   # raw Takeout archives too
```

`lock` also **moves the plaintext out of the repository** (default
`~/atlas-plaintext`, override with `--stash`) — a password screen is worthless
while `data/atlas.json` still sits beside it for any static server to hand out.
`build_atlas.py` can do the whole thing in one pass:

```bash
ATLAS_PASSWORD='your passphrase' python3 tools/build_atlas.py
```

### Two independent gates

| Gate | Protects | Works on |
|---|---|---|
| **Dataset encryption** (`tools/lock_atlas.py`) | the data itself — even a full copy of the repository is useless without the passphrase | any host, including GitHub Pages |
| **HTTP password** (`tools/serve_locked.py`) | the whole surface — page, scripts, styles, exports; nothing is served unauthenticated | any machine you run it on |

Use both if the archive is going anywhere near the internet.

### In the app

* The lock screen shows before anything is read. `Unlock` derives the key and
  decrypts the index; a wrong passphrase says so (never silently fails).
* **Keep me unlocked in this tab** stores only the *derived key* in
  sessionStorage — it dies with the tab, and it is not the passphrase.
* The **🔒 button** in the top bar re-locks instantly: key dropped, transcript
  cache cleared, built packets and rendered passages wiped, screen back up.
* `?plain=1` forces the plaintext path — only useful when `atlas/data/` exists
  locally for development.
* Decrypting on demand means transcripts, packets and exports are all read from
  ciphertext; nothing is pre-decrypted onto disk.

### Caveats worth knowing

* WebCrypto only exists in a **secure context**: `https://` or `http://localhost`.
  Served over plain HTTP from a LAN IP the app will refuse, with that message.
* **Losing the passphrase loses the data.** There is no recovery, by design.
* File sizes are visible to anyone holding the ciphertext (contents are not).
  Blobs are padded to 4 KiB blocks so the exact sizes are not.
* Git history is not rewritten by `lock`. If plaintext was ever committed, the
  old blobs still exist in past commits until the history is rewritten.

GitHub Pages works too — the encrypted dataset is what gets published — but see
**Privacy** below before deciding what should be public.

## The seven views

| View | What it is |
|---|---|
| **Mind map** | Radial / horizontal-tree / status / theme-cluster layouts. Root → 12 themes → 183 threads → every turn. Node ring = completeness, node size ∝ volume, click to inspect and fan out a thread's turns, scroll to zoom, drag to pan. |
| **Story (CYOA)** | Each thread becomes a chapter. You read the actual prompt → the actual output, then choose: *the path taken*, *roads not taken* (options the assistant offered that you never followed), *meanwhile* (parallel threads in the same theme), or *resume from here*, which builds the handoff packet. Keeps your place across sessions. |
| **Timeline** | Every turn in order, grouped by month/week/day, with the local timestamp, timezone and relative age. |
| **Ledger** | Sortable inventory: when, theme, thread, prompt, output volume, completeness, artifacts, links, media. CSV/JSON export of the current selection. |
| **Handoff** | Packet builder: one thread, one theme, the whole resume queue, or the entire archive. Markdown + JSON + resume prompt, zipped. Optional email/phone redaction and transcript caps. |
| **Sources & coverage** | What is inside the archive, the full Google-export inventory (Drive, Photos, NotebookLM, My Activity, Gmail, YouTube…), Drive artifacts with links, the published transcripts, and a list of the known gaps with instructions to close them. |
| **Import** | Drop a Takeout `.zip`, `MyActivity.html`, `MyActivity.json`, exported chat text, or a previous `atlas.json`. Parsed in the browser, merged into the live view, then re-downloadable. |

Keyboard: `1–7` switch views · `/` or `⌘K` search everything · `←/→` `j/k` move
through a thread · `E` export the open thread · `Backspace` back to the map.

## Where the data comes from

`tools/build_atlas.py` reads whatever it finds and writes `atlas/data/`:

| Source | Records | Notes |
|---|---|---|
| `MyActivity.html` (Google Takeout, Gemini Apps) | 3,054 | prompts **and** the model's replies, with local timestamps and attachments |
| `Geminiexportedchats80pagesoct1.pdf` | 80 pages | printed Gem sessions (Promethean / Paradox Engine work) |
| Saved Gemini pages (`.mht`, `.htm`) | 2 | keeps the real `gemini.google.com` conversation URL |
| Exported Google Docs | 1 | Paradox Engine framework text |
| Takeout `archive_browser.html` × 2 | 38 services | the coverage map of the whole Google export |
| Drive catalog | 31 items | verified files with live links |
| `cheyenne-2026-transcripts/meetings.json` | 85 meetings | public transcripts + video URLs |

Raw downloads live in `data/raw/` and `data/unpacked/` and are **git-ignored**
(seal them with `lock_atlas.py seal` if you want them versioned as ciphertext).
The build writes plaintext to `atlas/data/`, which `lock` then encrypts into
`atlas/enc/` and moves out of the repository — so what ships is ciphertext, and
what the app reads is whatever *it* decrypts into memory.

## How thread reconstruction works

1. **Sessions** — consecutive turns less than 90 minutes apart.
2. **Threads** — sessions merged into the nearest recent thread when their
   salient-vocabulary profiles (unigrams + bigrams + capitalised terms,
   stop-worded) are similar enough (`0.13` overlap) and no more than 14 days
   apart.
3. **Naming** — a curated domain lexicon first (`Iron Guard Man-Camp Fight`,
   `Forensic Dossier Build`, `Promethean / Paradox Engine`…), then proper nouns,
   then salient bigrams. Rename anything locally — it is stored in your browser.
4. **Themes** — weighted keyword scoring across twelve themes, with a
   sustained-topic bonus; primary + up to two secondary themes per turn.

## How completeness is scored

Every number is auditable — the UI lists the exact signals behind it. A turn
starts at 45 ("asked and answered") and moves on evidence:

* **+** delivered a table / code / numbered procedure / final-form artifact,
  cited statutes, carried hard figures, reported source work, very long answer
* **−** assistant asked whether to continue, offered options, declined, lacked
  access, thin answer, thread ends awaiting your direction
* **±** you confirmed the result next turn (+16) or rejected/re-aimed it (−14)
* thread score = 68 % weighted mean + 32 % final turn, plus an effort bonus for
  high-volume threads

Buckets: Seed · Exploring · Partial · Substantial · Near-complete · Complete.
Status: active · open · parked · blocked · dormant · complete.

## Agent handoff packets

`atlas/exports/` ships pre-built packets for the ten highest-value threads
(Markdown + JSON). Build more in the **Handoff** view or from the CLI:

```bash
python3 tools/handoff.py                       # rebuild from atlas/data
python3 tools/build_atlas.py                   # full pipeline: parse → analyse → export
```

A packet contains the thread state, the objective as you last stated it, where
it stopped, open threads, artifacts with links, source URLs, the completeness
evidence, the turn-by-turn record, and a paste-ready **resume prompt**.

## Privacy

This archive contains personal prompts, legal matters, addresses and names.

* The dataset is encrypted at rest and the plaintext is kept out of the repository.
* Handoff packets contain the same material in the clear *after you decrypt them* —
  and the export dialog has a one-click **redact emails / phones** toggle plus a
  per-turn character cap worth using before anything leaves your machine.
* Raw Takeout archives are git-ignored and never served; seal them if you want a
  commit-able copy (`lock_atlas.py seal`).
* The repository is private. If you ever publish it, publish only `atlas/enc/`
  plus the code — and remember that publishing plaintext history is forever.
