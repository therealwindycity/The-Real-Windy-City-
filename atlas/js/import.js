/* import.js — client-side Takeout / MyActivity importer (nothing leaves the browser) */
'use strict';

const Importer = {
  pending: [],      // parsed turn records awaiting merge
  driveRows: [],
  gmailCount: 0,
  chromeRows: [],
  log: [],
};

const IMP_THEMES = [
  ['legal', /court|evict|landlord|tenant|bankrupt|chapter 1[37]|trustee|judge|hearing|lawsuit|statute|motion|affidavit|subpoena|detainer|forcible entry|deposition|docket|attorney|counsel|settlement|injunction|garnishment/gi],
  ['property', /property|parcel|annex|zoning|plat|deed|easement|\bhoa\b|\bacres?\b|man camp|site plan|variance|setback|right of way|survey|parcel|table mountain|happy jack|wyfresh|eminent domain/gi],
  ['vehicles', /vehicle|tow|impound|registration|\bvin\b|bill of sale|traffic|license plate|ticket|citation|odometer|salvage|drivers license/gi],
  ['policing', /police|officer|sheriff|dispatch|body ?cam|public records|foia|records request|scanner|radio|frequency|incident report|warrant|arrest|use of force/gi],
  ['forensics', /forensic|dossier|timeline|evidence|chain of custody|red team|veracity|cross-reference|audit|metadata|exhibit|contradiction|provenance/gi],
  ['meetings', /transcript|council|city council|meeting|minutes|agenda|ordinance|mayor|commission|public comment|podium|work session|verbatim|resolution|urban renewal/gi],
  ['ai', /prompt|\bgem\b|persona|system directive|gemini|chatgpt|notebooklm|context window|llm|agent|promethean|paradox engine|jailbreak|token|finetune|fine-tune/gi],
  ['code', /python|javascript|html|css|json|\bapi\b|github|repo|colab|notebook|streamlit|sqlite|\bsql\b|regex|scrape|cron|deploy|server|debug|cloudflare|sitemap|\bseo\b/gi],
  ['media', /image|png|jpe?g|photo|picture|meme|thumbnail|logo|audio|\bwav\b|\bmp3\b|\bmp4\b|video|screen recording|caption|graphic|banner|drone/gi],
  ['publishing', /blotter|newsletter|subscriber|press release|distro|client|invoice|revenue|business|\bllc\b|brand|marketing|monetiz|sponsor|advertis|audience|outreach|pitch/gi],
  ['personal', /generator|u-haul|utility|school|daughter|son|wife|doctor|prescription|appointment|weather|recipe|grocery|hotel|flight/gi],
];

function impClassify(text) {
  const scores = {};
  for (const [id, re] of IMP_THEMES) {
    const m = text.match(re);
    if (m) scores[id] = m.length;
  }
  const entries = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  return entries.length ? entries[0][0] : 'general';
}

function impLog(msg) {
  Importer.log.push(msg);
  const box = $('#impLog');
  if (box) box.textContent = Importer.log.slice(-14).join('\n');
  box && (box.scrollTop = box.scrollHeight);
}

function impProgress(frac) {
  const bar = $('#impBar');
  if (bar) bar.style.width = Math.round(frac * 100) + '%';
}

/* ---------------------------------------------------------------- zip */
async function readZip(file) {
  const buf = new Uint8Array(await file.arrayBuffer());
  const dv = new DataView(buf.buffer);
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 66000); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('Not a zip (no end-of-central-directory record)');
  const count = dv.getUint16(eocd + 10, true);
  let ptr = dv.getUint32(eocd + 16, true);
  const entries = [];
  for (let i = 0; i < count; i++) {
    if (dv.getUint32(ptr, true) !== 0x02014b50) break;
    const method = dv.getUint16(ptr + 10, true);
    const compSize = dv.getUint32(ptr + 20, true);
    const nameLen = dv.getUint16(ptr + 28, true);
    const extraLen = dv.getUint16(ptr + 30, true);
    const cmtLen = dv.getUint16(ptr + 32, true);
    const localOff = dv.getUint32(ptr + 42, true);
    const name = new TextDecoder().decode(buf.subarray(ptr + 46, ptr + 46 + nameLen));
    entries.push({ name, method, compSize, localOff });
    ptr += 46 + nameLen + extraLen + cmtLen;
  }
  return { buf, dv, entries };
}

async function unzipEntry(zip, entry) {
  const { buf, dv } = zip;
  const lnameLen = dv.getUint16(entry.localOff + 26, true);
  const lextraLen = dv.getUint16(entry.localOff + 28, true);
  const start = entry.localOff + 30 + lnameLen + lextraLen;
  const data = buf.subarray(start, start + entry.compSize);
  if (entry.method === 0) return new TextDecoder().decode(data);
  if (entry.method !== 8) throw new Error('unsupported compression ' + entry.method);
  if (typeof DecompressionStream === 'undefined') throw new Error('This browser cannot inflate zip entries (DecompressionStream missing). Unzip manually and drop the files.');
  const ds = new DecompressionStream('deflate-raw');
  // Prefer Response().body: it exists in every browser that ships
  // DecompressionStream, and unlike Blob.stream() it is also available in
  // non-browser runtimes, which keeps the importer testable outside a tab.
  const source = (typeof Response !== 'undefined' && new Response(data).body)
    ? new Response(data).body
    : new Blob([data]).stream();
  const stream = source.pipeThrough(ds);
  return await new Response(stream).text();
}

/* ---------------------------------------------------------------- parsing */
const DATE_RE = /([A-Z][a-z]{2}) (\d{1,2}), (\d{4}), (\d{1,2}):(\d{2}):(\d{2})[ \u202f\u00a0]*([AP]M) (\w{2,4})/;
const MONTHS = { Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6, Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12 };
const TZ_OFF = { EDT: -4, EST: -5, CDT: -5, CST: -6, MDT: -6, MST: -7, PDT: -7, PST: -8, UTC: 0 };

function impParseStamp(raw) {
  const m = DATE_RE.exec(raw || '');
  if (!m) return null;
  const [, mon, day, year, hh, mm, ss, ap, tz] = m;
  const hour = (parseInt(hh, 10) % 12) + (ap === 'PM' ? 12 : 0);
  const ms = Date.UTC(+year, MONTHS[mon] - 1, +day, hour, +mm, +ss) - (TZ_OFF[tz] || 0) * 3600e3;
  return new Date(ms).toISOString();
}

function stripTags(html) {
  return String(html || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|h[1-6]|tr)>/gi, '\n')
    .replace(/<li[^>]*>/gi, '- ')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/\u202f|\u00a0/g, ' ')
    .replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
}

function impParseActivityHtml(html, sourceLabel) {
  const out = [];
  const blocks = html.split(/<div class="outer-cell/).slice(1);
  for (const block of blocks) {
    const titleM = /mdl-typography--title">([\s\S]*?)<\/p>/.exec(block);
    const product = titleM ? stripTags(titleM[1]) : (sourceLabel || 'Google');
    const cellM = /content-cell[^"]*?mdl-typography--body-1[^"]*">([\s\S]*?)<\/div>\s*(?=<div class="content-cell|<div class="mdl-grid|<\/div>)/.exec(block);
    if (!cellM) continue;
    const left = cellM[1];
    const stampM = DATE_RE.exec(left);
    const tsRaw = stampM ? stampM[0] : '';
    const head = stampM ? left.slice(0, stampM.index) : left;
    const tail = stampM ? left.slice(stampM.index + stampM[0].length) : '';
    let prompt = stripTags(head);
    let kind = 'event';
    const pm = /^(Prompted|Asked|Said)\s+([\s\S]*)$/i.exec(prompt);
    if (pm) { kind = 'prompt'; prompt = pm[2].trim(); }
    else if (/^Searched for/i.test(prompt)) { kind = 'search'; prompt = prompt.replace(/^Searched for\s*/i, ''); }
    const output = stripTags(tail);
    if (!prompt && !output) continue;
    const attachments = [];
    for (const m of head.matchAll(/<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g)) {
      attachments.push({ name: stripTags(m[2]) || 'attachment', href: m[1] });
    }
    out.push({ product, kind, tsRaw, prompt, output, attachments });
  }
  return out;
}

function impParseActivityJson(text, sourceLabel) {
  let data;
  try { data = JSON.parse(text); } catch { return []; }
  const items = Array.isArray(data) ? data : (data.items || data.activity || []);
  const out = [];
  for (const it of items) {
    const prompt = (it.subtitles || []).map((s) => stripTags(typeof s === 'string' ? s : s.name)).join('\n').trim();
    const output = Array.isArray(it.details) ? it.details.map((d) => stripTags(typeof d === 'string' ? d : d.text)).join('\n\n') : '';
    out.push({
      product: it.header || sourceLabel || 'Google',
      kind: prompt ? 'prompt' : 'event',
      tsRaw: it.time || '',
      prompt, output, attachments: [],
      iso: it.time ? new Date(it.time).toISOString() : null,
    });
  }
  return out;
}

/* ---------------------------------------------------------------- ingestion */
async function ingestFiles(files) {
  const list = Array.from(files);
  impLog(`Ingesting ${list.length} file(s)…`);
  let i = 0;
  for (const file of list) {
    try {
      await ingestOne(file);
    } catch (err) {
      impLog(`✗ ${file.name}: ${err.message}`);
    }
    impProgress(++i / list.length);
  }
  summarizeImport();
}

async function ingestOne(file) {
  const name = file.name;
  const lower = name.toLowerCase();
  if (lower.endsWith('.zip')) {
    const zip = await readZip(file);
    const interesting = zip.entries.filter((e) =>
      /my activity\/.*\.(html|json)$/i.test(e.name) ||
      /(gemini|search|chrome|youtube|assistant|bard)/i.test(e.name) && /\.(html|json)$/i.test(e.name) ||
      /drive\/.*\.csv$/i.test(e.name) ||
      /mail\/.*\.mbox$/i.test(e.name) ||
      /browserhistory\.json$/i.test(e.name));
    impLog(`  ${name}: ${zip.entries.length} entries, ${interesting.length} readable`);
    let n = 0;
    for (const entry of interesting) {
      if (entry.compSize > 80 * 1024 * 1024) { impLog(`  ↷ skipped huge entry ${entry.name}`); continue; }
      const text = await unzipEntry(zip, entry);
      const short = entry.name.split('/').slice(-2).join('/');
      if (/drive\/.*\.csv$/i.test(entry.name)) { impDriveCsv(text, short); continue; }
      if (/mail\/.*\.mbox$/i.test(entry.name)) { Importer.gmailCount += (text.match(/^From /gm) || []).length; impLog(`  mail: ~${Importer.gmailCount} messages indexed (headers only)`); continue; }
      if (/browserhistory\.json$/i.test(entry.name)) { impChrome(text); continue; }
      const recs = /\.json$/i.test(entry.name) ? impParseActivityJson(text, short) : impParseActivityHtml(text, short);
      addRecords(recs, short);
      n += recs.length;
    }
    impLog(`✓ ${name}: ${n} activity records`);
    return;
  }
  const text = await file.text();
  if (lower.endsWith('.json') && /"mimeType"|"files"/.test(text.slice(0, 4000)) && /drive/i.test(text.slice(0, 2000))) {
    const recs = impParseActivityJson(text, name); addRecords(recs, name); impLog(`✓ ${name}: ${recs.length} records`); return;
  }
  if (lower.endsWith('.json')) {
    if (/"kind"\s*:\s*"atlas-index"|"counts"\s*:/.test(text.slice(0, 600))) { impLog(`· ${name}: looks like an atlas index — import merged atlas.json instead`); return; }
    const recs = impParseActivityJson(text, name); addRecords(recs, name); impLog(`✓ ${name}: ${recs.length} records`); return;
  }
  if (/\.(html|htm)$/.test(lower)) {
    const recs = impParseActivityHtml(text, name.replace(/\.[a-z]+$/, '')); addRecords(recs, name); impLog(`✓ ${name}: ${recs.length} records`); return;
  }
  if (/\.(txt|md)$/.test(lower)) {
    addRecords([{ product: name, kind: 'document', tsRaw: '', prompt: '', output: text, attachments: [] }], name);
    impLog(`✓ ${name}: 1 document (${text.length} chars)`); return;
  }
  impLog(`· ${name}: nothing readable (supported: zip, MyActivity html/json, txt/md)`);
}

function addRecords(recs, origin) {
  for (const r of recs) {
    const iso = r.iso || impParseStamp(r.tsRaw);
    const text = (r.prompt + ' ' + r.output).slice(0, 8000);
    Importer.pending.push({
      id: 'imp-' + Math.random().toString(36).slice(2, 10),
      ts: iso,
      ts_raw: r.tsRaw,
      date: iso ? iso.slice(0, 10) : null,
      time: iso ? iso.slice(11, 16) : null,
      source: origin,
      product: r.product,
      kind: r.kind,
      prompt: r.prompt,
      output: r.output,
      output_chars: (r.output || '').length,
      output_excerpt: (r.output || '').slice(0, 520),
      prompt_excerpt: (r.prompt || '').slice(0, 300),
      theme: impClassify(text),
      secondary_themes: [],
      artifacts: r.attachments || [],
      urls: [...new Set((r.attachments || []).map((a) => a.href).filter((h) => h && h.startsWith('http')))],
      choices: [],
      completeness_pct: Math.max(20, Math.min(90, 40 + Math.round(Math.min(30, (r.output || '').length / 900)))),
      turn_index: 0,
      prev: null, next: null,
      _imported: true,
    });
  }
}

function impDriveCsv(text, origin) {
  const lines = text.split(/\r?\n/).filter(Boolean);
  const head = (lines[0] || '').split(',').map((h) => h.replace(/"/g, '').trim().toLowerCase());
  const idx = (...names) => names.map((n) => head.indexOf(n)).filter((i) => i >= 0)[0];
  const nameI = idx('title', 'filename', 'name', 'file name');
  const urlI = idx('url', 'link', 'webviewlink');
  const createdI = idx('created', 'creation time', 'date');
  const count = Math.max(0, lines.length - 1);
  for (const line of lines.slice(1)) {
    const cells = line.match(/("([^"]|"")*"|[^,]*)(,|$)/g)?.map((c) => c.replace(/,$/, '').replace(/^"|"$/g, '')) || [];
    Importer.driveRows.push({
      name: cells[nameI] || '(unnamed)', url: cells[urlI] || '', created: cells[createdI] || '', origin,
    });
  }
  impLog(`  drive: ${count} files indexed from ${origin}`);
}

function impChrome(text) {
  try {
    const data = JSON.parse(text);
    const visits = data['Browser History'] || data.history || [];
    for (const v of visits) {
      Importer.chromeRows.push({ url: v.url, title: v.title, ts: v.time_usec ? new Date(v.time_usec / 1000).toISOString() : null });
    }
    impLog(`  chrome: ${visits.length} visits indexed`);
  } catch { impLog('  chrome: could not parse BrowserHistory.json'); }
}

function summarizeImport() {
  const n = Importer.pending.length;
  impLog(`— parsed ${fmtInt(n)} activity records, ${fmtInt(Importer.driveRows.length)} Drive files, ${fmtInt(Importer.chromeRows.length)} Chrome visits`);
  $('#impMerge').disabled = n === 0;
  $('#impDownload').disabled = n === 0;
  if (n) impLog('Ready to merge into the archive view.');
}

function mergeImport() {
  const recs = Importer.pending.slice().sort((a, b) => (a.ts || '').localeCompare(b.ts || ''));
  // group into synthetic threads on a 3-hour gap + theme
  let cur = null, groups = [];
  for (const r of recs) {
    if (cur && cur.theme === r.theme && r.ts && cur.last &&
        (new Date(r.ts) - new Date(cur.last)) < 3 * 3600e3) {
      cur.turns.push(r); cur.last = r.ts;
    } else {
      cur = { theme: r.theme, turns: [r], last: r.ts };
      groups.push(cur);
    }
  }
  let added = 0;
  for (const g of groups) {
    const first = g.turns[0];
    const id = 'imp-' + (Atlas.data.threads.length + 1) + '-' + Math.random().toString(36).slice(2, 6);
    const chars = g.turns.reduce((s, t) => s + t.output_chars, 0);
    const start = g.turns[0].ts, end = g.turns[g.turns.length - 1].ts;
    for (let i = 0; i < g.turns.length; i++) {
      const t = g.turns[i];
      t.thread = id;
      t.turn_index = i;
      t.prev = i ? g.turns[i - 1].id : null;
      t.next = i < g.turns.length - 1 ? g.turns[i + 1].id : null;
      Atlas.imported.push(t);
      added++;
    }
    const themeName = (Atlas.data.themes.find((t) => t.id === g.theme) || { name: 'Imported activity' }).name;
    Atlas.data.threads.push({
      id, index: Atlas.data.threads.length + 1,
      name: (first.prompt || 'Imported activity').slice(0, 60),
      theme: g.theme, secondary_themes: [],
      start, end, duration_hours: 0, turn_count: g.turns.length,
      completeness: { percent: Math.round(g.turns.reduce((s, t) => s + t.completeness_pct, 0) / g.turns.length), label: 'Imported', reasons: [{ signal: 'imported from Takeout in the browser', delta: 0 }] },
      artifacts: g.turns.flatMap((t) => t.artifacts).slice(0, 10),
      urls: [...new Set(g.turns.flatMap((t) => t.urls))].slice(0, 10),
      open_threads: [], sources: ['browser import'],
      first_prompt: first.prompt_excerpt, last_prompt: g.turns[g.turns.length - 1].prompt_excerpt,
      last_output: g.turns[g.turns.length - 1].output_excerpt,
      chars, slug: 'imported-' + id, status: 'open',
      status_note: 'Imported in-browser — status will settle once merged into a rebuilt atlas.',
      resume_score: 50, summary: `Imported ${g.turns.length} turns from browser import (${themeName}).`,
      _imported: true,
    });
  }
  index();
  try {
    const blob = JSON.stringify({ prefs: Atlas.prefs, imported: Atlas.imported.slice(-4000) });
    if (blob.length < 3_000_000) Store.write({ imported: Atlas.imported.slice(-4000) });
    else impLog('! Too much imported data for browser storage — use "Download merged atlas.json" to keep it.');
  } catch {}
  refreshAll();
  impLog(`✓ merged ${fmtInt(added)} turns into ${groups.length} new threads`);
  toast(`Merged ${fmtInt(added)} imported turns`);
}

function downloadMerged() {
  const merged = {
    meta: { ...Atlas.data.meta, generated: new Date().toISOString(), imported: Importer.pending.length,
            drive_files_imported: Importer.driveRows.length, chrome_visits: Importer.chromeRows.length },
    themes: Atlas.data.themes, threads: Atlas.data.threads,
    turns: [...Atlas.data.turns, ...Atlas.imported],
    drive_artifacts: [...(Atlas.data.drive_artifacts || []), ...Importer.driveRows.slice(0, 5000)],
    archive: Atlas.data.archive,
  };
  const blob = download('atlas.json', JSON.stringify(merged), 'application/json');
  impLog(`Downloaded merged atlas.json (${fmtBytes(blob.size)}) — replace atlas/data/atlas.json with it, `
    + 'then re-run tools/build_atlas.py to re-split atlas/data/threads/*.json and refresh the exports.');
  return blob;
}

function importInit() {
  const zone = $('#dropzone'), input = $('#fileInput');
  if (!zone) return;
  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('hot'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('hot'));
  zone.addEventListener('drop', async (e) => {
    e.preventDefault(); zone.classList.remove('hot');
    await ingestFiles(e.dataTransfer.files);
    zone.classList.remove('hot');
  });
  input.addEventListener('change', async () => { await ingestFiles(input.files); input.value = ''; });
  $('#impMerge').addEventListener('click', mergeImport);
  $('#impDownload').addEventListener('click', downloadMerged);
  $('#impReset').addEventListener('click', () => {
    Atlas.imported = [];
    Atlas.data.threads = Atlas.data.threads.filter((t) => !t._imported);
    Importer.pending = [];
    Store.write({ imported: [] });
    index(); refreshAll(); impLog('Imported data cleared.');
  });
}
