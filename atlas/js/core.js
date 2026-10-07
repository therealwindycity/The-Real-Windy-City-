/* core.js — state, loading, filtering, search, persistence, small utilities */
'use strict';

const Atlas = {
  data: null,              // atlas.json
  inventory: null,         // inventory.json
  threadsById: new Map(),
  turnsById: new Map(),
  turnsByThread: new Map(),
  threadCache: new Map(),  // full text loaded on demand
  imported: [],            // records merged from Takeout imports this session
  filters: {
    themes: null,          // null = all
    status: new Set(),
    source: new Set(),
    min: 0, max: 100,
    from: null, to: null,
    artifacts: false, urls: false, branches: false, open: false,
    text: '',
  },
  sel: { threadId: null, turnId: null, nodeKey: null },
  trail: [],               // story path
  prefs: {},
};

/* ------------------------------------------------------------------ storage */
const Store = {
  key: 'paradox-atlas-v1',
  read() {
    try { return JSON.parse(localStorage.getItem(this.key) || '{}'); } catch { return {}; }
  },
  write(patch) {
    const cur = this.read();
    const next = { ...cur, ...patch };
    try { localStorage.setItem(this.key, JSON.stringify(next)); } catch {}
    return next;
  },
};

/* ------------------------------------------------------------------ helpers */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function fmtBytes(n) {
  if (!n) return '0';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(n < 10 && i > 0 ? 1 : 0) + ' ' + u[i];
}
function fmtInt(n) { return (n ?? 0).toLocaleString('en-US'); }
function fmtDate(ts, withTime = true) {
  if (!ts) return '—';
  const d = new Date(ts);
  if (isNaN(d)) return ts;
  const date = d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
  if (!withTime) return date;
  return date + ' · ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + 'Z';
}
function relTime(ts, now) {
  if (!ts) return '';
  const days = Math.round((now - new Date(ts)) / 864e5);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return days + ' days ago';
  if (days < 365) return Math.round(days / 30) + ' mo ago';
  return (days / 365).toFixed(1) + ' yr ago';
}
function themeById(id) { return (Atlas.data?.themes || []).find((t) => t.id === id) || { id, name: id, color: '#7c7c7c' }; }
function threadTitle(t) { return Atlas.prefs.renames?.[t.id] || t.name; }

function toast(msg, ms = 2200) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, ms);
}

/* Very small markdown renderer for chat output (safe: escapes first). */
function mdToHtml(src) {
  let s = esc(src || '');
  s = s.replace(/```([\s\S]*?)```/g, (m, code) => '<pre>' + code.replace(/^\w+\n/, '') + '</pre>');
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  s = s.replace(/^######\s?(.*)$/gm, '<h6>$1</h6>')
       .replace(/^#####\s?(.*)$/gm, '<h5>$1</h5>')
       .replace(/^####\s?(.*)$/gm, '<h4>$1</h4>')
       .replace(/^###\s?(.*)$/gm, '<h3>$1</h3>')
       .replace(/^##\s?(.*)$/gm, '<h2>$1</h2>')
       .replace(/^#\s?(.*)$/gm, '<h1>$1</h1>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>');
  s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/(^|\s)(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  // pipe tables
  s = s.replace(/(?:^\|.*\|\s*$\n?)+/gm, (block) => {
    const rows = block.trim().split('\n').map((r) => r.split('|').slice(1, -1).map((c) => c.trim()));
    if (!rows.length) return block;
    const head = rows[0];
    const body = rows.slice(rows[1] && /^[-\s|:]+$/.test(rows[1].join('')) ? 2 : 1);
    return '<table><thead><tr>' + head.map((c) => `<th>${c}</th>`).join('') + '</tr></thead><tbody>' +
      body.map((r) => '<tr>' + r.map((c) => `<td>${c}</td>`).join('') + '</tr>').join('') + '</tbody></table>';
  });
  // lists
  s = s.replace(/(?:^[-*•]\s+.*$\n?)+/gm, (block) =>
    '<ul>' + block.trim().split('\n').map((r) => '<li>' + r.replace(/^[-*•]\s+/, '') + '</li>').join('') + '</ul>');
  s = s.replace(/(?:^\d+\.\s+.*$\n?)+/gm, (block) =>
    '<ol>' + block.trim().split('\n').map((r) => '<li>' + r.replace(/^\d+\.\s+/, '') + '</li>').join('') + '</ol>');
  return s.split(/\n{2,}/).map((p) => /^<(h\d|ul|ol|pre|table)/.test(p.trim()) ? p : '<p>' + p.replace(/\n/g, '<br>') + '</p>').join('');
}

/* ------------------------------------------------------------------ loading */
async function loadAtlas() {
  // Every read goes through Lock, which resolves the logical name to either
  // atlas/data/<name> (plain) or a ciphertext blob in atlas/enc/ (locked).
  Atlas.data = await Lock.json('atlas.json');
  const saved = Store.read();
  Atlas.prefs = saved.prefs || {};
  Atlas.imported = saved.imported || [];
  if (saved.filters) Object.assign(Atlas.filters, saved.filters, {
    status: new Set(saved.filters.status || []),
    source: new Set(saved.filters.source || []),
    themes: saved.filters.themes || null,
  });
  if (saved.trail) Atlas.trail = saved.trail;
  index();
  try {
    Atlas.inventory = await Lock.json('inventory.json');
  } catch {}
}

function index() {
  Atlas.threadsById.clear();
  Atlas.turnsById.clear();
  Atlas.turnsByThread.clear();
  const allTurns = [...Atlas.data.turns, ...Atlas.imported];
  for (const t of Atlas.data.threads) Atlas.threadsById.set(t.id, t);
  for (const t of allTurns) {
    Atlas.turnsById.set(t.id, t);
    if (!Atlas.turnsByThread.has(t.thread)) Atlas.turnsByThread.set(t.thread, []);
    Atlas.turnsByThread.get(t.thread).push(t);
  }
  for (const [, list] of Atlas.turnsByThread) list.sort((a, b) => (a.ts || '').localeCompare(b.ts || ''));
  Atlas.now = new Date(Atlas.data.meta.data_through || Date.now());
}

async function loadThread(id) {
  if (Atlas.threadCache.has(id)) return Atlas.threadCache.get(id);
  try {
    const data = await Lock.json(`threads/${id}.json`);
    Atlas.threadCache.set(id, data);
    return data;
  } catch {
    return null;
  }
}
async function turnsOfThread(id) {
  const cached = Atlas.threadCache.get(id);
  if (cached) return cached.turns;
  const local = (Atlas.turnsByThread.get(id) || []).filter((t) => t._imported);
  const data = await loadThread(id);
  if (data && local.length) return [...data.turns, ...local].sort((a, b) => (a.ts || '').localeCompare(b.ts || ''));
  if (data) return data.turns;
  return Atlas.turnsByThread.get(id) || [];
}

/* ------------------------------------------------------------------ filtering */
function activeThemes() {
  const f = Atlas.filters;
  const all = Atlas.data.themes.map((t) => t.id);
  if (!f.themes) return new Set(all);
  return new Set(f.themes);
}
function passFilter(turn) {
  const f = Atlas.filters;
  if (!activeThemes().has(turn.theme) && !(turn.secondary_themes || []).some((s) => activeThemes().has(s))) return false;
  const th = Atlas.threadsById.get(turn.thread);
  if (f.status.size && (!th || !f.status.has(th.status))) return false;
  if (f.source.size && !f.source.has(turn.source)) return false;
  const pct = th ? th.completeness.percent : (turn.completeness_pct ?? 0);
  if (pct < f.min || pct > f.max) return false;
  if (f.from && (turn.ts || '') < f.from) return false;
  if (f.to && (turn.ts || '') > f.to + 'T23:59:59Z') return false;
  if (f.artifacts && !(turn.artifacts || []).length) return false;
  if (f.urls && !(turn.urls || []).length) return false;
  if (f.branches && !(turn.choices || []).length) return false;
  if (f.open && th && !(th.open_threads || []).length) return false;
  if (f.text) {
    const hay = (turn.prompt + ' ' + (turn.output_excerpt || '')).toLowerCase();
    if (!hay.includes(f.text.toLowerCase())) return false;
  }
  return true;
}
function filteredTurns() {
  // Imported turns are first-class: everything the user drops into the Import
  // view flows through the same filters, search, timeline and story reader.
  return [...Atlas.data.turns, ...Atlas.imported].filter(passFilter);
}
function filteredThreads() {
  const f = Atlas.filters;
  const counts = new Map();
  for (const t of filteredTurns()) counts.set(t.thread, (counts.get(t.thread) || 0) + 1);
  return Atlas.data.threads.filter((th) => {
    if (!activeThemes().has(th.theme) && !(th.secondary_themes || []).some((s) => activeThemes().has(s))) return false;
    if (f.status.size && !f.status.has(th.status)) return false;
    if (th.completeness.percent < f.min || th.completeness.percent > f.max) return false;
    if (f.from && (th.end || '') < f.from) return false;
    if (f.to && (th.start || '') > f.to + 'T23:59:59Z') return false;
    if (f.artifacts && !(th.artifacts || []).length) return false;
    if (f.urls && !(th.urls || []).length) return false;
    if (f.open && !(th.open_threads || []).length) return false;
    // Source/text filters are turn-level: a thread only qualifies if at least
    // one of its turns survived them.
    if (!counts.get(th.id) && (f.source.size || f.text)) return false;
    return true;
  });
}
function filterSummary() {
  const f = Atlas.filters;
  const bits = [];
  if (f.themes) bits.push(f.themes.length + ' themes');
  if (f.status.size) bits.push([...f.status].join('/'));
  if (f.source.size) bits.push(f.source.size + ' sources');
  if (f.min > 0 || f.max < 100) bits.push(`${f.min}–${f.max}%`);
  if (f.from || f.to) bits.push('dates');
  if (f.artifacts) bits.push('artifacts');
  if (f.urls) bits.push('URLs');
  if (f.branches) bits.push('branches');
  if (f.open) bits.push('open');
  if (f.text) bits.push('“' + f.text.slice(0, 18) + '”');
  return bits;
}
function saveFilters() {
  Store.write({
    filters: {
      ...Atlas.filters,
      status: [...Atlas.filters.status],
      source: [...Atlas.filters.source],
    },
  });
}

/* ------------------------------------------------------------------ search */
let searchIndex = null;
function buildSearchIndex() {
  searchIndex = Atlas.data.turns.map((t) => {
    const hay = (t.prompt + ' ' + (t.output_excerpt || '') + ' ' +
      (t.artifacts || []).map((a) => a.name).join(' ') + ' ' +
      (t.urls || []).join(' ') + ' ' + t.theme + ' ' + t.thread).toLowerCase();
    return { t, hay };
  });
}
function search(q, limit = 60) {
  if (!searchIndex) buildSearchIndex();
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  const out = [];
  for (const row of searchIndex) {
    let score = 0, ok = true;
    for (const term of terms) {
      const i = row.hay.indexOf(term);
      if (i < 0) { ok = false; break; }
      score += i === 0 ? 6 : row.t.prompt.toLowerCase().includes(term) ? 3 : 1;
    }
    if (ok) out.push({ ...row, score });
    if (out.length > 4000) break;
  }
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, limit);
}
function highlight(text, q) {
  let out = esc(text || '');
  for (const term of (q || '').split(/\s+/).filter((t) => t.length > 1)) {
    out = out.replace(new RegExp('(' + term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'), '<mark>$1</mark>');
  }
  return out;
}

/* ------------------------------------------------------------------ misc */
function download(filename, content, type = 'application/octet-stream') {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return blob;
}
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied ' + fmtInt(text.length) + ' characters');
    return true;
  } catch {
    toast('Clipboard blocked — select the text and copy manually');
    return false;
  }
}
