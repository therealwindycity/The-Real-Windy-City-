'use strict';
const $ = id => document.getElementById(id);
const label = value => value.split('-').map(word => word[0].toUpperCase() + word.slice(1)).join(' ');
let meetings = [], limit = 12, request = 0;
function render() {
  const query = $('search').value.trim().toLowerCase();
  const filtered = meetings.filter(m => (!$('body').value || m.body === $('body').value) && `${m.date} ${label(m.body)}`.toLowerCase().includes(query));
  $('status').textContent = `${filtered.length} matching meetings · showing ${Math.min(limit, filtered.length)}. Latest catalog entry: ${meetings[0]?.date || 'none'}.`;
  $('results').replaceChildren();
  for (const m of filtered.slice(0, limit)) {
    const row = document.createElement('article'); row.className = 'meeting';
    const heading = document.createElement('div');
    const date = document.createElement('time'); date.dateTime = m.date; date.textContent = m.date;
    const title = document.createElement('h3'); title.textContent = label(m.body);
    heading.append(date, title);
    const links = document.createElement('div'); links.className = 'meeting-links';
    const read = document.createElement('button'); read.type = 'button'; read.textContent = 'Read transcript'; read.setAttribute('aria-label', `Read ${label(m.body)} transcript for ${m.date}`); read.onclick = () => openTranscript(m);
    const video = document.createElement('a'); video.href = `https://www.youtube.com/watch?v=${encodeURIComponent(m.youtube_id)}`; video.textContent = 'Source video ↗';
    links.append(read, video); row.append(heading, links); $('results').append(row);
  }
  if (!filtered.length) $('results').textContent = 'No meetings match these filters. Try another date or public body.';
  $('more').hidden = filtered.length <= limit;
}
async function openTranscript(m) {
  const ticket = ++request;
  $('reader').hidden = false; $('reader-title').textContent = `${label(m.body)} · ${m.date}`;
  $('transcript').textContent = 'Loading transcript…';
  const path = `../cheyenne-2026-transcripts/${m.file.split('/').map(encodeURIComponent).join('/')}`;
  $('download').href = path; $('reader').focus(); $('reader').scrollIntoView();
  try {
    const response = await fetch(path); if (!response.ok) throw new Error('Unavailable');
    const text = await response.text(); if (ticket === request) $('transcript').textContent = text;
  } catch { if (ticket === request) $('transcript').textContent = 'Unable to load this transcript. Try the source Markdown link above or the source video in the catalog.'; }
}
$('close').onclick = () => { request++; $('reader').hidden = true; $('search').focus(); };
$('more').onclick = () => { limit += 12; render(); };
for (const id of ['search', 'body']) $(id).addEventListener(id === 'search' ? 'input' : 'change', () => { limit = 12; render(); });
(async () => {
  try {
    const response = await fetch('../cheyenne-2026-transcripts/meetings.json'); if (!response.ok) throw new Error('Unavailable');
    const data = await response.json();
    if (!Array.isArray(data)) throw new Error('Invalid catalog');
    meetings = data.filter(m => typeof m.date === 'string' && typeof m.body === 'string' && typeof m.youtube_id === 'string' && typeof m.file === 'string' && /^[\w-]+\/[\w-]+\.md$/.test(m.file)).sort((a,b) => b.date.localeCompare(a.date));
    for (const body of [...new Set(meetings.map(m => m.body))].sort()) { const option = document.createElement('option'); option.value = body; option.textContent = label(body); $('body').append(option); }
    render();
  } catch { $('status').textContent = 'The catalog could not be loaded. Reload this page or browse the archive on GitHub using the link under Research tools.'; }
})();
