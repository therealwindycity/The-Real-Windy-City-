/* story.js — choose-your-own-adventure reader + inspectors + turn drawer */
'use strict';

const Story = {
  threadId: null,
  turnIndex: 0,
  expandedOutputs: new Set(),
  search: '',
};

/* ---------------------------------------------------------------- chapters */
function renderChapters() {
  const box = $('#chapterList');
  if (!box) return;
  const threads = filteredThreads().slice().sort((a, b) => (b.resume_score || 0) - (a.resume_score || 0));
  const q = Story.search.toLowerCase();
  box.innerHTML = '';
  let shown = 0;
  for (const th of threads) {
    if (q && !(threadTitle(th) + ' ' + th.theme + ' ' + (th.first_prompt || '')).toLowerCase().includes(q)) continue;
    if (shown++ > 400) break;
    const color = themeById(th.theme).color;
    const b = el('button', {
      class: 'th' + (th.id === Story.threadId ? ' active' : ''),
      onclick: () => openStory(th.id, 0),
      title: `${th.turn_count} turns · ${th.status} · ${fmtDate(th.start, false)}`,
    },
      el('span', { class: 't' },
        el('span', { class: 'dot', style: `background:${color};display:inline-block;margin-right:6px` }),
        threadTitle(th)),
      el('span', { class: 'm' }, `${th.turn_count}t · ${th.completeness.percent}% · ${th.status} · ${(th.start || '').slice(0, 10)}`));
    box.append(b);
  }
  if (!shown) box.append(el('p', { class: 'muted small' }, 'No threads match the current filters.'));
}

function chapterSearchInit() {
  const input = $('#chapterSearch');
  if (!input) return;
  input.addEventListener('input', () => { Story.search = input.value; renderChapters(); });
}

/* ---------------------------------------------------------------- story view */
async function openStory(threadId, turnIndex = 0, opts = {}) {
  const thread = Atlas.threadsById.get(threadId);
  if (!thread) { toast('Thread not found'); return; }
  Story.threadId = threadId;
  const turns = await turnsOfThread(threadId);
  Story.turns = turns;
  Story.turnIndex = Math.max(0, Math.min(turnIndex, turns.length - 1));
  const cur = turns[Story.turnIndex];
  if (cur) {
    Atlas.trail = [{ threadId, turnId: cur.id, ts: cur.ts }];
    Store.write({ trail: Atlas.trail, lastThread: threadId, lastTurn: cur.id });
    Atlas.sel.threadId = threadId;
    Atlas.sel.turnId = cur.id;
  }
  renderChapters();
  renderStory();
  renderThreadInspector($('#storyInspector'), threadId);
  if (!opts.silent) showView('story');
}

function gotoStoryTurn(index) {
  const turns = Story.turns || [];
  if (!turns.length) return;
  Story.turnIndex = Math.max(0, Math.min(index, turns.length - 1));
  const cur = turns[Story.turnIndex];
  Atlas.sel.turnId = cur.id;
  Atlas.trail = [...Atlas.trail.filter((x) => x.threadId !== Story.threadId),
                 { threadId: Story.threadId, turnId: cur.id, ts: cur.ts }];
  Store.write({ trail: Atlas.trail, lastThread: Story.threadId, lastTurn: cur.id });
  renderStory();
  renderThreadInspector($('#storyInspector'), Story.threadId);
  $('#storyBody').scrollTo({ top: 0, behavior: 'smooth' });
}

function renderStory() {
  const box = $('#storyBody');
  if (!box || !Story.threadId) return;
  const th = Atlas.threadsById.get(Story.threadId);
  const turns = Story.turns || [];
  if (!turns.length) { box.innerHTML = '<div class="empty">No turns in this thread.</div>'; return; }
  const cur = turns[Story.turnIndex];
  const color = themeById(th.theme).color;
  box.innerHTML = '';

  /* header */
  const head = el('div', { class: 'story-head' },
    el('div', { class: 'row' },
      el('span', { class: 'dot', style: `background:${color}` }),
      el('span', { class: 'small muted' }, themeById(th.theme).name),
      el('span', { class: `badge-status st-${th.status}` }, th.status),
      el('span', { class: 'small muted' }, `${th.turn_count} turns · ${fmtInt(th.chars)} chars · ${fmtDate(th.start)} → ${fmtDate(th.end)}`),
      el('span', { style: 'flex:1' }),
      el('button', { class: 'btn sm ghost', onclick: () => renameThread(th) }, 'rename'),
      el('button', { class: 'btn sm', onclick: () => { Atlas.sel.threadId = th.id; buildHandoff('thread'); showView('handoff'); } }, '⇪ handoff'),
    ),
    el('h1', { style: 'margin:8px 0 6px;font-size:21px' }, threadTitle(th)),
    el('p', { class: 'small muted', style: 'margin:0 0 8px' }, th.status_note),
    el('div', { class: 'row', style: 'gap:10px' },
      el('div', { class: 'meter', style: 'max-width:280px' }, el('i', { style: `width:${th.completeness.percent}%` })),
      el('span', { class: 'pct' }, th.completeness.percent + '% · ' + th.completeness.label),
      el('span', { class: 'small muted' }, 'arc on the mind map shows the same value'),
    ),
  );
  box.append(head);

  /* trail */
  const trail = el('div', { class: 'trail' });
  const maxTrail = 60;
  const start = Math.max(0, Story.turnIndex - Math.floor(maxTrail / 2));
  for (let i = start; i < Math.min(turns.length, start + maxTrail); i++) {
    const t = turns[i];
    trail.append(el('button', {
      class: i === Story.turnIndex ? 'cur' : '',
      title: (t.prompt_excerpt || '').slice(0, 120),
      onclick: () => gotoStoryTurn(i),
    }, String(i + 1).padStart(2, '0')));
  }
  box.append(trail);

  /* passage */
  const p = el('div', { class: 'passage' });
  if (cur.prompt) {
    p.append(el('div', { class: 'who' }, `you · turn ${Story.turnIndex + 1} · ${fmtDate(cur.ts)} · ${cur.source || ''}`));
    p.append(el('div', { class: 'you' }, cur.prompt.length > 2600 && !Story.expandedOutputs.has('p' + cur.id)
      ? cur.prompt.slice(0, 2600) + '\n\n… [truncated in view]'
      : cur.prompt));
    if (cur.prompt.length > 2600) {
      p.append(el('button', {
        class: 'btn sm ghost', style: 'margin-top:6px',
        onclick: () => { const k = 'p' + cur.id; Story.expandedOutputs.has(k) ? Story.expandedOutputs.delete(k) : Story.expandedOutputs.add(k); renderStory(); },
      }, Story.expandedOutputs.has('p' + cur.id) ? 'collapse prompt' : 'show full prompt'));
    }
  }
  if (cur.output) {
    const expanded = Story.expandedOutputs.has(cur.id);
    const text = expanded ? cur.output : cur.output.slice(0, 4200);
    p.append(el('div', { class: 'who' }, `assistant · ${cur.product || 'Gemini'} · ${fmtInt(cur.output.length || cur.output_chars || 0)} chars`));
    p.append(el('div', { class: 'them', html: mdToHtml(text) }));
    if ((cur.output || '').length > 4200) {
      p.append(el('button', {
        class: 'btn sm ghost', style: 'margin-top:6px',
        onclick: () => { expanded ? Story.expandedOutputs.delete(cur.id) : Story.expandedOutputs.add(cur.id); renderStory(); },
      }, expanded ? 'collapse output' : `show full output (${fmtInt(cur.output.length)} chars)`));
    }
  }
  if (cur.title) p.append(el('div', { class: 'small muted', style: 'margin-top:6px' }, 'Document: ' + cur.title));
  box.append(p);

  /* meta strip */
  const meta = el('div', { class: 'row small muted', style: 'margin-top:6px' },
    el('span', {}, `completeness of this turn: `),
    el('b', { class: 'pct' }, (cur.completeness_pct ?? '—') + '%'),
    cur.artifacts?.length ? el('span', {}, '· produced ' + cur.artifacts.map((a) => a.name).slice(0, 3).join(', ')) : null,
    el('span', {}, `· ts_raw: ${cur.ts_raw || '—'}`),
    el('span', { style: 'flex:1' }),
    el('button', { class: 'btn sm ghost', onclick: () => openDrawer(cur.id) }, 'full record'),
  );
  box.append(meta);

  /* ------------------------------------------------------------ choices */
  const choices = el('div', { class: 'choices' }, el('h4', {}, `What happens next — ${Story.turnIndex + 1} of ${turns.length}`));

  const next = turns[Story.turnIndex + 1];
  if (next) {
    choices.append(el('button', { class: 'choice taken', onclick: () => gotoStoryTurn(Story.turnIndex + 1) },
      el('div', { class: 'k' }, 'the path taken'),
      el('div', { class: 'l' }, (next.prompt || '(no prompt text)').slice(0, 180)),
      el('div', { class: 'd' }, `${fmtDate(next.ts)} · produced ${fmtInt(next.output_chars)} chars`)));
  } else {
    choices.append(el('button', {
      class: 'choice resume', onclick: () => { Atlas.sel.threadId = Story.threadId; buildHandoff('thread'); showView('handoff'); },
    },
      el('div', { class: 'k' }, 'end of the recorded path'),
      el('div', { class: 'l' }, '⟳ Resume from here — build the handoff packet'),
      el('div', { class: 'd' }, `State, evidence, artifacts and a paste-ready prompt for another agent · thread at ${th.completeness.percent}%`)));
  }

  const offered = cur.choices || [];
  for (const c of offered) {
    choices.append(el('button', {
      class: 'choice ghost',
      onclick: () => exploreBranch(c, cur),
    },
      el('div', { class: 'k' }, 'road not taken · offered by the assistant'),
      el('div', { class: 'l' }, c.label),
      el('div', { class: 'd' }, 'Copy as a prompt, or annotate it in the branch ledger')));
  }

  const parallel = filteredThreads()
    .filter((t) => t.theme === th.theme && t.id !== th.id)
    .sort((a, b) => Math.abs(new Date(b.start || 0) - new Date(cur.ts || 0)) - Math.abs(new Date(a.start || 0) - new Date(cur.ts || 0)))
    .slice(0, 3);
  for (const t of parallel) {
    choices.append(el('button', { class: 'choice parallel', onclick: () => openStory(t.id, 0) },
      el('div', { class: 'k' }, 'meanwhile · same theme'),
      el('div', { class: 'l' }, threadTitle(t) + ` — ${t.completeness.percent}% (${t.status})`),
      el('div', { class: 'd' }, (t.first_prompt || '').slice(0, 150))));
  }
  box.append(choices);

  /* footer nav */
  box.append(el('div', { class: 'row', style: 'margin-top:22px' },
    el('button', { class: 'btn', disabled: Story.turnIndex === 0, onclick: () => gotoStoryTurn(Story.turnIndex - 1) }, '‹ previous turn'),
    el('button', { class: 'btn', disabled: Story.turnIndex >= turns.length - 1, onclick: () => gotoStoryTurn(Story.turnIndex + 1) }, 'next turn ›'),
    el('span', { class: 'small muted' }, 'keys: ← → j k · Esc closes · ⌘K search'),
  ));
}

function exploreBranch(choice, turn) {
  const prompt = `Continue from this branch: ${choice.label}\n\nContext: in the thread "${threadTitle(Atlas.threadsById.get(turn.thread))}" on ${fmtDate(turn.ts)}, you were working through: ${(turn.prompt || '').slice(0, 400)}`;
  const ok = confirm(`Copy this branch prompt to the clipboard?\n\n"${prompt.slice(0, 400)}…"`);
  if (ok) copy(prompt);
}

function renameThread(th) {
  const cur = threadTitle(th);
  const name = prompt('Rename this thread (stored locally in your browser):', cur);
  if (name === null) return;
  Atlas.prefs.renames = { ...(Atlas.prefs.renames || {}), [th.id]: name.trim() || th.name };
  Store.write({ prefs: Atlas.prefs });
  renderChapters();
  renderStory();
  renderThreadInspector($('#storyInspector'), th.id);
  mapRender();
  toast('Renamed');
}

/* ---------------------------------------------------------------- inspectors */
function renderThreadInspector(host, threadId) {
  if (!host) return;
  const th = Atlas.threadsById.get(threadId);
  host.innerHTML = '';
  if (!th) { host.append(el('div', { class: 'ipad muted small' }, 'Thread not found.')); return; }
  const color = themeById(th.theme).color;
  const pad = el('div', { class: 'ipad' },
    el('div', { class: 'row' }, el('span', { class: 'dot', style: `background:${color}` }),
      el('span', { class: 'small muted' }, themeById(th.theme).name)),
    el('h3', {}, threadTitle(th)),
    el('p', { class: 'small muted', style: 'margin:4px 0 10px' }, th.summary || ''),
    el('div', { class: 'meter' }, el('i', { style: `width:${th.completeness.percent}%` })),
    el('div', { class: 'row', style: 'margin-top:6px' },
      el('span', { class: 'pct' }, th.completeness.percent + '% · ' + th.completeness.label),
      el('span', { class: `badge-status st-${th.status}` }, th.status)),
  );

  const kv = el('dl', { class: 'kv' },
    el('dt', {}, 'Window'), el('dd', { class: 'mono small' }, `${fmtDate(th.start)} → ${fmtDate(th.end)}`),
    el('dt', {}, 'Turns'), el('dd', {}, String(th.turn_count)),
    el('dt', {}, 'Length'), el('dd', {}, fmtInt(th.chars) + ' chars produced'),
    el('dt', {}, 'Sources'), el('dd', { class: 'small' }, (th.sources || []).join(', ')),
    el('dt', {}, 'Thread id'), el('dd', { class: 'mono small' }, th.id),
  );
  pad.append(kv);

  if (th.open_threads?.length) {
    pad.append(el('div', { class: 'small', style: 'margin-top:6px;color:var(--gold-2)' }, 'Open threads'));
    const ul = el('ul', { class: 'small', style: 'padding-left:16px;margin:4px 0' });
    for (const o of th.open_threads) ul.append(el('li', { style: 'margin:3px 0' }, o));
    pad.append(ul);
  }

  pad.append(el('div', { class: 'small', style: 'margin-top:10px;color:var(--ink-3)' }, 'Completeness evidence'));
  const rl = el('ul', { class: 'reasons' });
  for (const r of (th.completeness.reasons || []).slice(0, 8)) {
    rl.append(el('li', {},
      el('span', { class: 'delta ' + (r.delta >= 0 ? 'pos' : 'neg') }, (r.delta >= 0 ? '+' : '') + r.delta),
      el('span', {}, r.signal + (r.terminal ? ' (final turn)' : ''))));
  }
  pad.append(rl);

  if (th.artifacts?.length) {
    pad.append(el('div', { class: 'small', style: 'margin-top:12px;color:var(--ink-3)' }, 'Artifacts'));
    const row = el('div', { class: 'pill-row', style: 'margin-top:4px' });
    for (const a of th.artifacts.slice(0, 12)) {
      row.append(a.href
        ? el('a', { class: 'chip link', href: a.href, target: '_blank', rel: 'noopener' }, a.name)
        : el('span', { class: 'chip' }, a.name));
    }
    pad.append(row);
  }
  if (th.urls?.length) {
    pad.append(el('div', { class: 'small', style: 'margin-top:12px;color:var(--ink-3)' }, `URLs (${th.urls.length})`));
    const list = el('div', { class: 'scroll-y small' });
    for (const u of th.urls.slice(0, 20)) list.append(el('div', {}, el('a', { href: u, target: '_blank', rel: 'noopener' }, u.slice(0, 90))));
    pad.append(list);
  }
  pad.append(el('div', { class: 'row', style: 'margin-top:14px' },
    el('button', { class: 'btn sm primary', onclick: () => { Atlas.sel.threadId = th.id; buildHandoff('thread'); showView('handoff'); } }, '⇪ Handoff packet'),
    el('button', { class: 'btn sm', onclick: () => openStory(th.id, 0) }, 'Open story'),
  ));
  host.append(pad);
}

function renderTurnInspector(host, turnId) {
  if (!host) return;
  const t = Atlas.turnsById.get(turnId);
  host.innerHTML = '';
  if (!t) { host.append(el('div', { class: 'ipad muted small' }, 'Turn not found in the index.')); return; }
  const th = Atlas.threadsById.get(t.thread);
  const pad = el('div', { class: 'ipad' },
    el('div', { class: 'row' }, el('span', { class: 'dot', style: `background:${themeById(t.theme).color}` }),
      el('span', { class: 'small muted' }, themeById(t.theme).name)),
    el('h3', {}, (t.prompt_excerpt || '(document)').slice(0, 90)),
    el('dl', { class: 'kv' },
      el('dt', {}, 'When'), el('dd', { class: 'mono small' }, fmtDate(t.ts)),
      el('dt', {}, 'Local stamp'), el('dd', { class: 'small' }, t.ts_raw || '—'),
      el('dt', {}, 'Source'), el('dd', { class: 'small' }, t.source || '—'),
      el('dt', {}, 'Output'), el('dd', {}, fmtInt(t.output_chars) + ' chars'),
      el('dt', {}, 'Turn'), el('dd', {}, `#${(t.turn_index ?? 0) + 1} of ${th ? th.turn_count : '?'} · ${t.completeness_pct}%`),
      th ? el('dt', {}, 'Story') : null, th ? el('dd', {}, el('a', { href: '#', onclick: (e) => { e.preventDefault(); openStory(th.id, t.turn_index || 0); } }, threadTitle(th))) : null,
    ));
  if (t.artifacts?.length) {
    const row = el('div', { class: 'pill-row', style: 'margin:6px 0' });
    for (const a of t.artifacts) row.append(a.href ? el('a', { class: 'chip link', href: a.href, target: '_blank', rel: 'noopener' }, a.name) : el('span', { class: 'chip' }, a.name));
    pad.append(el('div', { class: 'small', style: 'color:var(--ink-3)' }, 'Artifacts'), row);
  }
  pad.append(el('div', { class: 'row', style: 'margin-top:10px' },
    el('button', { class: 'btn sm', onclick: () => openDrawer(t.id) }, 'Full record'),
    el('button', { class: 'btn sm ghost', onclick: () => copy(t.prompt || '') }, 'Copy prompt')));
  host.append(pad);
}

function renderThemeInspector(host, id) {
  if (!host) return;
  host.innerHTML = '';
  const th = Atlas.data.themes.find((t) => t.id === id) || (id && id.length === 2 ? null : null);
  const pad = el('div', { class: 'ipad' });
  if (!th) {
    pad.append(el('h3', {}, 'Filtered view'), el('p', { class: 'small muted' }, 'Select a theme node or a thread node.'));
    host.append(pad); return;
  }
  const threads = filteredThreads().filter((t) => t.theme === th.id);
  pad.append(el('h3', {}, th.name));
  pad.append(el('p', { class: 'small muted' }, th.blurb));
  pad.append(el('div', { class: 'meter' }, el('i', { style: `width:${th.completeness}%` })));
  pad.append(el('div', { class: 'row', style: 'margin:6px 0 10px' },
    el('span', { class: 'pct' }, th.completeness + '% mean completeness'),
    el('span', { class: 'small muted' }, `${fmtInt(th.turns)} turns · ${threads.length} threads · ${th.share}% of archive`)));
  pad.append(el('div', { class: 'small muted' }, `Active ${(th.start || '').slice(0, 10)} → ${(th.end || '').slice(0, 10)}`));
  pad.append(el('div', { class: 'small', style: 'margin-top:8px;color:var(--ink-3)' }, 'Top vocabulary'));
  const row = el('div', { class: 'pill-row', style: 'margin-top:4px' });
  for (const w of (th.top_terms || []).slice(0, 16)) row.append(el('span', { class: 'chip' }, w));
  pad.append(row);
  pad.append(el('div', { class: 'row', style: 'margin-top:12px' },
    el('button', { class: 'btn sm', onclick: () => { Atlas.filters.themes = [th.id]; saveFilters(); refreshAll(); } }, 'Filter to this theme'),
    el('button', { class: 'btn sm ghost', onclick: () => { Atlas.sel.threadId = null; buildHandoff('theme', th.id); showView('handoff'); } }, 'Theme handoff'),
  ));
  const list = el('div', { style: 'margin-top:12px;max-height:260px;overflow:auto' });
  for (const t of threads.slice(0, 40)) {
    list.append(el('button', { class: 'th', onclick: () => { renderThreadInspector(host, t.id); } },
      el('span', { class: 't' }, threadTitle(t)),
      el('span', { class: 'm' }, `${t.turn_count}t · ${t.completeness.percent}% · ${t.status}`)));
  }
  pad.append(list);
  host.append(pad);
}

function renderOverviewInspector(host) {
  if (!host) return;
  const meta = Atlas.data.meta;
  host.innerHTML = '';
  host.append(el('div', { class: 'ipad' },
    el('h3', {}, 'The whole archive'),
    el('p', { class: 'small muted' }, `Every prompt and output the atlas could read, ${meta.date_range[0].slice(0, 10)} → ${meta.date_range[1].slice(0, 10)}.`),
    el('dl', { class: 'kv' },
      el('dt', {}, 'Turns'), el('dd', {}, fmtInt(meta.counts.turns)),
      el('dt', {}, 'Threads'), el('dd', {}, fmtInt(meta.counts.threads)),
      el('dt', {}, 'Words'), el('dd', {}, fmtInt(meta.counts.chars)),
      el('dt', {}, 'URLs found'), el('dd', {}, fmtInt(meta.counts.urls)),
      el('dt', {}, 'Artifacts'), el('dd', {}, fmtInt(meta.counts.artifacts)),
      el('dt', {}, 'Drive items'), el('dd', {}, fmtInt(meta.counts.drive_items))),
    el('p', { class: 'small muted' }, 'Use the rail to filter by theme, or the Continue story button to jump back to the last place you were working.'),
    el('button', { class: 'btn sm', onclick: () => showView('coverage') }, 'Sources & coverage →'),
  ));
}

/* ---------------------------------------------------------------- drawer */
async function openDrawer(turnId) {
  const t = Atlas.turnsById.get(turnId);
  const drawer = $('#drawer'), body = $('#drawerBody');
  if (!t) return;
  const th = Atlas.threadsById.get(t.thread);
  drawer.classList.add('open');
  $('#drawerTitle').textContent = th ? threadTitle(th) : 'Turn';
  const full = await turnsOfThread(t.thread);
  const rec = full.find((x) => x.id === turnId) || t;
  body.innerHTML = '';
  body.append(el('div', {},
    el('div', { class: 'row' },
      el('span', { class: 'dot', style: `background:${themeById(rec.theme).color}` }),
      el('span', { class: 'small muted' }, themeById(rec.theme).name),
      th ? el('span', { class: `badge-status st-${th.status}` }, th.status) : null,
      el('span', { class: 'small muted' }, `turn #${(rec.turn_index ?? 0) + 1} · ${rec.completeness_pct}% complete`)),
    el('dl', { class: 'kv' },
      el('dt', {}, 'When (UTC)'), el('dd', { class: 'mono' }, fmtDate(rec.ts)),
      el('dt', {}, 'Original stamp'), el('dd', { class: 'mono' }, rec.ts_raw || '—'),
      el('dt', {}, 'Source'), el('dd', {}, rec.source || '—'),
      el('dt', {}, 'Product'), el('dd', {}, rec.product || '—'),
      ...(th ? [el('dt', {}, 'Thread'),
        el('dd', {}, el('a', {
          href: '#',
          onclick: (e) => { e.preventDefault(); closeDrawer(); openStory(th.id, rec.turn_index || 0); },
        }, threadTitle(th)))] : []),
      el('dt', {}, 'Id'), el('dd', { class: 'mono small' }, rec.id)),
    rec.title ? el('div', { class: 'small muted', style: 'margin:6px 0' }, 'Document: ' + rec.title) : null,
    el('h3', { style: 'margin-top:12px' }, 'Your prompt'),
    el('div', { class: 'you', style: 'white-space:pre-wrap' }, rec.prompt || '(none — document output)'),
    el('div', { class: 'row', style: 'margin:6px 0 16px' },
      el('button', { class: 'btn sm ghost', onclick: () => copy(rec.prompt || '') }, 'Copy prompt'),
      rec.prompt ? el('button', { class: 'btn sm ghost', onclick: () => copy(rec.prompt) }, '') : null),
    el('h3', {}, `Output (${fmtInt((rec.output || '').length || rec.output_chars)} chars)`),
    el('div', { class: 'them', style: 'white-space:pre-wrap', html: mdToHtml((rec.output || '').slice(0, 20000)) }),
    (rec.output || '').length > 20000 ? el('p', { class: 'small muted' }, '…output truncated in this view; the full text is in data/threads/' + rec.thread + '.json') : null,
    rec.artifacts?.length ? el('h3', { style: 'margin-top:16px' }, 'Artifacts') : null,
    rec.artifacts?.length ? el('div', { class: 'pill-row' }, ...rec.artifacts.map((a) => a.href
      ? el('a', { class: 'chip link', href: a.href, target: '_blank', rel: 'noopener' }, a.name)
      : el('span', { class: 'chip' }, a.name))) : null,
    rec.urls?.length ? el('h3', { style: 'margin-top:16px' }, `URLs (${rec.urls.length})`) : null,
    rec.urls?.length ? el('div', { class: 'small' }, ...rec.urls.map((u) => el('div', {}, el('a', { href: u, target: '_blank', rel: 'noopener' }, u)))) : null,
    rec.choices?.length ? el('h3', { style: 'margin-top:16px' }, 'Branches offered here') : null,
    rec.choices?.length ? el('div', {}, ...rec.choices.map((c) => el('div', { class: 'chip', style: 'margin:4px 0;display:block' }, c.label))) : null,
    el('div', { class: 'hr' }),
    el('div', { class: 'row' },
      el('button', { class: 'btn sm', onclick: () => { Atlas.sel.threadId = rec.thread; Atlas.sel.turnId = rec.id; buildHandoff('thread'); closeDrawer(); showView('handoff'); } }, '⇪ Handoff from this thread'),
      el('button', { class: 'btn sm ghost', onclick: () => { closeDrawer(); openStory(rec.thread, rec.turn_index || 0); } }, 'Open in story'),
      el('button', { class: 'btn sm ghost', onclick: () => copy(JSON.stringify(rec, null, 1)) }, 'Copy JSON'),
    ),
  ));
  // prev / next wiring
  $('#drawerPrev').onclick = () => { const r = Atlas.turnsById.get(rec.prev); if (r) openDrawer(r.id); };
  $('#drawerNext').onclick = () => { const r = Atlas.turnsById.get(rec.next); if (r) openDrawer(r.id); };
}
function closeDrawer() { $('#drawer').classList.remove('open'); }
