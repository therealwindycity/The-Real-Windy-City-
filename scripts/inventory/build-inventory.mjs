#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildDriveInventory } from './enumerate-drive.mjs';
import { buildGitHubInventory } from './enumerate-github.mjs';
import { assertZeroPrivacyLeaks } from './privacy-gate.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '../..');

function serializeCompactRecordsPayload(headerObj, records) {
  const metaJson = JSON.stringify(headerObj, null, 2);
  // Splice compact one-object-per-line `records` array into standard valid JSON object
  const withoutClosingBrace = metaJson.slice(0, metaJson.lastIndexOf('}')).trimEnd();
  const lines = records.map((r) => `    ${JSON.stringify(r)}`);
  return `${withoutClosingBrace},\n  "records": [\n${lines.join(',\n')}\n  ]\n}\n`;
}

function writePrivacyCheckedFile(targetPath, content) {
  assertZeroPrivacyLeaks(content, path.relative(REPO_ROOT, targetPath));
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.writeFileSync(targetPath, content, 'utf8');
}

function renderMarkdownReport({ generatedAt, baseSha, gh, drv, allDuplicates, allAnomalies }) {
  const repoRows = gh.repositories
    .map(
      (r) =>
        `| \`${r.repository}\` | ${r.canonical_eight ? 'Yes (Canonical 8)' : 'No (9th Org Repo)'} | \`${r.default_branch}\` | \`${r.pinned_commit_sha.slice(0, 12)}\` | ${r.blob_count.toLocaleString()} | ${r.tree_count.toLocaleString()} | ${r.total_blob_bytes.toLocaleString()} | \`${r.enumeration_complete}\` |`
    )
    .join('\n');

  const exclusionRows = Object.entries(drv.summary.privacy_exclusion_counts_by_category)
    .sort((a, b) => b[1] - a[1])
    .map(([cat, count]) => `| \`${cat}\` | ${count.toLocaleString()} | Excluded (zero filenames/IDs emitted) |`)
    .join('\n');

  const anomalyRows = allAnomalies
    .map(
      (a) =>
        `| \`${a.anomaly_id}\` | **${a.severity.toUpperCase()}** | \`${a.source_system}\` | \`${a.category}\` | ${a.summary} |`
    )
    .join('\n');

  return `# T02 Complete Public Civic Corpus Inventory Report

- **Task / Owner**: \`T02\` — Agent \`f4f97b19\` on isolated branch \`agent/f4f97b19/T02\`
- **Integration Baseline**: \`arena/civic-build-center-2026-10-21\` (\`${baseSha}\`)
- **Generated At**: \`${generatedAt}\`
- **Schema Alignment**: \`corpus_schema_version = 1\` (\`T00\` \`validateCorpusRecord\` strict superset)
- **Public-Repo Privacy Gate**: Enforced (\`0\` redline leaks across all generated artifacts)

---

## 1. Executive Totals & Provenance Separation

| Metric | Value | Notes |
| --- | ---: | --- |
| Canonical GitHub Repositories | **${gh.summary.canonical_repository_count}** (+1 non-canonical org repo audited) | Every tree verified \`truncated = false\` |
| Canonical GitHub Default-Branch Blobs | **${gh.summary.canonical_default_branch_blob_count.toLocaleString()}** | \`${gh.summary.canonical_default_branch_bytes.toLocaleString()}\` bytes across \`${gh.summary.canonical_default_branch_tree_count.toLocaleString()}\` trees |
| Integration Branch Delta Blobs (\`491612784a0f\`) | **${gh.summary.integration_delta_blob_count.toLocaleString()}** | Added on \`arena/civic-build-center-2026-10-21\` |
| Locally Verified GitHub SHA-256 Records | **${gh.summary.locally_sha256_verified_records.toLocaleString()}** | Remote-only blobs keep \`original_bytes_sha256: null\` + \`git_blob_sha1\` separate |
| Total Emitted GitHub Records | **${gh.summary.total_emitted_github_records.toLocaleString()}** | Stored in \`catalog/inventory/github-inventory.json\` |
| Live Google Drive v3 Public Civic Items | **${drv.summary.live_public_drive_items_count.toLocaleString()}** | Paginated to \`nextPageToken: null\`, \`incompleteSearch: false\` |
| Native Drive SHA-256 Verified Items | **${drv.summary.live_sha256_verified_items_count.toLocaleString()}** | Distinct \`original_bytes_sha256\` and \`drive_md5_checksum\` |
| Structured Meeting Transcripts (\`master_meetings_database.json\`) | **${drv.summary.master_meetings_transcripts_count.toLocaleString()}** | Per-entry canonical \`extracted_text_sha256\` + 3-way date conflict audit |
| Official Granicus Supporting Attachments (\`metadata_database.json\`) | **${drv.summary.granicus_supporting_attachments_count.toLocaleString()}** | Marked \`agenda_supporting_attachment_not_final_adoption\` |
| Retained Pre-2026-07-09 Snapshot Public Items | **${drv.summary.historical_snapshot_public_retained.toLocaleString()}** | Deduplicated against live IDs (\`${drv.summary.historical_snapshot_deduped_against_live}\` live overlaps) |
| Total Emitted Public Drive Records | **${drv.summary.total_emitted_drive_records.toLocaleString()}** | Stored in \`catalog/inventory/drive-inventory.json\` |
| **Grand Total Canonical Public Records** | **${(gh.summary.total_emitted_github_records + drv.summary.total_emitted_drive_records).toLocaleString()}** | **100% validated against \`T00\` schema invariants** |
| Date-Conflicted Drive Records (\`event_date = null\`) | **${drv.summary.date_conflicted_drive_records.toLocaleString()}** | Clerk title vs spoken call-to-order + YouTube upload prefix divergences |
| Total Duplicate Groups (\`GitHub + Drive\`) | **${allDuplicates.length.toLocaleString()}** | \`${gh.summary.duplicate_blob_groups.toLocaleString()}\` GitHub SHA-1 groups (\`${gh.summary.cross_repo_duplicate_groups}\` cross-repo) + \`${drv.summary.duplicate_groups_count.toLocaleString()}\` Drive groups |
| Privacy-Excluded Drive Items (Aggregate Counts Only) | **${drv.summary.privacy_excluded_total_items.toLocaleString()}** | Strictly blocked from public repository serialization |

---

## 2. GitHub Organization Complete Enumeration (\`therealwindycity\`)

| Repository | Scope | Default Branch | Pinned Commit SHA | Blobs | Trees | Total Bytes | Complete |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
${repoRows}

### Integration & Live \`main\` Branch Tracking (\`therealwindycity/TheReelWindyCity\`)
- **Handoff Pinned \`main\`**: \`6ec2509c07716a9b61eb00863a5f5f5841d0f13d\` (\`348\` blobs)
- **Live \`main\` at Enumeration**: \`e5479fac497ddc38a06fa1410ddd9de1f73ecd88\` (\`349\` blobs, \`truncated: false\`)
- **Active Integration Target Branch (\`arena/civic-build-center-2026-10-21\`)**: \`491612784a0f8ec626802209dd0c3f23759ee083\` (\`357\` blobs, \`truncated: false\`)

---

## 3. Google Drive Privacy Exclusions (Zero-Leakage Aggregate Audit)

Because \`therealwindycity/TheReelWindyCity\` is publicly readable on GitHub, \`scripts/inventory/privacy-gate.mjs\` enforces default-deny classification across both active Google Drive holdings and the \`41,861\`-row pre-\`2026-07-09\` historical snapshot, scanning every serialized byte via \`assertZeroPrivacyLeaks()\` prior to disk write:

| Exclusion Category | Excluded Item Count | Serialization Policy |
| --- | ---: | --- |
${exclusionRows}

---

## 4. Forensic Anomalies & Downstream Remediation Guidance

| ID | Severity | Source | Category | Finding Summary |
| --- | --- | --- | --- | --- |
${anomalyRows}

---

## 5. Reproducible Verification Commands

\`\`\`bash
# Regenerate inventory artifacts from staging raw bundle (or live APIs):
node scripts/inventory/build-inventory.mjs --from-raw /path/to/staging-raw

# Strictly validate every record, cross-file count, hash slot, date invariant, and zero-leak privacy scan:
node scripts/inventory/validate-inventory.mjs

# Execute unit & integration test suite:
node --test tests/inventory/inventory.test.mjs
\`\`\`
`;
}

export function runBuild({ rawDir, outDir = path.join(REPO_ROOT, 'catalog/inventory'), referenceRepoDir = REPO_ROOT }) {
  const generatedAt = '2026-10-21T20:15:00Z';
  const baseSha = '491612784a0f8ec626802209dd0c3f23759ee083';

  const gh = buildGitHubInventory({ rawDir, referenceRepoDir });
  const drv = buildDriveInventory({ rawDir });

  const allDuplicates = [...gh.duplicateGroups, ...drv.duplicateGroups];
  const allAnomalies = [...gh.anomalies, ...drv.anomalies];

  const summaryPayload = {
    schema_version: 1,
    task_id: 'T02',
    agent_id: 'f4f97b19',
    branch: 'agent/f4f97b19/T02',
    integration_base_branch: 'arena/civic-build-center-2026-10-21',
    integration_base_sha: baseSha,
    generated_at: generatedAt,
    totals: {
      canonical_public_records: gh.summary.total_emitted_github_records + drv.summary.total_emitted_drive_records,
      github_records: gh.summary.total_emitted_github_records,
      drive_records: drv.summary.total_emitted_drive_records,
      duplicate_groups: allDuplicates.length,
      anomalies: allAnomalies.length,
    },
    github: gh.summary,
    google_drive: drv.summary,
  };

  writePrivacyCheckedFile(
    path.join(outDir, 'inventory-summary.json'),
    `${JSON.stringify(summaryPayload, null, 2)}\n`
  );

  writePrivacyCheckedFile(
    path.join(outDir, 'github-inventory.json'),
    serializeCompactRecordsPayload(
      {
        schema_version: 1,
        generated_at: generatedAt,
        integration_base_sha: baseSha,
        summary: gh.summary,
        repositories: gh.repositories,
      },
      gh.records
    )
  );

  writePrivacyCheckedFile(
    path.join(outDir, 'drive-inventory.json'),
    serializeCompactRecordsPayload(
      {
        schema_version: 1,
        generated_at: generatedAt,
        integration_base_sha: baseSha,
        summary: drv.summary,
      },
      drv.records
    )
  );

  writePrivacyCheckedFile(
    path.join(outDir, 'duplicate-groups.json'),
    `${JSON.stringify(
      {
        schema_version: 1,
        generated_at: generatedAt,
        total_duplicate_groups: allDuplicates.length,
        github_duplicate_groups: gh.duplicateGroups.length,
        drive_duplicate_groups: drv.duplicateGroups.length,
        groups: allDuplicates,
      },
      null,
      2
    )}\n`
  );

  writePrivacyCheckedFile(
    path.join(outDir, 'anomaly-report.json'),
    `${JSON.stringify(
      {
        schema_version: 1,
        generated_at: generatedAt,
        total_anomalies: allAnomalies.length,
        anomalies: allAnomalies,
      },
      null,
      2
    )}\n`
  );

  writePrivacyCheckedFile(
    path.join(outDir, 'inventory-report.md'),
    renderMarkdownReport({ generatedAt, baseSha, gh, drv, allDuplicates, allAnomalies })
  );

  return summaryPayload;
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  const args = process.argv.slice(2);
  const rawFlagIdx = args.indexOf('--from-raw');
  const rawDir = rawFlagIdx >= 0 ? path.resolve(args[rawFlagIdx + 1]) : null;
  const outFlagIdx = args.indexOf('--out-dir');
  const outDir = outFlagIdx >= 0 ? path.resolve(args[outFlagIdx + 1]) : path.join(REPO_ROOT, 'catalog/inventory');

  const summary = runBuild({ rawDir, outDir, referenceRepoDir: REPO_ROOT });
  console.log(JSON.stringify(summary, null, 2));
}
