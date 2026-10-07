/* map.js — interactive mind map (radial / tree / status / theme-cluster) */
'use strict';

const MapView = {
  svg: null, root: null,
  xf: { x: 0, y: 0, k: 1 },
  layout: 'radial',
  depth: 3,
  showLabels: true,
  sizeByVolume: false,
  expanded: new Set(),
  focusTheme: null,
  nodes: [],
  links: [],
  selectedKey: null,
};

function mapInit() {
  MapView.svg = $('#mapsvg');
  MapView.root = $('#maproot');
  const svg = MapView.svg;

  svg.addEventListener('wheel', (e) => {
    e.preventDefault();
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const k2 = Math.min(4, Math.max(0.15, MapView.xf.k * (e.deltaY < 0 ? 1.12 : 0.89)));
    const s = k2 / MapView.xf.k;
    MapView.xf.x = mx - (mx - MapView.xf.x) * s;
    MapView.xf.y = my - (my - MapView.xf.y) * s;
    MapView.xf.k = k2;
    mapApply();
  }, { passive: false });

  let drag = null;
  svg.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.mnode')) return;
    drag = { x: e.clientX, y: e.clientY, ox: MapView.xf.x, oy: MapView.xf.y };
    svg.classList.add('dragging');
    svg.setPointerCapture(e.pointerId);
  });
  svg.addEventListener('pointermove', (e) => {
    if (!drag) return;
    MapView.xf.x = drag.ox + (e.clientX - drag.x);
    MapView.xf.y = drag.oy + (e.clientY - drag.y);
    mapApply();
  });
  svg.addEventListener('pointerup', (e) => {
    drag = null;
    svg.classList.remove('dragging');
  });

  $('#mapLayout').addEventListener('change', (e) => { MapView.layout = e.target.value; mapRender(); });
  $('#mapDepth').addEventListener('change', (e) => { MapView.depth = +e.target.value; mapRender(); });
  $('#mapLabels').addEventListener('change', (e) => { MapView.showLabels = e.target.checked; mapRender(); });
  $('#mapSized').addEventListener('change', (e) => { MapView.sizeByVolume = e.target.checked; mapRender(); });
  $('#mapFit').addEventListener('click', mapFit);
  $('#mapZoomIn').addEventListener('click', () => { MapView.xf.k = Math.min(4, MapView.xf.k * 1.2); mapApply(); });
  $('#mapZoomOut').addEventListener('click', () => { MapView.xf.k = Math.max(0.15, MapView.xf.k / 1.2); mapApply(); });
  window.addEventListener('resize', () => mapFit());
}

function mapApply() {
  MapView.root.setAttribute('transform',
    `translate(${MapView.xf.x},${MapView.xf.y}) scale(${MapView.xf.k})`);
}

function mapFit() {
  const svg = MapView.svg;
  const w = svg.clientWidth || 900, h = svg.clientHeight || 600;
  const xs = MapView.nodes.map((n) => n.x), ys = MapView.nodes.map((n) => n.y);
  if (!xs.length) return;
  const pad = 70;
  const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad;
  const minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
  const k = Math.min(w / (maxX - minX), h / (maxY - minY), 2);
  MapView.xf = { k, x: w / 2 - ((minX + maxX) / 2) * k, y: h / 2 - ((minY + maxY) / 2) * k };
  mapApply();
}

function mapRender() {
  const threads = filteredThreads();
  const active = filteredTurns().length;
  MapView.nodes = [];
  MapView.links = [];
  const R = MapView.root;
  R.innerHTML = '';

  const depth = MapView.depth;
  if (MapView.layout === 'radial') layoutRadial(threads, depth);
  else if (MapView.layout === 'tree') layoutTree(threads, depth);
  else if (MapView.layout === 'status') layoutStatus(threads, depth);
  else layoutClusters(threads, depth);

  // links first
  for (const l of MapView.links) {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', l.d);
    path.setAttribute('class', 'mlink');
    path.setAttribute('stroke-width', l.w || 1);
    if (l.color) path.setAttribute('stroke', l.color);
    path.setAttribute('stroke-opacity', l.o ?? 0.5);
    R.append(path);
  }
  // nodes
  for (const n of MapView.nodes) R.append(mapNodeEl(n));

  renderMapLegend();
  if (!MapView._fitted) { mapFit(); MapView._fitted = true; }
  else mapApply();
}

function mapNodeEl(n) {
  const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  g.setAttribute('class', 'mnode' + (MapView.selectedKey === n.key ? ' sel' : ''));
  g.setAttribute('transform', `translate(${n.x},${n.y})`);
  g.dataset.key = n.key;
  if (n.type === 'topic' || n.type === 'cluster') {
    const w = n.w || Math.max(120, (n.label.length * 7.2) + 26);
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', -w / 2); rect.setAttribute('y', -n.r);
    rect.setAttribute('width', w); rect.setAttribute('height', n.r * 2);
    rect.setAttribute('rx', n.r);
    rect.setAttribute('fill', n.color + '2a');
    rect.setAttribute('stroke', n.color);
    rect.setAttribute('stroke-width', 1.6);
    g.append(rect);
  } else {
    const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('r', n.r);
    c.setAttribute('fill', n.color + (n.type === 'root' ? '' : 'cc'));
    c.setAttribute('stroke', n.type === 'root' ? '#f5d07a' : '#0b0e14');
    c.setAttribute('stroke-width', n.type === 'root' ? 2 : 1.5);
    g.append(c);
    if (n.type !== 'root' && n.pct !== undefined) {
      const arc = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      const r2 = n.r + 3.2;
      const circ = 2 * Math.PI * r2;
      arc.setAttribute('r', r2);
      arc.setAttribute('fill', 'none');
      arc.setAttribute('stroke', '#e8b33d');
      arc.setAttribute('stroke-width', 2.4);
      arc.setAttribute('stroke-dasharray', `${(n.pct / 100) * circ} ${circ}`);
      arc.setAttribute('transform', 'rotate(-90)');
      arc.setAttribute('stroke-linecap', 'round');
      g.append(arc);
    }
  }
  // Label density rules: threads are labelled only once the user zooms in
  // (or in the tree layout, which spreads them vertically) so the radial view
  // never turns into a pile of overlapping words.
  const roomy = MapView.layout === 'tree' || MapView.xf.k > 0.8;
  const show = MapView.showLabels && (n.type === 'root' || n.type === 'topic' ||
    n.type === 'cluster' || (n.type === 'thread' && (roomy || !n.labelCollides)));
  if (show && (n.type !== 'turn' || MapView.xf.k > 1.1)) {
    const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('class', 'maplabel');
    t.setAttribute('y', n.labelDy ?? (n.r + 12));
    t.setAttribute('text-anchor', 'middle');
    t.textContent = n.label.length > 34 ? n.label.slice(0, 33) + '…' : n.label;
    g.append(t);
    if (n.sub && MapView.xf.k > 0.6) {
      const s = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      s.setAttribute('class', 'mapmeta');
      s.setAttribute('y', (n.labelDy ?? (n.r + 12)) + 11);
      s.setAttribute('text-anchor', 'middle');
      s.textContent = n.sub;
      g.append(s);
    }
  }
  g.addEventListener('click', (e) => { e.stopPropagation(); mapSelect(n); });
  g.addEventListener('dblclick', (e) => {
    e.stopPropagation();
    MapView.xf.k = Math.min(3.2, MapView.xf.k * 1.9);
    MapView.xf.x = MapView.svg.clientWidth / 2 - n.x * MapView.xf.k;
    MapView.xf.y = MapView.svg.clientHeight / 2 - n.y * MapView.xf.k;
    mapApply();
  });
  return g;
}

const ROOT_NODE = { key: 'root', type: 'root', label: 'Your AI & Google history', r: 26, x: 0, y: 0, color: '#e8b33d' };

/* ---------------------------------------------------------------- layouts */
function radialPoint(cx, cy, r, a) { return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }

function layoutRadial(threads, depth) {
  const themes = Atlas.data.themes.filter((t) => threads.some((th) => th.theme === t.id) ||
    (Atlas.filters.themes || []).includes(t.id));
  const root = { ...ROOT_NODE };
  MapView.nodes.push(root);
  const innerR = 240, outerR = 620, turnR = 110;
  const total = threads.length || 1;
  const perTheme = new Map();
  for (const t of themes) perTheme.set(t.id, threads.filter((th) => th.theme === t.id));

  themes.forEach((th, i) => {
    const span = (perTheme.get(th.id).length / total) * Math.PI * 2;
    const mid = (i / themes.length) * Math.PI * 2 - Math.PI / 2 + span / 2;
    const [tx, ty] = radialPoint(0, 0, innerR, mid);
    MapView.nodes.push({
      key: 'th:' + th.id, type: 'topic', label: th.name, sub: `${perTheme.get(th.id).length} threads`,
      x: tx, y: ty, r: 15, color: th.color, w: 160, pct: th.completeness,
    });
    MapView.links.push({
      d: `M0,0 Q${tx * 0.55},${ty * 0.55} ${tx},${ty}`,
      color: th.color, w: 1 + Math.min(6, perTheme.get(th.id).length / 12), o: 0.75,
    });
    let acc = -span / 2;
    let prev = null;
    for (const thread of perTheme.get(th.id)) {
      const share = (thread.turn_count / Math.max(1, perTheme.get(th.id).reduce((s, x) => s + x.turn_count, 0))) * span;
      const a = mid + acc + share / 2;
      acc += share;
      const [x, y] = radialPoint(0, 0, outerR, a);
      const r = nodeRadius(thread);
      const collides = prev ? Math.hypot(x - prev[0], y - prev[1]) < 74 : false;
      prev = [x, y];
      MapView.nodes.push({
        key: 'thr:' + thread.id, type: 'thread', label: threadTitle(thread), sub: `${thread.turn_count} turns · ${thread.completeness.percent}%`,
        x, y, r, color: themeById(thread.theme).color, pct: thread.completeness.percent, threadId: thread.id,
        labelDy: r + 12, labelCollides: collides,
      });
      MapView.links.push({
        d: `M${tx},${ty} Q${(tx + x) / 2 + 18},${(ty + y) / 2 + 18} ${x},${y}`,
        color: themeById(thread.theme).color, w: 1, o: 0.4,
      });
      if (depth >= 3 && MapView.expanded.has(thread.id) && MapView.expanded.size <= 3) {
        const turns = Atlas.turnsByThread.get(thread.id) || [];
        const [bx, by] = radialPoint(0, 0, outerR + turnR, a);
        turns.slice(0, 60).forEach((turn, ti) => {
          const t1 = turn.ts ? new Date(turn.ts).getTime() : (ti * 1000);
          const [x1, y1] = radialPoint(0, 0, outerR + turnR + (t1 % 97), a + ((ti % 12) - 6) * 0.012);
          MapView.nodes.push({
            key: 'turn:' + turn.id, type: 'turn', label: '', x: x1, y: y1, r: 3.6,
            color: themeById(turn.theme).color, threadId: thread.id, turnId: turn.id,
            labelDy: 0,
          });
          MapView.links.push({ d: `M${x},${y} L${x1},${y1}`, color: themeById(turn.theme).color, w: 0.5, o: 0.32 });
        });
      }
    }
  });
}

function nodeRadius(thread) {
  if (!MapView.sizeByVolume) return Math.max(6, Math.min(22, 6 + Math.sqrt(thread.turn_count) * 0.9));
  return Math.max(6, Math.min(34, 6 + Math.sqrt(thread.chars / 500)));
}

function layoutTree(threads, depth) {
  const themes = Atlas.data.themes.filter((t) => threads.some((th) => th.theme === t.id));
  const root = { ...ROOT_NODE, x: 0, y: 0 };
  MapView.nodes.push(root);
  const x0 = 150, x1 = 430, x2 = 760, x3 = 1050;
  let y = 0;
  const rowH = 24;
  for (const th of themes) {
    const list = threads.filter((t) => t.theme === th.id);
    const y0 = y;
    const spanY = list.length * rowH;
    const yt = y0 + spanY / 2;
    MapView.nodes.push({
      key: 'th:' + th.id, type: 'topic', label: th.name, sub: `${list.length} threads · ${th.completeness}%`,
      x: x0, y: yt, r: 12, color: th.color, w: 160, pct: th.completeness, labelDy: 0,
    });
    MapView.links.push({ d: `M0,0 C${x0 * .5},0 ${x0 * .5},${yt} ${x0},${yt}`, color: th.color, w: 2.5, o: .8 });
    for (const thread of list) {
      const ty = y + rowH / 2;
      const r = nodeRadius(thread);
      MapView.nodes.push({
        key: 'thr:' + thread.id, type: 'thread', label: threadTitle(thread),
        sub: `${thread.turn_count}t · ${thread.completeness.percent}% · ${thread.status}`,
        x: x1, y: ty, r, color: themeById(thread.theme).color, pct: thread.completeness.percent,
        threadId: thread.id, labelDy: -r - 5,
      });
      MapView.links.push({ d: `M${x0 + 82},${yt} C${x0 + 150},${yt} ${x1 - 120},${ty} ${x1 - r},${ty}`, color: th.color, w: .8, o: .35 });
      if (depth >= 3 && MapView.expanded.has(thread.id)) {
        const turns = Atlas.turnsByThread.get(thread.id) || [];
        turns.slice(0, 80).forEach((turn, ti) => {
          const yy = ty + (ti - turns.length / 2) * 5.5;
          MapView.nodes.push({
            key: 'turn:' + turn.id, type: 'turn', label: '', x: x2, y: yy, r: 4,
            color: themeById(turn.theme).color, threadId: thread.id, turnId: turn.id, labelDy: 0,
          });
          MapView.links.push({ d: `M${x1 + r},${ty} L${x2 - 4},${yy}`, color: themeById(turn.theme).color, w: .5, o: .3 });
        });
      }
      y += rowH;
    }
  }
  MapView.rootBounds = { w: x3, h: Math.max(600, y + 40) };
}

function layoutStatus(threads, depth) {
  const groups = [['active', '#49c07a'], ['open', '#e8b33d'], ['parked', '#5b8def'],
                  ['blocked', '#ef5f6b'], ['dormant', '#6f7c96'], ['complete', '#35c0ac']];
  const cols = 3, colW = 420, rowH = 210;
  groups.forEach(([status, color], gi) => {
    const list = threads.filter((t) => t.status === status);
    const cx = (gi % cols) * colW, cy = Math.floor(gi / cols) * rowH;
    MapView.nodes.push({
      key: 'st:' + status, type: 'cluster', label: `${status} · ${list.length}`, x: cx, y: cy - 60,
      r: 14, color, w: 200, labelDy: 0,
    });
    const perRow = Math.max(1, Math.floor(colW / 46));
    list.slice(0, 200).forEach((thread, i) => {
      const px = cx - colW / 2 + 34 + (i % perRow) * 44;
      const py = cy - 20 + Math.floor(i / perRow) * 34;
      const r = Math.max(5, Math.min(16, 5 + Math.sqrt(thread.turn_count)));
      MapView.nodes.push({
        key: 'thr:' + thread.id, type: 'thread', label: i % 3 === 0 ? threadTitle(thread) : '',
        sub: '', x: px, y: py, r, color: themeById(thread.theme).color,
        pct: thread.completeness.percent, threadId: thread.id, labelDy: r + 11,
      });
    });
  });
}

function layoutClusters(threads, depth) {
  const themes = Atlas.data.themes.filter((t) => threads.some((th) => th.theme === t.id));
  const cols = 3, colW = 430, rowH = 300;
  themes.forEach((th, gi) => {
    const list = threads.filter((t) => t.theme === th.id);
    const cx = (gi % cols) * colW, cy = Math.floor(gi / cols) * rowH;
    MapView.nodes.push({
      key: 'th:' + th.id, type: 'cluster', label: `${th.name} · ${list.length}`, x: cx, y: cy - 92,
      r: 14, color: th.color, w: 300, pct: th.completeness, labelDy: 0,
    });
    const perRow = Math.max(1, Math.floor(colW / 52));
    list.slice(0, 240).forEach((thread, i) => {
      const px = cx - colW / 2 + 40 + (i % perRow) * 50;
      const py = cy - 56 + Math.floor(i / perRow) * 46;
      const r = nodeRadius(thread);
      MapView.nodes.push({
        key: 'thr:' + thread.id, type: 'thread',
        label: i % 4 === 0 ? threadTitle(thread) : '', sub: '',
        x: px, y: py, r, color: themeById(thread.theme).color,
        pct: thread.completeness.percent, threadId: thread.id, labelDy: r + 12,
      });
    });
  });
}

/* ---------------------------------------------------------------- selection */
function mapSelect(n) {
  MapView.selectedKey = n.key;
  Atlas.sel.nodeKey = n.key;
  if (n.type === 'thread') {
    Atlas.sel.threadId = n.threadId;
    Atlas.sel.turnId = null;
    renderThreadInspector($('#inspector'), n.threadId);
    // Depth view: clicking a thread reveals its turns as a fan of small nodes.
    if (MapView.depth >= 3) {
      if (MapView.expanded.has(n.threadId) && MapView.lastExpanded === n.threadId) {
        MapView.expanded.delete(n.threadId);
      } else {
        MapView.expanded.add(n.threadId);
        MapView.lastExpanded = n.threadId;
      }
    }
  } else if (n.type === 'turn') {
    Atlas.sel.turnId = n.turnId;
    Atlas.sel.threadId = n.threadId;
    renderTurnInspector($('#inspector'), n.turnId);
  } else if (n.type === 'topic' || n.type === 'cluster') {
    const id = n.key.startsWith('th:') ? n.key.slice(3) : (n.key.startsWith('st:') ? n.key : null);
    renderThemeInspector($('#inspector'), id);
  } else {
    renderOverviewInspector($('#inspector'));
  }
  mapRender();
}

function renderMapLegend() {
  const box = $('#maplegend');
  const shown = filteredThreads().length;
  box.innerHTML = '';
  box.append(el('div', {}, el('span', { class: 'dot', style: 'background:#e8b33d' }), 'ring = completeness'));
  box.append(el('div', {}, el('span', { class: 'dot', style: 'background:#49c07a' }), 'size ∝ turns produced'));
  box.append(el('div', { class: 'muted' }, `${fmtInt(shown)} threads · ${fmtInt(filteredTurns().length)} turns shown`));
  box.append(el('div', { class: 'muted' }, 'click = inspect · dbl-click = zoom in'));
}
