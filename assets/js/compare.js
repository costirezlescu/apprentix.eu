/* Apprentix — scheme comparison matrix.
   Rows: every apprenticeship scheme. Columns: Cedefop's coded fiche answers
   (meta.matrix.questions). Pick a column to colour it, sort by it and see how
   the schemes split. All labels are inserted with textContent. */

import { loadDataset, values, field } from './data.js';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const SLOTS = ['--series-1', '--series-2', '--series-3'];   // all-pairs validated; more values fold to neutral

let META, RECORDS, COLS;
const state = { section: params.get('section') || 'all', focus: params.get('q') || 'q_compensation', sort: 'country' };

init().catch(err => { $('matrix').textContent = `Could not load the schemes: ${err.message}`; console.error(err); });

async function init() {
  const { meta, records } = await loadDataset('apprenticeship-schemes');
  META = meta;
  RECORDS = records.slice().sort((a, b) => a.country.localeCompare(b.country) || a.name_en.localeCompare(b.name_en));
  COLS = meta.matrix.questions.map(k => field(meta, k)).filter(Boolean);
  const sections = meta.sections.filter(s => s.coded);
  COLS.forEach(c => { c.section = sections.find(s => s.fields.includes(c.key))?.title.replace(/^Cedefop coding — /, '') || ''; });
  if (!COLS.some(c => c.key === state.focus)) state.focus = COLS[0].key;

  const tabs = $('sections');
  for (const [key, label] of [['all', 'All'], ...[...new Set(COLS.map(c => c.section))].map(s => [s, s])]) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    b.textContent = label[0].toUpperCase() + label.slice(1);
    b.dataset.section = key;
    b.addEventListener('click', () => { state.section = key; render(); });
    tabs.appendChild(b);
  }
  const sel = $('focus');
  for (const c of COLS) {
    const o = document.createElement('option');
    o.value = c.key;
    o.textContent = `${c.question} · ${c.label}`;
    sel.appendChild(o);
  }
  sel.addEventListener('change', () => { state.focus = sel.value; render(); });
  $('sortby').addEventListener('change', e => { state.sort = e.target.value; render(); });
  $('count').textContent = `${RECORDS.length} schemes · ${COLS.length} coded questions · Cedefop 2026 fiches`;
  render();
}

function colourMap(col) {
  // Colour the focused column only when its answers fit the validated slots.
  const counts = new Map();
  for (const r of RECORDS) for (const v of values(r, col.key)) counts.set(v, (counts.get(v) || 0) + 1);
  const ordered = (col.order || []).filter(v => counts.has(v));
  return ordered.length <= SLOTS.length ? new Map(ordered.map((v, i) => [v, SLOTS[i]])) : new Map();
}

function render() {
  const col = COLS.find(c => c.key === state.focus);
  $('focus').value = col.key;
  document.querySelectorAll('#sections .chip').forEach(b => b.setAttribute('aria-pressed', b.dataset.section === state.section));
  const cols = COLS.filter(c => state.section === 'all' || c.section === state.section || c.key === col.key);
  const colours = colourMap(col);

  let rows = RECORDS.slice();
  if (state.sort === 'answer') {
    const rank = r => { const v = values(r, col.key); return v.length ? Math.min(...v.map(x => (col.order || []).indexOf(x))) : 99; };
    rows.sort((a, b) => rank(a) - rank(b) || a.country.localeCompare(b.country));
  }

  // Distribution of the focused question.
  const dist = $('dist');
  dist.replaceChildren();
  const h = document.createElement('h2');
  h.textContent = `${col.question}: ${col.label}`;
  dist.appendChild(h);
  const hint = document.createElement('p');
  hint.className = 'hint';
  hint.textContent = col.multi ? 'Several answers can apply to one scheme, so counts can add up to more than the number of schemes.'
    : 'One answer per scheme.';
  dist.appendChild(hint);
  const max = RECORDS.length;
  for (const opt of [...(col.order || []), '(not answered)']) {
    const members = RECORDS.filter(r => opt === '(not answered)' ? !values(r, col.key).length : values(r, col.key).includes(opt));
    if (!members.length) continue;
    const row = document.createElement('div');
    row.className = 'dist-row';
    const lab = document.createElement('div');
    lab.className = 'dist-label';
    const key = colours.get(opt);
    if (key) { const sw = document.createElement('i'); sw.className = 'sw'; sw.style.background = `var(${key})`; lab.appendChild(sw); }
    lab.appendChild(document.createTextNode(opt));
    const bar = document.createElement('div');
    bar.className = 'dist-bar';
    const fill = document.createElement('span');
    fill.style.width = `${(members.length / max) * 100}%`;
    if (key) fill.style.background = `var(${key})`;
    bar.appendChild(fill);
    const n = document.createElement('strong');
    n.textContent = members.length;
    const who = document.createElement('div');
    who.className = 'dist-who';
    who.textContent = members.map(r => `${r.flag} ${r.name_en}`).join(' · ');
    row.append(lab, bar, n, who);
    dist.appendChild(row);
  }

  // The matrix.
  const table = document.createElement('table');
  table.className = 'matrix';
  const thead = table.createTHead();
  const hr = thead.insertRow();
  const corner = document.createElement('th');
  corner.textContent = 'Scheme';
  corner.className = 'rowhead';
  hr.appendChild(corner);
  for (const c of cols) {
    const th = document.createElement('th');
    th.scope = 'col';
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'colbtn' + (c.key === col.key ? ' on' : '');
    b.textContent = c.label;
    b.title = `${c.question} — select to colour and summarise this column`;
    b.addEventListener('click', () => { state.focus = c.key; render(); });
    th.appendChild(b);
    hr.appendChild(th);
  }
  const tb = table.createTBody();
  for (const r of rows) {
    const tr = tb.insertRow();
    const th = document.createElement('th');
    th.scope = 'row';
    th.className = 'rowhead';
    const a = document.createElement('a');
    a.href = `explore.html?dataset=apprenticeship-schemes&open=${encodeURIComponent(r.id)}`;
    a.textContent = `${r.flag} ${r.name_en}`;
    const sub = document.createElement('span');
    sub.className = 'oc';
    sub.textContent = r.country;
    th.append(a, sub);
    tr.appendChild(th);
    for (const c of cols) {
      const td = tr.insertCell();
      const vs = values(r, c.key);
      if (!vs.length) { td.textContent = '—'; td.className = 'na'; continue; }
      for (const v of vs) {
        const s = document.createElement('span');
        s.className = 'cell-tag';
        const key = c.key === col.key ? colours.get(v) : null;
        if (key) { s.classList.add('coloured'); s.style.setProperty('--tag', `var(${key})`); }
        s.textContent = v;
        td.appendChild(s);
      }
      if (c.key === col.key) td.classList.add('focus');
    }
  }
  $('matrix').replaceChildren(table);

  const p = new URLSearchParams({ q: state.focus });
  if (state.section !== 'all') p.set('section', state.section);
  history.replaceState(null, '', '?' + p);
}
