# Phase 6 — source access and recording status (2026-10-02, successor-session update)

**This file supersedes the `phase-06-recording-status.md` on branch `arena/01a0fdbc-therealwindycity` of `therealwindycity/therealwindycity`.** That branch's video-production workspace is read-only for the current session token, so this continuation package lives on branch `arena/01a0fe75-the-real-windy-city` of `therealwindycity/The-Real-Windy-City-` (the same repo that hosts the `cheyenne-2026-transcripts` corpus the project references).

**Bottom line: no new source recordings could be acquired, and no new videos were rendered.** The handoff's gating first step ("acquire and verify public recordings") is blocked by network policy in this environment, exactly as in the prior environment. Per the handoff instruction — *"If video-host access is unavailable, stop and report the exact missing URLs rather than fabricating clips"* — this package is that report, plus everything needed to resume the moment source access exists.

## What this pass verified and produced

| Deliverable in this package | Purpose |
|---|---|
| [`connectivity_test_2026-10-02.log`](connectivity_test_2026-10-02.log) | Raw evidence: host-by-host reachability matrix and failed yt-dlp/Granicus attempts, timestamped. |
| [`source_acquisition_manifest.json`](source_acquisition_manifest.json) | Machine-readable manifest of all 85 catalog meetings + the September 28 Granicus recording: official URLs, tier priority, which of the 17 videos need each, candidate-cue counts, and 17 recovered direct-MP4 links. |
| [`missing_source_urls.md`](missing_source_urls.md) | Human-readable exact missing-URL list, tiered (7 Tier-1 / 27 Tier-2 / 48 Tier-3 / 4 none-needed), plus seven uncataloged 2026 special City Council sessions discovered on Granicus but absent from the transcript corpus. |
| [`fetch_source_recordings.sh`](fetch_source_recordings.sh) | One-command fetch kit (yt-dlp/curl, public access only, checksums + retrieval log) to run on any machine with egress. |
| [`available-footage-inventory.md`](available-footage-inventory.md) | The only real footage reachable from this sandbox: nine legacy source clips recovered via the GitHub API, hashed, probed, with provenance and honest scope limits. |

Tooling was also bootstrapped and verified in the sandbox: `ffmpeg 7.0.2` (via `imageio-ffmpeg`) and `yt-dlp 2026.08.19` (via PyPI). Render-side readiness is therefore not the blocker; source bytes are.

## Access verification results (2026-10-02)

- Every YouTube/Google host (`www.youtube.com`, `googlevideo.com` CDNs, `i.ytimg.com`), every Granicus host (`cheyenne.granicus.com`, `archive-video.granicus.com`), and every City/State/legal host (`cheyennecity.org`, `cityofcheyenne.gov`, `wyoleg.gov`, `deq.wyoming.gov`, `law.justia.com`, `archive.org`) **closes TLS immediately** (curl exit 35 / TLS EOF in ≤0.2 s). The failure is at the network boundary, before any HTTP exchange; it is not an authentication, cookie, or player issue.
- yt-dlp against the official June 22 City Council source (`https://www.youtube.com/watch?v=RjSGlhh4q9s`) fails identically after retries: `TLS/SSL connection has been closed (EOF)`.
- Allowed egress is limited to `github.com`, `api.github.com`, `codeload.github.com`, `pypi.org`, `files.pythonhosted.org`. **No video host is reachable through any route tested**, including plain HTTP, alternate Google endpoints, and direct Granicus MP4 URLs recovered from the legacy pipeline index.
- No cookies or credentials were used or are needed; these are public recordings. Per the prior status note, any previously attached browser-cookie file must not be relied upon.

## What was recovered instead (GitHub-routed assets)

- Nine real source clips (≈13½ minutes, 480p/360p) covering only **March 9, 2026** and **April 27, 2026** City Council windows plus two **January 14, 2026 Committee of the Whole** topic clips — see [`available-footage-inventory.md`](available-footage-inventory.md). These cannot complete any of the 17 requested videos and largely duplicate the legacy `THE_CALLER_TAPE` scope, which the handoff forbids remaking.
- Direct Granicus MP4 URLs for 15 catalog dates (from the legacy `pipeline/meetings.json` index, generated before 2026-08-24) — recorded in the manifest for use on an egress-enabled machine. An earlier draft attached 17; two were wrong-meeting attachments (March 16 PSC and March 17 Finance rows pointing at special-session City Council recordings) and were corrected after an audit. The audit also surfaced **seven 2026 special City Council sessions that exist on Granicus but are absent from the transcript corpus entirely** (Jan 23, Feb 23 special, Mar 5, Mar 12, Mar 16, Mar 17, Mar 23) — these carry no transcripts and no Phase 2–4 scan coverage, so any exhaustive-scope claim in videos 12/13 must either review them or state the limitation.
- The nine pre-existing render MP4s remain available unchanged in `existing-video-delivery.zip` on the source branch; they are not the new suite and were not modified.

## Status of the 17 requested videos

All 17 remain **blocked on source-recording access**. None has been rendered, and none can be honestly rendered from the available material:

| Videos | Blocking footage |
|---|---|
| 1 (Wolfe), 2 (Laybourn) | Six specific meeting masters: 2026-05-11 CC, 2026-06-15 PSC, 2026-06-22 CC, 2026-07-06 PSC, 2026-08-28 WS, 2026-09-14 CC (Phase 1 cut-plan windows). |
| 3, 11–13, 15–17 (Miller reels) | The 20 legacy-index meeting recordings + Phase 2 candidate coverage (30 meetings). |
| 4–9, 14 (comparator/rule audits) | Phase 3/4 candidate coverage (68 / 29 meetings) plus written rules; corpus-wide footage review required before any comparison. |
| 10 (Cox Ranch legal overview) | 2026-09-28 Granicus recording (unreviewed) + final-action documents still outstanding; counsel review required before any legal conclusion. |

No transcript-card substitute videos were produced: the handoff reserves that format for explicit user approval.

## How to unblock (any one suffices)

1. **Run the fetch kit elsewhere and hand the masters back.** On any machine with normal egress: `./fetch_source_recordings.sh --tier 1` (then tiers 2–3 as work proceeds). Hand `source-masters/` back through a GitHub-reachable channel — e.g. commit the recordings (split into <95 MB parts if needed: `zip -s 90m`) to a branch of `therealwindycity/The-Real-Windy-City-` or another repo this session can read; the production sandbox can pull anything served by `github.com`/`codeload.github.com`/`api.github.com`. Note: GitHub *Release assets* and *Actions artifact downloads* are **not** reachable here (they redirect to `objects.githubusercontent.com`, which is blocked).
2. **Re-run the production session in an environment with egress** to the YouTube/Granicus hosts.
3. **User-approved alternative format** (e.g. clearly-labeled transcript-research videos) — requires explicit approval per the handoff; not recommended for an evidence project.

Once masters are in hand, production proceeds in small batches per the handoff: Tier-1 first (videos 1 and 2 from the nine exact Phase 1 windows), each cut verified against the recording (speaker, item, complete turns, roll call), with SRT/VTT sidecars, edit-decision lists, provenance READMEs, and QA records per file.

## Preparation completed while blocked (2026-10-02, same session)

So that production can start the hour masters arrive, this session also staged a complete production package in [`production/`](production/):

- **`production/render_video.py`** — an evidence-video renderer with the handoff's rules encoded: it *refuses* to render EDL clips not marked `verified` by a human reviewer, burns a provenance slate (date, body, item, source URL, source in/out) before every clip, never upscales, and emits the SRT/VTT sidecar, EDL export, provenance README, and a QA record whose human-review fields must be signed before any "final/verified" label. Self-tested end-to-end in-sandbox on two real recovered clips (see `production/SELFTEST.md` — toolchain test only, not a deliverable).
- **`production/edl/01_wolfe_positions.edl.json` and `02_laybourn_positions.edl.json`** — Batch-1 EDL skeletons built from the Phase 1 cut manifest: all nine windows with source in/out, required text, editorial notes, and anti-conflation context cards between unlike items (≈32.5 min and ≈14.4 min estimated runtimes).
- **`production/workbooks/03…17_*.md`** — fifteen per-video review workbooks distilling the Phase 2–4 candidate scans into prioritized, timestamped, link-backed review queues with verification checklists, denominator/rule requirements for the comparator videos, and "not established" criteria.
- **`production/extract_review_windows.py`** — builds the human footage-review kit: for each pending EDL window it cuts a review MP4 (window + lead/lag) with the **master clock burned into the picture**, pulls DRAFT captions from the caption-derived transcript, and emits a pre-filled verification form. Self-tested in-sandbox, including pixel-differential verification of the clock burn-in (see `production/SELFTEST.md`).
- **Standing limitation:** the agent session that staged this package has no video/audio perception — footage verification (words, speaker, identity, timer) is a human or vision-capable-agent step. The kit above is built so that step takes minutes per window and its answers transfer directly into the EDL.
- **`production/reference/`** — hashed, byte-for-byte copies of the Phase 1 clip manifest and the legacy 616-row Miller index, so production does not depend on cross-repo checkout.
