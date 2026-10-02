# Pipeline self-test record — 2026-10-02

`render_video.py` and `extract_review_windows.py` were exercised end-to-end in the
production sandbox using two of the nine real legacy clips recovered via GitHub
(`mar9_return.mp4`, `apr27_nine.mp4`). **These were toolchain tests only — their outputs
are not deliverables and must not be published as one.**

## Renderer self-test (`render_video.py`)

| Check | Result |
|---|---|
| Refusal gate: EDL clips not marked `verified` | ✅ REFUSED with instruction (exit 1) |
| Render with `--allow-unverified` (self-test mode) | ✅ completed |
| Slate rendering (Pillow → H.264 segment) | ✅ first-frame extract non-black, std-dev 38.5 |
| Footage trim + canvas normalize (no upscaling) | ✅ 854x480 canvas, output 854x480 |
| Concat of mixed segments (slates, footage, context card) | ✅ |
| Output duration vs expected (72.0 s) | ✅ 72.08 s |
| Audio stream present and continuous | ✅ AAC 48 kHz stereo |
| SRT + VTT sidecar generation | ✅ 4 caption blocks, correct timeline |
| Rendered EDL export with per-source SHA-256 | ✅ |
| Provenance README skeleton | ✅ (TBD fields left for the reviewer) |
| QA JSON with automated checks + human-review gates | ✅ |
| First/last frame extraction | ✅ both non-black (last-frame std-dev 70.9) |

## Self-test output (not committed to Git — workspace only)

- `/home/user/selftest-output/SELFTEST_pipeline_check.mp4` — SHA-256
  `78a9844c46bcc6c6cc1dd12fb1096d0d1231f7d50fe987fee50f263f9aa584b6`, 3,153,359 bytes, 72.08 s
- Sidecars: `.srt`, `.vtt`, `.edl.json`, `_PROVENANCE.md`, `_QA.json`, `qa_frames/`

Environment: ffmpeg 7.0.2 (imageio-ffmpeg build; no ffprobe present — the script's
ffmpeg-banner fallback prober was used and validated against known clip parameters),
Pillow 12.3.0, Python 3.11.

## Known limitations carried into production

- ffprobe is preferred when available; the ffmpeg-banner fallback rounds fps (29.97 read
  back as 29.93 in the QA record) — cosmetic in the QA text, not in the render.
- Concat requires uniform segment parameters, which the builder guarantees by re-encoding
  every segment to the project canvas/fps.
- The self-test clips have no source-offset metadata, so its slates say "offset within
  official recording unknown" — real deliverables get exact source in/out slates from the
  verified EDL.

## Review-kit self-test (`extract_review_windows.py`)

Tested on `mar9_return.mp4` with a synthetic pending window (planned 00:00:30–00:01:00,
lead 15 s / lag 10 s):

| Check | Result |
|---|---|
| Review cut with lead/lag (55 s) | ✅ 1.6 MB, re-encoded frame-accurate |
| MASTER-clock burn-in (libass track, per-second) | ✅ verified pixel-differentially: same master frame with/without overlay differs strongly in the clock band (mean 11.9) and is unchanged elsewhere (mean 1.7) — `drawtext` is absent from the minimal ffmpeg builds, so the clock is burned via a generated `.ass` track |
| Draft caption extraction from transcript | ✅ 2 cues in-window, correct relative times (master 00:00:49 → review 00:00:34) |
| Transcript parser robustness | ✅ handles both blank-line-separated and single-line transcript formats (cues delimited by their own `[HH:MM:SS]` markers; the March 9 file has no blank lines and initially produced a 284 KB mega-cue — fixed and re-tested) |
| Pre-filled verification form | ✅ required text, editorial note, master/window facts, reviewer fields |
| Kit INDEX.md | ✅ |

Self-test outputs (not committed): `/tmp/reviewkit-test/kit/`.
