'use strict';
const $ = id => document.getElementById(id);
const label = value => value.split('-').map(word => word[0].toUpperCase() + word.slice(1)).join(' ');
const localNow = () => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Denver', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date()).map(part => [part.type, part.value]));
  return { date: `${parts.year}-${parts.month}-${parts.day}`, minute: Number(parts.hour) * 60 + Number(parts.minute) };
};
let meetings = [], limit = 12, request = 0;
async function fetchWithTimeout(url, ms = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}
function meetingStatus(m) {
  const explicit = String(m.outcome_status || m.meeting_status || '').toLowerCase();
  if (/cancel/.test(explicit)) return 'Cancelled';
  if (/postpon/.test(explicit)) return 'Postponed';
  if (/minutes/.test(explicit)) return 'Minutes available';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(m.date)) return 'Date incomplete · status unknown';
  const now = localNow();
  const rawTime = m.local_time || m.time || '';
  const match = String(rawTime).trim().match(/^(\d{1,2}):(\d{2})\s*(am|pm)?$/i);
  let meetingMinute = null;
  if (match) {
    let hour = Number(match[1]);
    const minute = Number(match[2]);
    const meridiem = (match[3] || '').toLowerCase();
    if (minute < 60 && hour <= (meridiem ? 12 : 23) && hour >= (meridiem ? 1 : 0)) {
      if (meridiem === 'pm' && hour < 12) hour += 12;
      if (meridiem === 'am' && hour === 12) hour = 0;
      meetingMinute = hour * 60 + minute;
    }
  }
  if (m.date < now.date || (m.date === now.date && meetingMinute !== null && meetingMinute <= now.minute)) return 'Meeting date passed · outcome not yet verified';
  if (m.date === now.date) return 'Meeting date is today · completion not verified';
  return m.agenda_url ? 'Upcoming · agenda posted' : 'Upcoming · agenda not verified';
}
function render() {
  const query = $('search').value.trim().toLowerCase();
  const filtered = meetings.filter(m => (!$('body').value || m.body === $('body').value) && `${m.date} ${label(m.body)} ${m.topic || ''}`.toLowerCase().includes(query));
  $('status').textContent = `${filtered.length} matching catalog entries · showing ${Math.min(limit, filtered.length)}. Status labels are based on meeting dates and recorded outcome fields; unknown is not treated as upcoming.`;
  $('results').replaceChildren();
  for (const m of filtered.slice(0, limit)) {
    const row = document.createElement('article'); row.className = 'meeting';
    const heading = document.createElement('div');
    const date = document.createElement('time'); date.dateTime = /^\d{4}-\d{2}-\d{2}$/.test(m.date) ? m.date : ''; date.textContent = m.date;
    const title = document.createElement('h3'); title.textContent = m.topic || label(m.body);
    const badge = document.createElement('p'); badge.className = 'meeting-status'; badge.textContent = meetingStatus(m);
    heading.append(date, title, badge);
    const links = document.createElement('div'); links.className = 'meeting-links';
    const read = document.createElement('button'); read.type = 'button'; read.textContent = m.file ? 'Read transcript' : 'Transcript unavailable'; read.disabled = !m.file; read.setAttribute('aria-label', `${m.file ? 'Read' : 'Transcript unavailable for'} ${label(m.body)} ${m.date}`); read.onclick = () => openTranscript(m);
    const video = document.createElement('a'); video.href = `https://www.youtube.com/watch?v=${encodeURIComponent(m.youtube_id)}`; video.target = '_blank'; video.rel = 'noopener'; video.textContent = 'Source video ↗';
    links.append(read, video); row.append(heading, links); $('results').append(row);
  }
  if (!filtered.length) $('results').textContent = 'No meetings match these filters. Try another date or public body.';
  $('more').hidden = filtered.length <= limit;
}
async function openTranscript(m) {
  const ticket = ++request;
  $('reader').hidden = false; $('reader-title').textContent = `${m.topic || label(m.body)} · ${m.date}`;
  $('transcript').textContent = 'Loading transcript…';
  const path = `../cheyenne-2026-transcripts/${m.file.split('/').map(encodeURIComponent).join('/')}`;
  const sourceUrl = `https://www.youtube.com/watch?v=${encodeURIComponent(m.youtube_id)}`;
  $('download').href = path; $('prov-meeting').textContent = `${label(m.body)} · ${m.date}${m.topic ? ` · ${m.topic}` : ''}`;
  $('prov-hash').textContent = 'Calculating after load…'; $('prov-type').textContent = 'Timestamped caption transcript; individual caption source loading…';
  $('caption-warning').textContent = 'Caption transcript. Names, technical terminology, and quotations may contain errors. Check the linked recording before formal use. This transcript is not official minutes.';
  $('prov-source').replaceChildren(); const link = document.createElement('a'); link.href = sourceUrl; link.target = '_blank'; link.rel = 'noopener'; link.textContent = sourceUrl; $('prov-source').append(link);
  $('reader').focus(); $('reader').scrollIntoView();
  try {
    const response = await fetchWithTimeout(path); if (!response.ok) throw new Error('Unavailable');
    const text = await response.text(); if (ticket !== request) return;
    $('transcript').textContent = text;
    const captionLine = text.match(/\*\*Captions:\*\*\s*([^\n]+)/i);
    const captionSource = captionLine ? captionLine[1].trim() : 'caption source not individually recorded';
    $('prov-type').textContent = `Timestamped caption transcript · ${captionSource}`;
    const warningLead = /auto[- ]generated/i.test(captionSource) ? 'Automated captions.' : /human[- ]uploaded/i.test(captionSource) ? 'Human-uploaded captions.' : 'Caption transcript.';
    $('caption-warning').textContent = `${warningLead} Names, technical terminology, and quotations may contain errors. Check the linked recording before formal use. This transcript is not official minutes.`;
    if (window.crypto && crypto.subtle) {
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
      const hash = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
      if (ticket === request) $('prov-hash').textContent = hash;
    } else $('prov-hash').textContent = 'Browser cannot calculate SHA-256';
  } catch {
    if (ticket === request) $('transcript').textContent = 'Unable to load this transcript. Try the source Markdown link above or the source video in the catalog.';
  }
}
async function loadFreshness() {
  try {
    const response = await fetchWithTimeout('freshness.json'); if (!response.ok) throw new Error('Unavailable');
    const data = await response.json();
    const checkedRaw = data.meeting_information_last_checked;
    // Plain YYYY-MM-DD collection dates display as dates only (UTC).
    const timestamp = !checkedRaw ? 'Not recorded'
      : /^\d{4}-\d{2}-\d{2}$/.test(checkedRaw) ? new Date(checkedRaw).toLocaleDateString(undefined, { dateStyle: 'medium', timeZone: 'UTC' })
      : new Date(checkedRaw).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Denver' });
    $('home-checked').textContent = timestamp;
    $('home-indexed').textContent = data.latest_meeting_indexed ? `${data.latest_meeting_indexed} (catalog maximum)` : 'Not recorded';
    $('home-outcome').textContent = data.latest_verified_outcome || 'None documented as verified';
    $('home-gaps').textContent = `${data.known_gaps?.length || 0} known gaps · ` + (data.known_gaps?.[0] || 'See coverage page');
  } catch {
    $('home-checked').textContent = 'Not available; no build time substituted';
    $('home-indexed').textContent = 'Not available'; $('home-outcome').textContent = 'Not available'; $('home-gaps').textContent = 'See coverage page';
  }
}
$('close').onclick = () => { request++; $('reader').hidden = true; $('search').focus(); };
$('more').onclick = () => { limit += 12; render(); };
for (const id of ['search', 'body']) $(id).addEventListener(id === 'search' ? 'input' : 'change', () => { limit = 12; render(); });
loadFreshness();
(async () => {
  try {
    const response = await fetchWithTimeout('../cheyenne-2026-transcripts/meetings.json'); if (!response.ok) throw new Error('Unavailable');
    const data = await response.json();
    if (!Array.isArray(data)) throw new Error('Invalid catalog');
    meetings = data.filter(m => typeof m.date === 'string' && typeof m.body === 'string' && typeof m.youtube_id === 'string' && (m.file === null || typeof m.file === 'string') && (!m.file || /^[\w-]+\/[\w-]+\.md$/.test(m.file))).sort((a,b) => b.date.localeCompare(a.date));
    for (const body of [...new Set(meetings.map(m => m.body))].sort()) { const option = document.createElement('option'); option.value = body; option.textContent = label(body); $('body').append(option); }
    render();
  } catch { $('status').textContent = 'The catalog could not be loaded. Reload this page or browse the archive on GitHub using the link under Research tools.'; }
})();
