# Batch 1 production plan — videos 01 (Wolfe) and 02 (Laybourn)

**Status:** ready except for source masters. Everything below is prepared; the only missing
input is the six Tier-1 recordings (see [`../missing_source_urls.md`](../missing_source_urls.md)).

| | Video 01 | Video 02 |
|---|---|---|
| Output | `01_wolfe_positions.mp4` | `02_laybourn_positions.mp4` |
| EDL skeleton | [`edl/01_wolfe_positions.edl.json`](edl/01_wolfe_positions.edl.json) | [`edl/02_laybourn_positions.edl.json`](edl/02_laybourn_positions.edl.json) |
| Windows | W-01, W-02A, W-02B, W-03, W-04 | L-01, L-02, L-03, L-04 |
| Footage | 31.8 min across 4 meetings | 13.8 min across 4 meetings |
| Est. runtime incl. slates/cards | ≈ 32.5 min | ≈ 14.4 min |

## Prerequisites

1. Fetch the six masters (five meetings; July 6 supplies one file for two windows):
   ```
   ./fetch_source_recordings.sh --tier 1
   ```
   (Sept 28 is not needed for Batch 1.) Verify with `--verify`; hashes land in
   `source-masters/SHA256SUMS` and `retrieval_log.jsonl`.
2. Confirm each master's duration covers the latest window end (W-04 ends 02:14:37 on
   Sept 14 — check the recording actually runs that long; YouTube recordings of long
   meetings are sometimes truncated or split).

## Review procedure — per window (do this for all 9 windows)

For each `clips[]` entry in the EDL:

1. **Watch the window plus lead/lag** (≥2 minutes before, until the exchange fully closes).
2. **Confirm `required_text` is actually spoken** (against audio, not captions). Note any
   caption mis-hearing in `caption_corrections` — never silently rewrite.
3. **Confirm speaker identity** for `speaker_focus` — Lawrence J. Wolfe / Pete Laybourn
   official-name spellings may go into graphics only after this confirmation (candidate
   packet link is in the Phase 1 manifest `identity_source`).
4. **Check the editorial note** for the window (kept in `verification.editorial_note`):
   - W-01: include Miller's preceding statement, Emmons's response, Wolfe's complete
     response; the line concerns the state industrial-siting process for Swan Ranch.
   - W-02A/W-02B: Microsoft item — a *proposed* motion / negotiating posture, not an
     adopted agreement and not a ruling on the June 22 question.
   - W-03: show the lawyer's question, Wolfe's proposal, the later scope dispute, and the
     chair's ruling.
   - W-04: Wolfe's full statement, intervening council comments, roll call and result.
   - L-01: retain the late recognition, Miller's uncertainty/correction, and the response
     before Laybourn's comment.
   - L-02: keep the chair's response and Laybourn's full ensuing comment; verify the
     timer on footage before any lost-time claim.
   - L-03: Laybourn's work-session argument + the chair's contrary scope ruling.
   - L-04: roll call — auto-captions mis-spell names ("Mr. Leborn… Mr. Wolf"); verify
     against the recording and official minutes.
5. **Adjust `in`/`out`** if the true exchange starts/ends outside the planned window —
   the cut sheet is a plan, not proof; trim to complete turns.
6. **Fill the verification block** (`speaker_identity_confirmed`,
   `complete_turns_preserved`, `context_lead_lag_reviewed`, `reviewer`, `review_date`)
   and set `"status": "verified"`.

## Render

```
python3 production/render_video.py \
  --edl production/edl/01_wolfe_positions.edl.json \
  --masters source-masters \
  --out renders/batch01
```

The renderer refuses any clip not marked `verified` (that refusal was tested — see
[`SELFTEST.md`](SELFTEST.md)). It produces the MP4, SRT/VTT, rendered EDL, provenance
README skeleton, and `_QA.json`; a named reviewer must complete the human-review fields
before the output is called final.

## Delivery checklist (per video, per the handoff)

- [ ] Standalone H.264/AAC MP4, no upscaling, clear audio
- [ ] SRT and/or VTT sidecar; caption corrections logged separately
- [ ] EDL export: source URL, source hash, in/out, clip order, trims/fades/overlays, corrections, cards
- [ ] Provenance README: recordings reviewed, retrieval date, review date, gaps, whether every quote/identity was verified
- [ ] QA record: opens, full start/end plays, no black/frozen/audio gaps at cuts, caption timing, spellings, citations, no omitted response changing meaning; SHA-256 recorded
- [ ] Commit sidecars to Git; keep MP4 masters/renders out of Git unless requested

## After Batch 1

Proceed in small batches (handoff: one or two videos at a time): Batch 2 = video 03
(in-person requests; 11 direct candidates in [`workbooks/03_in_person_requests.md`](workbooks/03_in_person_requests.md),
all in Tier-2 meetings) + video 11. Batch 3 = 12/16 (needs the full legacy-index meeting
set). Comparator videos (04–06, 14, 15) only after their denominator/rule review.
