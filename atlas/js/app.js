/* app.js — router, rail, filters, search palette, keyboard, boot */
'use strict';

let currentView = 'map';

function showView(name) {
  currentView = name;
  for (const btn of $$('#nav button')) btn.classList.toggle('active', btn.dataset.view === name);
  for (const v of $$('.view')) v.hidden = v.id !== 'view-' + name;
  if (name === 'map') mapRender();
  if (name === 'story') renderChapters();
  if (name === 'timeline') renderTimeline();
  if (name === 'ledger') renderLedger();
  if (name === 'handoff') renderHandoffSelectors();
  if (name === 'coverage') renderCoverage();
  if (name === 'import') { /* ready */ }
  try { history.replaceState(null, '', '#' + name); } catch {}
}

function refreshAll() {
  renderRail();
  renderQueue();
  renderFilterCount();
  if (currentView === 'map') mapRender();
  if (currentView === 'story') renderChapters();
  if (currentView === 'timeline') renderTimeline();
  if (currentView === 'ledger') renderLedger();
}

/* ---------------------------------------------------------------- rail */
function renderRail() {
  const m = Atlas.data.meta;
  $('#sTurns').textContent = fmtInt(Atlas.data.turns.length + Atlas.imported.length);
  $('#sPrompts').textContent = fmtInt(m.counts.prompts);
  $('#sThreads').textContent = fmtInt(Atlas.data.threads.length);
  $('#sChars').textContent = (m.counts.chars / 1e6).toFixed(1) + 'M';
  $('#sRange').textContent = `${(m.date_range[0] || '').slice(0, 10)} → ${(m.date_range[1] || '').slice(0, 10)}`;
  $('#brandsub').textContent = `${fmtInt(m.counts.turns)} turns · ${Atlas.data.threads.length} threads · local only`;

  const legend = $('#legend');
  legend.innerHTML = '';
  const active = activeThemes();
  for (const t of Atlas.data.themes) {
    const on = active.has(t.id);
    legend.append(el('button', {
      class: on ? '' : 'off',
      title: t.blurb,
      onclick: (e) => {
        const cur = Atlas.filters.themes ? new Set(Atlas.filters.themes) : new Set(Atlas.data.themes.map((x) => x.id));
        if (e.shiftKey) { cur.has(t.id) ? cur.delete(t.id) : cur.add(t.id); }
        else if (cur.size === 1 && cur.has(t.id)) Atlas.data.themes.forEach((x) => cur.add(x.id));
        else { cur.clear(); cur.add(t.id); }
        Atlas.filters.themes = cur.size === Atlas.data.themes.length ? null : [...cur];
        saveFilters(); refreshAll();
      },
    },
      el('span', { class: 'dot', style: `background:${t.color}` }),
      el('span', { style: 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap' }, t.name.split(',')[0]),
      el('span', { class: 'n' }, t.turns)));
  }
}

function renderQueue() {
  const box = $('#queue');
  box.innerHTML = '';
  for (const t of resumeQueue().slice(0, 8)) {
    box.append(el('button', { onclick: () => openStory(t.id, 0), title: t.summary || '' },
      el('span', { class: 'dot', style: `background:${themeById(t.theme).color}` }),
      el('span', { style: 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap' }, threadTitle(t)),
      el('span', { class: 'n' }, t.completeness.percent + '%')));
  }
}
function resumeQueue() {
  return Atlas.data.threads.slice().filter((t) => t.status !== 'complete')
    .sort((a, b) => (b.resume_score || 0) - (a.resume_score || 0));
}

/* ---------------------------------------------------------------- filters */
function filtersInit() {
  const statuses = [...new Set(Atlas.data.threads.map((t) => t.status))].sort();
  const sources = [...new Set(Atlas.data.turns.map((t) => t.source))].sort();
  const sSel = $('#fStatus'), srcSel = $('#fSource');
  for (const s of statuses) sSel.append(el('option', { value: s }, `${s} (${Atlas.data.threads.filter((t) => t.status === s).length})`));
  for (const s of sources) srcSel.append(el('option', { value: s }, s));

  const apply = () => {
    Atlas.filters.status = new Set([...sSel.selectedOptions].map((o) => o.value).filter(Boolean));
    Atlas.filters.source = new Set([...srcSel.selectedOptions].map((o) => o.value).filter(Boolean));
    Atlas.filters.min = +$('#fMin').value || 0;
    Atlas.filters.max = $('#fMax').value === '' ? 100 : +$('#fMax').value;
    Atlas.filters.from = $('#fFrom').value || null;
    Atlas.filters.to = $('#fTo').value || null;
    Atlas.filters.artifacts = $('#fArtifacts').checked;
    Atlas.filters.urls = $('#fUrls').checked;
    Atlas.filters.branches = $('#fBranches').checked;
    Atlas.filters.open = $('#fOpen').checked;
    saveFilters(); refreshAll();
  };
  ['fStatus', 'fSource', 'fMin', 'fMax', 'fFrom', 'fTo', 'fArtifacts', 'fUrls', 'fBranches', 'fOpen']
    .forEach((id) => $('#' + id)?.addEventListener('change', apply));
  $('#filtersClear')?.addEventListener('click', () => {
    Atlas.filters = { themes: null, status: new Set(), source: new Set(), min: 0, max: 100, from: null, to: null, artifacts: false, urls: false, branches: false, open: false, text: '' };
    $('#fMin').value = 0; $('#fMax').value = 100; $('#fFrom').value = ''; $('#fTo').value = '';
    ['fArtifacts', 'fUrls', 'fBranches', 'fOpen'].forEach((id) => { $('#' + id).checked = false; });
    [...sSel.options, ...srcSel.options].forEach((o) => (o.selected = false));
    saveFilters(); refreshAll();
  });
  $('#btnFilters')?.addEventListener('click', () => $('#filters').classList.toggle('open'));
  $('#filtersClose')?.addEventListener('click', () => $('#filters').classList.remove('open'));
}
function renderFilterCount() {
  const bits = filterSummary();
  $('#filterCount').textContent = bits.length ? `· ${bits.join(' · ')}` : '';
}

/* ---------------------------------------------------------------- palette */
function paletteInit() {
  const pal = $('#palette'), input = $('#paletteInput'), results = $('#paletteResults');
  const open = () => { pal.hidden = false; input.focus(); input.select(); };
  const close = () => { pal.hidden = true; };
  $('#q').addEventListener('focus', open);
  input.addEventListener('input', () => {
    const q = input.value.trim();
    results.innerHTML = '';
    if (q.length < 2) return;
    const hits = search(q, 40);
    if (!hits.length) { results.append(el('div', { class: 'r muted' }, 'No matches in the indexed text.')); return; }
    hits.forEach((h, i) => {
      const t = h.t, th = Atlas.threadsById.get(t.thread);
      results.append(el('div', {
        class: 'r' + (i === 0 ? ' sel' : ''),
        onclick: () => { close(); openTurnFromAnywhere(t.id); },
      },
        el('div', { class: 't', html: highlight(t.prompt_excerpt || t.title || '(document)', q) }),
        el('div', { class: 'm' }, `${fmtDate(t.ts)} · ${themeById(t.theme).name} · ${th ? threadTitle(th) : t.thread} · ${(th && th.completeness.percent) || t.completeness_pct}%`)));
    });
  });
  input.addEventListener('keydown', (e) => {
    const items = $$('.palette .r', results);
    const sel = items.findIndex((n) => n.classList.contains('sel'));
    if (e.key === 'ArrowDown') { e.preventDefault(); if (items[sel + 1]) { items[sel]?.classList.remove('sel'); items[sel + 1].classList.add('sel'); items[sel + 1].scrollIntoView({ block: 'nearest' }); } }
    else if (e.key === 'ArrowUp') { e.preventDefault(); if (items[sel - 1]) { items[sel]?.classList.remove('sel'); items[sel - 1].classList.add('sel'); items[sel - 1].scrollIntoView({ block: 'nearest' }); } }
    else if (e.key === 'Enter') { items[sel >= 0 ? sel : 0]?.click(); }
    else if (e.key === 'Escape') close();
  });
  $('#q').addEventListener('keydown', (e) => { if (e.key === 'Escape') { $('#q').blur(); close(); } });
  document.addEventListener('click', (e) => {
    if (!pal.hidden && !pal.contains(e.target) && e.target !== $('#q')) close();
  });
}

function openTurnFromAnywhere(turnId) {
  const t = Atlas.turnsById.get(turnId);
  if (!t) return;
  Atlas.sel.threadId = t.thread;
  openStory(t.thread, t.turn_index || 0);
  setTimeout(() => openDrawer(turnId), 60);
}

/* ---------------------------------------------------------------- keyboard */
function keyboardInit() {
  document.addEventListener('keydown', (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '');
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('#paletteInput').focus(); $('#palette').hidden = false; return; }
    if (typing) return;
    if (e.key === '/') { e.preventDefault(); $('#palette').hidden = false; $('#paletteInput').focus(); return; }
    if (e.key === 'Escape') { closeDrawer(); $('#filters').classList.remove('open'); $('#palette').hidden = true; return; }
    if (e.key === 'Backspace') { showView('map'); return; }
    if (currentView === 'story') {
      if (e.key === 'ArrowRight' || e.key === 'j') gotoStoryTurn(Story.turnIndex + 1);
      if (e.key === 'ArrowLeft' || e.key === 'k') gotoStoryTurn(Story.turnIndex - 1);
      if (e.key === 'e' && Story.threadId) { Atlas.sel.threadId = Story.threadId; buildHandoff('thread'); showView('handoff'); }
    }
    const views = ['map', 'story', 'timeline', 'ledger', 'handoff', 'coverage', 'import'];
    const num = parseInt(e.key, 10);
    if (num >= 1 && num <= views.length) showView(views[num - 1]);
  });
}

/* ---------------------------------------------------------------- help */
function helpText() {
  return `Paradox Atlas — shortcuts

  1..7          switch views (map, story, timeline, ledger, handoff, coverage, import)
  ⌘K  /  /      search every prompt and output
  ← →  j k      previous / next turn in story mode
  E             export a handoff packet for the open thread
  Backspace     back to the mind map
  Esc           close drawer / palette

Mind map: click a node to inspect, double-click to zoom, drag to pan, scroll to zoom.
Shift-click a theme in the rail to add it to the selection instead of replacing.
Completeness rings: the gold arc around a node is its completeness percentage.
`;
}

/* ---------------------------------------------------------------- boot */
async function boot() {
  // Encrypted dataset? Ask for the passphrase before anything is read.
  try {
    await Lock.probe();
  } catch { /* treat as plain */ }
  if (Lock.active && !Lock.unlocked) {
    document.documentElement.classList.add('locking');
    await Lock.prompt();          // resolves once the passphrase decrypts the index
    Lock._pending = null;
  }
  try {
    await loadAtlas();
  } catch (err) {
    const locked = Lock.active;
    const src = locked ? 'the encrypted dataset (atlas/enc/)' : 'atlas/data/atlas.json';
    document.body.innerHTML =
      `<div style="padding:40px;font:15px/1.6 system-ui;color:#e8ecf4">
        <h1 style="color:#e8b33d">Paradox Atlas could not load ${src}</h1>
        <p>${esc(err.message)}</p>
        ${locked ? `<p>The ciphertext is here, but the index would not decrypt — if that happened after a rebuild,
          the passphrase may belong to an older lock file. Re-lock with:<br>
          <code>python3 tools/lock_atlas.py lock --password '&lt;your passphrase&gt;'</code></p>`
      : `<p>This page needs to be served over HTTP (browsers block local file fetches). From the repository root run:</p>
        <pre style="background:#11151d;padding:14px;border-radius:8px">python3 -m http.server 8000
# then open http://localhost:8000/atlas/
# or with a password prompt in front of the whole app:
python3 tools/serve_locked.py --port 8000</pre>
        <p>Or build the dataset first: <code>python3 tools/build_atlas.py</code>,
           then encrypt it: <code>python3 tools/lock_atlas.py lock</code></p>`}
      </div>`;
    return;
  }

  mapInit();
  Atlas.mapReady = true;
  renderRail();
  renderQueue();
  renderOverviewInspector($('#inspector'));
  renderChapters();
  chapterSearchInit();
  exportInit();
  importInit();
  filtersInit();
  paletteInit();
  keyboardInit();
  renderHandoffSelectors();
  renderCoverage();

  $$('#nav button').forEach((b) => b.addEventListener('click', () => showView(b.dataset.view)));
  $('#btnStory').addEventListener('click', () => {
    const saved = Store.read();
    const tid = saved.lastThread || resumeQueue()[0]?.id;
    if (!tid) return;
    openStory(tid, 0);
    const turnId = saved.lastTurn;
    if (turnId) {
      const idx = (Atlas.turnsByThread.get(tid) || []).findIndex((t) => t.id === turnId);
      if (idx >= 0) setTimeout(() => gotoStoryTurn(idx), 40);
    }
  });
  $('#btnExport').addEventListener('click', () => { showView('handoff'); buildHandoff(Atlas.sel.threadId ? 'thread' : 'queue', Atlas.sel.threadId); });
  $('#btnHelp').addEventListener('click', () => alert(helpText()));
  const lockBtn = $('#btnLock');
  if (lockBtn) {
    if (!Lock.active) {
      lockBtn.textContent = '🔓 unencrypted';
      lockBtn.title = 'This copy runs from plaintext atlas/data/. Encrypt it: python3 tools/lock_atlas.py lock';
    } else {
      lockBtn.title = 'Re-lock: forget the key and clear every decrypted byte from this page';
      lockBtn.addEventListener('click', () => {
        Lock.lockNow();                                  // key + caches + rendered text
        document.getElementById('palette').hidden = true;
        $('#filters').classList.remove('open');
      });
    }
  }
  $('#drawerClose').addEventListener('click', closeDrawer);
  $('#themeAll').addEventListener('click', () => { Atlas.filters.themes = null; saveFilters(); refreshAll(); });
  $('#tlGroup').addEventListener('change', (e) => { Timeline.group = e.target.value; Timeline.page = 1; renderTimeline(); });
  $('#tlSort').addEventListener('change', (e) => { Timeline.sort = e.target.value; Timeline.page = 1; renderTimeline(); });
  $('#ledgerSearch').addEventListener('input', (e) => { Ledger.text = e.target.value; Ledger.page = 1; renderLedger(); });
  $('#ledgerCsv').addEventListener('click', () => downloadTurnsCsv());
  $('#ledgerJson').addEventListener('click', () => download('atlas-turns.json', JSON.stringify(filteredTurns(), null, 1), 'application/json'));
  $('#tlBody').addEventListener('scroll', maybeMoreTimeline);
  window.addEventListener('scroll', maybeMoreTimeline, true);

  const hash = (location.hash || '').replace('#', '');
  showView(['map', 'story', 'timeline', 'ledger', 'handoff', 'coverage', 'import'].includes(hash) ? hash : 'map');

  if (Atlas.imported.length) {
    impLog(`Loaded ${fmtInt(Atlas.imported.length)} previously imported turns from browser storage.`);
  }
}

/* Re-read the dataset without a page reload — used after the user re-locks and
   unlocks again, so the decrypted copy in memory is always the only copy. */
async function reloadData() {
  Atlas.threadCache.clear();
  await loadAtlas();
  if (!Atlas.data) return;
  if (Atlas.mapReady) mapRender();
  else { mapInit(); Atlas.mapReady = true; }
  renderRail();
  renderQueue();
  renderFilterCount();
  for (const id of ['hoThread', 'hoTheme']) { const s = $('#' + id); if (s) s.innerHTML = ''; }
  const files = $('#hoFiles'); if (files) files.dataset.done = '';
  renderHandoffSelectors();
  showView(currentView || 'map');
  document.documentElement.classList.remove('locking');
}

function maybeMoreTimeline(e) {
  const host = currentView === 'timeline' ? $('#view-timeline') : null;
  if (!host) return;
  const scroller = e.target === document ? host : e.target;
  if (scroller.scrollTop + scroller.clientHeight > scroller.scrollHeight - 400 && !Timeline._busy) {
    const total = filteredTurns().length;
    if (Timeline.page * Timeline.perPage < total) {
      Timeline._busy = true;
      Timeline.page++;
      renderTimeline();
      setTimeout(() => { Timeline._busy = false; }, 400);
    }
  }
}

document.addEventListener('DOMContentLoaded', boot);
