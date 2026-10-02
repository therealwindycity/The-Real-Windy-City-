# Reference copies — provenance

These files are byte-for-byte copies from branch `arena/01a0fdbc-therealwindycity` of
`therealwindycity/therealwindycity` (and its `main` ref), fetched read-only via the GitHub API
on 2026-10-02 so the production step in this repo does not depend on cross-repo checkout.

| File | Source | SHA-256 at copy |
|---|---|---|
| `phase-01_clip_manifest.json` | `video-production/phase-01-position-timelines/clip_manifest.json` @ `arena/01a0fdbc-therealwindycity` | (see below) |
| `miller_interventions.json` | `pipeline/miller_interventions.json` @ `main` (`b6e707a249912a0d076d4e28714bdbc913e6766d`) | (see below) |

`miller_interventions.json` is the legacy 616-row caption-aligned Miller index (20 meetings,
Jan 12 – Jul 27, 2026; flags include 219 `interrupted`, 38 `mic_cut`, 90 `point_of_order`,
119 `time_called`). Per the project README it is a caption-alignment lead set, **not** a
manually adjudicated count, and it ends July 27, 2026.

`phase-01_clip_manifest.json` is the Phase 1 cut plan (9 windows for the Wolfe/Laybourn
timelines). Status: candidate-cut-sheet-not-rendered; every window still requires footage
verification before rendering.
- `reference/phase-01_clip_manifest.json`: `66e691c416c6a3d772b5ecc7e03afee9baad06a83555d12f6733790547d76379`
- `reference/miller_interventions.json`: `3ed94f5fbbbb85cd76c1d07ef7a607fe832cef374a291357d8b82998d68b4b3e`
