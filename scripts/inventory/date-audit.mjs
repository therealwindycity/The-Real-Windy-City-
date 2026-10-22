/**
 * Multi-signal date extraction and conflict audit for T02 inventory records.
 *
 * Enforces T00 contract rule:
 * - Never conflate YouTube upload dates (`YYYYMMDD - ` prefix), filename dates,
 *   structured database `date` metadata, and spoken call-to-order dates.
 * - Whenever two signals disagree (or a signal is internally ambiguous), record
 *   human-readable strings in `date_conflicts` AND set `event_date = null`.
 */

const MONTHS = {
  january: 1,
  february: 2,
  march: 3,
  april: 4,
  may: 5,
  june: 6,
  july: 7,
  august: 8,
  september: 9,
  october: 10,
  november: 11,
  december: 12,
};

const TEEN_WORDS = {
  thirteen: 2013,
  fourteen: 2014,
  fifteen: 2015,
  sixteen: 2016,
  seventeen: 2017,
  eighteen: 2018,
  een: 2018, // common Whisper ASR split: "2008 een" -> 2018
  nineteen: 2019,
};

export function isValidIsoCalendarDate(iso) {
  if (typeof iso !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return false;
  const [y, m, d] = iso.split('-').map(Number);
  if (y < 1970 || y > 2030 || m < 1 || m > 12 || d < 1 || d > 31) return false;
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

function buildIso(yearRaw, monthRaw, dayRaw) {
  const yearNum = Number(yearRaw) < 100 ? 2000 + Number(yearRaw) : Number(yearRaw);
  const monthNum = Number(monthRaw);
  const dayNum = Number(dayRaw);
  const iso = `${String(yearNum).padStart(4, '0')}-${String(monthNum).padStart(2, '0')}-${String(dayNum).padStart(2, '0')}`;
  return isValidIsoCalendarDate(iso) ? iso : null;
}

/**
 * Extract leading `YYYYMMDD - ` upload prefix (used by `yt-dlp %(upload_date)s`).
 */
export function extractUploadPrefixDate(filenameOrTitle) {
  const m = /^(20[0-2]\d)([01]\d)([0-3]\d)\s*-\s*/.exec(String(filenameOrTitle || '').trim());
  if (!m) return null;
  return buildIso(m[1], m[2], m[3]);
}

/**
 * Extract explicit calendar date embedded inside a meeting title or filename
 * AFTER stripping any leading `YYYYMMDD - ` YouTube upload prefix.
 */
export function extractTitleDate(titleOrFilename) {
  const stripped = String(titleOrFilename || '')
    .trim()
    .replace(/^20[0-2]\d[01]\d[0-3]\d\s*-\s*/, '')
    .replace(/\.(?:f\d+\.)?(?:en\.vtt|en-orig\.vtt|vtt|srt|txt|md|json|mp4|mp3|m4a|webm|pdf|html)$/i, '')
    .replace(/\u29f8/g, '/'); // fullwidth solidus `⧸` used by yt-dlp sanitizers

  // 1. Spelled-out date: "January 5, 2026" or "June 22 2026"
  const spelledRe = /\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,\s*|\s+)(20\d{2}|\d{2})\b/i;
  const sm = spelledRe.exec(stripped);
  if (sm) {
    const iso = buildIso(sm[3], MONTHS[sm[1].toLowerCase()], sm[2]);
    if (iso) return { date: iso, raw: sm[0] };
  }

  // 2. ISO date inside title: "2026-07-09"
  const isoRe = /\b(20[0-2]\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b/;
  const im = isoRe.exec(stripped);
  if (im) {
    const iso = buildIso(im[1], im[2], im[3]);
    if (iso) return { date: iso, raw: im[0] };
  }

  // 3. US numeric date with hyphens, slashes, or parenthesized/spaced tokens: "01-07-25", "3-8-21", "(5/25/21)", "02 13 23", "(2 12 18)"
  const usRe = /(?:^|[\s(_|-])(0?[1-9]|1[0-2])[-/\s](0?[1-9]|[12]\d|3[01])[-/\s](20[0-2]\d|\d{2})(?=$|[\s)_|.-])/;
  const um = usRe.exec(stripped);
  if (um) {
    const iso = buildIso(um[3], um[1], um[2]);
    if (iso) return { date: iso, raw: um[0].trim() };
  }

  return null;
}

/**
 * Extract spoken opening call-to-order date from the opening transcript turns.
 * Require explicit whitespace/comma before year so phrases like "January 2025"
 * never falsely split "2025" into day 20 + year 25.
 */
export function extractSpokenOpeningDate(openingText) {
  const head = String(openingText || '')
    .replace(/^#[^\n]*\n?/, '')
    .slice(0, 950);
  if (!head) return null;

  const spokenRe = /\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,\s*|\s+)(20\d{2}|\d{2})(?:\s+(een|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen))?(?:\s+or\s+(20\d{2}))?\b/gi;
  let match;
  while ((match = spokenRe.exec(head)) !== null) {
    const ctxStart = Math.max(0, match.index - 85);
    const ctxEnd = Math.min(head.length, match.index + match[0].length + 85);
    const ctx = head.slice(ctxStart, ctxEnd).replace(/\s+/g, ' ').trim();
    const isCallToOrder = /\b(?:welcome|calling\s+the\s+meeting|come\s+to\s+order|called\s+to\s+order|call\s+the\b.*?\bto\s+order|good\s+(?:morning|afternoon|evening)|today\s+is)\b/i.test(ctx);
    const isHistoricalCitation = /\b(?:approved\s+on|dated|ordinance|resolution|memorandum|minutes\s+of|last\s+month|prior\s+meeting|as\s+of)\b/i.test(
      head.slice(Math.max(0, match.index - 35), match.index)
    );
    if (!isCallToOrder || isHistoricalCitation) continue;

    if (match[5]) {
      return {
        date: null,
        ambiguous: true,
        raw: match[0],
        note: `Speaker self-corrected or stated ambiguous opening year ("${match[0]}") in call-to-order`,
      };
    }

    let yearVal = match[3];
    if (yearVal === '2008' && match[4] && TEEN_WORDS[match[4].toLowerCase()]) {
      yearVal = String(TEEN_WORDS[match[4].toLowerCase()]);
    }
    const iso = buildIso(yearVal, MONTHS[match[1].toLowerCase()], match[2]);
    if (iso) {
      return {
        date: iso,
        ambiguous: false,
        raw: match[0],
        asrNormalized: Boolean(match[4]),
      };
    }
  }

  return null;
}

/**
 * Audit all available date signals for an inventory record and enforce:
 *   if (date_conflicts.length > 0) => event_date MUST be null.
 */
export function resolveAuditedEventDate({
  metadataDate = null,
  title = '',
  filename = '',
  openingTranscriptText = '',
}) {
  const conflicts = [];
  const validMetaDate = isValidIsoCalendarDate(metadataDate) ? metadataDate : null;
  const uploadPrefixDate = extractUploadPrefixDate(filename) || extractUploadPrefixDate(title);
  const titleSignal = extractTitleDate(title) || extractTitleDate(filename);
  const spokenSignal = openingTranscriptText ? extractSpokenOpeningDate(openingTranscriptText) : null;

  if (spokenSignal?.ambiguous) {
    conflicts.push(spokenSignal.note);
  }

  // Gather candidate meeting dates (explicitly NOT treating bare YouTube upload prefix as event_date
  // unless corroborated or unconflicted — and flagging when upload_date differs from title/meeting date).
  const meetingSignals = [];
  if (validMetaDate) {
    meetingSignals.push({ source: 'metadata.date', date: validMetaDate });
  }
  if (titleSignal?.date) {
    meetingSignals.push({ source: `title("${titleSignal.raw}")`, date: titleSignal.date });
  }
  if (spokenSignal?.date) {
    meetingSignals.push({ source: `transcript_call_to_order("${spokenSignal.raw}")`, date: spokenSignal.date });
  }

  const distinctMeetingDates = [...new Set(meetingSignals.map((s) => s.date))];
  if (distinctMeetingDates.length > 1) {
    const detail = meetingSignals.map((s) => `${s.source}=${s.date}`).join(' vs ');
    conflicts.push(`Conflicting meeting date signals (${detail})`);
  }

  if (uploadPrefixDate && distinctMeetingDates.length === 1 && uploadPrefixDate !== distinctMeetingDates[0]) {
    conflicts.push(
      `Filename YouTube upload prefix (${uploadPrefixDate}) differs from embedded meeting date (${distinctMeetingDates[0]})`
    );
  } else if (uploadPrefixDate && distinctMeetingDates.length === 0) {
    // Only a `YYYYMMDD - ` YouTube upload prefix exists with no corroborating meeting date in title/body:
    // Do NOT misreport upload timestamp as event_date! Keep event_date = null and record upload_date separately.
    return {
      event_date: null,
      date_evidence: null,
      date_conflicts: [],
      upload_date: uploadPrefixDate,
      date_status: 'upload-date-only-unverified-event-date',
    };
  }

  if (conflicts.length > 0) {
    return {
      event_date: null,
      date_evidence: null,
      date_conflicts: conflicts,
      upload_date: uploadPrefixDate,
      date_status: 'conflicted',
    };
  }

  if (distinctMeetingDates.length === 1) {
    const sources = meetingSignals.map((s) => s.source).join(' + ');
    return {
      event_date: distinctMeetingDates[0],
      date_evidence: sources,
      date_conflicts: [],
      upload_date: uploadPrefixDate,
      date_status: 'consistent',
    };
  }

  return {
    event_date: null,
    date_evidence: null,
    date_conflicts: [],
    upload_date: uploadPrefixDate,
    date_status: 'unknown',
  };
}
