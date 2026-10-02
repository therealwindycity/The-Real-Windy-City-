# Production package — everything staged for the 17-video suite

Built 2026-10-02 while source footage is blocked (see
[`../phase-06-recording-status.md`](../phase-06-recording-status.md)). Nothing here is
footage-verified yet; the point of this package is that production can start the hour
masters arrive, with the evidentiary rules enforced by tooling rather than memory.

## Layout

```
production/
├── render_video.py            # evidence-video renderer (slates, SRT/VTT, EDL export,
│                              #   provenance README, QA record, verification gate)
├── generate_edl_batch01.py    # builds the Batch-1 EDL skeletons from the Phase 1 manifest
├── generate_workbooks.py      # builds the per-video review workbooks from the phase scans
├── BATCH_01_PLAN.md           # production plan for videos 01–02 (ready except masters)
├── SELFTEST.md                # renderer self-test record (toolchain test, NOT a deliverable)
├── edl/
│   ├── 01_wolfe_positions.edl.json     # 5 windows (W-01…W-04), 4 masters, ~32.5 min
│   └── 02_laybourn_positions.edl.json  # 4 windows (L-01…L-04), 4 masters, ~14.4 min
├── workbooks/                 # videos 03–17: prioritized caption-cue review queues,
│                              #   verification checklists, comparison discipline
└── reference/                 # byte-for-byte copies (with hashes) of the Phase 1 cut
                               #   manifest and the legacy 616-row Miller index
```

## Order of work once masters arrive

1. **Batch 1 (videos 01, 02):** follow [`BATCH_01_PLAN.md`](BATCH_01_PLAN.md) — review the
   nine Phase 1 windows on the six Tier-1 masters, mark each EDL clip `verified`, render,
   complete the human QA gates.
2. **Batch 2 (videos 03, 11):** review the 11 direct in-person-request candidates and the
   staff-recognition/greeting candidates (Tier-2 masters).
3. **Batch 3 (videos 12, 16):** the interruption/time-credit reels over the legacy-index
   meeting set — the heaviest review load; timer claims need the visible timer on footage.
4. **Comparator videos (04–06, 14, 15):** only after the written-rule/denominator review
   each workbook specifies; otherwise deliver clearly-labeled "not established" videos.
5. **Video 10:** document-based; needs the Sept 28 recording and certified minutes plus
   counsel review before any legal overlay.

## Guardrails encoded in the tooling

- `render_video.py` **refuses to render any clip not marked `verified`** in the EDL
  (`--allow-unverified` exists for self-tests and prints warnings in the outputs).
- Every clip gets an on-screen provenance slate: date, body, agenda item, source URL,
  source in/out.
- No upscaling, ever: the canvas equals the largest source frame; smaller sources are
  padded, larger ones scaled down.
- QA records separate automated checks from human-review fields; nothing can be labeled
  final/complete/verified until a named reviewer signs the human fields.
