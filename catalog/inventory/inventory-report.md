# T02 Complete Public Civic Corpus Inventory Report

- **Task / Owner**: `T02` — Agent `f4f97b19` on isolated branch `agent/f4f97b19/T02`
- **Integration Baseline**: `arena/civic-build-center-2026-10-21` (`491612784a0f8ec626802209dd0c3f23759ee083`)
- **Generated At**: `2026-10-21T20:15:00Z`
- **Schema Alignment**: `corpus_schema_version = 1` (`T00` `validateCorpusRecord` strict superset)
- **Public-Repo Privacy Gate**: Enforced (`0` redline leaks across all generated artifacts)

---

## 1. Executive Totals & Provenance Separation

| Metric | Value | Notes |
| --- | ---: | --- |
| Canonical GitHub Repositories | **8** (+1 non-canonical org repo audited) | Every tree verified `truncated = false` |
| Canonical GitHub Default-Branch Blobs | **6,037** | `7,217,007,268` bytes across `1,405` trees |
| Integration Branch Delta Blobs (`491612784a0f`) | **9** | Added on `arena/civic-build-center-2026-10-21` |
| Locally Verified GitHub SHA-256 Records | **367** | Remote-only blobs keep `original_bytes_sha256: null` + `git_blob_sha1` separate |
| Total Emitted GitHub Records | **6,046** | Stored in `catalog/inventory/github-inventory.json` |
| Live Google Drive v3 Public Civic Items | **178** | Paginated to `nextPageToken: null`, `incompleteSearch: false` |
| Native Drive SHA-256 Verified Items | **51** | Distinct `original_bytes_sha256` and `drive_md5_checksum` |
| Structured Meeting Transcripts (`master_meetings_database.json`) | **720** | Per-entry canonical `extracted_text_sha256` + 3-way date conflict audit |
| Official Granicus Supporting Attachments (`metadata_database.json`) | **2,304** | Marked `agenda_supporting_attachment_not_final_adoption` |
| Retained Pre-2026-07-09 Snapshot Public Items | **1,208** | Deduplicated against live IDs (`8` live overlaps) |
| Total Emitted Public Drive Records | **4,410** | Stored in `catalog/inventory/drive-inventory.json` |
| **Grand Total Canonical Public Records** | **10,456** | **100% validated against `T00` schema invariants** |
| Date-Conflicted Drive Records (`event_date = null`) | **532** | Clerk title vs spoken call-to-order + YouTube upload prefix divergences |
| Total Duplicate Groups (`GitHub + Drive`) | **1,363** | `924` GitHub SHA-1 groups (`8` cross-repo) + `439` Drive groups |
| Privacy-Excluded Drive Items (Aggregate Counts Only) | **40,662** | Strictly blocked from public repository serialization |

---

## 2. GitHub Organization Complete Enumeration (`therealwindycity`)

| Repository | Scope | Default Branch | Pinned Commit SHA | Blobs | Trees | Total Bytes | Complete |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| `therealwindycity/TheReelWindyCity` | Yes (Canonical 8) | `main` | `6ec2509c0771` | 349 | 185 | 131,047,374 | `true` |
| `therealwindycity/The-Real-Windy-City-` | Yes (Canonical 8) | `main` | `3efc02e0d80c` | 548 | 35 | 115,809,190 | `true` |
| `therealwindycity/cheyenne-archives-2008-2013` | Yes (Canonical 8) | `main` | `e196265f60e6` | 1,006 | 283 | 859,817,686 | `true` |
| `therealwindycity/cheyenne-archives-2014-2017` | Yes (Canonical 8) | `main` | `e23950b20292` | 548 | 201 | 1,310,749,439 | `true` |
| `therealwindycity/cheyenne-archives-2018-2021` | Yes (Canonical 8) | `main` | `448e04248ea0` | 837 | 202 | 1,118,613,095 | `true` |
| `therealwindycity/cheyenne-archives-2022` | Yes (Canonical 8) | `main` | `e9ded74d71fd` | 637 | 58 | 1,274,738,607 | `true` |
| `therealwindycity/cheyenne-archives-2023-2024` | Yes (Canonical 8) | `main` | `6ccc8667d38e` | 1,383 | 241 | 1,570,132,755 | `true` |
| `therealwindycity/cheyenne-archives-2025-2026` | Yes (Canonical 8) | `main` | `266b7a49650d` | 729 | 200 | 836,099,122 | `true` |
| `therealwindycity/therealwindycity` | No (9th Org Repo) | `main` | `606128f6c428` | 2,699 | 48 | 549,763,844 | `true` |

### Integration & Live `main` Branch Tracking (`therealwindycity/TheReelWindyCity`)
- **Handoff Pinned `main`**: `6ec2509c07716a9b61eb00863a5f5f5841d0f13d` (`348` blobs)
- **Live `main` at Enumeration**: `e5479fac497ddc38a06fa1410ddd9de1f73ecd88` (`349` blobs, `truncated: false`)
- **Active Integration Target Branch (`arena/civic-build-center-2026-10-21`)**: `491612784a0f8ec626802209dd0c3f23759ee083` (`357` blobs, `truncated: false`)

---

## 3. Google Drive Privacy Exclusions (Zero-Leakage Aggregate Audit)

Because `therealwindycity/TheReelWindyCity` is publicly readable on GitHub, `scripts/inventory/privacy-gate.mjs` enforces default-deny classification across both active Google Drive holdings and the `41,861`-row pre-`2026-07-09` historical snapshot, scanning every serialized byte via `assertZeroPrivacyLeaks()` prior to disk write:

| Exclusion Category | Excluded Item Count | Serialization Policy |
| --- | ---: | --- |
| `default-deny-unverified-drive-item` | 35,827 | Excluded (zero filenames/IDs emitted) |
| `venv-or-package-runtime-noise` | 3,793 | Excluded (zero filenames/IDs emitted) |
| `browser-or-archive-export` | 762 | Excluded (zero filenames/IDs emitted) |
| `non-civic-or-unverified-youtube-download` | 220 | Excluded (zero filenames/IDs emitted) |
| `private-litigation-or-identity` | 38 | Excluded (zero filenames/IDs emitted) |
| `active-drive-private-personal-or-litigation-items` | 17 | Excluded (zero filenames/IDs emitted) |
| `minor-or-student-privacy` | 4 | Excluded (zero filenames/IDs emitted) |
| `email-address` | 1 | Excluded (zero filenames/IDs emitted) |

---

## 4. Forensic Anomalies & Downstream Remediation Guidance

| ID | Severity | Source | Category | Finding Summary |
| --- | --- | --- | --- | --- |
| `GH-ANOM-001` | **MEDIUM** | `github` | `branch-head-drift` | Handoff baseline main (6ec2509c0771) advanced on live main (e5479fac497d, 349 blobs) while active integration branch arena/civic-build-center-2026-10-21 stands at 491612784a0f (357 blobs). |
| `GH-ANOM-002` | **LOW** | `github` | `non-canonical-org-repository` | Organization contains 9th public repository therealwindycity/therealwindycity (2699 blobs, 549763844 bytes at 606128f6c428) outside the canonical 8-repo list. |
| `GH-ANOM-003` | **HIGH** | `github-actions` | `integration-branch-ci-lint-failure` | Integration baseline fails `npm run lint` with 5 `react/no-unescaped-entities` errors (`src/app/explore/public-safety/page.tsx:7:253`, `src/app/page.tsx:6:651,7:164,7:306`, `src/components/site-help.tsx:44:451`). Non-transcript node test suites pass. |
| `DRV-ANOM-001` | **HIGH** | `google-drive` | `clerk-title-vs-spoken-call-to-order-date-mismatch` | Cross-checking metadata.date, meeting title, and opening call-to-order speech across all 720 City of Cheyenne transcripts revealed 0 date conflicts — e.g., meet_0000 titled "Finance Committee 01-07-25" (Tuesday 2025-01-07) opens with Chair calling to order the "January 6th 25 finance committee meeting" (Monday 2025-01-06), and meet_0020 titled "Finance Committee 12-02-25" opens with "December 1st 2025 finance meeting will come to order". |
| `DRV-ANOM-002` | **MEDIUM** | `google-drive` | `unparsed-spelled-out-dates-in-master-meetings-db` | Upstream master_meetings_database.json left metadata.date="Unknown" on 227 meetings whose titles spell out months (e.g., meet_0016 "January 5, 2026, Cheyenne Planning Commission Meeting") instead of numeric MM-DD-YY. |
| `DRV-ANOM-003` | **HIGH** | `google-drive` | `youtube-upload-prefix-vs-meeting-date-divergence` | City of Cheyenne YouTube filenames prefixed `YYYYMMDD - ...` store `yt-dlp %(upload_date)s` (upload date to YouTube, typically 1–10 days after the actual meeting, e.g., `20210318 - Cheyenne City Council | Regular Meeting | 3-8-21.en.vtt` and `20260210 - City Council - 02-09-26.mp4`). |
| `DRV-ANOM-004` | **MEDIUM** | `google-drive` | `leading-hyphen-sibling-duplicate-json-files` | Folder contains systematic near-duplicate sibling JSON files differing by a leading hyphen (`-Work_Session_-_Belvoir_Master_Plan_Updates_06-28-24.json` [35,706 B, md5=707d7c18...] vs `Work_Session_-_Belvoir_Master_Plan_Updates_06-28-24.json` [35,658 B, md5=6ecc938e...], ~48 B title-header difference) produced by two runs of a slug serializer. |
| `DRV-ANOM-005` | **LOW** | `google-drive` | `flattened-paths-in-historical-drive-snapshot` | Historical exporter wrote `path = name` without ancestor folder IDs across all 41,861 rows, causing multi-folder archive copies (e.g., `.en.vtt` files stored in 3 historical backup folders) to appear with distinct Drive IDs but flattened paths, alongside mixed personal/runtime files. |
| `DRV-ANOM-006` | **LOW** | `google-drive` | `trashed-and-shared-drive-scope-audit` | Verified 0 Google Workspace Shared Drives (`list_drives = []`), 50 trashed items (`trashed = true`, excluded from active corpus), and confirmed `Promethean_Telemetry_Sync` (`shared = true`) has 2 explicit private user permissions rather than public link sharing. |

---

## 5. Reproducible Verification Commands

```bash
# Regenerate inventory artifacts from staging raw bundle (or live APIs):
node scripts/inventory/build-inventory.mjs --from-raw /path/to/staging-raw

# Strictly validate every record, cross-file count, hash slot, date invariant, and zero-leak privacy scan:
node scripts/inventory/validate-inventory.mjs

# Execute unit & integration test suite:
node --test tests/inventory/inventory.test.mjs
```
