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

/** Five-class breaks (4 values) from a pool of numbers: quantiles at 20/40/60/80 %. */
function quantileBreaks(sorted) {
  return sorted.length ? [0.2, 0.4, 0.6, 0.8].map(q => sorted[Math.floor(q * (sorted.length - 1))]) : [];
}

/**
 * A colour scale that stays fixed across years: pass every value that can be
 * shown (e.g. all countries × all years) and hand the result to tileMap as
 * { domain, breaks }. Breaks are quantiles of the pooled values.
 */
export function fixedScale(values) {
  const v = values.filter(x => x != null && !Number.isNaN(x)).sort((a, b) => a - b);
  if (!v.length) return null;
  return { domain: [v[0], v[v.length - 1]], breaks: quantileBreaks(v) };
}

/**
 * opts: { countries: [{code,name,tile}], values: Map(code -> {value, flag}),
 *         missing: Map(code -> flag), fmt, onSelect(code), selected: Set,
 *         domain?: [min, max], breaks?: [b1..b4] }
 * Sequential single-hue scale in 5 classes. By default the classes are
 * quantiles of the shown values; with `domain` (and optionally `breaks`) the
 * scale is fixed — e.g. the same for every year of a time-lapse — and the
 * legend shows that fixed scale. Without `breaks`, a domain is cut into five
 * equal intervals.
 * Returns { svg, update(partialOpts) }: update re-colours the existing tiles in
 * place (no DOM rebuild, so focus and CSS fill transitions survive).
 */
export function tileMap(host, opts) {
  host.replaceChildren();
  const tiles = opts.countries.filter(c => c.tile);
  const cols = Math.max(...tiles.map(c => c.tile[0])) + 1;
  const rows = Math.max(...tiles.map(c => c.tile[1])) + 1;
  const size = 44, gap = 3;
  const W = cols * (size + gap), H = rows * (size + gap);
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'viz tilemap', role: 'img' }, host);
  const legend = document.createElement('div');
  legend.className = 'viz-legend seq';

  let cur = { ...opts };
  let breaks = [], edges = [];
  const cls = v => breaks.filter(b => v > b).length; // 0..4

  const cells = tiles.map(c => {
    const [cx, cy] = c.tile;
    const g = svgEl('g', { transform: `translate(${cx * (size + gap)},${cy * (size + gap)})`,
      class: 'tile', tabindex: 0 }, svg);
    const rect = svgEl('rect', { width: size, height: size, rx: 4 }, g);
    const sel = svgEl('rect', { width: size - 2, height: size - 2, x: 1, y: 1, rx: 3, class: 'tile-sel' }, g);
    const label = text(g, size / 2, size / 2 + 4, c.code, { 'text-anchor': 'middle' });
    const over = e => {
      const v = cur.values.get(c.code), miss = cur.missing?.get(c.code);
      showTip(e, c.name, [{ value: v ? cur.fmt(v.value) : '—',
        label: v ? (v.flag ? `flag ${v.flag}` : cur.year || '') : miss ? `flag ${miss}` : 'no data' }]);
    };
    const pick = () => { if (cur.onSelect && cur.values.get(c.code)) cur.onSelect(c.code); };
    g.addEventListener('pointermove', over);
    g.addEventListener('focus', over);
    g.addEventListener('pointerleave', hideTip);
    g.addEventListener('blur', hideTip);
    g.addEventListener('click', pick);
    g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
    return { c, g, rect, sel, label };
  });

  function paint(next = {}) {
    cur = { ...cur, ...next };
    svg.setAttribute('aria-label', cur.label || 'Map of European countries');
    const shown = [...cur.values.values()].map(v => v.value).filter(v => v != null).sort((a, b) => a - b);
    if (cur.domain) {
      const [lo, hi] = cur.domain;
      breaks = cur.breaks?.length === 4 ? cur.breaks : [1, 2, 3, 4].map(i => lo + (hi - lo) * i / 5);
      edges = [lo, ...breaks, hi];
    } else {
      breaks = quantileBreaks(shown);
      edges = shown.length ? [shown[0], ...breaks, shown[shown.length - 1]] : [];
    }
    for (const { c, g, rect, sel, label } of cells) {
      const v = cur.values.get(c.code);
      const miss = cur.missing?.get(c.code);
      const k = v ? cls(v.value) : null;
      rect.setAttribute('class', v ? `seq-${k}` : miss ? 'tile-na' : 'tile-empty');
      sel.setAttribute('visibility', cur.selected?.has(c.code) ? 'visible' : 'hidden');
      label.setAttribute('class', `tile-code${v ? ` t-${k}` : ''}`);
      const desc = v ? `${cur.fmt(v.value)}${v.flag ? ` (${v.flag})` : ''}` : miss ? `no value (${miss})` : 'no data';
      g.setAttribute('aria-label', `${c.name}: ${desc}`);
      g.style.cursor = cur.onSelect && v ? 'pointer' : '';
    }
    renderLegend();
  }

  // Legend: 5 classes + no value.
  function renderLegend() {
    legend.replaceChildren();
    for (let i = 0; i < 5 && edges.length; i++) {
      const item = document.createElement('span');
      item.className = 'li';
      const sw = document.createElement('i');
      sw.className = `sw seq-${i}`;
      const lab = document.createElement('span');
      lab.textContent = `${cur.fmt.tick(edges[i])}–${cur.fmt.tick(edges[i + 1])}`;
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
  }

  paint();
  host.appendChild(legend);
  return { svg, update: paint };
}

/* ---------- time-lapse controls (play/pause + year slider) ---------- */

export const prefersReducedMotion = () =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * Play/pause button and a labelled year slider, appended to `host`.
 * opts: { steps: ['2014', …], index, interval = 900, label = 'Year',
 *         onStep(index, {source: 'play'|'user'|'set'}), onPlayState(playing), onEnd(),
 *         hasNext?(), advance?(), hold? }
 * Playing advances one step per `interval` ms and stops on the last step;
 * pressing play on the last step restarts from the first. Moving the slider
 * pauses. The elements are never rebuilt, so keyboard focus stays put.
 * Returns { play, pause, toggle, set(index), setSteps(steps, index), index, playing, button, slider }.
 */
export function timeControls(host, opts) {
  let steps = opts.steps.slice();
  let idx = Math.max(0, Math.min(steps.length - 1, opts.index ?? steps.length - 1));
  let timer = null;
  const interval = opts.interval || 900;
  const uid = 'tl-' + Math.random().toString(36).slice(2, 8);

  const wrap = document.createElement('div');
  wrap.className = 'tl-controls';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'tl-play';
  const icon = document.createElement('span');
  icon.className = 'tl-icon';
  icon.setAttribute('aria-hidden', 'true');
  const word = document.createElement('span');
  btn.append(icon, word);

  const lab = document.createElement('label');
  lab.className = 'tl-slider';
  lab.htmlFor = uid;
  const labText = document.createElement('span');
  labText.className = 'tl-slider-label';
  labText.textContent = opts.label || 'Year';
  const slider = document.createElement('input');
  slider.type = 'range';
  slider.id = uid;
  slider.min = '0';
  slider.step = '1';
  const out = document.createElement('output');
  out.className = 'tl-out';
  out.htmlFor = uid;
  lab.append(labText, slider);
  wrap.append(btn, lab, out);
  host.appendChild(wrap);

  const sync = () => {
    slider.max = String(Math.max(0, steps.length - 1));
    slider.value = String(idx);
    slider.disabled = steps.length < 2;
    slider.setAttribute('aria-valuetext', steps[idx] ?? '');
    out.textContent = steps[idx] ?? '';
    const playing = !!timer;
    icon.textContent = playing ? '❚❚' : '▶';
    word.textContent = playing ? 'Pause' : 'Play';
    btn.setAttribute('aria-label', playing ? `Pause the time-lapse (showing ${steps[idx]})` : 'Play the time-lapse, year by year');
    wrap.classList.toggle('is-playing', playing);
  };

  const go = (i, source) => {
    idx = Math.max(0, Math.min(steps.length - 1, i));
    sync();
    opts.onStep?.(idx, { source });
  };

  // At the last step: stop, unless opts.hasNext() says there is more to show
  // (e.g. the next indicator) — then hold the last frame for opts.hold ms while
  // still "playing" (so Pause can cancel it) and call opts.advance().
  const atEnd = () => {
    if (opts.hasNext?.()) {
      timer = setTimeout(() => { timer = null; sync(); opts.onPlayState?.(false); opts.advance(); }, opts.hold ?? 2400);
    } else { stop(); opts.onEnd?.(); }
  };
  const tick = () => {
    if (idx >= steps.length - 1) return atEnd();
    go(idx + 1, 'play');
    if (idx >= steps.length - 1) return atEnd();
    timer = setTimeout(tick, interval);
  };

  function stop() {
    const was = !!timer;
    clearTimeout(timer);
    timer = null;
    sync();
    if (was) opts.onPlayState?.(false);
  }

  function play() {
    if (timer || steps.length < 2) return;
    if (idx >= steps.length - 1) go(0, 'play');
    timer = setTimeout(tick, interval);
    sync();
    opts.onPlayState?.(true);
  }

  btn.addEventListener('click', () => (timer ? stop() : play()));
  slider.addEventListener('input', () => { const i = +slider.value; stop(); go(i, 'user'); });

  sync();
  return {
    play, pause: stop, toggle: () => (timer ? stop() : play()),
    set: i => go(i, 'set'),
    setSteps(next, i) { stop(); steps = next.slice(); idx = Math.max(0, Math.min(steps.length - 1, i ?? steps.length - 1)); sync(); },
    get index() { return idx; },
    get playing() { return !!timer; },
    button: btn, slider, element: wrap,
  };
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
