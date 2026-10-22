import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { resolveAuditedEventDate } from '../../scripts/inventory/date-audit.mjs';
import {
  assertZeroPrivacyLeaks,
  classifyDriveCandidate,
  scanTextForPrivacyLeaks,
} from '../../scripts/inventory/privacy-gate.mjs';
import { validateInventoryRecord } from '../../scripts/inventory/record-contract.mjs';
import { validateInventoryDirectory } from '../../scripts/inventory/validate-inventory.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '../..');

test('privacy-gate blocks non-public categories, runtime noise, and personal emails while allowing verified civic artifacts', () => {
  // Synthetic test fixtures only — never construct real private names or real personal dockets in tests!
  const syntheticPleading = classifyDriveCandidate({
    name: '2024-COM-9999 Motion to Suppress Sample Fixture.pdf',
    path: 'Synthetic_Legal_Folder/2024-COM-9999 Motion to Suppress Sample Fixture.pdf',
  });
  assert.equal(syntheticPleading.allowed, false);
  assert.equal(syntheticPleading.publication_review, 'blocked');

  const syntheticVenv = classifyDriveCandidate({
    name: '__init__.py',
    path: '.venv/lib/python3.11/site-packages/pkg/__init__.py',
  });
  assert.equal(syntheticVenv.allowed, false);
  assert.equal(syntheticVenv.exclusion_category, 'venv-or-package-runtime-noise');

  const syntheticEmailLeak = 'contact dummy-test-user@gmail.com in body';
  assert.throws(() => assertZeroPrivacyLeaks(syntheticEmailLeak, 'synthetic-fixture'));

  // Legitimate public industrial siting docket with common surname word ("Miller Generating Station") must pass
  const publicWdeq = classifyDriveCandidate({
    name: '2026 26-03 Miller Generating Station',
    mime_type: 'application/vnd.google-apps.folder',
    trusted_public_scope: true,
  });
  assert.equal(publicWdeq.allowed, true);
  assert.equal(publicWdeq.access_class, 'public');
  assert.doesNotThrow(() => assertZeroPrivacyLeaks(JSON.stringify(publicWdeq), 'wdeq-fixture'));
});

test('date-audit enforces event_date === null whenever metadata, title, YouTube upload prefix, or spoken opening dates conflict', () => {
  // Real forensic pattern 1: Clerk titled Finance Committee 01-07-25, Chair says January 6th 25 at call-to-order
  const clerkVsSpoken = resolveAuditedEventDate({
    metadataDate: '2025-01-07',
    title: 'Finance Committee 01-07-25',
    filename: 'Finance_Committee_01-07-25.md',
    openingTranscriptText:
      "good morning I'm calling the meeting to order welcome to the January 6th 25 finance committee meeting",
  });
  assert.equal(clerkVsSpoken.event_date, null);
  assert.ok(clerkVsSpoken.date_conflicts.length >= 1);

  // Real forensic pattern 2: YouTube upload prefix 20210318 differs from meeting title date 3-8-21
  const uploadVsTitle = resolveAuditedEventDate({
    title: '20210318 - Cheyenne City Council | Regular Meeting | 3-8-21.en.vtt',
    filename: '20210318 - Cheyenne City Council | Regular Meeting | 3-8-21.en.vtt',
  });
  assert.equal(uploadVsTitle.event_date, null);
  assert.equal(uploadVsTitle.upload_date, '2021-03-18');
  assert.ok(uploadVsTitle.date_conflicts.length >= 1);

  // Consistent multi-signal meeting date resolves cleanly with explicit evidence string
  const consistent = resolveAuditedEventDate({
    metadataDate: null,
    title: 'January 5, 2026, Cheyenne Planning Commission Meeting',
    openingTranscriptText: 'Good evening, welcome to the January 5, 2026 Cheyenne Planning Commission meeting.',
  });
  assert.equal(consistent.event_date, '2026-01-05');
  assert.equal(consistent.date_conflicts.length, 0);
  assert.ok(typeof consistent.date_evidence === 'string' && consistent.date_evidence.length > 0);
});

test('record-contract rejects 40-char Git SHA-1 or 32-char MD5 placed into original_bytes_sha256', () => {
  const baseValid = {
    schema_version: 1,
    record_id: 'test-rec-001',
    source_system: 'github',
    source_id: 'therealwindycity/TheReelWindyCity:README.md',
    source_version: 'commit:491612784a0f',
    document_type: 'repository_documentation_or_note',
    representation_kind: 'normalized-text',
    completeness: 'complete',
    access_class: 'public',
    publication_review: 'pending',
    original_bytes_sha256: null,
    extracted_text_sha256: null,
    git_blob_sha1: 'a'.repeat(40),
    event_date: null,
    date_evidence: null,
    date_conflicts: [],
    representation_note: 'Test blob provenance note',
  };
  assert.equal(validateInventoryRecord(baseValid).valid, true);

  // Putting 40-hex Git SHA-1 in original_bytes_sha256 MUST fail validation
  const badHash = { ...baseValid, original_bytes_sha256: 'a'.repeat(40) };
  assert.equal(validateInventoryRecord(badHash).valid, false);

  // Non-empty date_conflicts with non-null event_date MUST fail validation
  const badDate = {
    ...baseValid,
    event_date: '2025-01-07',
    date_evidence: 'metadata.date',
    date_conflicts: ['Spoken date 2025-01-06 disagrees'],
  };
  assert.equal(validateInventoryRecord(badDate).valid, false);
});

test('all generated catalog/inventory artifacts pass full contract + cross-file + zero-privacy-leak validation', () => {
  const invDir = path.join(REPO_ROOT, 'catalog/inventory');
  const result = validateInventoryDirectory(invDir);
  assert.equal(result.validated_files, 6);
  assert.equal(result.privacy_leaks, 0);
  assert.ok(result.github_records >= 6037);
  assert.ok(result.drive_records >= 4000);
});

test('every T02 script, handoff artifact, and test file contains zero redline privacy leaks', async () => {
  const fs = await import('node:fs');
  const handoffPath = path.join(REPO_ROOT, 'coordination/handoffs/T02/f4f97b19.json');
  const handoff = JSON.parse(fs.readFileSync(handoffPath, 'utf8'));
  assert.equal(handoff.task_id, 'T02');
  assert.equal(handoff.agent_id, 'f4f97b19');
  assert.equal(handoff.owned_paths.length, 15);

  for (const relPath of handoff.owned_paths) {
    const content = fs.readFileSync(path.join(REPO_ROOT, relPath), 'utf8');
    // Every single owned file — including privacy-gate.mjs and this test file — must have ZERO digest leaks
    const digestLeaks = scanTextForPrivacyLeaks(content, relPath).filter(
      (f) => f.category === 'private-litigation-or-identity-digest'
    );
    assert.deepEqual(digestLeaks, [], `Digest leak detected in ${relPath}`);

    // All non-gate, non-fixture files must pass full structural + digest leak scan cleanly
    if (relPath === 'tests/inventory/inventory.test.mjs' || relPath === 'scripts/inventory/privacy-gate.mjs') {
      continue;
    }
    assert.doesNotThrow(() => assertZeroPrivacyLeaks(content, relPath));
  }
});
