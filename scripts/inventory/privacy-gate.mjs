import crypto from 'node:crypto';

/**
 * Strict default-deny privacy classification gate and output leak scanner for T02.
 *
 * CRITICAL REDLINE: `therealwindycity/TheReelWindyCity` is a public GitHub repository.
 * Private filenames, personal legal dockets, identities, email addresses, credentials,
 * browser profile artifacts, Google Takeout dumps, and non-public Drive file IDs MUST
 * NEVER appear anywhere in committed source code, JSON inventories, reports, tests, or handoffs.
 *
 * Workspace-specific personal/litigation/minor bigrams are matched strictly by irreversible
 * SHA-256 digest so zero private personal strings appear even inside this gate file itself.
 */

export const REDLINE_STRUCTURAL_PATTERNS = [
  // Court docket case numbers and personal litigation filings
  { category: 'private-litigation-or-identity', pattern: /\b20\d{2}-(?:com|cv|cr|dr|jv|pr)-\d+\b/i },
  { category: 'private-litigation-or-identity', pattern: /\b(?:motion\s+to\s+suppress|motion\s+to\s+intervene|suppression\s+hearing|monell\s+liability|revocable\s+trust|pro\s+se\s+legal)\b/i },
  // Youth / student-identifiable items (while preserving official Juvenile Justice policy boards/agreements)
  { category: 'minor-or-student-privacy', pattern: /\b(?:teens?\s+take|juvenile\s+(?:case|court|docket|record|offender|detainee)|minor\s+victim|ferpa|student\s+roster)\b/i },
  // Secrets, credentials, browser profiles, and personal archive dumps
  { category: 'credentials-or-secrets', pattern: /\b(?:refresh[_-]?token|client[_-]?secret|private[_-]?key|id_rsa|credentials\.json|cookies\.sqlite|login\s+data)\b/i },
  { category: 'browser-or-archive-export', pattern: /\b(?:takeout|whatsapp|imessage|signal[_ -]?backup|chrome[_ -]?history|browser[_ -]?history|bookmarks?\.html)\b/i },
  { category: 'personal-financial-medical-or-hr', pattern: /\b(?:w-?2\b|1099\b|tax[_ -]?return|medical[_ -]?record|hipaa|passport|ssn\b|social[_ -]?security|curriculum[_ -]?vitae)\b/i },
  // Personal email addresses
  { category: 'email-address', pattern: /[a-z0-9._%+-]+@(?:gmail|yahoo|hotmail|outlook|proton|icloud|aol|live|msn)\.[a-z]{2,}/i },
];

// Irreversible SHA-256 digests of workspace-specific private/litigation/minor 2-grams
const BLOCKED_BIGRAM_SHA256 = new Set([
  '3d6ce1f4f8352162d8d5139cb5cdb40d9e77b1e53c8167d15726410d677957a7',
  '559fca7636cfecf7697629f49dfb411092987a09f371aa463a2f8bb246108b1e',
  '4760cd226ca18b3b960115d3456c7981b7081b56c400590a83191a1e5fac44c9',
  '8c3fab185f5404a4bb3e7d228607d358962c4d5fcc84466ab0cc92cb6ad668c6',
  '39b124453c60a3a330966b7b44f63f6efb267324865db59df9b3d9a8b8e1f151',
  'fe6eca2dadb1ec76955d666a65058a24998bff2ec9c8f59dc51711639cf4cc47',
  'c16bfc355f2a88ebe5476bc1d32d2572e4e993bf97e0110a62c576f9abbef640',
  '38b18bc40ad0fc1a9254096964dccc82cd50c753bd197ef755044f12c6e03195',
  '0e2454b19fd4231a6a88a2e46b222fbdbbe700b5037e4d0b044fd54ebc786dd5',
  '97e25c03bd4a8530fa5fb3c99333e09367cdb0d66a9dff3337fc53dd936286a9',
  'f154d09988ee9da22b26f55ece3dd70acc9e1d65baf34505140ce19147bb54cb',
  '67f1257e1dde096a7e151573bdff121844604f7f65fd46c88fff02b95ca8eea2',
  '99392ef1ee7dd41fa97bf1a3a66f5b5fc3b7bc730da55db1baf29f06a71aa3c4',
]);

function hasBlockedBigramDigest(text) {
  const words = String(text || '').toLowerCase().match(/[a-z0-9]+/g);
  if (!words || words.length < 2) return false;
  for (let i = 0; i < words.length - 1; i += 1) {
    const digest = crypto.createHash('sha256').update(`${words[i]} ${words[i + 1]}`, 'utf8').digest('hex');
    if (BLOCKED_BIGRAM_SHA256.has(digest)) {
      return true;
    }
  }
  return false;
}

export const VENV_AND_RUNTIME_NOISE_PATTERNS = [
  /(?:^|[\\/])(?:\.venv|venv|__pycache__|site-packages|dist-packages|node_modules|\.git|\.mypy_cache|\.pytest_cache)(?:[\\/]|$)/i,
  /\.(?:pyc|pyo|pyd|so|dll|dylib|whl|egg-info|dist-info)$/i,
  /^(?:__init__|_version|conftest|setup|pip|wheel|pkg_resources)\.(?:py|cfg|toml)$/i,
];

export const KNOWN_PUBLIC_CIVIC_FOLDER_NAMES = new Set([
  'Promethean_Telemetry_Sync',
  'Granicus_Docs',
  'cheyenne-granicus-metadata-bundle',
  'transcripts',
  'WindyCityMeetings',
  'processed_database',
  '2026_Cheyenne_Gov_Archive_Final',
  'Application and Permits',
  'Archive_Backup_2026-07-09',
  'Cheyenne_Total_Archive_Project',
  'Cheyenne_RAG_DB',
  'Website',
  'YouTube_Transcripts',
  'YouTube_Transcripts_Cleaned',
  'YouTube_Transcripts_Cleaned_2026',
  'YouTube_Transcripts_EXTRACTED',
  'June_22_City_Council_Meeting',
]);

export const EXPLICIT_PUBLIC_CIVIC_FILENAME_PATTERNS = [
  /^Granicus_(?:Attach_)?\d+_.*\.(?:html|pdf|docx?|xlsx?|csv|txt|json)$/i,
  /^Cheyenne_(?:Municipal|Omni)_(?:Corpus_)?Shard_\d+\.md$/i,
  /^master_meetings_database(?:_linked)?\.json$/i,
  /^metadata_database\.jsonl?$/i,
  /^-?(?:City_Council|Finance_Committee|Public_Services(?:_Committee)?|Planning_Commission|Governing_Body|Work_Session|Goal_Setting|Special_Meeting|Board_of_Public_Utilities|Cheyenne_City_Council|Urban_Renewal|Board_of_Adjustment|Historic_Preservation)(?:[ _-].*)?\.(?:md|txt|json|pdf|html|vtt|srt|mp4|mp3|m4a|webm)$/i,
  /^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2},\s+Cheyenne\s+.*\.(?:mp4|mp3|m4a|vtt|md|txt|json|pdf)$/i,
];

const YOUTUBE_DATED_MEDIA_RE = /^(20[0-2]\d[01]\d[0-3]\d)\s*-\s*(.+?)\.(?:f\d+\.)?(?:en\.vtt|en-orig\.vtt|vtt|srt|txt|md|json|mp4|mp3|m4a|webm)$/i;

const EXPLICIT_CIVIC_YOUTUBE_TOPIC_RE = /\b(?:cheyenne|city\s+council|finance\s+committee|public\s+services?|planning\s+commission|governing\s+body|work\s+session|goal\s+setting|special\s+meeting|mayor|bopu|board\s+of\s+public\s+utilities|board\s+of\s+adjustment|urban\s+renewal|historic\s+preservation|6th\s+penny|ctac|ordinance|annexation|fy\s*20\d{2}\s*budget|budget\s+overview|liquor\s+license|capitol\s+north|laramie\s+county|council\s+update)\b/i;

/**
 * Normalize a meeting/video title stem so YouTube caption/audio files from the official
 * City of Cheyenne channel match known `master_meetings_database.json` stems cleanly.
 */
export function normalizeCivicStem(value) {
  return String(value || '')
    .replace(/^(?:20[0-2]\d[01]\d[0-3]\d)\s*-\s*/, '')
    .replace(/\.(?:f\d+\.)?(?:en\.vtt|en-orig\.vtt|vtt|srt|txt|md|json|mp4|mp3|m4a|webm)$/i, '')
    .replace(/^[-_\s]+/, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/**
 * Classify a Drive candidate item under default-deny public-civic governance.
 *
 * Returns `{ allowed: boolean, access_class, publication_review, exclusion_category }`.
 */
export function classifyDriveCandidate(candidate, canonicalMeetingStems = new Set()) {
  const name = String(candidate?.name || '').trim();
  const pathStr = String(candidate?.path || '').trim();
  const combined = `${name}\n${pathStr}`;

  if (!name) {
    return {
      allowed: false,
      access_class: 'private',
      publication_review: 'blocked',
      exclusion_category: 'empty-or-malformed-metadata',
    };
  }

  for (const { category, pattern } of REDLINE_STRUCTURAL_PATTERNS) {
    if (pattern.test(combined)) {
      return {
        allowed: false,
        access_class: category === 'minor-or-student-privacy' ? 'restricted' : 'private',
        publication_review: 'blocked',
        exclusion_category: category,
      };
    }
  }

  if (hasBlockedBigramDigest(combined)) {
    return {
      allowed: false,
      access_class: 'private',
      publication_review: 'blocked',
      exclusion_category: 'private-litigation-or-identity',
    };
  }

  for (const noiseRe of VENV_AND_RUNTIME_NOISE_PATTERNS) {
    if (noiseRe.test(combined)) {
      return {
        allowed: false,
        access_class: 'private',
        publication_review: 'blocked',
        exclusion_category: 'venv-or-package-runtime-noise',
      };
    }
  }

  if (candidate?.trusted_public_scope === true) {
    return {
      allowed: true,
      access_class: 'public',
      publication_review: 'pending',
      exclusion_category: null,
    };
  }

  if (KNOWN_PUBLIC_CIVIC_FOLDER_NAMES.has(name)) {
    return {
      allowed: true,
      access_class: 'public',
      publication_review: 'pending',
      exclusion_category: null,
    };
  }

  if (EXPLICIT_PUBLIC_CIVIC_FILENAME_PATTERNS.some((rx) => rx.test(name))) {
    return {
      allowed: true,
      access_class: 'public',
      publication_review: 'pending',
      exclusion_category: null,
    };
  }

  const ytMatch = YOUTUBE_DATED_MEDIA_RE.exec(name);
  if (ytMatch) {
    const titlePart = ytMatch[2];
    const stem = normalizeCivicStem(titlePart);
    if (EXPLICIT_CIVIC_YOUTUBE_TOPIC_RE.test(titlePart) || canonicalMeetingStems.has(stem)) {
      return {
        allowed: true,
        access_class: 'public',
        publication_review: 'pending',
        exclusion_category: null,
      };
    }
    return {
      allowed: false,
      access_class: 'private',
      publication_review: 'blocked',
      exclusion_category: 'non-civic-or-unverified-youtube-download',
    };
  }

  return {
    allowed: false,
    access_class: 'private',
    publication_review: 'blocked',
    exclusion_category: 'default-deny-unverified-drive-item',
  };
}

/**
 * Scan serialized text (JSON or Markdown) before writing to disk to guarantee
 * zero leakage of private litigation identifiers, personal names, emails, or secrets.
 */
export function scanTextForPrivacyLeaks(content, label = 'output') {
  const findings = [];
  const text = String(content || '');

  for (const { category, pattern } of REDLINE_STRUCTURAL_PATTERNS) {
    const match = pattern.exec(text);
    if (match) {
      findings.push({
        label,
        category,
        offset: match.index,
      });
    }
  }

  if (hasBlockedBigramDigest(text)) {
    findings.push({
      label,
      category: 'private-litigation-or-identity-digest',
      offset: 0,
    });
  }

  return findings;
}

/**
 * Fail closed if any serialized output contains any redline privacy leak.
 */
export function assertZeroPrivacyLeaks(content, label = 'output') {
  const leaks = scanTextForPrivacyLeaks(content, label);
  if (leaks.length > 0) {
    const summary = leaks.map((item) => `${item.label}:${item.category}@${item.offset}`).join(', ');
    throw new Error(`PRIVACY REDLINE VIOLATION blocked before write (${summary})`);
  }
}
