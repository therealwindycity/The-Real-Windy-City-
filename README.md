# Cheyenne 2026 Meeting Transcripts

Verbatim, timestamped transcripts of every 2026 public meeting of the Cheyenne (Wyoming) City Council, committees, and boards — one Markdown file per meeting, each linked to the city's official video. See [cheyenne-2026-transcripts/](cheyenne-2026-transcripts/) ([catalog](cheyenne-2026-transcripts/meetings.json)).

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
