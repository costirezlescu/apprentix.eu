/* Apprentix — "Myth or fact?" (pages/myths.html).
   Ten statements from data/published/myths/myths.json (verdicts computed by pipeline/myths.py),
   one at a time: answer, see the data, move on; a score to share at the end.
   All text is set with textContent. Nothing is stored. */

import { url } from './data.js?v=0246fca6';

const ROUND = 10;
const host = document.getElementById('mf');
const announce = document.getElementById('mf-announce');
const VERDICT = { myth: 'Myth', fact: 'Fact', partly: 'Partly true' };

let pool = [], round = [], i = 0, score = 0;

function el(tag, cls, parent, txt) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  if (parent) parent.appendChild(e);
  return e;
}

function shuffle(a) {
  const b = a.slice();
  for (let k = b.length - 1; k > 0; k--) {
    const j = Math.floor(Math.random() * (k + 1));
    [b[k], b[j]] = [b[j], b[k]];
  }
  return b;
}

function start() {
  round = shuffle(pool).slice(0, ROUND);
  i = 0;
  score = 0;
  show();
}

function progress(parent) {
  const p = el('div', 'mf-progress', parent);
  el('span', 'mono', p, `Statement ${i + 1} of ${round.length}`);
  el('span', 'mono', p, `Score ${score}`);
}

function show() {
  const it = round[i];
  host.replaceChildren();
  host.setAttribute('aria-busy', 'false');
  progress(host);
  const card = el('article', 'mf-card', host);
  el('p', 'mf-statement', card, `“${it.statement}”`);
  const choices = el('div', 'mf-choices', card);
  const pick = choice => answer(it, choice, card, choices);
  for (const [key, label] of [['myth', 'Myth'], ['fact', 'Fact']]) {
    const b = el('button', `mf-btn mf-${key}`, choices, label);
    b.type = 'button';
    b.addEventListener('click', () => pick(key));
  }
  choices.querySelector('button').focus({ preventScroll: true });
  announce.textContent = `Statement ${i + 1} of ${round.length}: ${it.statement}`;
}

function answer(it, choice, card, choices) {
  choices.querySelectorAll('button').forEach(b => { b.disabled = true; });
  const right = it.verdict === 'partly' ? 0.5 : choice === it.verdict ? 1 : 0;
  score += right;
  const res = el('div', `mf-result ${right === 1 ? 'is-right' : right ? 'is-half' : 'is-wrong'}`, card);
  const head = el('p', 'mf-verdict', res);
  el('span', 'mf-mark', head, right === 1 ? '✓ Right' : right ? '◐ Half right' : '✕ Not quite');
  el('span', 'mf-v', head, ` — it's ${it.verdict === 'partly' ? 'partly true' : `a ${VERDICT[it.verdict].toLowerCase()}`}.`);
  el('p', 'mf-answer', res, it.answer);
  if (it.detail) el('p', 'mf-detail', res, it.detail);
  const src = el('p', 'mf-src', res);
  src.append('Source: ', it.source, ' · ');
  const a = el('a', null, src, 'See the data');
  a.href = url(it.link);
  const next = el('button', 'btn primary mf-next', res, i + 1 < round.length ? 'Next statement' : 'See your score');
  next.type = 'button';
  next.addEventListener('click', () => { i++; if (i < round.length) show(); else finish(); });
  next.focus({ preventScroll: true });
  announce.textContent = `${right === 1 ? 'Right' : right ? 'Half right' : 'Not quite'}. ${it.answer}`;
}

function finish() {
  host.replaceChildren();
  const box = el('section', 'mf-end', host);
  const pts = Number.isInteger(score) ? score : score.toFixed(1);
  el('p', 'mono play-kicker', box, 'Your score');
  el('p', 'mf-score', box, `${pts} / ${round.length}`);
  el('p', 'mf-end-text', box, score >= 8 ? 'You know your apprenticeships.'
    : score >= 5 ? 'Not bad — a few myths are stubborn.' : 'Plenty of myths out there — now you know.');
  const share = `I got ${pts}/${round.length} on "Myth or fact?" about apprenticeships in Europe. Try it: https://apprentix.eu/pages/myths.html`;
  const actions = el('p', 'cp-links', box);
  const again = el('button', 'btn primary', actions, 'Play again');
  again.type = 'button';
  again.addEventListener('click', start);
  const copy = el('button', 'btn', actions, 'Copy my score');
  copy.type = 'button';
  copy.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(share); copy.textContent = 'Copied ✓'; }
    catch { copy.textContent = share; }
  });
  const more = el('p', 'mf-more', box);
  more.append('More: ');
  for (const [href, text] of [['pages/find.html', 'Find my apprenticeship'], ['pages/play.html', 'Higher or lower?'], ['pages/compare.html', 'Compare all 34 schemes']]) {
    const a = el('a', null, more, text);
    a.href = url(href);
    if (text !== 'Compare all 34 schemes') more.append(' · ');
  }
  announce.textContent = `Your score: ${pts} out of ${round.length}.`;
  again.focus({ preventScroll: true });
}

try {
  const r = await fetch(url('data/published/myths/myths.json'));
  if (!r.ok) throw new Error(r.status);
  pool = (await r.json()).items || [];
  if (!pool.length) throw new Error('empty');
  start();
} catch {
  host.replaceChildren();
  el('p', 'play-loading', host, 'The statements could not be loaded. Please try again later.');
}
