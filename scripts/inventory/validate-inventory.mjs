#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { assertZeroPrivacyLeaks } from './privacy-gate.mjs';
import { validateInventoryRecord } from './record-contract.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '../..');

export function validateInventoryDirectory(invDir = path.join(REPO_ROOT, 'catalog/inventory')) {
  const requiredFiles = [
    'inventory-summary.json',
    'github-inventory.json',
    'drive-inventory.json',
    'duplicate-groups.json',
    'anomaly-report.json',
    'inventory-report.md',
  ];

  for (const file of requiredFiles) {
    const p = path.join(invDir, file);
    if (!fs.existsSync(p)) {
      throw new Error(`Missing required inventory artifact: ${p}`);
    }
    const rawContent = fs.readFileSync(p, 'utf8');
    assertZeroPrivacyLeaks(rawContent, file);
  }

  const summary = JSON.parse(fs.readFileSync(path.join(invDir, 'inventory-summary.json'), 'utf8'));
  const gh = JSON.parse(fs.readFileSync(path.join(invDir, 'github-inventory.json'), 'utf8'));
  const drv = JSON.parse(fs.readFileSync(path.join(invDir, 'drive-inventory.json'), 'utf8'));
  const dups = JSON.parse(fs.readFileSync(path.join(invDir, 'duplicate-groups.json'), 'utf8'));
  const anoms = JSON.parse(fs.readFileSync(path.join(invDir, 'anomaly-report.json'), 'utf8'));

  if (!Array.isArray(gh.records) || gh.records.length !== summary.totals.github_records) {
    throw new Error(`GitHub record count mismatch: summary=${summary.totals.github_records}, actual=${gh.records?.length}`);
  }
  if (!Array.isArray(drv.records) || drv.records.length !== summary.totals.drive_records) {
    throw new Error(`Drive record count mismatch: summary=${summary.totals.drive_records}, actual=${drv.records?.length}`);
  }
  if (gh.records.length + drv.records.length !== summary.totals.canonical_public_records) {
    throw new Error('Grand total record count mismatch in inventory-summary.json');
  }
  if (!Array.isArray(dups.groups) || dups.groups.length !== summary.totals.duplicate_groups) {
    throw new Error('Duplicate group count mismatch');
  }
  if (!Array.isArray(anoms.anomalies) || anoms.anomalies.length !== summary.totals.anomalies) {
    throw new Error('Anomaly count mismatch');
  }

  // Enforce unique `record_id` and strict `validateInventoryRecord` compliance on every single record
  const seenIds = new Set();
  const allRecords = [...gh.records, ...drv.records];
  for (const rec of allRecords) {
    if (seenIds.has(rec.record_id)) {
      throw new Error(`Duplicate record_id detected: ${rec.record_id}`);
    }
    seenIds.add(rec.record_id);

    if (rec.access_class !== 'public') {
      throw new Error(`Non-public record serialized in public inventory: ${rec.record_id}`);
    }

    const res = validateInventoryRecord(rec);
    if (!res.valid) {
      throw new Error(`Record ${rec.record_id} failed contract validation: ${res.errors.join('; ')}`);
    }
  }

  return {
    validated_files: requiredFiles.length,
    validated_records: allRecords.length,
    github_records: gh.records.length,
    drive_records: drv.records.length,
    duplicate_groups: dups.groups.length,
    anomalies: anoms.anomalies.length,
    privacy_leaks: 0,
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  const targetDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(REPO_ROOT, 'catalog/inventory');
  const report = validateInventoryDirectory(targetDir);
  console.log('Inventory validation passed:', JSON.stringify(report, null, 2));
}
