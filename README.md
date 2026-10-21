# Cheyenne 2026 Meeting Transcript Archive

A searchable catalog of 2026 Cheyenne (Wyoming) public-meeting caption transcripts, each linked to its source video where available. Captions may be human-uploaded or auto-generated; they are not official minutes and can mis-transcribe names, technical terms, and quotations. Verify important passages against the original recording. Catalog coverage is not a claim that every meeting or record is included. See [cheyenne-2026-transcripts/](cheyenne-2026-transcripts/) ([catalog](cheyenne-2026-transcripts/meetings.json)).

The [public archive homepage](https://therealwindycity.github.io/The-Real-Windy-City-/) now shows record-based freshness, a qualified October 19, 2026 Planning Commission outcome reconstruction, coverage definitions, known gaps, and a corrections page. The checked-in catalog currently has no recorded collection-check timestamp; deployment time is not used as a substitute.

Transcript text is dedicated to the public domain (CC0). Video remains © City of Cheyenne / YouTube.

## Paradox Atlas — the interactive layer over this work

[`atlas/`](atlas/) is a self-contained, dependency-free web app that turns a personal AI history
(Gemini activity exports, saved chats, printed chat PDFs, Drive artifacts, this repo's transcripts)
into an interactive **mind map** and a **choose-your-own-adventure** reader:

- every prompt and output, with the local timestamp, timezone and relative age
- what each turn **produced** — artifacts, files, links, generated media
- **completeness levels** with the exact evidence behind each score, so you can see
  where a project stalled and why
- **themes** (12, derived from the actual content) plus a coverage map of the full Google export
- **handoff packets** (Markdown + JSON + a paste-ready resume prompt, zipped) so any capable
  agent can pick a thread up exactly where it left off

**Live:** <https://therealwindycity.github.io/The-Real-Windy-City-/atlas/> — the published copy is
the encrypted build, so it asks for the Atlas passphrase before it shows anything.

```bash
python3 -m http.server 8000      # then open http://localhost:8000/atlas/
python3 tools/serve_locked.py --port 8000     # same app, behind an HTTP password
python3 tools/build_atlas.py     # rebuild the dataset from data/raw + the Drive catalog
```

The dataset ships **encrypted**: `atlas/enc/` is AES-256-GCM ciphertext and the
passphrase is never stored anywhere — the browser derives the key and decrypts in
memory. `python3 tools/lock_atlas.py lock` re-locks after a rebuild;
`python3 tools/serve_locked.py` adds an HTTP password in front of everything.

See [atlas/README.md](atlas/README.md) for the data model, the scoring rules and the privacy notes.
Raw archives (hundreds of MB) are git-ignored; the derived dataset in `atlas/data/` ships with the app.

## Audit pipeline: structured indexing of the transcripts

[`audit/`](audit/) holds a deterministic ingest node and a Streamlit review dashboard. Together
they break every transcript into timestamped passages and tag each one with entities (agencies,
officials, `W.S.` citations, ordinance numbers), procedural markers, a rhetorical profile and the
matching procedural remedies. It can also ingest CSV/JSONL files, Socrata datasets and ArcGIS layers.

```bash
pip install -r audit/requirements.txt
python3 audit/audit_ingest_node.py --mode rebuild transcripts
streamlit run audit/app.py
```

Scores are keyword counts that rank passages for human review. They are not findings. See
[audit/README.md](audit/README.md).

## Other archives in this series
- [Meeting archives, 2008–2013](https://github.com/therealwindycity/cheyenne-archives-2008-2013) — agendas, agenda packets, supporting documents, minutes.
- [Meeting archives, 2014–2017](https://github.com/therealwindycity/cheyenne-archives-2014-2017) — agendas, agenda packets, supporting documents, minutes.
- [Meeting archives, 2018–2021](https://github.com/therealwindycity/cheyenne-archives-2018-2021) — agendas, agenda packets, supporting documents, minutes.
- [Meeting archives, 2022](https://github.com/therealwindycity/cheyenne-archives-2022) — agendas, agenda packets, supporting documents, minutes.
- [Meeting archives, 2023–2024](https://github.com/therealwindycity/cheyenne-archives-2023-2024) — agendas, agenda packets, supporting documents, minutes.
- [Meeting archives, 2025–2026](https://github.com/therealwindycity/cheyenne-archives-2025-2026) — agendas, agenda packets, supporting documents, minutes.

## Classic city view

[`city/`](city/) provides an independent municipal-style directory, searchable
meeting catalog and plain-text transcript reader. It reads the existing
`cheyenne-2026-transcripts/meetings.json` without duplicating the archive.
No build dependencies or third-party scripts are required. Preview with
`python3 -m http.server 8000 --bind 0.0.0.0` and visit `/city/`.

The existing Pages workflow includes this directory when deployed; the expected
URL is https://therealwindycity.github.io/The-Real-Windy-City-/city/ . Changes on
other branches require merging to a publishing branch before they appear there.
This does not deploy to the separate `/therealwindycity/` site or Streamlit app.
The read-only city mirror and scheduled synchronization service are documented
in [city/SYNC.md](city/SYNC.md). Official transactions remain on the official city website.
