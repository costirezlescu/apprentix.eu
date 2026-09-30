/* Apprentix — generic dataset explorer.
   Driven entirely by meta.json: no dataset-specific code lives here. */

import {
  loadDataset, esc, values, field, facets, facetValues, matches
} from './data.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const DATASET = params.get('dataset') || 'apprenticeship-schemes';
const MAX_COMPARE = 6;

let META, RECORDS, ENTRY;
const state = { q: '', filters: {}, compare: [] };

init().catch(err => {
  $('grid').innerHTML =
    `<p class="empty">Could not load this dataset.<br><small>${esc(err.message)}</small></p>`;
  console.error(err);
});

async function init() {
  const { meta, records, entry } = await loadDataset(DATASET);
  META = meta; RECORDS = records; ENTRY = entry;

  for (const f of facets(META)) state.filters[f.key] = new Set();

  document.title = `${meta.title} — Apprentix`;
  $('ds-title').textContent = meta.title;
  $('ds-tagline').textContent = meta.tagline || '';
  $('source-link').href = meta.source.url;
  $('source-link').textContent = meta.source.name;
  $('caveat').textContent = meta.source.caveat || '';

  renderFilters();
  renderGrid();
  renderTray();
  wire();
}

/* ---------- filters ---------- */

function renderFilters() {
  const host = $('filters');
  host.innerHTML = '';
  for (const f of facets(META)) {
    const group = document.createElement('div');
    group.className = 'fgroup';
    group.innerHTML = `<div class="flabel">${esc(f.label)}</div>`;
    const chips = document.createElement('div');
    chips.className = 'chips';

    for (const { value, count } of facetValues(META, RECORDS, f.key)) {
      const on = state.filters[f.key].has(value);
      const b = document.createElement('button');
      b.className = 'chip';
      b.type = 'button';
      b.setAttribute('aria-pressed', on);
      b.innerHTML = `${esc(value)}<span class="n">${count}</span>`;
      b.addEventListener('click', () => {
        const set = state.filters[f.key];
        set.has(value) ? set.delete(value) : set.add(value);
        showList(); renderFilters(); renderGrid();
      });
      chips.appendChild(b);
    }
    group.appendChild(chips);
    host.appendChild(group);
  }
}

const filtered = () => RECORDS.filter(r => matches(META, r, state));

/* ---------- cards ---------- */

function renderGrid() {
  const list = filtered();
  const grid = $('grid');
  const d = META.display;
  grid.innerHTML = '';

  const label = list.length === 1 ? META.recordLabel.one : META.recordLabel.many;
  $('count').textContent = `${list.length} of ${RECORDS.length} ${label}`;
  $('empty').hidden = list.length > 0;

  for (const r of list) {
    const picked = state.compare.includes(r.id);
    const el = document.createElement('article');
    el.className = 'card' + (picked ? ' picked' : '');

    const factsHtml = (d.facts || []).map((k, i) => {
      const v = values(r, k).join(', ');
      return v ? `<span class="fact${i === 2 ? ' key' : ''}">${esc(v)}</span>` : '';
    }).join('');

    el.innerHTML =
      `<div class="group">${esc(r[d.badge] || '')} ${esc(values(r, d.group).join(', '))}</div>
       <h3>${esc(r[d.title])}</h3>
       ${r[d.subtitle] ? `<div class="sub">${esc(r[d.subtitle])}</div>` : ''}
       <div class="facts">${factsHtml}</div>
       <div class="card-actions">
         <button class="btn primary" data-open="${esc(r.id)}">Details</button>
         <button class="btn${picked ? ' on' : ''}" data-cmp="${esc(r.id)}">${picked ? '✓ Comparing' : '+ Compare'}</button>
       </div>`;
    grid.appendChild(el);
  }

  grid.querySelectorAll('[data-open]').forEach(b =>
    b.addEventListener('click', () => openDrawer(b.dataset.open)));
  grid.querySelectorAll('[data-cmp]').forEach(b =>
    b.addEventListener('click', () => toggleCompare(b.dataset.cmp)));
}

/* ---------- detail drawer ---------- */

function renderValue(f, rec) {
  const vs = values(rec, f.key);
  if (!vs.length) return '';
  if (f.type === 'link') {
    return `<a href="${esc(vs[0])}" target="_blank" rel="noopener">Open source record ↗</a>`;
  }
  return esc(vs.join(' · '));
}

function openDrawer(id) {
  const r = RECORDS.find(x => x.id === id);
  if (!r) return;
  const d = META.display;

  const sections = (META.sections || []).map(sec => {
    const rows = sec.fields.map(key => {
      const f = field(META, key);
      if (!f || f.type === 'hidden') return '';
      const v = renderValue(f, r);
      return v ? `<div class="row"><div class="k">${esc(f.label)}</div><div>${v}</div></div>` : '';
    }).join('');
    return rows ? `<div class="sec"><h3>${esc(sec.title)}</h3><div class="kv">${rows}</div></div>` : '';
  }).join('');

  const linkField = field(META, d.link);

  $('drawer').innerHTML =
    `<button class="close" id="drawerClose" aria-label="Close details">✕</button>
     <div class="group">${esc(r[d.badge] || '')} ${esc(values(r, d.group).join(', '))}</div>
     <h2 id="drawerTitle">${esc(r[d.title])}</h2>
     ${r[d.subtitle] ? `<div class="sub">${esc(r[d.subtitle])}</div>` : ''}
     ${r[d.summary] ? `<p class="summary">${esc(r[d.summary])}</p>` : ''}
     ${sections}
     <div class="foot">
       ${linkField && r[d.link] ? `<a href="${esc(r[d.link])}" target="_blank" rel="noopener">${esc(linkField.label)} ↗</a>` : ''}
       <button class="btn" id="drawerCmp">${state.compare.includes(r.id) ? '✓ In comparison' : '+ Add to comparison'}</button>
     </div>
     <p class="provenance">${esc(META.source.caveat || '')}</p>`;

  $('drawerClose').addEventListener('click', closeDrawer);
  $('drawerCmp').addEventListener('click', () => { toggleCompare(r.id); openDrawer(r.id); });
  $('drawer').classList.add('show');
  $('scrim').classList.add('show');
  $('drawerClose').focus();
}

function closeDrawer() {
  $('drawer').classList.remove('show');
  $('scrim').classList.remove('show');
}

/* ---------- compare ---------- */

function toggleCompare(id) {
  const i = state.compare.indexOf(id);
  if (i >= 0) state.compare.splice(i, 1);
  else {
    if (state.compare.length >= MAX_COMPARE) state.compare.shift();
    state.compare.push(id);
  }
  renderTray(); renderGrid();
  if (!$('compareView').hidden) {
    state.compare.length >= 2 ? renderCompare() : showList();
  }
}

function renderTray() {
  const slots = $('traySlots');
  slots.innerHTML = '';
  for (const id of state.compare) {
    const r = RECORDS.find(x => x.id === id);
    const el = document.createElement('span');
    el.className = 'slot';
    el.innerHTML = `${esc(r[META.display.title])}<button data-x="${esc(id)}" aria-label="Remove">✕</button>`;
    slots.appendChild(el);
  }
  slots.querySelectorAll('[data-x]').forEach(b =>
    b.addEventListener('click', () => toggleCompare(b.dataset.x)));

  $('tray').classList.toggle('show',
    state.compare.length > 0 && $('compareView').hidden && !$('drawer').classList.contains('show'));
  $('trayGo').disabled = state.compare.length < 2;
  $('trayGo').textContent = state.compare.length < 2
    ? `Pick 2–${MAX_COMPARE} to compare` : 'Compare side by side';
}

function renderCompare() {
  const sel = state.compare.map(id => RECORDS.find(x => x.id === id));
  const diffsOnly = $('diffsOnly').checked;
  let body = '';

  for (const sec of META.sections || []) {
    const rows = sec.fields
      .map(k => field(META, k))
      .filter(f => f && f.type !== 'hidden')
      .filter(f => {
        if (!diffsOnly) return true;
        const vs = sel.map(r => values(r, f.key).join(' · '));
        return vs.some(v => v !== vs[0]);
      });
    if (!rows.length) continue;
    body += `<tr class="sect"><th colspan="${sel.length + 1}">${esc(sec.title)}</th></tr>`;
    body += rows.map(f =>
      `<tr><th>${esc(f.label)}</th>${sel.map(r => `<td>${renderValue(f, r) || '—'}</td>`).join('')}</tr>`
    ).join('');
  }

  $('compareTable').innerHTML =
    `<thead><tr><th></th>${sel.map(r =>
      `<th>${esc(r[META.display.title])}<span class="oc">${esc(r[META.display.subtitle] || '')}</span></th>`
    ).join('')}</tr></thead><tbody>${body}</tbody>`;

  $('listView').hidden = true;
  $('compareView').hidden = false;
  $('viewbar').classList.add('show');
  renderTray();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showList() {
  $('listView').hidden = false;
  $('compareView').hidden = true;
  $('viewbar').classList.remove('show');
  renderTray();
}

/* ---------- wiring ---------- */

function wire() {
  $('search').addEventListener('input', e => {
    state.q = e.target.value.trim().toLowerCase();
    showList(); renderGrid();
  });
  $('reset').addEventListener('click', () => {
    state.q = '';
    $('search').value = '';
    for (const k of Object.keys(state.filters)) state.filters[k].clear();
    showList(); renderFilters(); renderGrid();
  });
  $('resetEmpty').addEventListener('click', () => $('reset').click());
  $('trayClear').addEventListener('click', () => {
    state.compare = []; showList(); renderTray(); renderGrid();
  });
  $('trayGo').addEventListener('click', () => {
    if (state.compare.length >= 2) renderCompare();
  });
  $('backToList').addEventListener('click', showList);
  $('diffsOnly').addEventListener('change', () => {
    if (state.compare.length >= 2) renderCompare();
  });
  $('scrim').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });
}
