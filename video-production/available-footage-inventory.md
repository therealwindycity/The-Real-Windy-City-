# Available real footage inventory (recovered via GitHub, 2026-10-02)

These nine MP4s are the **only real meeting footage reachable from the production sandbox** (GitHub hosts are the only allowed egress besides PyPI). They were recovered byte-for-byte from `pipeline/videos/` at `therealwindycity/therealwindycity` main `b6e707a249912a0d076d4e28714bdbc913e6766d`, fetched through the GitHub git-blobs API, and hashed locally.

Local copies (not committed to Git, per the handoff's storage rule): `/home/user/source-masters/` with `SHA256SUMS.txt`.

| File | Source meeting | YouTube ID | Duration | Streams | SHA-256 |
|---|---|---|---|---|---|
| `mar9_cut.mp4` | 2026-03-09 City Council | `19tQtLA8klo` | 00:01:50.01 | 854x480 h264 29.97fps + aac 48kHz stereo | `74fcf531de0ae1b0a344272c63b5129108919bd11965d1c7c7f9ab4e791ffc56` |
| `mar9_return.mp4` | 2026-03-09 City Council | `19tQtLA8klo` | 00:02:00.05 | 854x480 h264 29.97fps + aac 48kHz stereo | `b3be0142629e1e3bec98fef56f0f7048980b75f2642c8afabca8a5d03351d225` |
| `apr27_first.mp4` | 2026-04-27 City Council | `y9vnXtjZpR0` | 00:01:55.01 | 854x480 h264 29.97fps + aac 48kHz stereo | `c0bd0e5b26b6baf2056bb4b302b3d1e40633d33f130399c366305d864f99a670` |
| `apr27_hand.mp4` | 2026-04-27 City Council | `y9vnXtjZpR0` | 00:02:35.02 | 854x480 h264 29.97fps + aac 48kHz stereo | `9d2f8d408494a152efeaad917a3f7aca198804e2e5d543c0ca9ce7429236430e` |
| `apr27_1301.mp4` | 2026-04-27 City Council | `y9vnXtjZpR0` | 00:01:20.05 | 854x480 h264 29.97fps + aac 48kHz stereo | `55936e6574ab9b1fa2632f625917fbbbc68afe3a2dd91ac615ba8f2f05e0f184` |
| `apr27_nine.mp4` | 2026-04-27 City Council | `y9vnXtjZpR0` | 00:01:50.01 | 854x480 h264 29.97fps + aac 48kHz stereo | `fd913ed5e1e2e3beabbd13b3eb52f0dc45ad572de8df5c8b5000a04807e545e7` |
| `apr27_pileon.mp4` | 2026-04-27 City Council | `y9vnXtjZpR0` | 00:02:35.02 | 854x480 h264 29.97fps + aac 48kHz stereo | `83e663286e83c9b7164205f0db6f3848d20764b1d8ca42e89e0cb9082d1c7e81` |
| `nemecek_quote.mp4` | 2026-01-14 Committee of the Whole | `tUTtHJp87Iw` | 00:02:00.00 | 640x360 h264 25fps + aac 48kHz stereo | `fe121d3c64e151b30367f91a6b00a6d1ece89116f1c735584443b109dd4a9462` |
| `moody_swap.mp4` | 2026-01-14 Committee of the Whole | `tUTtHJp87Iw` | 00:01:20.00 | 640x360 h264 25fps + aac 48kHz stereo | `b2b3276b6c446768d274c27b31a093b459a2332fbdb562c1ebe31f7b202ca8cc` |

## Provenance

- `mar9_*`, `apr27_*` were cut from the March 9 and April 27, 2026 City Council recordings (Granicus clips 1071 and 1093) by the prior project's `montage_caller_tape.py` fetch path (yt-dlp, height<=480).
- `nemecek_quote.mp4`, `moody_swap.mp4` were cut from the **Committee of the Whole, January 14, 2026** recording (YouTube `tUTtHJp87Iw`) by `montage_voices.py`.
- None of the nine clips was re-encoded or recut in this pass; they are reference copies only.

## What this footage can and cannot support

It covers **three** of the ~70 meetings the 17-video suite needs, in selected windows only:

- **Cannot** complete any of the 17 requested deliverables. Videos 1–2 need six specific later meetings (May 11, Jun 15, Jun 22, Jul 6, Aug 28, Sep 14) with exact Phase 1 cut-plan windows; none is present. Videos 3–17 need corpus-wide coverage. The prior project's own `THE_CALLER_TAPE.mp4` already covers the 'selected Mar 9 + Apr 27 Miller moments' scope, and the handoff forbids remaking legacy scope.
- **Can** support footage-verification of the Phase 2 candidate cues that fall inside these three meetings' available windows (e.g., a subset of the 167 April 27 and 16 March 9 Phase 2 cues), once a full-date master is available to establish in/out times. The clips themselves do not carry source-timestamp offsets against the official recording, so they cannot yet be cited as exact-time evidence.
- The two January 14 Committee of the Whole clips are **administration-voice material** (Public Works Director Nemecek; chair on Moody's amendment) and may be relevant to video 8 (administration disagreement) leads — but only as leads; the Phase 4 scan flags candidates corpus-wide and none is footage-verified.

