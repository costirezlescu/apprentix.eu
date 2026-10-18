/* Apprentix — embeddable chart (embed/chart.html).
   One chart per page, with its title, source, licence and a link back, sized for an
   <iframe> on someone else's site. All text is set with textContent. */

import { url } from './data.js?v=af878328';
import { formatter, tileMap, barChart, lineChart, lineLegend, fixedScale, timeControls } from './charts.js?v=af878328';
import { drawInsight } from './insight-chart.js?v=af878328';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const SERIES_VARS = ['--series-1', '--series-2', '--series-3', '--series-4'];
const VIEWS = ['map', 'ranking', 'trend'];

const theme = params.get('theme');
if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;

const get = p => fetch(url(p)).then(r => {
  if (!r.ok) throw new Error(`${r.status} — ${p}`);
  return r.json();
});

let redraw = () => {};

main().catch(err => {
  console.error(err);
  $('em-title').textContent = 'This chart could not be loaded';
  $('em-sub').textContent = 'The link may be out of date. The full data is on apprentix.eu.';
  postHeight();
});

async function main() {
  if (params.get('insight')) await insight(params.get('insight'));
  else if (params.get('indicator')) await indicator(params.get('indicator'));
  else throw new Error('Nothing to show');
  let lastW = window.innerWidth, t;
  window.addEventListener('resize', () => {
    clearTimeout(t);
    t = setTimeout(() => { if (window.innerWidth !== lastW) { lastW = window.innerWidth; redraw(); } }, 150);
  });
  new ResizeObserver(postHeight).observe(document.querySelector('.embed-main'));
  postHeight();
}

/* Tell the host page how tall the chart is (optional for the host to use). */
function postHeight() {
  if (window.parent === window) return;
  const height = Math.ceil(document.querySelector('.embed-main').getBoundingClientRect().height);
  window.parent.postMessage({ type: 'apprentix-embed', height, src: location.href }, '*');
}

function setFooter(source, licence, link) {
  $('em-source').textContent = [source && `Source: ${source}`, licence && `Licence: ${licence}`].filter(Boolean).join(' · ');
  $('em-link').href = link;
  $('em-more').hidden = false;
  document.querySelectorAll('.embed-foot a').forEach(a => { a.target = '_blank'; a.rel = 'noopener'; });
}

/* ------------------------------------------------------------ indicator -- */

async function indicator(id) {
  const [index, ref] = await Promise.all([get('data/published/indicators/index.json'), get('data/reference/countries.json')]);
  const meta = index.indicators.find(i => i.id === id);
  if (!meta) throw new Error(`Unknown indicator ${id}`);
  const ind = await get(meta.path);
  const byCode = Object.fromEntries(ref.countries.map(c => [c.code, c]));
  const cname = code => code === 'EU27' ? 'EU-27' : byCode[code]?.name || code;
  const isCountry = code => !!byCode[code]?.tile;

  const geos = ind.coverage.geos;
  let view = VIEWS.includes(params.get('view')) ? params.get('view') : 'map';
  if (geos.length === 1) view = 'trend';
  const dims = {};
  for (const d of ind.dims || []) {
    const v = params.get(`dim_${d.key}`);
    dims[d.key] = v && v in d.values ? v : d.default;
  }
  const obs = ind.series.filter(o => (ind.dims || []).every(d => (o.dims?.[d.key] ?? d.default) === dims[d.key]));
  const fmt = formatter(ind.unit, ind.series.map(o => o.value));
  const target = ind.target && (ind.dims || []).every(d => dims[d.key] === d.default) ? ind.target : null;
  const years = [...new Set(obs.map(o => o.time))].sort();
  let year = params.get('year');
  if (!years.includes(year)) {
    year = defaultYear(obs);
  }

  const dimNote = (ind.dims || []).filter(d => dims[d.key] !== d.default).map(d => `${d.label}: ${d.values[dims[d.key]]}`);
  const title = ind.title;
  document.title = `${title} — Apprentix`;
  $('em-title').textContent = title;
  const sub = () => [view === 'trend' ? '' : year, ind.unit && `Unit: ${ind.unit}`, ...dimNote,
    ind.national ? 'National statistic: not comparable with other countries' : ''].filter(Boolean).join(' · ');

  const p = ind.provenance || {};
  const full = new URLSearchParams({ id });
  for (const d of ind.dims || []) if (dims[d.key] !== d.default) full.set(`dim_${d.key}`, dims[d.key]);
  if (view !== 'trend') full.set('year', year);
  const selected = (params.get('geo') || '').split(',').map(s => s.trim().toUpperCase()).filter(g => geos.includes(g)).slice(0, 4);
  if (selected.length) full.set('geo', selected.join(','));
  setFooter(`${p.publisher || ''}${p.dataset_code ? ` (${p.dataset_code})` : ''}${p.retrieved_at ? `, retrieved ${p.retrieved_at.slice(0, 10)}` : ''}`,
    p.licence, url(`pages/indicators.html?${full}`));

  const chart = $('em-chart');
  if (view === 'map') {
    const scale = years.length >= 3 ? fixedScale(obs.filter(o => isCountry(o.geo)).map(o => o.value)) : null;
    const stage = document.createElement('div');
    stage.className = 'tl-stage';
    const mapHost = document.createElement('div');
    const yearTag = document.createElement('div');
    yearTag.className = 'tl-year';
    yearTag.setAttribute('aria-hidden', 'true');
    stage.append(mapHost, yearTag);
    chart.replaceChildren(stage);
    const map = tileMap(mapHost, { countries: ref.countries, values: new Map(), fmt, ...(scale || {}) });
    const show = () => {
      const byGeo = new Map(obs.filter(o => o.time === year).map(o => [o.geo, o]));
      const missing = new Map((ind.missing || []).filter(m => m.time === year
        && (ind.dims || []).every(d => (m.dims?.[d.key] ?? d.default) === dims[d.key])).map(m => [m.geo, m.flag]));
      map.update({ values: byGeo, missing, year, label: `${title}, ${year}, map` });
      yearTag.textContent = year;
      $('em-sub').textContent = sub();
    };
    if (scale) {
      timeControls($('em-controls'), {
        steps: years, index: years.indexOf(year), interval: 900, label: 'Year shown on the map',
        onStep: i => { year = years[i]; show(); },
        onPlayState: playing => chart.classList.toggle('is-playing', playing),
      });
    }
    show();
  } else if (view === 'ranking') {
    redraw = () => {
      const rows = obs.filter(o => o.time === year && (o.geo === 'EU27' || isCountry(o.geo)))
        .sort((a, b) => (b.geo === 'EU27') - (a.geo === 'EU27') || b.value - a.value)
        .map(o => ({ code: o.geo, name: cname(o.geo), value: o.value, flag: o.flag, emphasis: o.geo === 'EU27' }));
      barChart(chart, rows, { fmt, target, year, fitLabels: true, selected: new Set(selected), label: `${title}, ${year}, ranking` });
      $('em-sub').textContent = sub() + (target ? ` · Amber line: EU target (${fmt(target.value)})` : '');
    };
    redraw();
  } else {
    let picks = selected;
    if (!picks.length && !geos.includes('EU27')) {
      picks = obs.filter(o => o.time === year).sort((a, b) => b.value - a.value).slice(0, geos.length === 1 ? 1 : 3).map(o => o.geo);
    }
    let series = [];
    const byDim = geos.length === 1 && (ind.dims || []).find(d => d.key === params.get('by') && Object.keys(d.values).length > 1);
    if (byDim) {
      // One national series broken down by a dimension: up to four lines, total first (as on the indicator page).
      const all = ind.series.filter(o => (ind.dims || []).every(d => d.key === byDim.key || (o.dims?.[d.key] ?? d.default) === dims[d.key]));
      const latest = [...new Set(all.map(o => o.time))].sort().pop();
      const keys = Object.keys(byDim.values)
        .map(k => ({ k, v: all.find(o => o.time === latest && (o.dims?.[byDim.key] ?? byDim.default) === k)?.value ?? -Infinity }))
        .sort((a, b) => (b.k === byDim.default) - (a.k === byDim.default) || b.v - a.v).slice(0, 4).map(x => x.k);
      series = keys.map((k, i) => ({ key: k, label: byDim.values[k], colorVar: i === 0 && k === byDim.default ? '--series-eu' : SERIES_VARS[i],
        points: all.filter(o => (o.dims?.[byDim.key] ?? byDim.default) === k) }));
      dimNote.push(`by ${byDim.label.toLowerCase()}`);
      full.set('by', byDim.key);
      $('em-link').href = url(`pages/indicators.html?${full}`);
    }
    if (!byDim && geos.includes('EU27')) series.push({ key: 'EU27', label: 'EU-27', colorVar: '--series-eu', points: obs.filter(o => o.geo === 'EU27') });
    if (!byDim) picks.forEach((g, i) => series.push({ key: g, label: cname(g), colorVar: geos.length === 1 ? '--bar' : SERIES_VARS[i],
      points: obs.filter(o => o.geo === g) }));
    $('em-sub').textContent = sub();
    redraw = () => {
      chart.replaceChildren();
      if (series.length > 1) {
        const lg = document.createElement('div');
        lg.className = 'viz-legend';
        chart.appendChild(lg);
        lineLegend(lg, series);
      }
      const box = document.createElement('div');
      chart.appendChild(box);
      lineChart(box, series, { fmt, target, label: `${title} over time` });
    };
    redraw();
  }
}

/* The latest year with at least 60% of the best year's coverage (as on the indicator page). */
export function defaultYear(obs) {
  const years = [...new Set(obs.map(o => o.time))].sort().reverse();
  const counts = years.map(y => obs.filter(o => o.time === y).length);
  const maxc = Math.max(0, ...counts);
  return years.find((y, i) => counts[i] >= maxc * 0.6) || years[0];
}

/* -------------------------------------------------------------- insight -- */

async function insight(id) {
  const data = await get('data/published/insights/insights.json');
  const item = data.items.find(i => i.id === id);
  if (!item || !item.chart) throw new Error(`Unknown insight ${id}`);
  document.title = `${item.title} — Apprentix`;
  $('em-title').textContent = item.title;
  $('em-sub').textContent = item.finding.length > 240 ? item.finding.slice(0, item.finding.lastIndexOf(' ', 237)) + ' …' : item.finding;
  setFooter(`Apprentix analysis of ${(item.sources || []).map(s => s.label).join('; ')}`, '',
    url(`pages/insights.html#${encodeURIComponent(id)}`));
  redraw = () => drawInsight($('em-chart'), item);
  redraw();
}
