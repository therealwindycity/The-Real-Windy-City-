/**
 * T02 Corpus Record Validator strictly aligned with T00 (`corpus-contract-v1`,
 * commit `864aee8cbab16c472b38a990cdba3f8345d0e7b7`).
 *
 * Ensures 100% forward compatibility when T00 merges into `arena/civic-build-center-2026-10-21`
 * without requiring T02 to edit `src/lib/` (owned by T00/T01).
 */

export const CORPUS_SCHEMA_VERSION = 1;

export const REPRESENTATION_KINDS = new Set([
  'original-binary',
  'connector-text',
  'normalized-text',
  'excerpt',
  'summary',
]);

export const COMPLETENESS_VALUES = new Set(['complete', 'partial', 'unknown']);
export const ACCESS_CLASSES = new Set(['public', 'private', 'restricted']);
export const PUBLICATION_REVIEWS = new Set(['pending', 'approved', 'blocked']);

const SHA256_RE = /^[a-f0-9]{64}$/;
const SHA1_RE = /^[a-f0-9]{40}$/;
const MD5_RE = /^[a-f0-9]{32}$/;
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Validate a single canonical inventory record against all T00 + T02 provenance invariants.
 * Returns `{ valid: boolean, errors: string[] }`.
 */
export function validateInventoryRecord(record) {
  const errors = [];
  if (!record || typeof record !== 'object' || Array.isArray(record)) {
    return { valid: false, errors: ['Record must be a plain object'] };
  }

  if (record.schema_version !== CORPUS_SCHEMA_VERSION) {
    errors.push(`schema_version must equal ${CORPUS_SCHEMA_VERSION}`);
  }

  for (const strField of [
    'record_id',
    'source_system',
    'source_id',
    'source_version',
    'document_type',
    'representation_note',
  ]) {
    if (typeof record[strField] !== 'string' || record[strField].trim().length === 0) {
      errors.push(`${strField} must be a non-empty string`);
    }
  }

  if (!REPRESENTATION_KINDS.has(record.representation_kind)) {
    errors.push(`Invalid representation_kind: ${String(record.representation_kind)}`);
  }
  if (!COMPLETENESS_VALUES.has(record.completeness)) {
    errors.push(`Invalid completeness: ${String(record.completeness)}`);
  }
  if (!ACCESS_CLASSES.has(record.access_class)) {
    errors.push(`Invalid access_class: ${String(record.access_class)}`);
  }
  if (!PUBLICATION_REVIEWS.has(record.publication_review)) {
    errors.push(`Invalid publication_review: ${String(record.publication_review)}`);
  }

  if (record.access_class !== 'public' && record.publication_review !== 'blocked') {
    errors.push('Non-public records MUST have publication_review === "blocked"');
  }

  // Strict cryptographic hash separation: never put Git SHA-1 (40 hex) or Drive MD5 (32 hex) in SHA-256 slots!
  if (record.original_bytes_sha256 !== null && !SHA256_RE.test(record.original_bytes_sha256)) {
    errors.push(`original_bytes_sha256 must be null or 64-char lowercase hex SHA-256 (got ${String(record.original_bytes_sha256)})`);
  }
  if (record.extracted_text_sha256 !== null && !SHA256_RE.test(record.extracted_text_sha256)) {
    errors.push(`extracted_text_sha256 must be null or 64-char lowercase hex SHA-256 (got ${String(record.extracted_text_sha256)})`);
  }
  if (record.git_blob_sha1 !== undefined && record.git_blob_sha1 !== null && !SHA1_RE.test(record.git_blob_sha1)) {
    errors.push(`git_blob_sha1 must be null or 40-char lowercase hex SHA-1 (got ${String(record.git_blob_sha1)})`);
  }
  if (record.drive_md5_checksum !== undefined && record.drive_md5_checksum !== null && !MD5_RE.test(record.drive_md5_checksum)) {
    errors.push(`drive_md5_checksum must be null or 32-char lowercase hex MD5 (got ${String(record.drive_md5_checksum)})`);
  }

  // Date & date conflict invariants
  if (!Array.isArray(record.date_conflicts)) {
    errors.push('date_conflicts must be an Array of strings');
  } else if (record.date_conflicts.some((c) => typeof c !== 'string' || c.trim().length === 0)) {
    errors.push('Every entry in date_conflicts must be a non-empty string');
  }

  if (record.event_date !== null) {
    if (typeof record.event_date !== 'string' || !ISO_DATE_RE.test(record.event_date)) {
      errors.push(`event_date must be null or YYYY-MM-DD (got ${String(record.event_date)})`);
    }
    if (typeof record.date_evidence !== 'string' || record.date_evidence.trim().length === 0) {
      errors.push('date_evidence must be a non-empty string whenever event_date is non-null');
    }
    if (Array.isArray(record.date_conflicts) && record.date_conflicts.length > 0) {
      errors.push('event_date MUST be null whenever date_conflicts is non-empty');
    }
  }

  return { valid: errors.length === 0, errors };
}
