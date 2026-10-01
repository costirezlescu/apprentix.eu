/* Apprentix — "Find my apprenticeship" quiz.
   One question at a time; answers live in the URL query only (no storage, no tracking).
   All record text is inserted with textContent / DOM nodes — never as HTML. */

import { loadDataset, url } from './data.js';
import {
  QUESTIONS, DONT_MIND, DONT_KNOW_STATUS, parseAnswers, encodeAnswers, answeredCount,
  rankSchemes, fitLabel, schemeLinks, siteCode
} from './find-score.js';

const $ = (id) => document.getElementById(id);
const SHOW_FIRST = 10;

let SCHEMES = [];
let NAMES = {};        // site code → country name (countries.json)
let VETSYS = {};       // site code → vet-systems source_url
let COUNTRY_GROUPS = []; // [{label, items:[{code, name, flag, n}]}]

let answers = parseAnswers('');
let step = 0;
let showAll = false;

/* ---------------- tiny DOM helper ---------------- */

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k != null) n.append(k);
  return n;
}

/* ---------------- quiz ---------------- */

const isAnswered = (q) => (q.multi ? answers[q.id].length > 0 : !!answers[q.id]);

function answerText(q) {
  if (q.multi) {
    return answers.c.map(c => NAMES[siteCode(c)] || c).join(', ');
  }
  const o = q.options.find(o => o.value === answers[q.id]);
  return o ? o.label : '';
}

function renderDots() {
  const ol = $('dots');
  ol.replaceChildren(...QUESTIONS.map((q, i) => {
    const state = isAnswered(q) ? 'answered' : 'not answered yet';
    const b = el('button', {
      type: 'button',
      class: 'find-dot' + (isAnswered(q) ? ' done' : ''),
      'aria-label': `Question ${i + 1}: ${q.title} (${state})`,
      'aria-current': i === step ? 'step' : null,
      onclick: () => go(i, true)
    });
    return el('li', {}, b);
  }));
}

function optionRow(type, name, value, label, help, checked) {
  const input = el('input', { type, name, value, checked: checked || null });
  return el('label', { class: 'find-opt' + (checked ? ' on' : '') },
    input,
    el('span', { class: 'find-opt-text' },
      el('span', { class: 'find-opt-label', text: label }),
      help ? el('span', { class: 'find-opt-help', text: help }) : null));
}

function renderCountryOptions(box) {
  const any = optionRow('checkbox', 'c-any', 'any', 'Anywhere in Europe', 'Show schemes in every country.', answers.c.length === 0);
  any.classList.add('find-any');
  box.append(any);
  for (const g of COUNTRY_GROUPS) {
    const grid = el('div', { class: 'find-cgrid' },
      g.items.map(c => {
        const row = optionRow('checkbox', 'c', c.code, `${c.name}`, c.n > 1 ? `${c.n} schemes` : '1 scheme', answers.c.includes(c.code));
        row.querySelector('.find-opt-label').prepend(el('span', { class: 'find-flag', 'aria-hidden': 'true', text: c.flag + ' ' }));
        return row;
      }));
    box.append(el('div', { class: 'find-cgroup', role: 'group', 'aria-label': g.label },
      el('div', { class: 'flabel', text: g.label }), grid));
  }
  box.addEventListener('change', (e) => {
    const t = e.target;
    if (t.name === 'c-any' && t.checked) {
      answers.c = [];
      box.querySelectorAll('input[name="c"]').forEach(i => { i.checked = false; });
    } else if (t.name === 'c') {
      answers.c = [...box.querySelectorAll('input[name="c"]:checked')].map(i => i.value);
      box.querySelector('input[name="c-any"]').checked = answers.c.length === 0;
    } else if (t.name === 'c-any' && !t.checked && answers.c.length === 0) {
      t.checked = true; // "anywhere" stays on until a country is picked
    }
    syncOn(box);
    renderDots();
  });
}

function syncOn(box) {
  box.querySelectorAll('.find-opt').forEach(l => l.classList.toggle('on', l.querySelector('input').checked));
}

function renderStep(focus) {
  const q = QUESTIONS[step];
  $('q-count').textContent = `Question ${step + 1} of ${QUESTIONS.length}`;
  $('q-title').textContent = q.title;
  $('q-help').textContent = q.help;
  const box = $('q-options');
  const fresh = box.cloneNode(false); // drop old listeners
  box.replaceWith(fresh);
  if (q.multi) {
    fresh.className = 'find-options find-countries';
    renderCountryOptions(fresh);
  } else {
    fresh.className = 'find-options';
    const none = q.id === 'status' ? DONT_KNOW_STATUS : DONT_MIND;
    fresh.append(...q.options.map(o => optionRow('radio', q.id, o.value, o.label, o.help, answers[q.id] === o.value)));
    fresh.append(optionRow('radio', q.id, none.value, none.label, null, !answers[q.id]));
    fresh.lastChild.classList.add('find-none');
    fresh.addEventListener('change', (e) => {
      answers[q.id] = e.target.value;
      syncOn(fresh);
      renderDots();
    });
  }
  $('back').disabled = step === 0;
  $('next').textContent = step === QUESTIONS.length - 1 ? 'See my matches' : 'Next';
  renderDots();
  const fs = $('step');
  fs.classList.remove('enter');
  void fs.offsetWidth; // restart the (optional) entry animation
  fs.classList.add('enter');
  if (focus) $('q-title').focus({ preventScroll: false });
}

function go(i, focus) {
  step = Math.max(0, Math.min(QUESTIONS.length - 1, i));
  showQuiz();
  renderStep(focus);
}

function showQuiz() {
  $('results').hidden = true;
  $('quiz').hidden = false;
}

/* ---------------- results ---------------- */

const MARK = { yes: '✓', part: '~', no: '–', note: '!' };
const MARK_SR = { yes: 'Fits: ', part: 'Partly: ', no: "Doesn't fit: ", note: 'Check: ' };

function fact(label, value) {
  if (!value) return null;
  return el('div', { class: 'find-fact' }, el('dt', { text: label }), el('dd', { text: value }));
}

function card(r, rank) {
  const rec = r.rec;
  const links = schemeLinks(rec, { names: NAMES, vetSystems: VETSYS });
  const label = fitLabel(r.pct);
  const head = el('div', { class: 'find-card-head' },
    el('span', { class: 'find-card-flag', 'aria-hidden': 'true', text: rec.flag || '' }),
    el('div', { class: 'find-card-titles' },
      el('div', { class: 'mono find-card-country', text: `${rank}. ${rec.country}` }),
      el('h3', { text: rec.name_en }),
      rec.name_original ? el('div', { class: 'find-card-orig', text: rec.name_original }) : null),
    label ? el('div', { class: 'find-fit find-fit-' + (r.pct >= 85 ? 'hi' : r.pct >= 60 ? 'mid' : 'lo') },
      el('span', { text: label }), el('span', { class: 'find-fit-pct', text: `${r.pct}%` })) : null);

  const facts = el('dl', { class: 'find-facts' },
    fact('Duration', rec.duration),
    fact('Time at work', rec.workplace_time_detail || rec.workplace_time),
    fact('Pay (as stated)', rec.compensation_detail || rec.compensation),
    fact('Level', rec.education_level_detail || rec.education_level),
    fact('Apprentices', rec.learners));

  const why = r.reasons.length
    ? el('div', { class: 'find-why' },
        el('h4', { class: 'flabel', text: 'Why it fits' }),
        el('ul', {}, r.reasons.map(x => el('li', { class: 'find-r-' + x.kind },
          el('span', { class: 'find-mark', 'aria-hidden': 'true', text: MARK[x.kind] }),
          el('span', { class: 'find-sr', text: MARK_SR[x.kind] }),
          el('span', { text: x.text })))))
    : null;

  const linkList = el('ul', { class: 'find-links' }, links.map(l =>
    el('li', { class: 'find-link-' + l.kind },
      el('a', { href: l.href, target: l.external ? '_blank' : null, rel: l.external ? 'noopener' : null, text: l.text }),
      l.external ? el('span', { class: 'find-sr', text: ' (opens in a new tab)' }) : null)));

  return el('li', { class: 'find-card' }, head,
    rec.overview ? el('p', { class: 'find-overview', text: rec.overview }) : null,
    facts, why, linkList);
}

function renderResults(focus) {
  $('quiz').hidden = true;
  $('results').hidden = false;
  const { results, excluded } = rankSchemes(SCHEMES, answers);
  const n = answeredCount(answers);

  const sum = $('r-summary');
  if (!results.length) {
    sum.textContent = 'No scheme matches every one of your must-haves. Try relaxing an answer — for example, choose more countries or "an allowance is fine".';
  } else {
    const must = excluded.filter(x => x.by !== 'country').length;
    sum.textContent = `${results.length} ${results.length === 1 ? 'scheme fits' : 'schemes fit'}` +
      (answers.c.length ? ` in the ${answers.c.length === 1 ? 'country' : 'countries'} you chose` : '') +
      (must ? `; ${must} left out by your must-haves` : '') +
      (n ? '. Best matches first.' : '. You skipped every question, so here is every scheme, largest first.');
  }

  $('r-answers').replaceChildren(...QUESTIONS.map((q, i) => {
    const t = answerText(q);
    return el('button', {
      type: 'button', class: 'chip find-achip' + (t ? '' : ' is-empty'),
      'aria-label': `${q.title} ${t || "Doesn't matter"}. Change this answer`,
      onclick: () => go(i, true)
    }, el('span', { class: 'find-achip-q', text: shortQ[q.id] + ': ' }), el('span', { text: t || 'any' }));
  }));

  const list = $('r-list');
  const shown = showAll ? results : results.slice(0, SHOW_FIRST);
  list.replaceChildren(...shown.map((r, i) => card(r, i + 1)));
  if (results.length > shown.length) {
    list.append(el('li', { class: 'find-more' },
      el('button', { type: 'button', class: 'btn', text: `Show all ${results.length} matches`, onclick: () => { showAll = true; renderResults(false); } })));
  }

  const ex = $('r-excluded');
  ex.replaceChildren();
  const listed = excluded.filter(x => x.by !== 'country'); // other countries are simply not shown
  if (listed.length) {
    ex.append(el('details', { class: 'find-excluded panel' },
      el('summary', { text: `${listed.length} ${listed.length === 1 ? 'scheme' : 'schemes'} left out by your must-haves` }),
      el('ul', {}, listed.map(x => el('li', {},
        el('span', { 'aria-hidden': 'true', text: (x.rec.flag || '') + ' ' }),
        el('a', { href: `explore.html?dataset=apprenticeship-schemes&open=${encodeURIComponent(x.rec.id)}`, text: x.rec.name_en }),
        el('span', { class: 'find-ex-why', text: ` — ${x.rec.country}: ${x.why}` }))))));
  }
  $('share-status').textContent = '';
  if (focus) $('r-title').focus();
}

const shortQ = { c: 'Where', age: 'Age', pay: 'Pay', he: 'University', work: 'At work', level: 'Level', status: 'Status' };

/* ---------------- URL ---------------- */

function resultsHref() {
  const qs = encodeAnswers(answers);
  return location.pathname + '?' + (qs || 'r=1');
}

function finish() {
  showAll = false;
  history.pushState(null, '', resultsHref());
  renderResults(true);
}

function fromURL() {
  const p = new URLSearchParams(location.search);
  answers = parseAnswers(p);
  showAll = false;
  const known = ['r', ...QUESTIONS.map(q => q.id)].some(k => p.has(k));
  if (known) renderResults(false);
  else { step = 0; showQuiz(); renderStep(false); }
}

/* ---------------- wiring ---------------- */

$('quiz-form').addEventListener('submit', (e) => {
  e.preventDefault();
  if (step < QUESTIONS.length - 1) go(step + 1, true);
  else finish();
});
$('back').addEventListener('click', () => go(step - 1, true));
$('skip').addEventListener('click', finish);
$('edit').addEventListener('click', () => go(0, true));
$('restart').addEventListener('click', () => {
  answers = parseAnswers('');
  history.pushState(null, '', location.pathname);
  go(0, true);
});
$('share').addEventListener('click', async () => {
  const href = location.href;
  const st = $('share-status');
  try {
    await navigator.clipboard.writeText(href);
    st.textContent = 'Link copied.';
  } catch {
    st.textContent = href;
  }
});
window.addEventListener('popstate', fromURL);

(async function init() {
  try {
    const [schemes, vet, ref] = await Promise.all([
      loadDataset('apprenticeship-schemes'),
      loadDataset('vet-systems').catch(() => ({ records: [] })),
      fetch(url('data/reference/countries.json')).then(r => r.json())
    ]);
    SCHEMES = schemes.records;
    const groups = {};
    for (const c of ref.countries) {
      NAMES[c.code] = c.name;
      groups[c.code] = c.group;
    }
    for (const v of vet.records) if (v.country_code && v.source_url) VETSYS[siteCode(v.country_code)] = v.source_url;

    const byCode = new Map();
    for (const s of SCHEMES) {
      const code = String(s.country_code).toUpperCase();
      const e = byCode.get(code) || { code, name: NAMES[siteCode(code)] || s.country, flag: s.flag || '', n: 0 };
      e.n++;
      byCode.set(code, e);
    }
    const items = [...byCode.values()].sort((a, b) => a.name.localeCompare(b.name));
    const eu = items.filter(c => groups[siteCode(c.code)] === 'eu');
    const other = items.filter(c => groups[siteCode(c.code)] !== 'eu');
    COUNTRY_GROUPS = [{ label: 'EU countries', items: eu }];
    if (other.length) COUNTRY_GROUPS.push({ label: 'Also in Europe', items: other });
    QUESTIONS[0].options = items.map(c => ({ value: c.code, label: c.name }));
    $('loading').remove();
    fromURL();
  } catch (err) {
    $('loading').textContent = `Could not load the schemes. ${err.message}`;
  }
})();
