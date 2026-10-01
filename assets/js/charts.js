/* Apprentix — small SVG chart kit. No dependencies.
   Colours come from CSS custom properties (see "Charts" in site.css), so light
   and dark mode are handled by the stylesheet. Labels are inserted with
   textContent, never as HTML. */

const NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs = {}, parent) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
  if (parent) parent.appendChild(el);
  return el;
}

function text(parent, x, y, str, attrs = {}) {
  const t = svgEl('text', { x, y, ...attrs }, parent);
  t.textContent = str;
  return t;
}

/* ---------- formatting ---------- */

export function formatter(unit, values = []) {
  const max = Math.max(0, ...values.map(Math.abs));
  const pct = /%|percent/i.test(unit || '');
  const digits = pct ? 1 : max >= 1000 ? 0 : max >= 100 ? 0 : max >= 10 ? 1 : 2;
  const nf = new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: pct ? 1 : 0 });
  const compact = new Intl.NumberFormat('en-GB', { notation: 'compact', maximumFractionDigits: 1 });
  const fmt = v => v == null || Number.isNaN(v) ? '—' : nf.format(v) + (pct ? '%' : '');
  fmt.tick = v => (Math.abs(v) >= 10000 ? compact.format(v) : new Intl.NumberFormat('en-GB', { maximumFractionDigits: pct ? 0 : 1 }).format(v)) + (pct ? '%' : '');
  return fmt;
}

function niceTicks(min, max, count = 5) {
  if (min === max) { max = min + 1; }
  const span = max - min;
  const step0 = Math.pow(10, Math.floor(Math.log10(span / count)));
  const err = (span / count) / step0;
  const step = step0 * (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1);
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

/* ---------- tooltip (one per page) ---------- */

let tip;
function tooltip() {
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'viz-tip';
    tip.setAttribute('role', 'status');
    document.body.appendChild(tip);
  }
  return tip;
}

/** rows: [{value, label, key?: css colour var name}] — values lead, labels follow. */
function showTip(evt, title, rows) {
  const t = tooltip();
  t.replaceChildren();
  const h = document.createElement('div');
  h.className = 'tt-title';
  h.textContent = title;
  t.appendChild(h);
  for (const r of rows) {
    const row = document.createElement('div');
    row.className = 'tt-row';
    if (r.key) {
      const k = document.createElement('span');
      k.className = 'tt-key';
      k.style.background = `var(${r.key})`;
      row.appendChild(k);
    }
    const v = document.createElement('strong');
    v.textContent = r.value;
    const l = document.createElement('span');
    l.textContent = r.label;
    row.append(v, l);
    t.appendChild(row);
  }
  const x = evt.clientX ?? evt.target.getBoundingClientRect().right;
  const y = evt.clientY ?? evt.target.getBoundingClientRect().top;
  t.classList.add('show');
  const w = t.offsetWidth, hgt = t.offsetHeight;
  t.style.left = Math.min(window.innerWidth - w - 8, x + 14) + 'px';
  t.style.top = Math.max(8, y - hgt - 10) + 'px';
}
function hideTip() { tooltip().classList.remove('show'); }

/* ---------- tile-grid map ---------- */

/**
 * opts: { countries: [{code,name,tile}], values: Map(code -> {value, flag}),
 *         missing: Map(code -> flag), fmt, onSelect(code), selected: Set }
 * Sequential single-hue scale in 5 classes (quantiles of the shown values).
 */
export function tileMap(host, opts) {
  host.replaceChildren();
  const tiles = opts.countries.filter(c => c.tile);
  const cols = Math.max(...tiles.map(c => c.tile[0])) + 1;
  const rows = Math.max(...tiles.map(c => c.tile[1])) + 1;
  const size = 44, gap = 3;
  const W = cols * (size + gap), H = rows * (size + gap);
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'viz tilemap', role: 'img',
    'aria-label': opts.label || 'Map of European countries' }, host);

  const vals = [...opts.values.values()].map(v => v.value).filter(v => v != null).sort((a, b) => a - b);
  const breaks = vals.length ? [0.2, 0.4, 0.6, 0.8].map(q => vals[Math.floor(q * (vals.length - 1))]) : [];
  const cls = v => breaks.filter(b => v > b).length; // 0..4

  for (const c of tiles) {
    const [cx, cy] = c.tile;
    const g = svgEl('g', { transform: `translate(${cx * (size + gap)},${cy * (size + gap)})`,
      class: 'tile', tabindex: 0 }, svg);
    const v = opts.values.get(c.code);
    const miss = opts.missing?.get(c.code);
    const k = v ? cls(v.value) : null;
    svgEl('rect', { width: size, height: size, rx: 4,
      class: v ? `seq-${k}` : miss ? 'tile-na' : 'tile-empty' }, g);
    if (opts.selected?.has(c.code)) svgEl('rect', { width: size - 2, height: size - 2, x: 1, y: 1, rx: 3, class: 'tile-sel' }, g);
    text(g, size / 2, size / 2 + 4, c.code, { 'text-anchor': 'middle', class: `tile-code${v ? ` t-${k}` : ''}` });
    const label = v ? `${opts.fmt(v.value)}${v.flag ? ` (${v.flag})` : ''}` : miss ? `no value (${miss})` : 'no data';
    g.setAttribute('aria-label', `${c.name}: ${label}`);
    const over = e => showTip(e, c.name, [{ value: v ? opts.fmt(v.value) : '—',
      label: v ? (v.flag ? `flag ${v.flag}` : opts.year || '') : miss ? `flag ${miss}` : 'no data' }]);
    g.addEventListener('pointermove', over);
    g.addEventListener('focus', over);
    g.addEventListener('pointerleave', hideTip);
    g.addEventListener('blur', hideTip);
    if (opts.onSelect && v) {
      g.style.cursor = 'pointer';
      g.addEventListener('click', () => opts.onSelect(c.code));
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); opts.onSelect(c.code); } });
    }
  }

  // Legend: 5 classes + no value.
  const legend = document.createElement('div');
  legend.className = 'viz-legend seq';
  const lo = vals[0], hi = vals[vals.length - 1];
  const edges = [lo, ...breaks, hi];
  for (let i = 0; i < 5 && vals.length; i++) {
    const item = document.createElement('span');
    item.className = 'li';
    const sw = document.createElement('i');
    sw.className = `sw seq-${i}`;
    const lab = document.createElement('span');
    lab.textContent = `${opts.fmt.tick(edges[i])}–${opts.fmt.tick(edges[i + 1])}`;
    item.append(sw, lab);
    legend.appendChild(item);
  }
  for (const [c, l] of [['tile-na', 'flagged, no value'], ['tile-empty', 'no data']]) {
    const item = document.createElement('span');
    item.className = 'li';
    const sw = document.createElement('i'); sw.className = `sw ${c}`;
    const lab = document.createElement('span'); lab.textContent = l;
    item.append(sw, lab);
    legend.appendChild(item);
  }
  host.appendChild(legend);
}

/* ---------- ranked horizontal bars ---------- */

/**
 * rows: [{code, name, value, flag, emphasis}] — sorted by caller.
 * opts: { fmt, target: {value,label}, onSelect(code), selected: Set }
 */
export function barChart(host, rows, opts) {
  host.replaceChildren();
  const width = Math.max(300, host.clientWidth || 600);
  const longest = Math.max(0, ...rows.map(r => String(r.name).length));
  const rowH = 26, top = 8, valueW = 64, right = 12;
  const labelW = opts.fitLabels ? Math.min(width * 0.48, Math.max(90, longest * 6.6 + 14)) : Math.min(150, width * 0.32);
  const H = top + rows.length * rowH + 28;
  const svg = svgEl('svg', { viewBox: `0 0 ${width} ${H}`, width, height: H, class: 'viz bars', role: 'img',
    'aria-label': opts.label || 'Bar chart by country' }, host);
  const values = rows.map(r => r.value);
  const min = Math.min(0, ...values), max = Math.max(...values, opts.target?.value ?? -Infinity);
  const ticks = niceTicks(min, max, 4);
  const x0 = labelW, x1 = width - valueW - right;
  const sx = v => x0 + (v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0]) * (x1 - x0);
  const plotBottom = top + rows.length * rowH;

  for (const t of ticks) {
    svgEl('line', { x1: sx(t), x2: sx(t), y1: top, y2: plotBottom, class: 'grid' }, svg);
    text(svg, sx(t), plotBottom + 16, opts.fmt.tick(t), { 'text-anchor': 'middle', class: 'tick' });
  }
  svgEl('line', { x1: sx(0), x2: sx(0), y1: top, y2: plotBottom, class: 'axis' }, svg);

  rows.forEach((r, i) => {
    const y = top + i * rowH;
    const g = svgEl('g', { class: 'bar-row' + (opts.selected?.has(r.code) ? ' sel' : ''), tabindex: 0,
      'aria-label': `${r.name}: ${opts.fmt(r.value)}${r.flag ? ` (flag ${r.flag})` : ''}` }, svg);
    svgEl('rect', { x: 0, y, width, height: rowH, class: 'hit' }, g);
    text(g, x0 - 8, y + rowH / 2 + 4, r.name, { 'text-anchor': 'end', class: 'cat' + (r.emphasis ? ' strong' : '') });
    const bx = sx(Math.min(0, r.value)), bw = Math.max(1, Math.abs(sx(r.value) - sx(0)));
    const h = Math.min(16, rowH - 8);
    // 4px rounded data end, square at the baseline: draw a path.
    const yb = y + (rowH - h) / 2, rr = Math.min(4, bw);
    const pos = r.value >= 0;
    const d = pos
      ? `M${bx},${yb} h${bw - rr} a${rr},${rr} 0 0 1 ${rr},${rr} v${h - 2 * rr} a${rr},${rr} 0 0 1 -${rr},${rr} h-${bw - rr} z`
      : `M${bx + bw},${yb} h-${bw - rr} a${rr},${rr} 0 0 0 -${rr},${rr} v${h - 2 * rr} a${rr},${rr} 0 0 0 ${rr},${rr} h${bw - rr} z`;
    svgEl('path', { d, class: r.emphasis ? 'bar emph' : 'bar' }, g);
    text(g, sx(Math.max(0, r.value)) + 6, y + rowH / 2 + 4, opts.fmt(r.value) + (r.flag ? ` ${r.flag}` : ''), { class: 'val' });
    const over = e => showTip(e, r.name, [{ value: opts.fmt(r.value), label: r.flag ? `flag ${r.flag}` : (opts.year || '') }]);
    g.addEventListener('pointermove', over);
    g.addEventListener('focus', over);
    g.addEventListener('pointerleave', hideTip);
    g.addEventListener('blur', hideTip);
    if (opts.onSelect) {
      g.style.cursor = 'pointer';
      g.addEventListener('click', () => opts.onSelect(r.code));
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); opts.onSelect(r.code); } });
    }
  });

  if (opts.target) {
    const tx = sx(opts.target.value);
    svgEl('line', { x1: tx, x2: tx, y1: top - 4, y2: plotBottom, class: 'target' }, svg);
  }
}

/* ---------- lines over time ---------- */

/**
 * series: [{key, label, colorVar, points: [{time, value, flag}]}]
 * opts: { fmt, target: {value, label}, height }
 */
export function lineChart(host, series, opts) {
  host.replaceChildren();
  const width = Math.max(300, host.clientWidth || 600);
  const H = opts.height || 300;
  const m = { t: 14, r: 96, b: 28, l: 52 };
  const svg = svgEl('svg', { viewBox: `0 0 ${width} ${H}`, width, height: H, class: 'viz lines', role: 'img',
    'aria-label': opts.label || 'Line chart over time' }, host);

  const times = [...new Set(series.flatMap(s => s.points.map(p => p.time)))].sort();
  if (!times.length) return;
  const vals = series.flatMap(s => s.points.map(p => p.value));
  if (opts.target) vals.push(opts.target.value);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo > 0 && lo / (hi || 1) < 0.5) lo = 0; // include zero when it doesn't flatten the story
  const ticks = niceTicks(lo, hi, 5);
  const sy = v => m.t + (1 - (v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0])) * (H - m.t - m.b);
  const sx = t => times.length === 1 ? (m.l + width - m.r) / 2
    : m.l + times.indexOf(t) / (times.length - 1) * (width - m.l - m.r);

  for (const t of ticks) {
    svgEl('line', { x1: m.l, x2: width - m.r, y1: sy(t), y2: sy(t), class: 'grid' }, svg);
    text(svg, m.l - 8, sy(t) + 4, opts.fmt.tick(t), { 'text-anchor': 'end', class: 'tick' });
  }
  const every = Math.ceil(times.length / Math.max(2, Math.floor((width - m.l - m.r) / 56)));
  times.forEach((t, i) => {
    const last = i === times.length - 1;
    // Always label the last period, dropping the previous label if they would collide.
    const nextShown = (i + every) <= times.length - 1 ? i + every : times.length - 1;
    const crowded = !last && nextShown === times.length - 1 && (times.length - 1 - i) < every * 0.75;
    if ((i % every === 0 && !crowded) || last) text(svg, sx(t), H - 8, t, { 'text-anchor': last ? 'end' : 'middle', class: 'tick' });
  });
  svgEl('line', { x1: m.l, x2: width - m.r, y1: H - m.b, y2: H - m.b, class: 'axis' }, svg);

  if (opts.target) {
    const y = sy(opts.target.value);
    svgEl('line', { x1: m.l, x2: width - m.r, y1: y, y2: y, class: 'target' }, svg);
    text(svg, width - m.r + 6, y + 4, `Target ${opts.fmt(opts.target.value)}`, { class: 'tick target-label' });
  }

  const endLabels = [];
  for (const s of series) {
    const pts = s.points.filter(p => p.value != null).sort((a, b) => a.time.localeCompare(b.time));
    if (!pts.length) continue;
    // Break the line where years are missing.
    let d = '', prev = -2;
    for (const p of pts) {
      const idx = times.indexOf(p.time);
      d += `${idx === prev + 1 ? 'L' : 'M'}${sx(p.time)},${sy(p.value)}`;
      prev = idx;
    }
    svgEl('path', { d, class: 'line', style: `stroke:var(${s.colorVar})` }, svg);
    const last = pts[pts.length - 1];
    svgEl('circle', { cx: sx(last.time), cy: sy(last.value), r: 4, class: 'dot', style: `fill:var(${s.colorVar})` }, svg);
    endLabels.push({ y: sy(last.value), x: sx(last.time), label: s.label });
  }
  // Direct end labels only when they don't collide; otherwise the legend carries identity.
  endLabels.sort((a, b) => a.y - b.y);
  const clear = endLabels.every((l, i) => i === 0 || l.y - endLabels[i - 1].y >= 13);
  if (clear && endLabels.length <= 4) {
    for (const l of endLabels) text(svg, l.x + 8, l.y + 4, l.label, { class: 'end-label' });
  }

  // Crosshair + one tooltip listing every series at that year.
  const cross = svgEl('line', { y1: m.t, y2: H - m.b, class: 'crosshair', visibility: 'hidden' }, svg);
  const overlay = svgEl('rect', { x: m.l, y: m.t, width: Math.max(1, width - m.l - m.r), height: H - m.t - m.b,
    class: 'hit', tabindex: 0, 'aria-label': 'Chart values by year; use arrow keys' }, svg);
  let focusIdx = times.length - 1;
  const showAt = (idx, evt) => {
    const t = times[idx];
    cross.setAttribute('x1', sx(t)); cross.setAttribute('x2', sx(t));
    cross.setAttribute('visibility', 'visible');
    const rows = series.map(s => {
      const p = s.points.find(p => p.time === t);
      return { value: p ? opts.fmt(p.value) + (p.flag ? ` ${p.flag}` : '') : '—', label: s.label, key: s.colorVar };
    });
    showTip(evt, t, rows);
  };
  overlay.addEventListener('pointermove', e => {
    const r = svg.getBoundingClientRect();
    const px = (e.clientX - r.left) * (width / r.width);
    let best = 0, bd = Infinity;
    times.forEach((t, i) => { const dd = Math.abs(sx(t) - px); if (dd < bd) { bd = dd; best = i; } });
    focusIdx = best;
    showAt(best, e);
  });
  overlay.addEventListener('focus', () => {
    const r = svg.getBoundingClientRect();
    showAt(focusIdx, { clientX: r.left + sx(times[focusIdx]) * r.width / width, clientY: r.top + 20 });
  });
  overlay.addEventListener('keydown', e => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    focusIdx = Math.max(0, Math.min(times.length - 1, focusIdx + (e.key === 'ArrowRight' ? 1 : -1)));
    const r = svg.getBoundingClientRect();
    showAt(focusIdx, { clientX: r.left + sx(times[focusIdx]) * r.width / width, clientY: r.top + 20 });
  });
  const hide = () => { cross.setAttribute('visibility', 'hidden'); hideTip(); };
  overlay.addEventListener('pointerleave', hide);
  overlay.addEventListener('blur', hide);
}

/* ---------- legend for categorical series ---------- */

export function lineLegend(host, series, onRemove) {
  host.replaceChildren();
  for (const s of series) {
    const item = document.createElement('span');
    item.className = 'li';
    const k = document.createElement('i');
    k.className = 'line-key';
    k.style.background = `var(${s.colorVar})`;
    const l = document.createElement('span');
    l.textContent = s.label;
    item.append(k, l);
    if (onRemove && s.removable) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'li-x';
      b.setAttribute('aria-label', `Remove ${s.label}`);
      b.textContent = '✕';
      b.addEventListener('click', () => onRemove(s.key));
      item.appendChild(b);
    }
    host.appendChild(item);
  }
}

/* ---------- scatter (one series, labelled points, optional target lines) ---------- */

/**
 * points: [{geo, name, x, y}]; opts: { fmtX, fmtY, xLabel, yLabel, targets: {x, y} }
 */
export function scatterChart(host, points, opts) {
  host.replaceChildren();
  const width = Math.max(300, host.clientWidth || 600);
  const H = Math.min(420, Math.max(300, width * 0.62));
  const m = { t: 30, r: 18, b: 44, l: 52 };
  const svg = svgEl('svg', { viewBox: `0 0 ${width} ${H}`, width, height: H, class: 'viz scatter', role: 'img',
    'aria-label': opts.label || 'Scatter chart' }, host);
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  if (opts.targets?.x != null) xs.push(opts.targets.x);
  if (opts.targets?.y != null) ys.push(opts.targets.y);
  const tx = niceTicks(Math.min(...xs), Math.max(...xs), 5), ty = niceTicks(Math.min(...ys), Math.max(...ys), 5);
  const sx = v => m.l + (v - tx[0]) / (tx[tx.length - 1] - tx[0]) * (width - m.l - m.r);
  const sy = v => m.t + (1 - (v - ty[0]) / (ty[ty.length - 1] - ty[0])) * (H - m.t - m.b);
  for (const t of ty) {
    svgEl('line', { x1: m.l, x2: width - m.r, y1: sy(t), y2: sy(t), class: 'grid' }, svg);
    text(svg, m.l - 8, sy(t) + 4, opts.fmtY.tick(t), { 'text-anchor': 'end', class: 'tick' });
  }
  for (const t of tx) {
    svgEl('line', { x1: sx(t), x2: sx(t), y1: m.t, y2: H - m.b, class: 'grid' }, svg);
    text(svg, sx(t), H - m.b + 16, opts.fmtX.tick(t), { 'text-anchor': 'middle', class: 'tick' });
  }
  text(svg, (m.l + width - m.r) / 2, H - 6, opts.xLabel || '', { 'text-anchor': 'middle', class: 'tick axis-title' });
  text(svg, m.l - 40, 12, opts.yLabel || '', { class: 'tick axis-title' });
  if (opts.targets?.x != null) svgEl('line', { x1: sx(opts.targets.x), x2: sx(opts.targets.x), y1: m.t, y2: H - m.b, class: 'target' }, svg);
  if (opts.targets?.y != null) svgEl('line', { x1: m.l, x2: width - m.r, y1: sy(opts.targets.y), y2: sy(opts.targets.y), class: 'target' }, svg);
  for (const p of points) {
    const g = svgEl('g', { class: 'pt', tabindex: 0, 'aria-label': `${p.name}: ${opts.fmtX(p.x)}, ${opts.fmtY(p.y)}` }, svg);
    svgEl('circle', { cx: sx(p.x), cy: sy(p.y), r: 12, class: 'hit' }, g);
    svgEl('circle', { cx: sx(p.x), cy: sy(p.y), r: 4.5, class: 'dot', style: 'fill:var(--bar)' }, g);
    text(g, sx(p.x) + 7, sy(p.y) - 6, p.geo, { class: 'pt-label' });
    const over = e => showTip(e, p.name, [{ value: opts.fmtX(p.x), label: opts.xShort || 'x' }, { value: opts.fmtY(p.y), label: opts.yShort || 'y' }]);
    g.addEventListener('pointermove', over); g.addEventListener('focus', over);
    g.addEventListener('pointerleave', hideTip); g.addEventListener('blur', hideTip);
  }
}

/* ---------- paired horizontal bars (two groups, legend) ---------- */

export function pairedBars(host, rows, opts) {
  host.replaceChildren();
  const width = Math.max(300, host.clientWidth || 600);
  const rowH = 40, top = 6, labelW = Math.min(230, width * 0.42), right = 48;
  const H = top + rows.length * rowH + 24;
  const svg = svgEl('svg', { viewBox: `0 0 ${width} ${H}`, width, height: H, class: 'viz bars', role: 'img',
    'aria-label': opts.label || 'Paired bar chart' }, host);
  const x0 = labelW, x1 = width - right;
  const sx = v => x0 + v / 100 * (x1 - x0);
  for (const t of [0, 25, 50, 75, 100]) {
    svgEl('line', { x1: sx(t), x2: sx(t), y1: top, y2: top + rows.length * rowH, class: 'grid' }, svg);
    text(svg, sx(t), top + rows.length * rowH + 16, t + '%', { 'text-anchor': 'middle', class: 'tick' });
  }
  rows.forEach((r, i) => {
    const y = top + i * rowH;
    text(svg, x0 - 8, y + rowH / 2 + 4, r.label, { 'text-anchor': 'end', class: 'cat' });
    [['a', '--series-1'], ['b', '--series-2']].forEach(([k, c], j) => {
      const v = r[k], by = y + 6 + j * 14, w = Math.max(1, sx(v) - sx(0));
      const g = svgEl('g', { tabindex: 0, 'aria-label': `${r.label}, ${opts.groups[j]}: ${v}%` }, svg);
      svgEl('rect', { x: sx(0), y: by, width: w, height: 11, rx: 3, style: `fill:var(${c})` }, g);
      text(g, sx(v) + 5, by + 9, v + '%', { class: 'val' });
      const over = e => showTip(e, r.label, [{ value: v + '%', label: opts.groups[j], key: c }]);
      g.addEventListener('pointermove', over); g.addEventListener('focus', over);
      g.addEventListener('pointerleave', hideTip); g.addEventListener('blur', hideTip);
    });
  });
}
