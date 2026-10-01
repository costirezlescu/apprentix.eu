/* Apprentix — indicators: EU targets overview and a generic indicator view.
   Driven entirely by data/published/indicators/*.json. */

import { url, esc } from './data.js';
import { formatter, tileMap, barChart, lineChart, lineLegend } from './charts.js';
import { addShareControls } from './share.js';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const MAX_LINES = 4;
const SERIES_VARS = ['--series-1', '--series-2', '--series-3', '--series-4'];

const get = p => fetch(url(p)).then(r => {
  if (!r.ok) throw new Error(`${r.status} — ${p}`);
  return r.json();
});

let INDEX, COUNTRIES, IND, state;

init().catch(err => {
  $('view').innerHTML = `<p class="empty">Could not load indicators.<br><small>${esc(err.message)}</small></p>`;
  console.error(err);
});

async function init() {
  [INDEX, COUNTRIES] = await Promise.all([
    get('data/published/indicators/index.json'),
    get('data/reference/countries.json'),
  ]);
  COUNTRIES.byCode = Object.fromEntries(COUNTRIES.countries.map(c => [c.code, c]));
  renderList();
  $('ind-search').addEventListener('input', e => renderList(e.target.value.trim().toLowerCase()));

  const id = params.get('id');
  if (id) await showIndicator(id);
  else await showOverview();

  let t;
  window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => IND && draw(), 150); });
}

const cname = code => COUNTRIES.byCode[code]?.name || code;

/* ---------- sidebar list ---------- */

function renderList(q = '') {
  const items = INDEX.indicators.filter(i =>
    !q || `${i.title} ${i.topic} ${i.provenance?.publisher} ${i.id}`.toLowerCase().includes(q));
  const byTopic = new Map();
  for (const i of items) {
    const t = i.national ? 'National statistics' : i.topic;
    if (!byTopic.has(t)) byTopic.set(t, []);
    byTopic.get(t).push(i);
  }
  const current = params.get('id');
  $('ind-list').innerHTML = [...byTopic].sort((a, b) => a[0].localeCompare(b[0])).map(([t, list]) =>
    `<div class="topic">${esc(t)}</div>` + list.map(i =>
      `<a href="?id=${encodeURIComponent(i.id)}"${i.id === current ? ' aria-current="page"' : ''}>${esc(i.title)}
         <span class="pub">${esc(i.provenance?.publisher || '')}${i.national && i.coverage?.geos?.length === 1 ? ' · ' + esc(cname(i.coverage.geos[0])) : ''}</span></a>`
    ).join('')).join('') || '<p class="hint">No indicator matches.</p>';
  $('ind-count').textContent = `${INDEX.indicators.length} indicators`;
}

/* ---------- overview: EU targets ---------- */

async function showOverview() {
  document.title = 'Indicators — Apprentix';
  const targets = INDEX.indicators.filter(i => i.target);
  const loaded = await Promise.all(targets.map(t => get(t.path)));
  const cards = loaded.map(ind => {
    const fmt = formatter(ind.unit);
    const eu = ind.series.filter(o => o.geo === (ind.target.geo || 'EU27') && defaultsMatch(ind, o))
      .sort((a, b) => a.time.localeCompare(b.time));
    const last = eu[eu.length - 1];
    if (!last) return '';
    const met = last.value >= ind.target.value;
    const max = Math.max(100, ind.target.value, last.value);
    return `<a class="target-card" href="?id=${encodeURIComponent(ind.id)}">
      <div class="mono">${esc(ind.topic)}</div>
      <h2 style="font-size:1.05rem;margin-top:6px">${esc(ind.title)}</h2>
      <div class="big">${fmt(last.value)}</div>
      <div class="note" style="color:var(--muted);font-size:.85rem">EU-27, ${esc(last.time)} · target ${fmt(ind.target.value)} by ${esc(ind.target.year)}</div>
      <div class="meter" aria-hidden="true"><span class="fill" style="width:${(last.value / max) * 100}%"></span><span class="mark" style="left:${(ind.target.value / max) * 100}%"></span></div>
      <div class="status ${met ? 'good' : 'bad'}">${met ? '✓ Target met' : '✕ Target not met'}${eu.length > 1 ? ` · ${fmt(eu[0].value)} in ${esc(eu[0].time)}` : ''}</div>
      <p style="font-size:.82rem;color:var(--muted);margin:10px 0 0">${esc(ind.target.label)}</p>
    </a>`;
  }).join('');

  const pubs = new Map();
  for (const i of INDEX.indicators) pubs.set(i.provenance?.publisher, (pubs.get(i.provenance?.publisher) || 0) + 1);
  const featured = ['eurostat-ed3sw-share-of-vet', 'eurostat-educ_uoe_enrs04-ed3sw', 'cedefop-kivet-1020',
    'eurostat-trng_cvt_34s', 'cedefop-kivet-2090a', 'cedefop-kivet-1026']
    .map(id => INDEX.indicators.find(i => i.id === id)).filter(Boolean);

  $('view').innerHTML = `
    <h1>Indicators</h1>
    <p class="sub" style="color:var(--muted);max-width:70ch">Statistics on apprenticeship and vocational education across Europe,
      refreshed automatically from their publishers. Each indicator shows its source, licence and the date it was retrieved,
      and can be downloaded as CSV or JSON.</p>
    <h2 style="margin-top:28px;font-size:1.15rem">EU targets for vocational education</h2>
    <p class="hint" style="color:var(--muted);font-size:.88rem;margin:4px 0 0">Set by the 2020 Council Recommendation on VET for 2025. Values are live from Eurostat.</p>
    <div class="targets">${cards}</div>
    <h2 style="margin-top:32px;font-size:1.15rem">Start here</h2>
    <div class="ds-grid" style="margin-top:12px">${featured.map(i => `
      <a class="ds-card" href="?id=${encodeURIComponent(i.id)}">
        <h3>${esc(i.title)}</h3><p>${esc((i.description || '').slice(0, 160))}${(i.description || '').length > 160 ? '…' : ''}</p>
        <div class="meta"><span>${esc(i.provenance?.publisher || '')}</span><span>${esc(i.coverage.time.join('–'))}</span></div>
      </a>`).join('')}</div>
    <p class="provenance" style="margin-top:26px">Sources: ${[...pubs].map(([p, n]) => `${esc(p)} (${n})`).join(' · ')}.
      Machine-readable index: <a href="${url('data/published/indicators/index.json')}">index.json</a> ·
      <a href="${url('datapackage.json')}">datapackage.json</a> ·
      <a href="${url('pages/indicators/')}">all indicators as citable pages</a>.</p>`;
}

function defaultsMatch(ind, o) {
  return (ind.dims || []).every(d => (o.dims?.[d.key] ?? d.default) === d.default);
}

/* ---------- single indicator ---------- */

async function showIndicator(id) {
  const meta = INDEX.indicators.find(i => i.id === id);
  if (!meta) throw new Error(`Unknown indicator: ${id}`);
  IND = await get(meta.path);
  IND.csv = meta.csv;
  document.title = `${IND.title} — Apprentix`;
  const geos = IND.coverage.geos;
  const single = geos.length === 1;

  const dims = {};
  for (const d of IND.dims || []) dims[d.key] = params.get(`dim_${d.key}`) || d.default;
  const breakable = (IND.dims || []).filter(d => Object.keys(d.values).length > 1);
  state = {
    dims,
    year: params.get('year'),
    selected: (params.get('geo') || '').split(',').filter(g => geos.includes(g)),
    single,
    breakdown: single && breakable.length ? (params.get('by') || breakable[0].key) : null,
  };

  $('view').innerHTML = `
    <div class="mono">${esc(IND.national ? 'National statistics · ' + cname(geos[0]) : IND.topic)}</div>
    <h1 style="margin-top:4px">${esc(IND.title)}</h1>
    <p style="color:var(--muted);max-width:75ch;margin:6px 0 0">${esc(IND.description)}</p>
    <div class="filterbar" id="filterbar"></div>
    <div class="tiles" id="tiles"></div>
    <div id="charts"></div>
    <div class="chart-card" id="table-card"></div>
    <div class="chart-card prov" id="prov"></div>`;
  renderProvenance();
  draw();
}

function obsFor(dimsOverride = {}) {
  const want = { ...state.dims, ...dimsOverride };
  return IND.series.filter(o => (IND.dims || []).every(d => {
    if (d.key in dimsOverride && dimsOverride[d.key] === '*') return true;
    return (o.dims?.[d.key] ?? d.default) === want[d.key];
  }));
}

function syncUrl() {
  const p = new URLSearchParams({ id: IND.id });
  for (const d of IND.dims || []) if (state.dims[d.key] !== d.default) p.set(`dim_${d.key}`, state.dims[d.key]);
  if (state.year) p.set('year', state.year);
  if (state.selected.length) p.set('geo', state.selected.join(','));
  if (state.breakdown) p.set('by', state.breakdown);
  history.replaceState(null, '', '?' + p);
}

function draw() {
  const fmt = formatter(IND.unit, IND.series.map(o => o.value));
  const obs = obsFor(state.breakdown ? { [state.breakdown]: '*' } : {});
  const years = [...new Set(obs.map(o => o.time))].sort().reverse();
  if (!state.year || !years.includes(state.year)) {
    const counts = years.map(y => obs.filter(o => o.time === y).length);
    const maxc = Math.max(0, ...counts);
    state.year = years.find((y, i) => counts[i] >= maxc * 0.6) || years[0];
  }

  renderFilters(years);
  if (state.single) drawSingle(fmt, obs);
  else drawMulti(fmt, obs);
  syncUrl();
  shareCharts();
}

/* Every chart card gets "Download image" (with title, source and licence on it) and "Copy link". */
function shareCharts() {
  const p = IND.provenance || {};
  const dimsNote = (IND.dims || []).filter(d => state.dims[d.key] !== d.default || d.key === state.breakdown)
    .map(d => d.key === state.breakdown ? `by ${d.label.toLowerCase()}` : `${d.label}: ${d.values[state.dims[d.key]]}`).join(' · ');
  document.querySelectorAll('#charts .chart-card').forEach(card => {
    const part = card.querySelector('h2')?.textContent || '';
    addShareControls(card, {
      title: `${IND.title} — ${part}`,
      subtitle: [IND.unit && `Unit: ${IND.unit}`, dimsNote].filter(Boolean).join(' · '),
      source: `${p.publisher || ''}${p.dataset_code ? ` (${p.dataset_code})` : ''}, retrieved ${(p.retrieved_at || '').slice(0, 10)}`,
      licence: p.licence ? `Licence: ${p.licence}` : '',
      url: location.href,
    });
  });
}

function renderFilters(years) {
  const bar = $('filterbar');
  const parts = [];
  for (const d of IND.dims || []) {
    if (d.key === state.breakdown) continue;
    parts.push(`<label>${esc(d.label)}<select data-dim="${esc(d.key)}">${Object.entries(d.values).map(([k, v]) =>
      `<option value="${esc(k)}"${k === state.dims[d.key] ? ' selected' : ''}>${esc(v)}</option>`).join('')}</select></label>`);
  }
  if (state.single) {
    const breakable = (IND.dims || []).filter(d => Object.keys(d.values).length > 1);
    if (breakable.length > 1) parts.unshift(`<label>Lines show<select id="by">${breakable.map(d =>
      `<option value="${esc(d.key)}"${d.key === state.breakdown ? ' selected' : ''}>${esc(d.label)}</option>`).join('')}</select></label>`);
  } else {
    parts.unshift(`<label>Year for map and ranking<select id="year">${years.map(y =>
      `<option${y === state.year ? ' selected' : ''}>${esc(y)}</option>`).join('')}</select></label>`);
  }
  bar.innerHTML = parts.join('');
  bar.hidden = !parts.length;
  bar.querySelectorAll('[data-dim]').forEach(s => s.addEventListener('change', () => { state.dims[s.dataset.dim] = s.value; draw(); }));
  $('year')?.addEventListener('change', e => { state.year = e.target.value; draw(); });
  $('by')?.addEventListener('change', e => { state.breakdown = e.target.value; draw(); });
}

function toggleCountry(code) {
  const i = state.selected.indexOf(code);
  if (i >= 0) state.selected.splice(i, 1);
  else {
    if (state.selected.length >= MAX_LINES) state.selected.shift();
    state.selected.push(code);
  }
  draw();
}

function drawMulti(fmt, obs) {
  const yearObs = obs.filter(o => o.time === state.year);
  const byGeo = new Map(yearObs.map(o => [o.geo, o]));
  const countries = yearObs.filter(o => o.geo !== 'EU27').sort((a, b) => b.value - a.value);
  const eu = byGeo.get('EU27');
  const target = IND.target && (IND.dims || []).every(d => state.dims[d.key] === d.default) ? IND.target : null;

  // Stat tiles
  const tiles = [];
  if (eu) {
    let status = '';
    if (target) {
      const met = eu.value >= target.value;
      status = `<div class="status ${met ? 'good' : 'bad'}">${met ? '✓ Above' : '✕ Below'} the ${fmt(target.value)} target</div>`;
    }
    tiles.push(tile('EU-27', fmt(eu.value), `${state.year}${eu.flag ? ' · flag ' + eu.flag : ''}`, status));
  }
  if (countries.length) {
    tiles.push(tile('Highest', fmt(countries[0].value), cname(countries[0].geo)));
    tiles.push(tile('Lowest', fmt(countries[countries.length - 1].value), cname(countries[countries.length - 1].geo)));
  }
  tiles.push(tile('Countries with data', String(countries.length), `in ${state.year}`));
  $('tiles').innerHTML = tiles.join('');

  // Line series: EU27 + selected countries (colour follows the selection slot, not rank).
  if (!state.selected.length && !eu) state.selected = countries.slice(0, 3).map(o => o.geo);
  const series = [];
  if (IND.coverage.geos.includes('EU27')) series.push({ key: 'EU27', label: 'EU-27', colorVar: '--series-eu', points: obs.filter(o => o.geo === 'EU27') });
  state.selected.forEach((g, i) => series.push({ key: g, label: cname(g), colorVar: SERIES_VARS[i], removable: true,
    points: obs.filter(o => o.geo === g) }));

  $('charts').innerHTML = `
    <div class="chart-grid">
      <div class="chart-card"><h2>Map, ${esc(state.year)}</h2><p class="hint">Colour shows the value (see the legend). Select a country to add it to the chart over time.</p><div id="map"></div></div>
      <div class="chart-card"><h2>Ranking, ${esc(state.year)}</h2><p class="hint">${target ? `The amber line is the EU target (${esc(fmt(target.value))}). ` : ''}Select a country to compare it over time.</p><div id="bars"></div></div>
    </div>
    <div class="chart-card"><h2>Over time</h2><p class="hint">${state.selected.length ? '' : 'Select up to four countries on the map or in the ranking to compare them. '}Hover or use the arrow keys for values.</p>
      <div class="viz-legend" id="legend"></div><div id="lines"></div></div>`;

  const missing = new Map((IND.missing || [])
    .filter(m => m.time === state.year && (IND.dims || []).every(d => (m.dims?.[d.key] ?? d.default) === state.dims[d.key]))
    .map(m => [m.geo, m.flag]));
  const sel = new Set(state.selected);
  tileMap($('map'), { countries: COUNTRIES.countries, values: byGeo, missing, fmt, year: state.year,
    onSelect: toggleCountry, selected: sel, label: `${IND.title}, ${state.year}, map` });
  const rows = [...(eu ? [{ code: 'EU27', name: 'EU-27', value: eu.value, flag: eu.flag, emphasis: true }] : []),
    ...countries.map(o => ({ code: o.geo, name: cname(o.geo), value: o.value, flag: o.flag }))];
  barChart($('bars'), rows, { fmt, target, year: state.year, selected: sel, fitLabels: true,
    onSelect: c => c !== 'EU27' && toggleCountry(c), label: `${IND.title}, ${state.year}, ranking` });
  lineLegend($('legend'), series, code => toggleCountry(code));
  lineChart($('lines'), series, { fmt, target, label: `${IND.title} over time` });

  // Table view of the selected year.
  $('table-card').innerHTML = `<h2>Table, ${esc(state.year)}</h2>
    <div style="overflow-x:auto"><table class="data"><thead><tr><th>Country</th><th class="num">${esc(IND.unit || 'Value')}</th><th>Flag</th></tr></thead>
    <tbody>${rows.map(r => `<tr><td>${esc(r.name)}</td><td class="num">${esc(fmt(r.value))}</td><td>${esc(r.flag ? `${r.flag} — ${IND.flags?.[r.flag] || ''}` : '')}</td></tr>`).join('')}
    ${[...missing].map(([g, f]) => `<tr><td>${esc(cname(g))}</td><td class="num">—</td><td>${esc(`${f} — ${IND.flags?.[f] || ''}`)}</td></tr>`).join('')}</tbody></table></div>`;
}

function drawSingle(fmt, obs) {
  const geo = IND.coverage.geos[0];
  let series, hidden = 0;
  if (state.breakdown) {
    const d = IND.dims.find(x => x.key === state.breakdown);
    const latest = [...new Set(obs.map(o => o.time))].sort().pop();
    const keys = Object.keys(d.values)
      .map(k => ({ k, v: obs.find(o => o.time === latest && o.dims?.[d.key] === k)?.value ?? -Infinity }))
      .sort((a, b) => (b.k === d.default) - (a.k === d.default) || b.v - a.v)
      .slice(0, MAX_LINES).map(x => x.k);
    series = keys.map((k, i) => ({ key: k, label: d.values[k], colorVar: i === 0 && k === d.default ? '--series-eu' : SERIES_VARS[i],
      points: obs.filter(o => o.dims?.[d.key] === k) }));
    hidden = Object.keys(d.values).length - keys.length;
  } else {
    series = [{ key: geo, label: cname(geo), colorVar: '--bar', points: obs }];
  }
  const latestPts = series[0].points.slice().sort((a, b) => a.time.localeCompare(b.time));
  const last = latestPts[latestPts.length - 1], first = latestPts[0];
  // Monthly/quarterly data is seasonal: compare with the same period a year earlier.
  const sub = last && /^\d{4}-/.test(last.time);
  const prevTime = last && (sub ? `${+last.time.slice(0, 4) - 1}${last.time.slice(4)}` : null);
  const base = sub ? latestPts.find(p => p.time === prevTime) : first;
  const signed = v => (v >= 0 ? '+' : '−') + fmt(Math.abs(v));
  $('tiles').innerHTML = [
    last ? tile(`Latest, ${series[0].label}`, fmt(last.value), last.time + (last.flag ? ` · flag ${last.flag}` : '')) : '',
    base && last && base !== last ? tile(sub ? `Change vs ${base.time}` : `Change since ${base.time}`,
      signed(last.value - base.value), `from ${fmt(base.value)}`) : '',
    tile('Period covered', `${IND.coverage.time[0]} to ${IND.coverage.time[1]}`, `${cname(geo)} only`),
  ].join('');

  $('charts').innerHTML = `<div class="chart-card"><h2>Over time</h2>
    <p class="hint">National source: not comparable with other countries' figures — see “What is counted” below.${hidden ? ` ${hidden} more ${hidden === 1 ? 'category is' : 'categories are'} in the downloads.` : ''}</p>
    ${series.length > 1 ? '<div class="viz-legend" id="legend"></div>' : ''}<div id="lines"></div></div>`;
  if (series.length > 1) lineLegend($('legend'), series);
  lineChart($('lines'), series, { fmt, label: `${IND.title} over time` });

  const times = [...new Set(series.flatMap(s => s.points.map(p => p.time)))].sort().reverse();
  $('table-card').innerHTML = `<h2>Table</h2><div style="overflow-x:auto"><table class="data">
    <thead><tr><th>Period</th>${series.map(s => `<th class="num">${esc(s.label)}</th>`).join('')}</tr></thead>
    <tbody>${times.map(t => `<tr><td>${esc(t)}</td>${series.map(s => {
      const p = s.points.find(p => p.time === t);
      return `<td class="num">${p ? esc(fmt(p.value) + (p.flag ? ' ' + p.flag : '')) : '—'}</td>`;
    }).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function tile(label, value, note, extra = '') {
  return `<div class="stat-tile"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div>
    <div class="note">${esc(note || '')}</div>${extra}</div>`;
}

function renderProvenance() {
  const p = IND.provenance || {};
  const row = (k, v) => v ? `<div class="row"><div class="k">${esc(k)}</div><div>${v}</div></div>` : '';
  const link = (u, t) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t || u)} ↗</a>`;
  const flags = Object.entries(IND.flags || {});
  $('prov').innerHTML = `<h2>Source and reuse</h2>
    <div class="kv" style="margin-top:10px">
      ${row('Publisher', esc(p.publisher))}
      ${row('Dataset', p.source_url ? link(p.source_url, p.dataset_code || 'Source page') : esc(p.dataset_code))}
      ${row('What is counted', esc(IND.comparability))}
      ${row('Licence', p.licence_url ? link(p.licence_url, p.licence) : esc(p.licence))}
      ${row('Cite as', esc(p.citation))}
      ${row('Source updated', esc(p.source_updated))}
      ${row('Retrieved', esc((p.retrieved_at || '').slice(0, 10)))}
      ${row('Original file', p.raw_file ? `<a href="${url(p.raw_file)}">${esc(p.raw_file.split('/').pop())}</a>` : '')}
      ${row('Flags', flags.length ? flags.map(([k, v]) => `<b>${esc(k)}</b> ${esc(v)}`).join(' · ') : '')}
    </div>
    <div class="downloads">
      <a class="btn" href="${url(IND.csv)}" download>Download CSV</a>
      <a class="btn" href="${url('data/published/indicators/' + IND.id + '.json')}">JSON with provenance</a>
      <a class="btn" href="${url('pages/indicators/' + encodeURIComponent(IND.id) + '.html')}">Cite / about this dataset</a>
      ${p.api_url ? `<a class="btn" href="${esc(p.api_url)}" target="_blank" rel="noopener">Publisher's data ↗</a>` : ''}
    </div>`;
}
