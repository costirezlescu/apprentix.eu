/* Apprentix — scheme comparison matrix.
   Rows: every apprenticeship scheme. Columns: Cedefop's coded fiche answers
   (meta.matrix.questions). Pick a column to colour it, sort by it and see how
   the schemes split. All labels are inserted with textContent. */

import { loadDataset, values, field, url } from './data.js?v=5ec0f233';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const SLOTS = ['--series-1', '--series-2', '--series-3'];   // all-pairs validated; more values fold to neutral

let META, RECORDS, COLS, COUNTRIES = [];
const state = { section: params.get('section') || 'all', focus: params.get('q') || 'q_compensation', sort: 'country',
  value: params.get('v') || null, country: null };

init().catch(err => { $('matrix').textContent = `Could not load the schemes: ${err.message}`; console.error(err); });

async function init() {
  const [{ meta, records }, ref] = await Promise.all([
    loadDataset('apprenticeship-schemes'),
    fetch(url('data/reference/countries.json')).then(r => r.json()).catch(() => ({ countries: [] })),
  ]);
  COUNTRIES = ref.countries.filter(c => c.tile);
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
  sel.addEventListener('change', () => { state.focus = sel.value; state.value = null; state.country = null; render(); });
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

  renderShare(col);

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
    b.addEventListener('click', () => { state.focus = c.key; state.value = null; state.country = null; render(); });
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
  if (state.value) p.set('v', state.value);
  history.replaceState(null, '', '?' + p);
}

/* "Who shares a feature?": pick an answer to the focused question; the map lights up every
   country with at least one scheme giving that answer (the reverse of reading row by row). */
function renderShare(col) {
  const host = $('share');
  host.replaceChildren();
  const opts = (col.order || []).filter(v => RECORDS.some(r => values(r, col.key).includes(v)));
  if (!opts.length || !COUNTRIES.length) { host.hidden = true; return; }
  host.hidden = false;
  if (!opts.includes(state.value)) state.value = opts[0];

  const h = document.createElement('h2');
  h.id = 'share-h';
  h.textContent = 'Who shares a feature?';
  const hint = document.createElement('p');
  hint.className = 'hint';
  hint.textContent = `Pick an answer to “${col.label}”: the map lights up every country with at least one scheme that gives it.`;
  const chips = document.createElement('div');
  chips.className = 'chips share-chips';
  chips.setAttribute('role', 'group');
  chips.setAttribute('aria-label', `Answers to ${col.label}`);
  for (const v of opts) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    b.textContent = v;
    b.setAttribute('aria-pressed', String(v === state.value));
    b.addEventListener('click', () => { state.value = v; state.country = null; render(); });
    chips.appendChild(b);
  }
  host.append(h, hint, chips);

  // Schemes per country (several countries have more than one scheme).
  const byCountry = new Map();
  for (const r of RECORDS) {
    const cc = String(r.country_code || '').toUpperCase().replace(/^GR$/, 'EL');   // map uses Eurostat codes
    if (!byCountry.has(cc)) byCountry.set(cc, []);
    byCountry.get(cc).push(r);
  }
  const match = r => values(r, col.key).includes(state.value);
  const status = cc => !byCountry.has(cc) ? 'none' : byCountry.get(cc).some(match) ? 'on' : 'off';

  const wrap = document.createElement('div');
  wrap.className = 'share-layout';
  const mapBox = document.createElement('div');
  mapBox.className = 'share-map';
  const NS = 'http://www.w3.org/2000/svg';
  const size = 44, gap = 3;
  const cols = Math.max(...COUNTRIES.map(c => c.tile[0])) + 1, rowsN = Math.max(...COUNTRIES.map(c => c.tile[1])) + 1;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${cols * (size + gap)} ${rowsN * (size + gap)}`);
  svg.setAttribute('class', 'viz share-tiles');
  svg.setAttribute('role', 'group');
  svg.setAttribute('aria-label', `Countries with at least one scheme answering “${state.value}”`);
  for (const c of COUNTRIES) {
    const st = status(c.code);
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('transform', `translate(${c.tile[0] * (size + gap)},${c.tile[1] * (size + gap)})`);
    g.setAttribute('class', `share-tile ${st}` + (state.country === c.code ? ' sel' : ''));
    const schemes = byCountry.get(c.code) || [];
    const yes = schemes.filter(match);
    const label = st === 'none' ? `${c.name}: no scheme in the database`
      : st === 'on' ? `${c.name}: yes — ${yes.map(r => r.name_en).join(', ')}` : `${c.name}: no`;
    g.setAttribute('aria-label', label);
    const rect = document.createElementNS(NS, 'rect');
    rect.setAttribute('width', size); rect.setAttribute('height', size); rect.setAttribute('rx', 4);
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x', size / 2); t.setAttribute('y', size / 2 + 4); t.setAttribute('text-anchor', 'middle');
    t.textContent = st === 'on' ? `${c.code}✓` : c.code;
    const title = document.createElementNS(NS, 'title');
    title.textContent = label;
    g.append(title, rect, t);
    if (st !== 'none') {
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      const pick = () => { state.country = state.country === c.code ? null : c.code; render(); };
      g.addEventListener('click', pick);
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
    }
    svg.appendChild(g);
  }
  mapBox.appendChild(svg);
  const legend = document.createElement('div');
  legend.className = 'viz-legend';
  for (const [cls, text] of [['on', 'Yes (at least one scheme)'], ['off', 'No'], ['none', 'No scheme in the database']]) {
    const li = document.createElement('span');
    li.className = 'li';
    const sw = document.createElement('i');
    sw.className = `sw share-sw ${cls}`;
    li.append(sw, document.createTextNode(text));
    legend.appendChild(li);
  }
  mapBox.appendChild(legend);

  // Text list: the same answer, readable without the map.
  const side = document.createElement('div');
  side.className = 'share-side';
  const countries = [...byCountry.keys()].filter(cc => status(cc) === 'on');
  const total = byCountry.size;
  const nSchemes = RECORDS.filter(match).length;
  const sum = document.createElement('p');
  sum.className = 'share-sum';
  sum.textContent = `${countries.length} of ${total} countries · ${nSchemes} of ${RECORDS.length} schemes`;
  side.appendChild(sum);
  const list = document.createElement('ul');
  list.className = 'share-list';
  const name = cc => COUNTRIES.find(c => c.code === cc)?.name || cc;
  for (const cc of countries.sort((a, b) => name(a).localeCompare(name(b)))) {
    const li = document.createElement('li');
    if (state.country === cc) li.className = 'sel';
    const strong = document.createElement('strong');
    strong.textContent = name(cc);
    li.append(strong, document.createTextNode(': '));
    byCountry.get(cc).filter(match).forEach((r, i) => {
      if (i) li.append(', ');
      const a = document.createElement('a');
      a.href = `explore.html?dataset=apprenticeship-schemes&open=${encodeURIComponent(r.id)}`;
      a.textContent = r.name_en;
      li.appendChild(a);
    });
    list.appendChild(li);
  }
  side.appendChild(list);
  if (state.country && status(state.country) === 'off') {
    const p = document.createElement('p');
    p.className = 'share-note';
    const answers = byCountry.get(state.country).map(r => `${r.name_en}: ${values(r, col.key).join(', ') || 'not answered'}`);
    p.textContent = `${name(state.country)} — ${answers.join(' · ')}`;
    side.appendChild(p);
  }
  wrap.append(mapBox, side);
  host.appendChild(wrap);
}
