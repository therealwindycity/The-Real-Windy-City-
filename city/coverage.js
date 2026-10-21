'use strict';
(async () => {
  const $ = id => document.getElementById(id);
  const fmt = value => value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Denver' }) : 'Not recorded';
  async function fetchWithTimeout(url, ms = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    try {
      return await fetch(url, { signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }
  try {
    const [freshResponse, coverageResponse] = await Promise.all([fetchWithTimeout('freshness.json'), fetchWithTimeout('coverage.json')]);
    if (!freshResponse.ok || !coverageResponse.ok) throw new Error('Coverage data unavailable');
    const fresh = await freshResponse.json();
    const coverage = await coverageResponse.json();
    $('checked-at').textContent = fmt(fresh.meeting_information_last_checked);
    $('latest-indexed').textContent = `${fresh.latest_meeting_indexed || 'None recorded'} — catalog maximum; not a completeness claim.`;
    $('latest-outcome').textContent = fresh.latest_verified_outcome || 'None documented as verified';
    $('known-gaps').replaceChildren(...fresh.known_gaps.map(text => { const li = document.createElement('li'); li.textContent = text; return li; }));
    $('scope').textContent = coverage.scope;
    const definitions = {
      meetings_indexed: 'Meeting entries in the JSON catalog; not necessarily unique dates or complete meetings.',
      unique_document_contents: coverage.rules.unique_document_contents,
      stored_markdown_files: coverage.rules.stored_markdown_files,
      searchable_catalog_documents: coverage.rules.searchable_catalog_documents,
      caption_transcripts: coverage.rules.caption_transcripts,
      auto_generated_caption_transcripts: coverage.rules.auto_generated_caption_transcripts,
      other_or_unlabeled_caption_sources: coverage.rules.other_or_unlabeled_caption_sources,
      catalog_entries_without_transcript_file: 'Catalog entries without a corresponding transcript Markdown file.',
      audio_checked_excerpts: coverage.rules.audio_checked_excerpts,
      original_source_checks: coverage.rules.original_source_checks,
      image_review_or_ocr_pending: coverage.rules.image_review_or_ocr_pending
    };
    const labels = {
      meetings_indexed: 'Meetings indexed', unique_document_contents: 'Unique document contents', stored_markdown_files: 'Stored Markdown files',
      searchable_catalog_documents: 'Searchable catalog documents', caption_transcripts: 'Caption transcripts',
      auto_generated_caption_transcripts: 'Auto-generated caption transcripts', other_or_unlabeled_caption_sources: 'Other / unlabeled caption sources',
      catalog_entries_without_transcript_file: 'Catalog entries without transcript file', audio_checked_excerpts: 'Audio-checked excerpts',
      original_source_checks: 'Original-source checks', image_review_or_ocr_pending: 'Image-review / OCR pending'
    };
    $('metrics').replaceChildren(...Object.entries(coverage.metrics).map(([key, value]) => {
      const row = document.createElement('tr');
      for (const text of [labels[key] || key, value === null ? 'Not measured' : String(value), definitions[key] || 'See coverage index.']) {
        const cell = document.createElement('td'); cell.textContent = text; row.append(cell);
      }
      return row;
    }));
    $('count-note').textContent = coverage.verification_note;
  } catch {
    $('checked-at').textContent = 'Coverage status could not be loaded; no timestamp inferred.';
    $('latest-indexed').textContent = 'Not available'; $('latest-outcome').textContent = 'Not available';
    $('known-gaps').textContent = 'Freshness metadata unavailable.';
    $('metrics').textContent = 'Coverage data could not be loaded.';
  }
})();
