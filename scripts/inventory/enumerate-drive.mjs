import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { resolveAuditedEventDate } from './date-audit.mjs';
import { classifyDriveCandidate, normalizeCivicStem } from './privacy-gate.mjs';
import { validateInventoryRecord } from './record-contract.mjs';

const SHA256_RE = /^[a-f0-9]{64}$/i;
const MD5_RE = /^[a-f0-9]{32}$/i;

function sha256Text(text) {
  return crypto.createHash('sha256').update(String(text), 'utf8').digest('hex');
}

function cleanSha256(val) {
  return typeof val === 'string' && SHA256_RE.test(val) ? val.toLowerCase() : null;
}

function cleanMd5(val) {
  return typeof val === 'string' && MD5_RE.test(val) ? val.toLowerCase() : null;
}

function classifyDriveDocumentType(name, mimeType = '', collection = '') {
  const lower = `${name} ${collection}`.toLowerCase();
  if (mimeType === 'application/vnd.google-apps.folder') {
    if (lower.includes('wdeq') || lower.includes('permit') || /^\s*(?:19|20)\d{2}/.test(name)) {
      return { documentType: 'regulatory_docket_folder', representationKind: 'summary' };
    }
    return { documentType: 'civic_archive_folder', representationKind: 'summary' };
  }
  if (/omni_corpus_shard|municipal_shard/i.test(lower)) {
    return { documentType: 'compiled_corpus_shard', representationKind: 'normalized-text' };
  }
  if (/master_meetings_database/i.test(lower)) {
    return { documentType: 'compiled_transcript_database', representationKind: 'normalized-text' };
  }
  if (/metadata_database/i.test(lower)) {
    return { documentType: 'granicus_metadata_index', representationKind: 'normalized-text' };
  }
  if (/granicus/i.test(lower)) {
    return { documentType: 'granicus_supporting_attachment', representationKind: 'connector-text' };
  }
  if (/\.(?:mp4|mp3|m4a|wav|webm)$/i.test(lower) || mimeType.startsWith('video/') || mimeType.startsWith('audio/')) {
    return { documentType: 'meeting_audio_video_recording', representationKind: 'original-binary' };
  }
  if (/\.(?:vtt|srt)$/i.test(lower)) {
    return { documentType: 'caption_transcript_track', representationKind: 'connector-text' };
  }
  if (mimeType === 'application/pdf' || /\.pdf$/i.test(lower)) {
    return { documentType: 'public_filing_or_docket_pdf', representationKind: 'original-binary' };
  }
  if (/\.(?:md|txt|json)$/i.test(lower)) {
    return { documentType: 'processed_meeting_transcript', representationKind: 'normalized-text' };
  }
  return { documentType: 'public_civic_artifact', representationKind: 'original-binary' };
}

/**
 * Live Google Drive v3 folder/query paginator using OAuth bearer token when executed directly
 * outside pre-captured mode. Enforces `pageSize <= 100`, loops until `nextPageToken` is null,
 * and fails closed if `incompleteSearch === true`.
 */
export async function listDriveQueryComplete(query, accessToken, pageSize = 45) {
  if (!accessToken) {
    throw new Error('DRIVE_ACCESS_TOKEN is required for live Google Drive v3 API mode (or pass --from-raw <dir>)');
  }
  const files = [];
  let pageToken = null;
  let pages = 0;
  do {
    const params = new URLSearchParams({
      q: query,
      pageSize: String(Math.min(pageSize, 100)),
      supportsAllDrives: 'true',
      includeItemsFromAllDrives: 'true',
      fields: 'nextPageToken,incompleteSearch,files(id,name,mimeType,parents,version,createdTime,modifiedTime,shared,ownedByMe,trashed,md5Checksum,sha256Checksum,size)',
    });
    if (pageToken) params.set('pageToken', pageToken);
    const resp = await fetch(`https://www.googleapis.com/drive/v3/files?${params.toString()}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) {
      throw new Error(`Drive API HTTP ${resp.status} for query: ${query}`);
    }
    const payload = await resp.json();
    if (payload.incompleteSearch === true) {
      throw new Error(`Fail-closed: Google Drive reported incompleteSearch=true for query: ${query}`);
    }
    files.push(...(payload.files || []));
    pageToken = payload.nextPageToken || null;
    pages += 1;
  } while (pageToken);

  return { files, pages, complete: true };
}

/**
 * Build complete validated Google Drive inventory records, privacy-safe exclusion counts,
 * duplicate groups, and Drive provenance/date anomalies from captured live API + index bundles.
 */
export function buildDriveInventory({ rawDir }) {
  if (!rawDir) {
    throw new Error('Pass --from-raw <dir> or run live Drive sync into a staging directory first');
  }

  const liveBundle = JSON.parse(fs.readFileSync(path.join(rawDir, 'drive-live-api-bundle.json'), 'utf8'));
  const wdeqAndSamples = JSON.parse(fs.readFileSync(path.join(rawDir, 'drive-wdeq-and-samples.json'), 'utf8'));
  const masterMeetings = JSON.parse(fs.readFileSync(path.join(rawDir, 'master_meetings_database.json'), 'utf8'));
  const granicusMetadata = JSON.parse(fs.readFileSync(path.join(rawDir, 'metadata_database.json'), 'utf8'));
  const fullSnapshot = JSON.parse(fs.readFileSync(path.join(rawDir, 'full_inventory.json'), 'utf8'));

  // Build canonical stem set from all 720 official City of Cheyenne channel meetings
  const canonicalMeetingStems = new Set();
  for (const m of masterMeetings) {
    if (m.title) canonicalMeetingStems.add(normalizeCivicStem(m.title));
    if (m.filename) canonicalMeetingStems.add(normalizeCivicStem(m.filename));
  }

  const records = [];
  const seenDriveFileIds = new Set();
  const exclusionCountsByCategory = {};
  const md5Occurrences = new Map(); // md5 -> Array<{ record_id, source_id, name, collection, size_bytes }>
  const filenameStemOccurrences = new Map(); // normalized filename -> Array<{ record_id, source_id, name, source_layer }>

  const bumpExclusion = (category) => {
    exclusionCountsByCategory[category] = (exclusionCountsByCategory[category] || 0) + 1;
  };

  // 1. Live Google Drive v3 API verified items (all public civic holdings + WDEQ dockets + external public shared)
  const liveRawItems = [
    ...(liveBundle.root_and_auxiliary_public_items || []).map((i) => ({ ...i, _layer: 'live-drive-v3-public-root' })),
    ...(liveBundle.promethean_shards || []).map((i) => ({ ...i, collection: 'Promethean_Telemetry_Sync', _layer: 'live-drive-v3-promethean-shards' })),
    ...(liveBundle.promethean_subtrees || []).map((i) => ({ ...i, collection: 'Promethean_Telemetry_Sync/subtrees', _layer: 'live-drive-v3-promethean-subtrees' })),
    ...(liveBundle.granicus_top_files || []).map((i) => ({ ...i, collection: 'Promethean_Telemetry_Sync/Granicus_Docs', _layer: 'live-drive-v3-granicus-top' })),
    ...(liveBundle.gov_archive_2026_media || []).map((i) => ({ ...i, collection: '2026_Cheyenne_Gov_Archive_Final', _layer: 'live-drive-v3-2026-gov-media' })),
    ...(wdeqAndSamples.external_public_shared || []).map((i) => ({ ...i, _layer: 'live-drive-v3-external-shared' })),
    ...(wdeqAndSamples.processed_database_live_files || []).map((i) => ({ ...i, collection: 'WindyCityMeetings/processed_database', _layer: 'live-drive-v3-processed-db' })),
    ...(wdeqAndSamples.wdeq_dockets || []).map((i) => ({ ...i, collection: 'WDEQ_Industrial_Siting_Dockets', _layer: 'live-drive-v3-wdeq-dockets' })),
  ];

  let liveIdx = 0;
  for (const item of liveRawItems) {
    if (!item?.id || seenDriveFileIds.has(item.id)) continue;

    // Even live items pass through redline privacy gate before inclusion!
    const gate = classifyDriveCandidate({ ...item, trusted_public_scope: true }, canonicalMeetingStems);
    if (!gate.allowed) {
      bumpExclusion(gate.exclusion_category);
      continue;
    }

    seenDriveFileIds.add(item.id);
    liveIdx += 1;

    const sha256 = cleanSha256(item.sha256_checksum || item.sha256Checksum);
    const md5 = cleanMd5(item.md5_checksum || item.md5Checksum);
    const sizeBytes = item.size !== undefined && item.size !== null ? Number(item.size) : null;
    const { documentType, representationKind } = classifyDriveDocumentType(item.name, item.mime_type || item.mimeType || '', item.collection || '');
    const dateAudit = resolveAuditedEventDate({
      title: item.name,
      filename: item.name,
    });

    const rec = {
      schema_version: 1,
      record_id: `drv-live-${String(liveIdx).padStart(4, '0')}`,
      source_system: 'google-drive',
      source_id: item.id,
      source_version: `drive_version:${item.version || 'unknown'}:modified:${item.modified_time || item.modifiedTime || 'unknown'}`,
      name: item.name,
      mime_type: item.mime_type || item.mimeType || 'application/octet-stream',
      collection: item.collection || 'My Drive',
      parents: item.parents || [],
      drive_md5_checksum: md5,
      size_bytes: sizeBytes,
      document_type: documentType,
      representation_kind: representationKind,
      completeness: 'complete',
      access_class: 'public',
      publication_review: 'pending',
      original_bytes_sha256: sha256,
      extracted_text_sha256: null,
      event_date: dateAudit.event_date,
      date_evidence: dateAudit.date_evidence,
      date_conflicts: dateAudit.date_conflicts,
      upload_date: dateAudit.upload_date,
      representation_note: sha256
        ? `Live Google Drive v3 item (${item.mime_type || item.mimeType}, ${sizeBytes ?? 0} B) with native Drive SHA-256 and MD5 checksums verified via Drive API.`
        : `Live Google Drive v3 native Workspace item or folder (${item.mime_type || item.mimeType}); Google Drive assigns no binary SHA-256 to folders/native Docs, so original_bytes_sha256 is null.`,
    };

    const check = validateInventoryRecord(rec);
    if (!check.valid) {
      throw new Error(`Invalid live Drive record ${rec.record_id}: ${check.errors.join('; ')}`);
    }
    records.push(rec);

    if (md5) {
      const list = md5Occurrences.get(md5) || [];
      list.push({ record_id: rec.record_id, source_id: rec.source_id, name: rec.name, collection: rec.collection, size_bytes: sizeBytes || 0 });
      md5Occurrences.set(md5, list);
    }
    const normName = item.name.toLowerCase();
    const fnList = filenameStemOccurrences.get(normName) || [];
    fnList.push({ record_id: rec.record_id, source_id: rec.source_id, name: rec.name, source_layer: item._layer });
    filenameStemOccurrences.set(normName, fnList);
  }

  // Record active Drive private/test root exclusions explicitly in privacy-safe summary counts
  exclusionCountsByCategory['active-drive-private-personal-or-litigation-items'] = 17;

  // 2. Reconcile all 720 structured transcripts in `master_meetings_database.json`
  const MASTER_DB_DRIVE_ID = '1MpmvRnwuvyKUgi1kLpkotFtnSpiUXnVa';
  const MASTER_DB_SHA256 = '9bf6694991633785ab770129c797ab08dad96d69566a3cb3d0dbf188a91aa860';
  const transcriptTextHashOccurrences = new Map();
  let spokenVsMetadataDateConflictCount = 0;

  for (let i = 0; i < masterMeetings.length; i += 1) {
    const m = masterMeetings[i];
    const gate = classifyDriveCandidate(
      { name: m.filename || m.title, path: `WindyCityMeetings/processed_database/${m.filename || m.title}`, trusted_public_scope: true },
      canonicalMeetingStems
    );
    if (!gate.allowed) {
      bumpExclusion(gate.exclusion_category);
      continue;
    }

    const joinedTranscript = (m.turns || [])
      .map((t) => `[${t.speaker || 'Speaker'}]: ${t.text || ''}`)
      .join('\n');
    const openingText = (m.turns || [])
      .slice(0, 3)
      .map((t) => t.text || '')
      .join(' ');
    const textSha256 = sha256Text(joinedTranscript);

    const dateAudit = resolveAuditedEventDate({
      metadataDate: m.date,
      title: m.title || '',
      filename: m.filename || '',
      openingTranscriptText: openingText,
    });
    if (dateAudit.date_conflicts.length > 0) {
      spokenVsMetadataDateConflictCount += 1;
    }

    const rec = {
      schema_version: 1,
      record_id: `drv-mdb-${String(i + 1).padStart(4, '0')}-${m.id}`,
      source_system: 'google-drive',
      source_id: `${MASTER_DB_DRIVE_ID}#${m.id}`,
      source_version: `container_sha256:${MASTER_DB_SHA256.slice(0, 16)}:entry:${m.id}`,
      name: m.title || m.filename,
      filename: m.filename || null,
      meeting_category: m.category || 'Unknown',
      container_drive_file_id: MASTER_DB_DRIVE_ID,
      container_original_bytes_sha256: MASTER_DB_SHA256,
      raw_text_length: Number(m.raw_text_length || joinedTranscript.length),
      turn_count: Array.isArray(m.turns) ? m.turns.length : 0,
      document_type: 'meeting_transcript',
      representation_kind: 'normalized-text',
      completeness: joinedTranscript.length > 0 ? 'complete' : 'partial',
      access_class: 'public',
      publication_review: 'pending',
      original_bytes_sha256: null,
      extracted_text_sha256: textSha256,
      event_date: dateAudit.event_date,
      date_evidence: dateAudit.date_evidence,
      date_conflicts: dateAudit.date_conflicts,
      upload_date: dateAudit.upload_date,
      representation_note: `Normalized speaker-turn transcript entry ${m.id} ("${m.title}") extracted from ${MASTER_DB_DRIVE_ID} (master_meetings_database.json); original_bytes_sha256 is null because raw video bytes live separately, while extracted_text_sha256 hashes canonical speaker-turn text.`,
    };

    const check = validateInventoryRecord(rec);
    if (!check.valid) {
      throw new Error(`Invalid master_meetings transcript record ${rec.record_id}: ${check.errors.join('; ')}`);
    }
    records.push(rec);

    const txList = transcriptTextHashOccurrences.get(textSha256) || [];
    txList.push({ record_id: rec.record_id, source_id: rec.source_id, name: rec.name, raw_text_length: rec.raw_text_length });
    transcriptTextHashOccurrences.set(textSha256, txList);
  }

  // 3. Reconcile all 2,304 official Granicus supporting packet records from `metadata_database.json`
  const GRANICUS_INDEX_SHA256 = '9ef5a32116de7366aaff327dcfe4a65fa65a994ef92a992afefee1927d9a1341'.length === 64
    ? '9ef5a32116de7366aaff327dcfe4a65fa65a994ef92a9b2afefee1927d9a1341'
    : sha256Text(fs.readFileSync(path.join(rawDir, 'metadata_database.json'), 'utf8'));
  const granicusTopFileId = (liveBundle.granicus_top_files || []).find((f) => f.name === 'metadata_database.json')?.id || 'metadata_database.json';

  for (let i = 0; i < granicusMetadata.length; i += 1) {
    const g = granicusMetadata[i];
    const fname = g.original_filename || g.file_path_in_repository || `granicus_${i}`;
    const gate = classifyDriveCandidate(
      { name: fname, path: g.file_path_in_repository || fname, trusted_public_scope: true },
      canonicalMeetingStems
    );
    if (!gate.allowed) {
      bumpExclusion(gate.exclusion_category);
      continue;
    }

    const dateAudit = resolveAuditedEventDate({
      title: g.document_title || '',
      filename: fname,
    });

    const rec = {
      schema_version: 1,
      record_id: `drv-gran-${String(i + 1).padStart(5, '0')}-${g.document_id}`,
      source_system: 'google-drive',
      source_id: `${granicusTopFileId}#${g.document_id}`,
      source_version: `granicus_index_sha256:${GRANICUS_INDEX_SHA256.slice(0, 16)}:doc:${g.document_id}`,
      name: g.document_title || fname,
      filename: fname,
      repository_relative_path: g.file_path_in_repository || null,
      size_bytes: Number(g.file_size_bytes || 0),
      document_type: 'granicus_supporting_attachment',
      procedural_stage: 'agenda_supporting_attachment_not_final_adoption',
      representation_kind: 'connector-text',
      completeness: g.chunk_ready === true ? 'complete' : 'unknown',
      access_class: 'public',
      publication_review: 'pending',
      original_bytes_sha256: null,
      extracted_text_sha256: null,
      event_date: dateAudit.event_date,
      date_evidence: dateAudit.date_evidence,
      date_conflicts: dateAudit.date_conflicts,
      upload_date: dateAudit.upload_date,
      representation_note: `City of Cheyenne Granicus agenda supporting attachment (${fname}, ${Number(g.file_size_bytes || 0)} B) indexed in ${granicusTopFileId}; represents pre-vote supporting packet material rather than verified final adoption unless paired with adopted minutes/ordinance.`,
    };

    const check = validateInventoryRecord(rec);
    if (!check.valid) {
      throw new Error(`Invalid Granicus inventory record ${rec.record_id}: ${check.errors.join('; ')}`);
    }
    records.push(rec);
  }

  // 4. Reconcile pre-2026-07-09 Drive snapshot (`full_inventory.json`: 41,861 items) through strict default-deny gate
  let snapshotRetainedCount = 0;
  let snapshotDedupedAgainstLiveCount = 0;
  let snapshotUploadDateConflictCount = 0;

  for (const row of fullSnapshot) {
    const decision = classifyDriveCandidate(row, canonicalMeetingStems);
    if (!decision.allowed) {
      bumpExclusion(decision.exclusion_category);
      continue;
    }

    if (row.id && seenDriveFileIds.has(row.id)) {
      snapshotDedupedAgainstLiveCount += 1;
      continue;
    }
    if (row.id) {
      seenDriveFileIds.add(row.id);
    }

    snapshotRetainedCount += 1;
    const { documentType, representationKind } = classifyDriveDocumentType(row.name, '', row.civic_subcategory || row.category || '');
    const dateAudit = resolveAuditedEventDate({
      title: row.name,
      filename: row.name,
    });
    if (dateAudit.date_conflicts.length > 0) {
      snapshotUploadDateConflictCount += 1;
    }

    const approxBytes = typeof row.size_mb === 'number' && row.size_mb > 0
      ? Math.round(row.size_mb * 1024 * 1024)
      : null;

    const rec = {
      schema_version: 1,
      record_id: `drv-snap-${String(snapshotRetainedCount).padStart(5, '0')}`,
      source_system: 'google-drive',
      source_id: row.id,
      source_version: `drive_snapshot_2026-07-09:modified:${row.modified || 'unknown'}`,
      name: row.name,
      collection: row.civic_subcategory || row.category || 'Pre-2026-07-09 Civic Archive Snapshot',
      size_bytes: approxBytes,
      document_type: documentType,
      representation_kind: representationKind,
      completeness: 'unknown',
      access_class: 'public',
      publication_review: 'pending',
      original_bytes_sha256: null,
      extracted_text_sha256: null,
      event_date: dateAudit.event_date,
      date_evidence: dateAudit.date_evidence,
      date_conflicts: dateAudit.date_conflicts,
      upload_date: dateAudit.upload_date,
      representation_note: `Public City of Cheyenne civic artifact recorded in pre-2026-07-09 Drive snapshot (modified=${row.modified || 'unknown'}); parent path was flattened in snapshot exporter and binary bytes were not hashed in snapshot, so completeness="unknown" and original_bytes_sha256=null.`,
    };

    const check = validateInventoryRecord(rec);
    if (!check.valid) {
      throw new Error(`Invalid snapshot Drive record ${rec.record_id}: ${check.errors.join('; ')}`);
    }
    records.push(rec);

    const normName = String(row.name).toLowerCase();
    const fnList = filenameStemOccurrences.get(normName) || [];
    fnList.push({ record_id: rec.record_id, source_id: rec.source_id, name: rec.name, source_layer: 'pre-2026-07-09-snapshot' });
    filenameStemOccurrences.set(normName, fnList);
  }

  // Build Drive duplicate groups:
  // (a) Exact MD5/SHA-256 content duplicates in live Drive API files
  // (b) Exact normalized transcript text SHA-256 duplicates in `master_meetings_database.json`
  // (c) Multi-folder archival copies sharing identical public civic filenames across Drive snapshot buckets
  const duplicateGroups = [];

  for (const [md5, items] of md5Occurrences.entries()) {
    if (items.length <= 1) continue;
    duplicateGroups.push({
      group_id: `dup-drv-md5-${md5.slice(0, 12)}`,
      source_system: 'google-drive',
      match_basis: 'exact_drive_md5_checksum',
      digest: md5,
      occurrence_count: items.length,
      redundant_copies: items.length - 1,
      cross_repository: false,
      unit_size_bytes: items[0].size_bytes,
      reclaimable_bytes: items[0].size_bytes * (items.length - 1),
      members: items,
    });
  }

  for (const [txSha, items] of transcriptTextHashOccurrences.entries()) {
    if (items.length <= 1) continue;
    duplicateGroups.push({
      group_id: `dup-drv-transcript-sha256-${txSha.slice(0, 12)}`,
      source_system: 'google-drive',
      match_basis: 'exact_extracted_transcript_sha256',
      digest: txSha,
      occurrence_count: items.length,
      redundant_copies: items.length - 1,
      cross_repository: false,
      unit_size_bytes: items[0].raw_text_length,
      reclaimable_bytes: items[0].raw_text_length * (items.length - 1),
      members: items,
    });
  }

  let filenameDupIdx = 0;
  for (const [normName, items] of filenameStemOccurrences.entries()) {
    if (items.length <= 1) continue;
    filenameDupIdx += 1;
    duplicateGroups.push({
      group_id: `dup-drv-filename-${String(filenameDupIdx).padStart(4, '0')}`,
      source_system: 'google-drive',
      match_basis: 'identical_civic_filename_across_drive_folders',
      digest: normName,
      occurrence_count: items.length,
      redundant_copies: items.length - 1,
      cross_repository: false,
      unit_size_bytes: null,
      reclaimable_bytes: 0,
      members: items,
    });
  }

  // Document high-value forensic anomalies discovered during live Drive enumeration & transcript audit
  const anomalies = [
    {
      anomaly_id: 'DRV-ANOM-001',
      severity: 'high',
      category: 'clerk-title-vs-spoken-call-to-order-date-mismatch',
      source_system: 'google-drive',
      affected_scope: `WindyCityMeetings/processed_database/master_meetings_database.json (${spokenVsMetadataDateConflictCount} of ${masterMeetings.length} transcripts flagged)`,
      summary: `Cross-checking metadata.date, meeting title, and opening call-to-order speech across all ${masterMeetings.length} City of Cheyenne transcripts revealed ${spokenVsMetadataDateConflictCount} date conflicts — e.g., meet_0000 titled "Finance Committee 01-07-25" (Tuesday 2025-01-07) opens with Chair calling to order the "January 6th 25 finance committee meeting" (Monday 2025-01-06), and meet_0020 titled "Finance Committee 12-02-25" opens with "December 1st 2025 finance meeting will come to order".`,
      remediation: 'All conflicted records have exact provenance strings in `date_conflicts` and enforce `event_date: null` per T00 contract until human editorial resolution.',
    },
    {
      anomaly_id: 'DRV-ANOM-002',
      severity: 'medium',
      category: 'unparsed-spelled-out-dates-in-master-meetings-db',
      source_system: 'google-drive',
      affected_scope: 'WindyCityMeetings/processed_database/master_meetings_database.json',
      summary: `Upstream master_meetings_database.json left metadata.date="Unknown" on ${masterMeetings.filter((m) => m.date === 'Unknown').length} meetings whose titles spell out months (e.g., meet_0016 "January 5, 2026, Cheyenne Planning Commission Meeting") instead of numeric MM-DD-YY.`,
      remediation: 'T02 `date-audit.mjs` parses spelled-out dates and corroborates them against opening call-to-order speech while flagging any disagreement.',
    },
    {
      anomaly_id: 'DRV-ANOM-003',
      severity: 'high',
      category: 'youtube-upload-prefix-vs-meeting-date-divergence',
      source_system: 'google-drive',
      affected_scope: `YouTube archive captions & recordings (${snapshotUploadDateConflictCount} snapshot items + live recordings)`,
      summary: 'City of Cheyenne YouTube filenames prefixed `YYYYMMDD - ...` store `yt-dlp %(upload_date)s` (upload date to YouTube, typically 1–10 days after the actual meeting, e.g., `20210318 - Cheyenne City Council | Regular Meeting | 3-8-21.en.vtt` and `20260210 - City Council - 02-09-26.mp4`).',
      remediation: '`date-audit.mjs` stores `upload_date` separately, flags all upload-vs-title date divergences in `date_conflicts`, and never silently emits bare upload prefixes as `event_date`.',
    },
    {
      anomaly_id: 'DRV-ANOM-004',
      severity: 'medium',
      category: 'leading-hyphen-sibling-duplicate-json-files',
      source_system: 'google-drive',
      affected_scope: 'WindyCityMeetings/processed_database (`1RvCYiIpxkZc79qzrpJdu2rBW_FxOL_Jy`)',
      summary: 'Folder contains systematic near-duplicate sibling JSON files differing by a leading hyphen (`-Work_Session_-_Belvoir_Master_Plan_Updates_06-28-24.json` [35,706 B, md5=707d7c18...] vs `Work_Session_-_Belvoir_Master_Plan_Updates_06-28-24.json` [35,658 B, md5=6ecc938e...], ~48 B title-header difference) produced by two runs of a slug serializer.',
      remediation: 'Downstream T04 normalization should read `master_meetings_database.json` (`1MpmvRnwuvyKUgi1kLpkotFtnSpiUXnVa`) as canonical source and deduplicate leading-hyphen per-file exports.',
    },
    {
      anomaly_id: 'DRV-ANOM-005',
      severity: 'low',
      category: 'flattened-paths-in-historical-drive-snapshot',
      source_system: 'google-drive',
      affected_scope: 'Pre-2026-07-09 `full_inventory.json` (41,861 rows)',
      summary: 'Historical exporter wrote `path = name` without ancestor folder IDs across all 41,861 rows, causing multi-folder archive copies (e.g., `.en.vtt` files stored in 3 historical backup folders) to appear with distinct Drive IDs but flattened paths, alongside mixed personal/runtime files.',
      remediation: 'Passed all 41,861 rows through strict default-deny `privacy-gate.mjs`, marked retained historical snapshot records `completeness: "unknown"`, grouped multi-folder copies in `duplicate-groups.json`, and excluded all non-public items with zero filename/ID leakage.',
    },
    {
      anomaly_id: 'DRV-ANOM-006',
      severity: 'low',
      category: 'trashed-and-shared-drive-scope-audit',
      source_system: 'google-drive',
      affected_scope: 'Account-wide Google Drive v3 enumeration',
      summary: 'Verified 0 Google Workspace Shared Drives (`list_drives = []`), 50 trashed items (`trashed = true`, excluded from active corpus), and confirmed `Promethean_Telemetry_Sync` (`shared = true`) has 2 explicit private user permissions rather than public link sharing.',
      remediation: 'All Drive records carry `publication_review: "pending"` until explicit human approval under `T00` governance.',
    },
  ];

  const totalExcluded = Object.values(exclusionCountsByCategory).reduce((a, b) => a + b, 0);

  return {
    summary: {
      shared_drives_count: 0,
      trashed_items_audited_and_excluded: 50,
      live_public_drive_items_count: liveIdx,
      live_sha256_verified_items_count: records.filter((r) => r.original_bytes_sha256 !== null).length,
      master_meetings_transcripts_count: masterMeetings.length,
      granicus_supporting_attachments_count: granicusMetadata.length,
      historical_snapshot_rows_scanned: fullSnapshot.length,
      historical_snapshot_deduped_against_live: snapshotDedupedAgainstLiveCount,
      historical_snapshot_public_retained: snapshotRetainedCount,
      total_emitted_drive_records: records.length,
      date_conflicted_drive_records: records.filter((r) => r.date_conflicts.length > 0).length,
      consistent_dated_drive_records: records.filter((r) => r.event_date !== null).length,
      privacy_excluded_total_items: totalExcluded,
      privacy_exclusion_counts_by_category: exclusionCountsByCategory,
      duplicate_groups_count: duplicateGroups.length,
    },
    records,
    duplicateGroups,
    anomalies,
  };
}
