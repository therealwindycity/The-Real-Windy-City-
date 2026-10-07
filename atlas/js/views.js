/* views.js — timeline, ledger, coverage */
'use strict';

/* ---------------------------------------------------------------- timeline */
const Timeline = { group: 'month', sort: 'desc', page: 1, perPage: 250 };

function renderTimeline() {
  const turns = filteredTurns().slice().sort((a, b) =>
    Timeline.sort === 'desc' ? (b.ts || '').localeCompare(a.ts || '') : (a.ts || '').localeCompare(b.ts || ''));
  const host = $('#tlBody');
  host.innerHTML = '';
  $('#tlCount').textContent = `${fmtInt(turns.length)} turns match the current filters`;
  if (!turns.length) { host.append(el('div', { class: 'empty' }, 'Nothing matches. Loosen the filters or clear the search.')); return; }

  const groups = new Map();
  for (const t of turns) {
    if (!t.ts) continue;
    const d = new Date(t.ts);
    let key;
    if (Timeline.group === 'day') key = d.toISOString().slice(0, 10);
    else if (Timeline.group === 'week') {
      const wd = new Date(d); wd.setUTCDate(wd.getUTCDate() - wd.getUTCDay());
      key = 'week of ' + wd.toISOString().slice(0, 10);
    } else key = d.toISOString().slice(0, 7);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(t);
  }
  const keys = [...groups.keys()].sort((a, b) => Timeline.sort === 'desc' ? b.localeCompare(a) : a.localeCompare(b));
  let rendered = 0;
  for (const key of keys) {
    const g = el('div', { class: 'tl-group' }, el('h3', {}, prettyKey(key) + ` · ${groups.get(key).length} turns`));
    for (const t of groups.get(key)) {
      if (rendered++ > Timeline.perPage * Timeline.page) break;
      const th = Atlas.threadsById.get(t.thread);
      const color = themeById(t.theme).color;
      const row = el('div', { class: 'tl-row' },
        el('div', { class: 'tl-time' }, `${(t.time || '')} · ${t.tz || 'UTC'}`, el('div', {}, relTime(t.ts, Atlas.now))),
        el('div', { class: 'tl-line' }, el('div', { class: 'tl-dot', style: `background:${color}` })),
        el('div', { class: 'tl-body', onclick: () => openDrawer(t.id) },
          el('div', { class: 'row', style: 'gap:8px' },
            el('span', { class: 'tl-prompt' }, (t.prompt || t.title || '(document)').slice(0, 190)),
            th ? el('span', { class: 'tag' }, `${th.completeness.percent}% · ${th.status}`) : null,
            el('span', { class: 'tag' }, t.source || ''),
          ),
          t.output_excerpt ? el('div', { class: 'tl-out' }, t.output_excerpt) : null,
          el('div', { class: 'row small muted', style: 'gap:8px;margin-top:4px' },
            el('span', {}, fmtInt(t.output_chars) + ' chars out'),
            t.artifacts?.length ? el('span', {}, '⧉ ' + t.artifacts.map((a) => a.name).slice(0, 3).join(', ')) : null,
            t.urls?.length ? el('span', {}, '🔗 ' + t.urls.length) : null,
            t.choices?.length ? el('span', { style: 'color:var(--violet)' }, '⤳ ' + t.choices.length + ' branches') : null,
            th ? el('span', {}, threadTitle(th)) : null,
          ),
        ));
      g.append(row);
    }
    host.append(g);
    if (rendered > Timeline.perPage * Timeline.page) break;
  }
  if (rendered > Timeline.perPage * Timeline.page) {
    host.append(el('button', { class: 'btn', onclick: () => { Timeline.page++; renderTimeline(); } }, 'Load more turns…'));
  }
}
function prettyKey(key) {
  if (key.startsWith('week of')) return key;
  if (key.length === 7) {
    const [y, m] = key.split('-');
    return new Date(Date.UTC(+y, +m - 1, 1)).toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  }
  return new Date(key + 'T00:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

/* ---------------------------------------------------------------- ledger */
const Ledger = { sort: 'ts', dir: -1, page: 1, perPage: 400, text: '' };

function renderLedger() {
  let rows = filteredTurns();
  if (Ledger.text) {
    const q = Ledger.text.toLowerCase();
    rows = rows.filter((t) => (t.prompt + (t.output_excerpt || '') + t.thread + t.theme + (t.artifacts || []).map((a) => a.name).join(' ')).toLowerCase().includes(q));
  }
  const key = (t) => {
    switch (Ledger.sort) {
      case 'ts': return t.ts || '';
      case 'theme': return t.theme;
      case 'thread': return threadTitle(Atlas.threadsById.get(t.thread) || { name: t.thread });
      case 'pct': return t.completeness_pct ?? 0;
      case 'chars': return t.output_chars || 0;
      case 'prompt': return (t.prompt || '').toLowerCase();
      case 'artifacts': return (t.artifacts || []).length;
      case 'urls': return (t.urls || []).length;
      case 'media': return t.media_count || 0;
      default: return t.ts || '';
    }
  };
  rows.sort((a, b) => {
    const ka = key(a), kb = key(b);
    if (ka < kb) return -Ledger.dir;
    if (ka > kb) return Ledger.dir;
    return 0;
  });
  const table = $('#ledgerTable');
  table.innerHTML = '';
  const cols = [['ts', 'When'], ['theme', 'Theme'], ['thread', 'Thread'], ['prompt', 'Prompt'],
                ['chars', 'Chars out'], ['pct', 'Complete'], ['artifacts', 'Artifacts'], ['urls', 'Links'], ['media', 'Media']];
  const head = el('tr', {});
  for (const [id, label] of cols) {
    head.append(el('th', {
      onclick: () => { if (Ledger.sort === id) Ledger.dir *= -1; else { Ledger.sort = id; Ledger.dir = -1; } renderLedger(); },
    }, label + (Ledger.sort === id ? (Ledger.dir > 0 ? ' ▲' : ' ▼') : '')));
  }
  table.append(el('thead', {}, head));
  const body = el('tbody');
  const slice = rows.slice(0, Ledger.perPage * Ledger.page);
  for (const t of slice) {
    const th = Atlas.threadsById.get(t.thread);
    const tr = el('tr', { style: 'cursor:pointer', onclick: () => openDrawer(t.id) },
      el('td', { class: 'nowrap mono small' }, (t.date || '') + ' ' + (t.time || '')),
      el('td', {}, el('span', { class: 'dot', style: `background:${themeById(t.theme).color};display:inline-block;margin-right:5px` }), themeById(t.theme).name.split(',')[0]),
      el('td', { class: 'nowrap small' }, th ? threadTitle(th) : t.thread),
      el('td', {}, el('div', { class: 'tbltrunc' }, t.prompt_excerpt || t.title || '')),
      el('td', { class: 'num' }, fmtInt(t.output_chars)),
      el('td', { class: 'num' }, (t.completeness_pct ?? 0) + '%'),
      el('td', { class: 'num' }, (t.artifacts || []).length),
      el('td', { class: 'num' }, (t.urls || []).length),
      el('td', { class: 'num' }, t.media_count || 0),
    );
    body.append(tr);
  }
  table.append(body);
  $('#ledgerCount').textContent = `${fmtInt(rows.length)} rows · showing ${fmtInt(slice.length)}`;
  if (rows.length > slice.length) {
    table.append(el('tfoot', {}, el('tr', {}, el('td', { colspan: 9, style: 'text-align:center' },
      el('button', { class: 'btn sm', onclick: () => { Ledger.page++; renderLedger(); } }, 'Load more…')))));
  }
}

/* ---------------------------------------------------------------- coverage */
function renderCoverage() {
  const host = $('#coverageBody');
  host.innerHTML = '';
  const meta = Atlas.data.meta;

  host.append(el('div', { class: 'grid2' },
    card('What this archive reads', [
      ['Turns indexed', fmtInt(meta.counts.turns)],
      ['Prompts', fmtInt(meta.counts.prompts)],
      ['Document outputs', fmtInt(meta.counts.documents)],
      ['Threads reconstructed', fmtInt(meta.counts.threads)],
      ['Characters of output', fmtInt(meta.counts.chars)],
      ['Distinct URLs', fmtInt(meta.counts.urls)],
      ['Artifacts referenced', fmtInt(meta.counts.artifacts)],
      ['Window', `${(meta.date_range[0] || '').slice(0, 10)} → ${(meta.date_range[1] || '').slice(0, 10)}`],
    ]),
    card('Where it came from', (meta.sources || []).map((s) => [s.label, fmtInt(s.records) + ' records'])),
  ));

  // Where the work went — destinations, links and published output.
  const d = meta.destinations;
  if (d) {
    const rows = [];
    if (d.products?.length) {
      rows.push(['Product / surface used', d.products.map((p) => `${p.name} (${fmtInt(p.turns)})`).join(' · ')]);
    }
    rows.push(['Turns that carry links', `${fmtInt(d.turns_with_links)} of ${fmtInt(meta.counts.turns)}`]);
    rows.push(['Turns that produced files', `${fmtInt(d.turns_with_files)}`]);
    if (d.meetings_published) {
      rows.push(['Meetings published as transcripts + video', fmtInt(d.meetings_published)]);
    }
    if (d.repo) {
      rows.push(['Source of record', d.repo]);
      rows.push(['Published site', d.site]);
    }
    const hostChips = (d.hosts || []).map((h) => el('a', {
      class: 'chip', href: h.url, target: '_blank', rel: 'noopener', title: h.url,
    }, `${h.host} · ${h.turns}`));
    host.append(el('div', { style: 'margin-top:14px' },
      el('h2', { class: 'page', style: 'font-size:16px;margin-bottom:8px' }, 'Where the work went'),
      el('p', { class: 'small muted', style: 'margin-bottom:10px' }, 'Destinations counted from the records: which surface each turn ran on, which sites it linked out to, and what got published.'),
      card(null, rows),
      el('div', { class: 'row', style: 'gap:6px;flex-wrap:wrap;margin-top:10px' }, ...hostChips)));
  }

  // Takeout coverage
  if (Atlas.inventory?.services?.length) {
    const rows = Atlas.inventory.services.map((s) => [s.label + (s.archive ? ` (${s.archive.replace('arch_', '').replace('.html', '')})` : ''), s.summary]);
    host.append(el('div', { style: 'margin-top:14px' },
      el('h2', { class: 'page', style: 'font-size:16px;margin-bottom:8px' }, 'Your Google exports — full inventory'),
      el('p', { class: 'small muted', style: 'margin-bottom:10px' }, 'Read from the Takeout archive index files: every service Google packaged for you, and how much is in each.'),
      card(null, rows)));
  }

  // Drive artifacts
  const drives = Atlas.data.drive_artifacts || [];
  if (drives.length) {
    const rows = drives.map((d) => el('tr', {},
      el('td', { class: 'nowrap mono small' }, (d.created || '').slice(0, 10)),
      el('td', {}, d.name, d.note ? el('div', { class: 'small muted' }, d.note) : null),
      el('td', { class: 'small' }, d.kind || ''),
      el('td', {}, el('a', { href: d.url, target: '_blank', rel: 'noopener' }, 'open ↗'))));
    const table = el('table', { class: 'ledger' },
      el('thead', {}, el('tr', {},
        el('th', {}, 'Created'), el('th', {}, 'Artifact'), el('th', {}, 'Type'), el('th', {}, 'Link'))),
      el('tbody', {}, ...rows));
    host.append(el('div', { style: 'margin-top:14px' },
      el('h2', { class: 'page', style: 'font-size:16px;margin-bottom:8px' }, 'Drive artifacts tied to the work'),
      el('p', { class: 'small muted', style: 'margin-bottom:10px' }, 'Files that hold the outputs — exports, saved pages, recordings and notebooks.'),
      el('div', { class: 'tbl-wrap', style: 'max-height:none' }, table)));
  }

  // repo archive
  const arch = Atlas.data.archive || [];
  if (arch.length) {
    const byBody = new Map();
    for (const m of arch) {
      if (!byBody.has(m.body)) byBody.set(m.body, []);
      byBody.get(m.body).push(m);
    }
    host.append(el('div', { style: 'margin-top:14px' },
      el('h2', { class: 'page', style: 'font-size:16px;margin-bottom:8px' }, `Published transcripts linked from this repo (${arch.length} meetings)`),
      el('p', { class: 'small muted', style: 'margin-bottom:10px' }, 'The public-record side of the work: verbatim meeting transcripts, each with its official video link.'),
      el('div', { class: 'grid2' }, ...[...byBody.entries()].map(([body, items]) => el('div', { class: 'card padc' },
        el('h3', {}, body.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())),
        el('div', { class: 'small' }, `${items.length} meetings: ${items.map((m) => m.date).slice(0, 8).join(', ')}${items.length > 8 ? '…' : ''}`),
        el('div', { class: 'row', style: 'margin-top:6px' }, el('a', { class: 'chip link', href: items[0].artifact_url, target: '_blank', rel: 'noopener' }, 'transcripts ↗'),
          el('a', { class: 'chip link', href: items[0].video_url, target: '_blank', rel: 'noopener' }, 'video ↗')))))));
  }

  // gaps
  const gaps = [
    ['Google Search history', 'Not present in the files read so far. Takeout → My Activity → Search exports as MyActivity.html and imports here.'],
    ['Chrome browsing history', 'Takeout → Chrome → BrowserHistory.json — the importer reads it and turns visits into timeline events.'],
    ['YouTube watch history', 'Takeout → YouTube and YouTube Music → history.'],
    ['NotebookLM (47,694 files in your export)', 'Takeout → NotebookLM — notebook sources and notes become artifacts in the ledger.'],
    ['Gmail correspondence', 'Gmail connector authentication failed during this build; Takeout → Mail exports as .mbox and is read by the importer.'],
    ['Gemini “Saved Info” and Gem definitions', 'Partially captured via gemini_gems_data.html; re-export from Gemini settings for the rest.'],
  ];
  host.append(el('div', { style: 'margin-top:14px' },
    el('h2', { class: 'page', style: 'font-size:16px;margin-bottom:8px' }, 'Known gaps — and how to close them'),
    card(null, gaps, true)));
}

function card(title, rows, prose = false) {
  const box = el('div', { class: 'card padc' });
  if (title) box.append(el('h3', {}, title));
  const grid = el('div', { style: `display:grid;grid-template-columns:${prose ? '220px 1fr' : '1fr auto'};gap:6px 12px;font-size:12.8px` });
  for (const [k, v] of rows) {
    grid.append(el('div', { class: prose ? '' : 'muted' }, prose ? el('b', {}, k) : k));
    grid.append(el('div', { class: prose ? 'muted' : 'mono' }, v));
  }
  box.append(grid);
  return box;
}
