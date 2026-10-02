# Phase 6 — source-access verification & unblock package

**Status (2026-10-02): the 17-video suite remains blocked on source-recording access. This package documents the blocker with evidence and provides everything needed to resume immediately.**

This is the continuation of the video-evidence project started on branch `arena/01a0fdbc-therealwindycity` of `therealwindycity/therealwindycity` (see that branch's `video-production/NEW_VIDEO_AGENT_HANDOFF.md` for the task brief and the 17-video scope). The current session cannot write to that repo, so its Phase 6 continuation lives here, next to the `cheyenne-2026-transcripts` corpus the project cites.

## What happened this pass

1. **Handoff and project state were read in full** (README, all five phase packages, the Phase 1 cut manifest, and the legacy Miller index).
2. **Tooling was bootstrapped**: `ffmpeg 7.0.2` + `yt-dlp 2026.08.19` installed and verified working in-sandbox.
3. **Every plausible source route was tested and failed at the network boundary** — YouTube (watch pages, CDN hosts), Granicus (player and direct MP4 hosts), City/State sites, and legal-reference hosts all close TLS before any media byte. Only GitHub and PyPI egress is allowed. Full log: [`connectivity_test_2026-10-02.log`](connectivity_test_2026-10-02.log).
4. **Per the handoff's explicit instruction** (no footage → stop and report the exact missing URLs; no fabricated clips; no transcript-card videos without approval), the pass produced this report instead of videos.

## Package contents

| File | What it is |
|---|---|
| [`phase-06-recording-status.md`](phase-06-recording-status.md) | Full status report: verification results, what was recovered, per-video blockers, unblock options. |
| [`source_acquisition_manifest.json`](source_acquisition_manifest.json) | All 85 catalog meetings + Sept 28 Granicus: official URLs, priority tiers, needed-for-video mapping, cue counts, 17 direct MP4 links. |
| [`missing_source_urls.md`](missing_source_urls.md) | The exact missing URLs, human-readable, tiered. |
| [`fetch_source_recordings.sh`](fetch_source_recordings.sh) | One-command public-source fetch kit (checksums, retrieval log, caption-track capture). |
| [`available-footage-inventory.md`](available-footage-inventory.md) | The only real footage reachable from this sandbox (9 legacy clips, hashed + probed) and its honest scope limits. |
| [`connectivity_test_2026-10-02.log`](connectivity_test_2026-10-02.log) | Raw connectivity evidence. |

## Fastest path to the 17 videos

```
# on any machine with egress:
./fetch_source_recordings.sh --tier 1        # 7 recordings ≈ videos 1, 2, and 10's core
./fetch_source_recordings.sh --verify

# hand source-masters/ back via a GitHub-served channel (see phase-06-recording-status.md § unblock)
```

Then production resumes in small batches (Tier 1 first: the nine exact Phase 1 cut-plan windows), with full evidentiary discipline per the handoff: verified speakers/quotes against the recording, complete turns and roll calls preserved, SRT/VTT sidecars, edit-decision lists, provenance READMEs, and per-file QA records with SHA-256 hashes.

## Standing editorial rules (carried from the handoff, unchanged)

- Official-name spellings **Lawrence J. Wolfe** / **Pete Laybourn** only after identity confirmation from the recording or reliable contemporaneous records.
- Never conflate the June 22 Swan Ranch item, July 6 Microsoft item, August 28 work session, and September Cox Ranch readings.
- Caption proximity is a review lead, never proof of identity, motive, response, or timer credit.
- No "final/complete/verified" labels until the QA checks are actually done; no legality conclusions without counsel review.
