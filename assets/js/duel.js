/* Apprentix — Country vs country.
   Loads data/published/duel/countries.json (built by pipeline/duel.py) once and
   renders two profiles side by side. All data text goes in via textContent. */

import { url } from './data.js';
import {
  fmtValue, fmtEur, fmtInt, fold, compareMeasure, scorecard, scorecardText,
  onlyIn, euFor, scaleMax, pickFromParams, MAX_YEAR_GAP,
} from './duel-core.js';

const $ = (s, el = document) => el.querySelector(s);
const SVGNS = 'http://www.w3.org/2000/svg';
const reduceMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Element builder: strings/numbers become text nodes, never HTML. */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.appendChild(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const S = { data: null, codes: [], a: null, b: null };

const P = (code) => S.data.countries[code];
const nm = (code) => P(code)?.name || code;
const page = (code) => P(code)?.page ? url(P(code).page) : null;
const indUrl = (id, geos) => url(`pages/indicators.html?id=${encodeURIComponent(id)}&geo=${geos.filter(g => g).map(encodeURIComponent).join(',')}`);
const indPage = (id) => url(`pages/indicators/${encodeURIComponent(id)}.html`);

/* ------------------------------------------------------------ pickers -- */

function options() {
  const list = S.codes.map(c => ({ code: c, name: nm(c), flag: P(c).flag || '', full: P(c).full_name || '' }));
  const eu = list.filter(o => o.code === S.data.eu);
  const rest = list.filter(o => o.code !== S.data.eu).sort((x, y) => x.name.localeCompare(y.name, 'en'));
  return [...eu, ...rest];
}

function combo(side) {
  const input = $(`#pick-${side}`);
  const list = $(`#list-${side}`);
  const flag = $(`.duel-combo[data-side="${side}"] .duel-combo-flag`);
  const all = options();
  let shown = [], active = -1;

  const current = () => S[side];
  const reset = () => { input.value = nm(current()); flag.textContent = P(current()).flag || ''; };

  function render(q) {
    const f = fold(q);
    shown = all.filter(o => !f || fold(o.name).includes(f) || fold(o.full).includes(f) || fold(o.code) === f);
    list.replaceChildren(...shown.map((o, i) => h('li', {
      id: `opt-${side}-${o.code}`, role: 'option', class: 'duel-opt',
      'aria-selected': o.code === current() ? 'true' : 'false', 'data-i': i,
    }, h('span', { class: 'duel-opt-flag', 'aria-hidden': 'true', text: o.flag }), h('span', { text: o.name }),
       o.code === S[side === 'a' ? 'b' : 'a'] ? h('span', { class: 'duel-opt-note', text: 'other side' }) : null)));
    if (!shown.length) list.appendChild(h('li', { class: 'duel-opt-none', role: 'presentation', text: 'No match' }));
    const ci = shown.findIndex(o => o.code === current());
    setActive(f ? (shown.length ? 0 : -1) : ci);
  }
  function setActive(i) {
    active = i;
    list.querySelectorAll('.duel-opt').forEach((li, j) => li.classList.toggle('active', j === i));
    if (i >= 0 && shown[i]) {
      const li = $(`#opt-${side}-${shown[i].code}`);
      input.setAttribute('aria-activedescendant', li.id);
      li.scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  }
  function open() {
    if (!list.hidden) return;
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    render('');
  }
  function close(restore = true) {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    if (restore) reset();
  }
  function choose(i) {
    const o = shown[i];
    if (!o) return;
    close(false);
    select(side, o.code);
  }

  input.addEventListener('focus', () => { input.select(); });
  input.addEventListener('click', () => { open(); input.select(); });
  input.addEventListener('input', () => { if (list.hidden) { list.hidden = false; input.setAttribute('aria-expanded', 'true'); } render(input.value); });
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      if (list.hidden) { open(); return; }
      const n = shown.length;
      if (!n) return;
      setActive(ev.key === 'ArrowDown' ? (active + 1) % n : (active - 1 + n) % n);
    } else if (ev.key === 'Home' && !list.hidden) { ev.preventDefault(); setActive(0); }
    else if (ev.key === 'End' && !list.hidden) { ev.preventDefault(); setActive(shown.length - 1); }
    else if (ev.key === 'Enter') {
      ev.preventDefault();
      if (!list.hidden && active >= 0) choose(active);
    } else if (ev.key === 'Escape') {
      if (!list.hidden) { ev.preventDefault(); close(); input.select(); }
    } else if (ev.key === 'Tab') {
      if (!list.hidden) close();
    }
  });
  input.addEventListener('blur', () => { setTimeout(() => { if (document.activeElement !== input) close(); }, 120); });
  list.addEventListener('mousedown', (ev) => ev.preventDefault());
  list.addEventListener('click', (ev) => {
    const li = ev.target.closest('.duel-opt');
    if (li) choose(+li.dataset.i);
  });
  return { reset };
}

let combos = {};

function select(side, code) {
  const other = side === 'a' ? 'b' : 'a';
  if (code === S[other]) S[other] = S[side]; // picking the other side's country swaps them
  S[side] = code;
  update();
}

function update() {
  combos.a.reset(); combos.b.reset();
  const params = new URLSearchParams(location.search);
  params.set('a', S.a); params.set('b', S.b);
  history.replaceState(null, '', `${location.pathname}?${params.toString()}${location.hash}`);
  document.title = `${nm(S.a)} vs ${nm(S.b)} — Apprentix`;
  render();
  $('#duel-announce').textContent = `Showing ${nm(S.a)} compared with ${nm(S.b)}.`;
}

/* ------------------------------------------------------------ pieces -- */

function section(id, title, sub, ...body) {
  return h('section', { class: 'duel-sec', id, 'aria-labelledby': `h-${id}` },
    h('h2', { id: `h-${id}`, text: title }),
    sub ? h('p', { class: 'duel-sub', text: sub }) : null,
    ...body);
}

function flagAbbr(indId, flag) {
  if (!flag) return null;
  const label = S.data.indicators[indId]?.flags?.[flag] || `flag ${flag}`;
  return h('abbr', { class: 'duel-flag', title: label }, flag, h('span', { class: 'duel-sr', text: ` (${label})` }));
}

/** Dot plot on a shared 0-based scale: A, B and an optional EU tick. */
function dotPlot(va, vb, veu, label) {
  const max = scaleMax([va, vb, veu]);
  const W = 200, H = 26, pad = 7;
  const x = (v) => pad + (Math.max(0, v) / max) * (W - 2 * pad);
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'duel-dots');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const el = (tag, attrs) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); svg.appendChild(e); return e; };
  el('line', { class: 'duel-track', x1: pad, x2: W - pad, y1: H / 2, y2: H / 2 });
  if (va != null && vb != null) el('line', { class: 'duel-gap', x1: x(Math.min(va, vb)), x2: x(Math.max(va, vb)), y1: H / 2, y2: H / 2 });
  if (veu != null) el('line', { class: 'duel-eu-tick', x1: x(veu), x2: x(veu), y1: 4, y2: H - 4 });
  const dots = [];
  if (va != null) dots.push(el('circle', { class: 'duel-dot duel-dot-a', cx: x(va), cy: H / 2, r: 5.5 }));
  if (vb != null) dots.push(el('circle', { class: 'duel-dot duel-dot-b', cx: x(vb), cy: H / 2, r: 5.5 }));
  if (!reduceMotion()) {
    // Final position is set up front; only a transform animates, so the dots are right even if animation never runs.
    for (const d of dots) {
      const dx = pad - Number(d.getAttribute('cx'));
      d.animate?.([{ transform: `translateX(${dx}px)` }, { transform: 'translateX(0)' }], { duration: 500, easing: 'ease-out' });
    }
  }
  const wrap = h('div', { class: 'duel-viz' });
  wrap.appendChild(svg);
  if (label) wrap.appendChild(h('span', { class: 'duel-sr', text: label }));
  return wrap;
}

function edgeMark() {
  return h('span', { class: 'duel-edge', title: 'Better on this measure' }, h('span', { 'aria-hidden': 'true', text: '▲ ' }), 'edge');
}

function valueCell(side, text, flagEl, isEdge, year, showYear) {
  return h('div', { class: `duel-val duel-val-${side}${isEdge ? ' is-edge' : ''}` },
    h('span', { class: 'duel-val-n' }, text), flagEl,
    showYear && year ? h('span', { class: 'duel-val-y', text: ` ${year}` }) : null,
    isEdge ? edgeMark() : null);
}

/** A generic two-sided row: label | A | viz | B | ref. */
function pairRow({ label, meta, href, a, b, viz, ref, cls }) {
  const lab = h('div', { class: 'duel-label' },
    href ? h('a', { href, text: label }) : h('span', { text: label }),
    meta ? h('span', { class: 'duel-meta' }, meta) : null);
  return h('div', { class: `duel-row${cls ? ' ' + cls : ''}`, role: 'row' },
    h('div', { role: 'rowheader', class: 'duel-c-label' }, lab),
    h('div', { role: 'cell', class: 'duel-c-a' }, a),
    h('div', { role: 'cell', class: 'duel-c-viz' }, viz || null),
    h('div', { role: 'cell', class: 'duel-c-b' }, b),
    h('div', { role: 'cell', class: 'duel-c-ref' }, ref || null));
}

function tableHead(refLabel) {
  return h('div', { class: 'duel-row duel-row-head', role: 'row' },
    h('div', { role: 'columnheader', class: 'duel-c-label', text: 'Measure' }),
    h('div', { role: 'columnheader', class: 'duel-c-a' }, h('span', { class: 'duel-key duel-key-a', 'aria-hidden': 'true' }), nm(S.a)),
    h('div', { role: 'columnheader', class: 'duel-c-viz' }, h('span', { class: 'duel-sr', text: 'Comparison' })),
    h('div', { role: 'columnheader', class: 'duel-c-b' }, h('span', { class: 'duel-key duel-key-b', 'aria-hidden': 'true' }), nm(S.b)),
    h('div', { role: 'columnheader', class: 'duel-c-ref', text: refLabel || '' }));
}

/* ------------------------------------------------------------ sections -- */

function header() {
  const side = (code, cls) => {
    const p = P(code);
    const link = page(code);
    return h('div', { class: `duel-side ${cls}` },
      h('div', { class: 'duel-big-flag', 'aria-hidden': 'true', text: p.flag || '' }),
      h('div', { class: 'duel-side-name' }, link ? h('a', { href: link, text: p.name }) : h('span', { text: p.full_name || p.name })),
      h('div', { class: 'duel-side-meta' }, ...sideMeta(p)));
  };
  return h('div', { class: 'duel-banner' },
    side(S.a, 'duel-side-a'),
    h('div', { class: 'duel-vs', 'aria-hidden': 'true', text: 'vs' }),
    side(S.b, 'duel-side-b'));
}

function sideMeta(p) {
  if (p.group === 'aggregate') return ['EU aggregate — key figures and Erasmus+ totals only'];
  const bits = [];
  if (p.schemes) bits.push(`${p.schemes.count} apprenticeship scheme${p.schemes.count === 1 ? '' : 's'}`);
  const nf = Object.keys(p.figures || {}).length;
  if (nf) bits.push(`${nf} key figure${nf === 1 ? '' : 's'}`);
  return [bits.join(' · ') || 'Limited data'];
}

function schemesSection() {
  const A = P(S.a), B = P(S.b);
  if (!A.schemes && !B.schemes) {
    return section('schemes', 'Apprenticeship schemes', null,
      h('p', { class: 'duel-empty', text: `Cedefop's database on apprenticeship schemes has no scheme for ${notApplicable(A, B)}.` }));
  }
  const Q = S.data.questions;
  const card = (code, other, cls) => {
    const p = P(code), o = P(other);
    if (!p.schemes) {
      return h('article', { class: `duel-card ${cls} is-empty` },
        h('h3', { text: p.name }),
        h('p', { class: 'duel-empty', text: p.group === 'aggregate'
          ? 'Not applicable: schemes are national.'
          : `No scheme in Cedefop's database on apprenticeship schemes for ${p.name}.` }));
    }
    const s = p.schemes;
    const rows = Object.keys(Q).map(q => {
      const mine = s.answers[q] || [];
      const diff = onlyIn(mine, o.schemes ? o.schemes.answers[q] : null);
      return h('div', { class: 'duel-qa' },
        h('dt', { text: Q[q].label }),
        h('dd', {}, mine.length
          ? mine.map(v => h('span', { class: `duel-chip${diff.has(v) ? ' is-diff' : ''}` }, v,
              diff.has(v) ? h('span', { class: 'duel-sr', text: ` (only in ${p.name})` }) : null))
          : h('span', { class: 'duel-na', text: 'Not stated' })));
    });
    return h('article', { class: `duel-card ${cls}` },
      h('h3', {}, h('span', { class: `duel-key duel-key-${cls.slice(-1)}`, 'aria-hidden': 'true' }), p.name,
        h('span', { class: 'duel-count', text: ` ${s.count} scheme${s.count === 1 ? '' : 's'}` })),
      h('ul', { class: 'duel-schemes' }, s.list.map(x => h('li', {},
        h('a', { href: url(`pages/explore.html?dataset=apprenticeship-schemes&open=${encodeURIComponent(x.id)}`), text: x.name }),
        x.orig && x.orig !== x.name ? h('span', { class: 'duel-orig', text: ` ${x.orig}` }) : null,
        h('span', { class: 'duel-meta', text: [x.education_level, x.duration, x.workplace_time].filter(Boolean).join(' · ') })))),
      h('dl', { class: 'duel-qas' }, rows));
  };
  const nDiff = A.schemes && B.schemes
    ? Object.keys(Q).filter(q => onlyIn(A.schemes.answers[q], B.schemes.answers[q]).size || onlyIn(B.schemes.answers[q], A.schemes.answers[q]).size).length
    : null;
  return section('schemes', 'Apprenticeship schemes',
    'Cedefop’s coded answers from the 2026 scheme fiches. Where a country has several schemes, all their answers are listed. '
    + (nDiff != null ? `Highlighted answers appear on one side only — the two countries differ on ${nDiff} of ${Object.keys(Q).length} questions.` : ''),
    h('div', { class: 'duel-cards' }, card(S.a, S.b, 'duel-card-a'), card(S.b, S.a, 'duel-card-b')),
    h('p', { class: 'duel-links' }, h('a', { class: 'btn', href: url('pages/compare.html'), text: 'Compare all 34 schemes' })));
}

function notApplicable(A, B) {
  return A.group === 'aggregate' || B.group === 'aggregate' ? `${A.name} or ${B.name} (the EU-27 is an aggregate)` : `${A.name} or ${B.name}`;
}

function figuresSection() {
  const A = P(S.a), B = P(S.b);
  const rows = [];
  for (const m of S.data.measures) {
    const c = compareMeasure(m, A, B);
    if (!c.a && !c.b) continue;
    const id = (c.a || c.b).id;
    const ind = S.data.indicators[id] || {};
    const unit = ind.unit;
    const sameYear = c.a && c.b && c.a.y === c.b.y;
    const eu = c.comparable || (!c.a || !c.b) ? euFor(S.data.eu_ref, id, c.a?.y, c.b?.y) : null;
    const showEu = eu && S.a !== S.data.eu && S.b !== S.data.eu;
    const fa = c.a ? valueCell('a', fmtValue(c.a.v, S.data.indicators[c.a.id]?.unit), flagAbbr(c.a.id, c.a.f), c.edge === 'a', c.a.y, !sameYear) : valueCell('a', '—', null, false);
    const fb = c.b ? valueCell('b', fmtValue(c.b.v, S.data.indicators[c.b.id]?.unit), flagAbbr(c.b.id, c.b.f), c.edge === 'b', c.b.y, !sameYear) : valueCell('b', '—', null, false);
    let viz = null;
    if (c.comparable) {
      viz = dotPlot(c.a.v, c.b.v, showEu ? eu.v : null,
        `${nm(S.a)} ${fmtValue(c.a.v, unit)}, ${nm(S.b)} ${fmtValue(c.b.v, unit)}${showEu ? `, EU-27 ${fmtValue(eu.v, unit)}` : ''}.`);
    } else if (c.a && c.b) {
      viz = h('p', { class: 'duel-note', text: c.reason === 'years'
        ? `Years too far apart to compare (${c.a.y} vs ${c.b.y}).`
        : 'Different sources — not directly comparable.' });
    }
    const dir = m.better === 'higher' ? 'Higher is better' : m.better === 'lower' ? 'Lower is better' : 'Descriptive — no better side';
    const meta = [sameYear ? c.a.y : null, ind.publisher, dir].filter(Boolean).join(' · ');
    const geos = [S.a, S.b].filter(g => g !== S.data.eu);
    rows.push(pairRow({
      label: m.label, href: indUrl(id, geos.length ? geos : [S.data.eu]),
      meta: [meta, c.a && c.b && c.a.id !== c.b.id ? ` · ${nm(S.a)}: ${S.data.indicators[c.a.id]?.title}; ${nm(S.b)}: ${S.data.indicators[c.b.id]?.title}` : ''].join(''),
      a: fa, b: fb, viz,
      ref: showEu ? h('span', { class: 'duel-ref' }, h('span', { class: 'duel-ref-k', text: `EU-27${eu.y !== c.a?.y || !sameYear ? ' ' + eu.y : ''}` }),
        ' ', fmtValue(eu.v, unit), flagAbbr(id, eu.f)) : null,
      cls: c.edge ? `has-edge edge-${c.edge}` : '',
    }));
  }
  if (!rows.length) return section('figures', 'Key figures', null, h('p', { class: 'duel-empty', text: 'No key figures for either side.' }));
  return section('figures', 'Key figures',
    'Latest value of each measure (default breakdown, usually the total). The ▲ edge marks the better side only where a direction is defined and both values come from the same indicator. Select a measure to open it with both countries highlighted.',
    h('div', { class: 'duel-table', role: 'table', 'aria-label': `Key figures: ${nm(S.a)} and ${nm(S.b)}` },
      tableHead(S.a === S.data.eu || S.b === S.data.eu ? '' : 'EU-27'), ...rows),
    h('p', { class: 'duel-legend' },
      h('span', { class: 'duel-li' }, h('span', { class: 'duel-swatch duel-dot-a' }), nm(S.a)),
      h('span', { class: 'duel-li' }, h('span', { class: 'duel-swatch duel-dot-b' }), nm(S.b)),
      S.a !== S.data.eu && S.b !== S.data.eu ? h('span', { class: 'duel-li' }, h('span', { class: 'duel-swatch duel-swatch-eu' }), 'EU-27') : null,
      h('span', { class: 'duel-li', text: 'Flags: hover or focus the letter for its meaning.' })));
}

function moneySection() {
  const A = P(S.a), B = P(S.b);
  const row = (label, fa, fb, opts = {}) => {
    const va = fa(A), vb = fb(B);
    if ((va == null || va === '') && (vb == null || vb === '')) return null;
    const fmt = opts.fmt || ((v) => v);
    const num = opts.numeric && typeof va === 'number' && typeof vb === 'number';
    return pairRow({
      label, meta: opts.meta, href: opts.href,
      a: h('div', { class: 'duel-val duel-val-a' }, h('span', { class: 'duel-val-n' }, va == null ? '—' : fmt(va, A))),
      b: h('div', { class: 'duel-val duel-val-b' }, h('span', { class: 'duel-val-n' }, vb == null ? '—' : fmt(vb, B))),
      viz: num ? dotPlot(va, vb, null, '') : null,
      cls: num ? '' : 'is-text',
    });
  };
  const reform = (p) => {
    const r = p.policy?.latest_reform;
    if (!r) return null;
    return h('span', { class: 'duel-reform' },
      h('a', { href: url(`pages/explore.html?dataset=vet-policy-timeline&open=${encodeURIComponent(r.id)}`), text: r.title }),
      h('span', { class: 'duel-meta', text: [r.year ? `from ${r.year}` : '', r.type, r.stage ? `${r.stage}${r.stage_year ? ' (' + r.stage_year + ')' : ''}` : ''].filter(Boolean).join(' · ') }));
  };
  const finTypes = (p) => p.financing
    ? h('span', {}, `${p.financing.count}: `, Object.entries(p.financing.types).map(([t, n]) => `${t}${n > 1 ? ' ×' + n : ''}`).join(', '))
    : null;
  const grantYear = A.erasmus?.grant?.year || B.erasmus?.grant?.year || '2025';
  const perPupilMeta = () => {
    const ys = [...new Set([A, B].map(p => p.erasmus?.grant?.pupils_year).filter(Boolean))].join('/');
    return `Grant ÷ upper-secondary VET pupils (Eurostat${ys ? ', ' + ys : ''})`;
  };
  const rows = [
    row('VET policies recorded', p => p.policy?.vet ?? null, p => p.policy?.vet ?? null,
      { fmt: fmtInt, meta: 'Cedefop VET policy timeline · counts reflect national reporting, not effort' }),
    row('… of which concern apprenticeship', p => p.policy?.apprenticeship ?? null, p => p.policy?.apprenticeship ?? null, { fmt: fmtInt }),
    row('Most recent apprenticeship measure', reform, reform, { meta: 'Latest by year introduced' }),
    row('Financing instruments for apprenticeships', finTypes, finTypes, { meta: 'Cedefop financing database, 2016–17 (not updated since)' }),
    row('Erasmus+ accredited VET organisations', p => p.erasmus?.orgs ?? null, p => p.erasmus?.orgs ?? null,
      { fmt: fmtInt, meta: 'Accreditations 2021–2025 · size-dependent' }),
    row(`Erasmus+ VET mobility grant (${grantYear} call)`, p => p.erasmus?.grant?.eur ?? null, p => p.erasmus?.grant?.eur ?? null,
      { fmt: fmtEur, numeric: true, href: indUrl('erasmus-ka1-vet-grant', [S.a, S.b]), meta: 'By coordinator country · size-dependent' }),
    row('Erasmus+ grant per upper-secondary VET pupil', p => p.erasmus?.grant?.per_pupil ?? null, p => p.erasmus?.grant?.per_pupil ?? null,
      { fmt: (v) => fmtEur(v), numeric: true, meta: perPupilMeta() }),
    row('Centres of Vocational Excellence projects', p => p.cove ? p.cove.projects : null, p => p.cove ? p.cove.projects : null,
      { fmt: (v, p) => `${fmtInt(v)} (coordinating ${fmtInt(p.cove.coordinated)})`, meta: 'Erasmus+ CoVE projects with a participant from the country' }),
  ].filter(Boolean);
  return section('money', 'Policy & money',
    'Counts and amounts depend on country size and reporting practice, so no side is marked as ahead here.',
    h('div', { class: 'duel-table', role: 'table', 'aria-label': 'Policy and money' }, tableHead(''), ...rows));
}

function qualSection() {
  const col = (code, cls) => {
    const p = P(code);
    if (!p.nqf) {
      return h('article', { class: `duel-card ${cls} is-empty` }, h('h3', { text: p.name }),
        h('p', { class: 'duel-empty', text: p.group === 'aggregate' ? 'Not applicable: qualification frameworks are national.' : 'No NQF levels recorded.' }));
    }
    const q = p.nqf;
    return h('article', { class: `duel-card ${cls}` },
      h('h3', {}, h('span', { class: `duel-key duel-key-${cls.slice(-1)}`, 'aria-hidden': 'true' }), p.name),
      h('p', { class: 'duel-meta', text: `${q.types} qualification types in the national framework; ${q.apprenticeship.length} marked as apprenticeship or craft.` }),
      q.eqf_levels.length ? h('p', { class: 'duel-eqf' }, 'EQF levels: ', q.eqf_levels.map(l => h('span', { class: 'duel-chip duel-chip-eqf', text: l }))) : null,
      q.apprenticeship.length
        ? h('ul', { class: 'duel-quals' }, q.apprenticeship.map(x => h('li', {},
            h('span', { text: x.t }),
            h('span', { class: 'duel-meta', text: `NQF ${x.nqf || '?'} · ${(x.eqf || []).join(', ') || 'EQF level not stated'}` }))))
        : h('p', { class: 'duel-empty', text: 'No qualification type is flagged as apprenticeship or craft in Cedefop’s NQF tool.' }));
  };
  return section('quals', 'Qualifications',
    'Apprenticeship and craft qualifications in each national qualifications framework, with the European (EQF) level they are referenced to. Cedefop NQF online tool, 2024.',
    h('div', { class: 'duel-cards' }, col(S.a, 'duel-card-a'), col(S.b, 'duel-card-b')));
}

function nationalSection() {
  const col = (code, cls) => {
    const p = P(code);
    const items = p.national || [];
    return h('article', { class: `duel-card ${cls}${items.length ? '' : ' is-empty'}` },
      h('h3', {}, h('span', { class: `duel-key duel-key-${cls.slice(-1)}`, 'aria-hidden': 'true' }), p.name),
      items.length
        ? h('ul', { class: 'duel-nat' }, items.map((x, i) => h('li', { class: i === 0 ? 'is-headline' : '' },
            h('a', { href: indUrl(x.id, [code]), text: x.title }),
            h('span', { class: 'duel-nat-v' }, fmtValue(x.v, x.unit), flagAbbr(x.id, x.f)),
            h('span', { class: 'duel-meta', text: [x.y, x.breakdown, x.publisher].filter(Boolean).join(' · ') }))))
        : h('p', { class: 'duel-empty', text: p.group === 'aggregate' ? 'Not applicable.' : `No national series for ${p.name} in Apprentix yet.` }));
  };
  const A = P(S.a), B = P(S.b);
  if (!(A.national || []).length && !(B.national || []).length) return null;
  return section('national', 'National statistics',
    null,
    h('p', { class: 'duel-warn' }, h('strong', { text: 'Not comparable between countries. ' }),
      'Each office counts apprentices under its own national definition (contracts, learners, qualifications), at different dates. Read each figure on its own.'),
    h('div', { class: 'duel-cards' }, col(S.a, 'duel-card-a'), col(S.b, 'duel-card-b')));
}

function scoreSection() {
  const sc = scorecard(S.data.measures, P(S.a), P(S.b));
  const ask = `Compare apprenticeships and VET in ${P(S.a).full_name || nm(S.a)} and ${P(S.b).full_name || nm(S.b)}`;
  const links = [
    page(S.a) ? h('a', { class: 'btn', href: page(S.a), text: `${nm(S.a)} profile` }) : null,
    page(S.b) ? h('a', { class: 'btn', href: page(S.b), text: `${nm(S.b)} profile` }) : null,
    h('a', { class: 'btn primary', href: url(`pages/ask.html?q=${encodeURIComponent(ask)}`), text: 'Ask Apprentix to compare them' }),
  ];
  return section('score', 'Scorecard', null,
    h('p', { class: 'duel-score' }, scorecardText(sc, nm(S.a), nm(S.b))),
    h('p', { class: 'duel-caveat', text:
      `Counts only key figures with a defined direction (such as employment or early leaving) where both values come from the same indicator, at most ${MAX_YEAR_GAP} year apart. `
      + 'Descriptive measures, counts and national statistics are left out. A tally is not a ranking of systems: measures are not weighted, some carry low-reliability flags, and countries organise VET for different purposes.' }),
    h('p', { class: 'duel-links' }, links));
}

/* ------------------------------------------------------------ render -- */

function render() {
  const root = $('#duel');
  root.replaceChildren(
    header(),
    h('nav', { class: 'duel-toc', 'aria-label': 'On this page' }, h('ul', {},
      [['schemes', 'Schemes'], ['figures', 'Key figures'], ['money', 'Policy & money'], ['quals', 'Qualifications'], ['national', 'National statistics'], ['score', 'Scorecard']]
        .map(([id, l]) => h('li', {}, h('a', { href: `#${id}`, text: l }))))),
    schemesSection(), figuresSection(), moneySection(), qualSection(), nationalSection(), scoreSection(),
    h('p', { class: 'provenance', text: `Built from data/published/duel/countries.json (data updated ${S.data.updated}). Sources: Eurostat, Cedefop, OECD, UNESCO UIS, European Commission (Erasmus+), and national statistical offices — see each indicator page.` }),
  );
  // Drop TOC entries for sections that were not rendered.
  root.querySelectorAll('.duel-toc a').forEach(a => { if (!root.querySelector(a.getAttribute('href'))) a.parentElement.remove(); });
  root.setAttribute('aria-busy', 'false');
}

function random() {
  const pool = S.codes.filter(c => P(c).schemes && Object.keys(P(c).figures).length >= 8);
  const src = pool.length >= 2 ? pool : S.codes.filter(c => c !== S.data.eu);
  let a = src[Math.floor(Math.random() * src.length)], b = a;
  while (b === a || (a === S.a && b === S.b)) {
    a = src[Math.floor(Math.random() * src.length)];
    b = src[Math.floor(Math.random() * src.length)];
  }
  S.a = a; S.b = b;
  update();
}

async function init() {
  const res = await fetch(url('data/published/duel/countries.json'));
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  S.data = await res.json();
  S.codes = Object.keys(S.data.countries);
  Object.assign(S, pickFromParams(location.search, S.codes));
  combos = { a: combo('a'), b: combo('b') };
  $('#pickers').addEventListener('submit', (ev) => ev.preventDefault());
  $('#swap').addEventListener('click', () => { [S.a, S.b] = [S.b, S.a]; update(); });
  $('#random').addEventListener('click', random);
  $('#copy').addEventListener('click', async () => {
    const st = $('#copy-status');
    try { await navigator.clipboard.writeText(location.href); st.textContent = 'Link copied.'; }
    catch { st.textContent = 'Copy the address bar to share this duel.'; }
    setTimeout(() => { st.textContent = ''; }, 3000);
  });
  update();
}

init().catch(err => {
  const root = $('#duel');
  root.replaceChildren(h('p', { class: 'duel-empty' }, 'Could not load the comparison data. ', h('span', { text: String(err.message || err) })));
  root.setAttribute('aria-busy', 'false');
});
