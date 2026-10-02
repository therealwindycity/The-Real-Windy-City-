# Pipeline self-test record — 2026-10-02

`render_video.py` was exercised end-to-end in the production sandbox using two of the nine
real legacy clips recovered via GitHub (`mar9_return.mp4`, `apr27_nine.mp4`). **This was a
toolchain test only — the output is not a deliverable and must not be published as one.**

## What was tested

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
