/* export.js — handoff packets, bundle export, CSV, and a tiny store-only ZIP writer */
'use strict';

const Handoff = { last: null, lastKind: null, scope: 'thread', threadId: null, themeId: null };

/* ---------------------------------------------------------------- zip (store) */
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(bytes) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
function makeZip(files) {
  // files: [{name, data: string|Uint8Array}]
  const enc = new TextEncoder();
  const chunks = [], central = [];
  let offset = 0;
  const push = (u8) => { chunks.push(u8); offset += u8.length; };
  for (const f of files) {
    const nameBytes = enc.encode(f.name);
    const data = typeof f.data === 'string' ? enc.encode(f.data) : f.data;
    const crc = crc32(data);
    const local = new Uint8Array(30 + nameBytes.length);
    const dv = new DataView(local.buffer);
    dv.setUint32(0, 0x04034b50, true);
    dv.setUint16(4, 20, true);
    dv.setUint16(6, 0, true);
    dv.setUint16(8, 0, true);          // store
    dv.setUint16(10, 0, true);
    dv.setUint16(12, 0x21, true);      // date
    dv.setUint32(14, crc, true);
    dv.setUint32(18, data.length, true);
    dv.setUint32(22, data.length, true);
    dv.setUint16(26, nameBytes.length, true);
    dv.setUint16(28, 0, true);
    local.set(nameBytes, 30);
    push(local); push(data);
    const cen = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(cen.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true); cv.setUint16(6, 20, true);
    cv.setUint16(8, 0, true); cv.setUint16(10, 0, true);
    cv.setUint16(12, 0, true); cv.setUint16(14, 0x21, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, data.length, true);
    cv.setUint32(24, data.length, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint32(42, 0, true);
    cen.set(nameBytes, 46);
    central.push(cen);
  }
  const centralStart = offset;
  for (const c of central) push(c);
  const end = new Uint8Array(22);
  const ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, files.length, true);
  ev.setUint16(10, files.length, true);
  ev.setUint32(12, offset - centralStart, true);
  ev.setUint32(16, centralStart, true);
  push(end);
  return new Blob(chunks, { type: 'application/zip' });
}

/* ---------------------------------------------------------------- redaction */
function redact(text) {
  return String(text || '')
    .replace(/[\w.+-]+@[\w-]+\.[\w.]+/g, '[email]')
    .replace(/\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g, '[phone]')
    .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[ssn]');
}

function opts() {
  return {
    transcript: $('#hoTranscript')?.checked ?? true,
    redact: $('#hoRedact')?.checked ?? false,
    cap: Math.max(500, +($('#hoCap')?.value || 6000)),
  };
}

/* ---------------------------------------------------------------- packet text */
function resumePrompt(thread, turns) {
  const o = opts();
  const clean = (s) => (o.redact ? redact(s) : s);
  const arts = (thread.artifacts || []).slice(0, 8)
    .map((a) => '- ' + a.name + (a.href ? ' — ' + a.href : '')).join('\n') || '- (none recorded)';
  const urls = (thread.urls || []).slice(0, 8).map((u) => '- ' + u).join('\n') || '- (none recorded)';
  const opens = (thread.open_threads || []).map((x) => '- ' + x).join('\n') || '- (none detected)';
  const last = turns[turns.length - 1] || {};
  return `You are resuming an existing work thread. Absorb the state below, then continue — do not restart from scratch.

## Thread
${threadTitle(thread)}  ·  theme: ${themeById(thread.theme).name}  ·  ${thread.turn_count} turns
Window: ${fmtDate(thread.start)} → ${fmtDate(thread.end)}
Progress when paused: ${thread.completeness.percent}% (${thread.completeness.label})
Status: ${thread.status} — ${thread.status_note || ''}

## Objective as last stated by the user
"${clean((thread.last_prompt || '').slice(0, 400))}"

## Where it stopped (final output)
${clean((last.output_excerpt || last.output || '').slice(0, 1200))}

## Open threads to resolve first
${opens}

## Artifacts produced so far
${arts}

## Source URLs
${urls}

## Completeness evidence
${(thread.completeness.reasons || []).slice(0, 6).map((r) => '- ' + r.signal + ' (' + (r.delta >= 0 ? '+' : '') + r.delta + ')').join('\n')}

## Your task
1. Confirm in one paragraph what state you have absorbed.
2. Resolve the open threads above in priority order.
3. Continue the work to completion, matching the established voice and formats.
4. End with a short changelog of what you added and the new completeness estimate.
`;
}

function packetMarkdown(thread, turns, o) {
  const clean = (s) => (o.redact ? redact(s) : s);
  const L = [];
  const add = (...x) => L.push(...x);
  add(`# Handoff — ${threadTitle(thread)}`, '');
  add(`- **Thread id:** \`${thread.id}\``);
  add(`- **Theme:** ${themeById(thread.theme).name}` + (thread.secondary_themes?.length ? ` (+ ${thread.secondary_themes.join(', ')})` : ''));
  add(`- **Turns:** ${thread.turn_count}  ·  **Characters produced:** ${fmtInt(thread.chars)}`);
  add(`- **Window:** ${fmtDate(thread.start)} → ${fmtDate(thread.end)}  (${thread.duration_hours} h)`);
  add(`- **Completeness:** ${thread.completeness.percent}% (${thread.completeness.label})`);
  add(`- **Status:** ${thread.status} — ${thread.status_note || ''}`);
  add(`- **Sources:** ${(thread.sources || []).join(', ')}`, '');
  add('## Resume prompt (paste into any capable agent)', '', '```text', resumePrompt(thread, turns), '```', '');
  if (thread.open_threads?.length) {
    add('## Open threads');
    for (const x of thread.open_threads) add('- [ ] ' + x);
    add('');
  }
  if (thread.artifacts?.length) {
    add('## Artifacts');
    for (const a of thread.artifacts) add(`- \`${a.name}\`` + (a.href ? ` — ${a.href}` : ''));
    add('');
  }
  if (thread.urls?.length) {
    add('## URLs');
    for (const u of thread.urls) add('- ' + u);
    add('');
  }
  add('## Completeness evidence');
  for (const r of thread.completeness.reasons || []) add(`- ${r.signal} (${r.delta >= 0 ? '+' : ''}${r.delta})`);
  add('', '## Turn timeline');
  for (const t of turns) {
    add('', `### ${String((t.turn_index ?? 0) + 1).padStart(3, '0')} · ${fmtDate(t.ts)} · ${t.kind || 'turn'}`);
    if (t.prompt) add('', '**Prompt**', '', '> ' + clean(t.prompt).replace(/\n/g, '\n> ').slice(0, 2000));
    const out = t.output || '';
    if (out) {
      if (o.transcript) {
        add('', '**Output**', '', clean(out.slice(0, o.cap)));
        if (out.length > o.cap) add('', `*…${fmtInt(out.length - o.cap)} characters trimmed from this turn (full text in data/threads/${thread.id}.json).*`);
      } else {
        add('', '**Output (excerpt)**', '', clean((t.output_excerpt || '').slice(0, 600)));
      }
    }
    if (t.choices?.length) {
      add('', '**Branches offered:**');
      for (const c of t.choices) add('- ' + c.label);
    }
  }
  add('', '---', `Generated ${new Date().toISOString()} by Paradox Atlas (local export).`);
  return L.join('\n');
}

function packetJSON(thread, turns, o) {
  const clean = (s) => (o.redact ? redact(s) : s);
  return JSON.stringify({
    kind: 'agent-handoff',
    version: 1,
    generated: new Date().toISOString(),
    scope: 'thread',
    thread: {
      ...thread,
      name: threadTitle(thread),
    },
    resume_prompt: resumePrompt(thread, turns),
    completeness: thread.completeness,
    open_threads: thread.open_threads,
    artifacts: thread.artifacts,
    urls: thread.urls,
    turns: turns.map((t) => ({
      ...t,
      prompt: clean(t.prompt),
      output: o.transcript ? clean((t.output || '').slice(0, o.cap)) : clean(t.output_excerpt || ''),
    })),
  }, null, 1);
}

/* ---------------------------------------------------------------- builders */
async function buildHandoff(scope, id) {
  Handoff.scope = scope || Handoff.scope;
  if (id) { if (scope === 'theme') Handoff.themeId = id; else Handoff.threadId = id; }
  const o = opts();
  const status = $('#hoStatus');
  const preview = $('#hoPreview');
  let files = [];
  let previewText = '';
  let downloadName = 'handoff';

  const scopeSel = $('#hoScope');
  if (scopeSel) scopeSel.value = Handoff.scope;

  if (Handoff.scope === 'thread') {
    const tid = Handoff.threadId || Atlas.sel.threadId || filteredThreads()[0]?.id;
    const thread = Atlas.threadsById.get(tid);
    if (!thread) { status.textContent = 'No thread selected.'; return; }
    Handoff.threadId = tid;
    if ($('#hoThread')) $('#hoThread').value = tid;
    const turns = await turnsOfThread(tid);
    const md = packetMarkdown(thread, turns, o);
    const json = packetJSON(thread, turns, o);
    previewText = resumePrompt(thread, turns);
    downloadName = 'handoff-' + thread.slug;
    files = [
      { name: `${thread.slug}.md`, data: md },
      { name: `${thread.slug}.json`, data: json },
      { name: 'RESUME-PROMPT.txt', data: previewText },
    ];
    status.textContent = `${thread.turn_count} turns · ${fmtInt(md.length)} chars of Markdown`;
  } else if (Handoff.scope === 'theme') {
    const tid = Handoff.themeId || $('#hoTheme')?.value || Atlas.data.themes[0].id;
    Handoff.themeId = tid;
    const theme = themeById(tid);
    const threads = filteredThreads().filter((t) => t.theme === tid)
      .sort((a, b) => b.completeness.percent - a.completeness.percent);
    const index = [`# Theme handoff — ${theme.name}`, '',
      `Threads: ${threads.length} · turns: ${fmtInt(threads.reduce((s, t) => s + t.turn_count, 0))}`, ''];
    const partial = [];
    for (const th of threads.slice(0, 40)) {
      index.push(`## ${threadTitle(th)} — ${th.completeness.percent}% (${th.status})`,
        `- id: \`${th.id}\` · turns: ${th.turn_count} · window: ${(th.start || '').slice(0, 10)} → ${(th.end || '').slice(0, 10)}`,
        `- open: ${(th.open_threads || []).slice(0, 2).join(' / ') || '—'}`, '');
      const turns = await turnsOfThread(th.id);
      partial.push({ name: `${th.slug}.md`, data: packetMarkdown(th, turns, { ...o, transcript: false }) });
      partial.push({ name: `${th.slug}.json`, data: packetJSON(th, turns, o) });
    }
    previewText = index.join('\n');
    downloadName = 'theme-' + tid;
    files = [{ name: 'INDEX.md', data: previewText }, ...partial];
    status.textContent = `${threads.length} threads queued (first 40 exported in full)`;
  } else if (Handoff.scope === 'queue') {
    const q = resumeQueue().slice(0, 25);
    const L = ['# Resume queue', '', 'Threads ranked by how much value resuming them recovers.', ''];
    const partial = [];
    for (const th of q) {
      L.push(`- **${threadTitle(th)}** — ${th.completeness.percent}% · ${th.status} · score ${th.resume_score}`,
        `  - ${(th.open_threads || [])[0] || th.status_note || ''}`);
      const turns = await turnsOfThread(th.id);
      partial.push({ name: `${th.slug}.md`, data: packetMarkdown(th, turns, { ...o, transcript: false }) });
    }
    previewText = L.join('\n');
    downloadName = 'resume-queue';
    files = [{ name: 'RESUME-QUEUE.md', data: previewText }, ...partial];
    status.textContent = `${q.length} threads in the queue`;
  } else {
    const L = ['# Paradox Atlas — full archive handoff', '',
      `Generated ${new Date().toISOString()}`, '',
      '## Inventory',
      `- Turns: ${fmtInt(Atlas.data.meta.counts.turns)}`,
      `- Threads: ${fmtInt(Atlas.data.meta.counts.threads)}`,
      `- Themes: ${Atlas.data.themes.length}`,
      `- Window: ${(Atlas.data.meta.date_range[0] || '').slice(0, 10)} → ${(Atlas.data.meta.date_range[1] || '').slice(0, 10)}`, '',
      '## Themes'];
    for (const t of Atlas.data.themes) {
      L.push(`### ${t.name} — ${t.completeness}% mean completeness (${fmtInt(t.turns)} turns)`, t.blurb,
        `Top vocabulary: ${(t.top_terms || []).slice(0, 12).join(', ')}`, '');
    }
    L.push('## Threads by resumability', '');
    const ranked = Atlas.data.threads.slice().sort((a, b) => b.resume_score - a.resume_score);
    for (const th of ranked) {
      L.push(`- ${th.completeness.percent}% · ${th.status} · **${threadTitle(th)}** (${th.turn_count}t, ${th.id}) — ${(th.open_threads || [])[0] || ''}`);
    }
    previewText = L.join('\n');
    downloadName = 'atlas-full';
    const partial = [];
    for (const th of ranked.slice(0, 60)) {
      const turns = await turnsOfThread(th.id);
      partial.push({ name: `${th.slug}.md`, data: packetMarkdown(th, turns, { ...o, transcript: false }) });
    }
    files = [{ name: 'README.md', data: previewText },
             { name: 'atlas-index.json', data: JSON.stringify(atlasIndexObject(), null, 1) },
             ...partial];
    status.textContent = `Full archive: ${ranked.length} threads (first 60 as packets)`;
  }

  Handoff.last = files;
  Handoff.lastKind = Handoff.scope;
  Handoff.previewText = previewText;
  if (preview) preview.value = previewText.slice(0, 20000);
  $('#hoCopy').disabled = false;
  $('#hoDownload').disabled = false;
  $('#hoCopyPrompt').disabled = false;
  $('#hoOpenStory').disabled = !(Handoff.scope === 'thread' && Handoff.threadId);
  toast('Packet built — ' + files.length + ' file(s)');
}

function atlasIndexObject() {
  return {
    kind: 'atlas-index', generated: new Date().toISOString(), meta: Atlas.data.meta,
    themes: Atlas.data.themes.map((t) => ({ id: t.id, name: t.name, blurb: t.blurb, turns: t.turns, completeness: t.completeness, top_terms: t.top_terms })),
    threads: Atlas.data.threads.map((t) => ({ id: t.id, name: threadTitle(t), theme: t.theme, status: t.status, turn_count: t.turn_count, completeness: t.completeness.percent, start: t.start, end: t.end, resume_score: t.resume_score, open_threads: t.open_threads })),
  };
}

function resumeQueue() {
  return Atlas.data.threads.slice()
    .filter((t) => t.status !== 'complete')
    .sort((a, b) => b.resume_score - a.resume_score);
}

/* ---------------------------------------------------------------- wiring */
function exportInit() {
  $('#hoBuild')?.addEventListener('click', () => buildHandoff($('#hoScope').value));
  $('#hoScope')?.addEventListener('change', (e) => { Handoff.scope = e.target.value; showcaseScope(); });
  $('#hoDownload')?.addEventListener('click', () => {
    if (!Handoff.last) return;
    if ($('#hoZip').checked) download(`paradox-atlas-${Handoff.scope}-${Date.now()}.zip`, makeZip(Handoff.last), 'application/zip');
    else download(Handoff.last[0].name, Handoff.last[0].data, 'text/plain');
  });
  $('#hoCopy')?.addEventListener('click', () => {
    const md = (Handoff.last || []).find((f) => f.name.endsWith('.md'));
    if (md) copy(String(md.data).slice(0, 200000));
  });
  $('#hoCopyPrompt')?.addEventListener('click', () => copy(Handoff.previewText || ''));
  $('#hoOpenStory')?.addEventListener('click', () => Handoff.threadId && openStory(Handoff.threadId, 0));
  $('#hoThread')?.addEventListener('change', (e) => { Handoff.threadId = e.target.value; if (Handoff.scope === 'thread') buildHandoff('thread'); });
  $('#hoTheme')?.addEventListener('change', (e) => { Handoff.themeId = e.target.value; if (Handoff.scope === 'theme') buildHandoff('theme'); });
  $('#dlAtlas')?.addEventListener('click', () => download('atlas.json', JSON.stringify(Atlas.data), 'application/json'));
  $('#dlIndex')?.addEventListener('click', () => download('atlas-index.json', JSON.stringify(atlasIndexObject(), null, 1), 'application/json'));
  $('#dlInventory')?.addEventListener('click', () => download('inventory.json', JSON.stringify(Atlas.inventory || {}, null, 1), 'application/json'));
  $('#dlTurns')?.addEventListener('click', () => downloadTurnsCsv());
}

function showcaseScope() {
  const scope = $('#hoScope').value;
  $('#hoThread').disabled = scope !== 'thread';
  $('#hoTheme').disabled = scope !== 'theme';
}

function renderHandoffSelectors() {
  const ts = $('#hoThread');
  if (ts && !ts.options.length) {
    for (const th of Atlas.data.threads.slice().sort((a, b) => b.resume_score - a.resume_score)) {
      ts.append(el('option', { value: th.id }, `${th.completeness.percent}% · ${th.status} · ${threadTitle(th)} (${th.turn_count}t)`));
    }
  }
  const ths = $('#hoTheme');
  if (ths && !ths.options.length) {
    for (const t of Atlas.data.themes) ths.append(el('option', { value: t.id }, `${t.name} (${t.turns} turns, ${t.completeness}%)`));
  }
  const files = $('#hoFiles');
  if (files && !files.dataset.done) {
    files.dataset.done = '1';
    files.innerHTML = '';
    const ranked = Atlas.data.threads.slice().sort((a, b) => b.resume_score - a.resume_score).slice(0, 12);
    if (Lock.active) {
      // The packets on disk are ciphertext: decrypt on demand, never link them raw.
      files.append(el('p', { class: 'small muted', style: 'margin:0 0 6px' },
        'Pre-built packets are encrypted on disk — clicking one decrypts it into your downloads.'));
    }
    for (const th of ranked) {
      const row = el('div', { style: 'margin:4px 0' });
      if (Lock.active) {
        row.append(el('a', {
          href: '#',
          onclick: async (e) => {
            e.preventDefault();
            try { await Lock.downloadExport(th.slug + '.md', th.slug + '.md'); }
            catch { toast('Could not decrypt that packet'); }
          },
        }, th.slug + '.md'));
      } else {
        row.append(el('a', { href: `exports/${th.slug}.md`, target: '_blank', rel: 'noopener' }, th.slug + '.md'));
      }
      row.append(el('span', { class: 'muted' }, `  ${th.completeness.percent}% · ${th.status}`));
      files.append(row);
    }
  }
  showcaseScope();
}

function downloadTurnsCsv() {
  const rows = filteredTurns();
  const head = ['ts_utc', 'local_stamp', 'theme', 'thread_id', 'thread_name', 'status', 'completeness_pct',
                'source', 'kind', 'output_chars', 'artifacts', 'urls', 'prompt', 'output_excerpt'];
  const esc2 = (s) => '"' + String(s ?? '').replace(/"/g, '""').replace(/\r?\n/g, ' ') + '"';
  const lines = [head.join(',')];
  for (const t of rows) {
    const th = Atlas.threadsById.get(t.thread) || {};
    lines.push([
      t.ts, t.ts_raw, t.theme, t.thread, threadTitle({ id: t.thread, name: th.name || t.thread }),
      th.status, t.completeness_pct, t.source, t.kind, t.output_chars,
      (t.artifacts || []).map((a) => a.name).join(' | '),
      (t.urls || []).join(' | '), t.prompt, t.output_excerpt,
    ].map(esc2).join(','));
  }
  download('atlas-turns.csv', lines.join('\n'), 'text/csv');
}
