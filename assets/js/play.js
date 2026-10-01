/* Apprentix — "Higher or lower?" game (pages/play.html).
   Questions come from data/published/play/questions.json (pipeline/play.py).
   All text is set with textContent. No tracking: the only thing stored is the
   viewer's best score, in their own browser. */

import { url } from './data.js';
import {
  ROUND, parseSeed, newSeed, drawRound, isCorrect, record, freshState, verdict,
  shareText, roundLink, tweenDisplay, meterWidths,
} from './play-core.js';

const BEST_KEY = 'apprentix-play-best';
const root = document.getElementById('play');
const announce = document.getElementById('play-announce');
const reduceMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

let POOL = [];
let game = null;   // { seed, round, i, state, answers: [{q, pick, correct}], locked }

/* ---------- tiny DOM helper (text only, never innerHTML) ---------- */

function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c);
  return n;
}

function say(msg) {
  // Clear first so the same message is announced again.
  announce.textContent = '';
  setTimeout(() => { announce.textContent = msg; }, 30);
}

/* ---------- best score (per-viewer convenience only) ---------- */

function getBest() {
  try { const v = parseInt(localStorage.getItem(BEST_KEY), 10); return Number.isFinite(v) ? v : null; } catch { return null; }
}
function setBest(v) {
  try { localStorage.setItem(BEST_KEY, String(v)); } catch { /* storage unavailable: ignore */ }
}

/* ---------- round lifecycle ---------- */

function start(seed, { focus = false } = {}) {
  const round = drawRound(POOL, seed, ROUND);
  game = { seed, round, i: 0, state: freshState(), answers: [], locked: false };
  try { history.replaceState(null, '', `?seed=${encodeURIComponent(seed)}`); } catch { /* sandboxed: ignore */ }
  renderQuestion(focus);
}

function sideLabel(side) { return side === 'a' ? 'A' : 'B'; }

function renderQuestion(focus = true) {
  const q = game.round[game.i];
  const n = game.round.length;
  root.textContent = '';
  root.setAttribute('aria-busy', 'false');

  const bar = el('div', { class: 'play-bar' },
    el('span', { class: 'play-count', text: `Question ${game.i + 1} of ${n}` }),
    el('span', { class: 'play-stat' }, el('span', { class: 'play-stat-k', text: 'Score ' }), el('strong', { id: 'play-score', text: String(game.state.score) })),
    el('span', { class: 'play-stat' }, el('span', { class: 'play-stat-k', text: 'Streak ' }), el('strong', { id: 'play-streak', text: String(game.state.streak) })),
  );
  const best = getBest();
  if (best != null) bar.append(el('span', { class: 'play-stat' }, el('span', { class: 'play-stat-k', text: 'Best ' }), el('strong', { text: `${best}/${ROUND}` })));

  const progress = el('div', { class: 'play-progress', 'aria-hidden': 'true' },
    el('span', { style: `width:${(game.i / n) * 100}%` }));

  const heading = el('h2', { class: 'play-q', id: 'play-q', tabindex: '-1', text: q.measure });
  const meta = el('p', { class: 'play-meta' },
    el('span', { text: q.kind === 'scheme' ? `Cedefop apprenticeship scheme fiches, ${q.year}` : `${q.source}, ${q.year}` }),
    el('span', { class: 'play-diff', text: ['', 'Easier', 'Medium', 'Harder'][q.difficulty] || '' }));

  const cards = el('div', { class: 'play-cards', role: 'group', 'aria-labelledby': 'play-q' },
    card(q, 'a'), el('span', { class: 'play-vs', 'aria-hidden': 'true', text: 'or' }), card(q, 'b'));

  const hint = el('p', { class: 'play-hint', id: 'play-hint', text: 'Choose with a tap or click — or press A / ← for the first country and B / → for the second.' });
  const result = el('div', { class: 'play-result', id: 'play-result', hidden: true });

  root.append(bar, progress, heading, meta, cards, hint, result);
  if (focus) heading.focus();
}

function card(q, side) {
  const s = q[side];
  return el('button', {
    type: 'button', class: `play-card play-card-${side}`, 'data-side': side,
    'aria-describedby': 'play-hint', onclick: () => choose(side),
  },
  el('span', { class: 'play-key', 'aria-hidden': 'true', text: sideLabel(side) }),
  el('span', { class: 'play-emoji', 'aria-hidden': 'true', text: s.emoji || '' }),
  el('span', { class: 'play-name', text: s.name }),
  s.scheme ? el('span', { class: 'play-scheme', text: s.scheme }) : null,
  el('span', { class: 'play-reveal' },
    el('span', { class: 'play-value' }),
    el('span', { class: 'play-mark' })),
  el('span', { class: 'play-meter', 'aria-hidden': 'true' }, el('span')));
}

function choose(side) {
  if (!game || game.locked || game.i >= game.round.length) return;
  game.locked = true;
  const q = game.round[game.i];
  const correct = isCorrect(q, side);
  game.state = record(game.state, correct);
  game.answers.push({ q, pick: side, correct });
  reveal(q, side, correct);
}

function reveal(q, pick, correct) {
  const widths = meterWidths(q.a.value, q.b.value);
  for (const side of ['a', 'b']) {
    const btn = root.querySelector(`.play-card-${side}`);
    const s = q[side];
    const higher = q.answer === side;
    btn.setAttribute('aria-disabled', 'true');
    btn.classList.add('is-revealed', higher ? 'is-higher' : 'is-lower');
    if (side === pick) btn.classList.add('is-picked');
    const val = btn.querySelector('.play-value');
    const mark = btn.querySelector('.play-mark');
    mark.textContent = (higher ? '▲ Higher' : '▼ Lower') + (side === pick ? ' · your pick' : '');
    countUp(val, s.display, typeof s.value === 'number');
    btn.setAttribute('aria-label', `${s.name}: ${s.display}${s.flag_label ? ` (${s.flag_label})` : ''}. ${higher ? 'Higher' : 'Lower'}${side === pick ? ', your pick' : ''}.`);
    if (s.flag_label) btn.querySelector('.play-reveal').append(el('span', { class: 'play-flag', text: s.flag_label }));
    const meter = btn.querySelector('.play-meter > span');
    if (widths) requestAnimationFrame(() => { meter.style.width = `${widths[side === 'a' ? 0 : 1]}%`; });
    else btn.querySelector('.play-meter').hidden = true;
  }
  root.querySelector('#play-hint').hidden = true;
  root.querySelector('#play-score').textContent = String(game.state.score);
  root.querySelector('#play-streak').textContent = String(game.state.streak);

  const last = game.i === game.round.length - 1;
  const winner = q[q.answer].name;
  const res = root.querySelector('#play-result');
  res.hidden = false;
  res.classList.add(correct ? 'is-correct' : 'is-wrong');
  const next = el('button', { type: 'button', class: 'btn primary play-next', id: 'play-next', onclick: nextQuestion, text: last ? 'See your score' : 'Next question' });
  res.append(
    el('p', { class: 'play-outcome' },
      el('span', { class: 'play-icon', 'aria-hidden': 'true', text: correct ? '✓' : '✗' }),
      el('strong', { text: correct ? 'Correct' : 'Not this time' }),
      el('span', { text: ` — ${winner} is higher.` })),
    el('p', { class: 'play-explain', text: q.explain }),
    el('div', { class: 'play-actions' },
      el('a', { class: 'btn play-link', href: q.link, target: '_blank', rel: 'noopener', text: 'See the data' },
        el('span', { class: 'play-sr', text: ' (opens in a new tab)' })),
      next));
  say(`${correct ? 'Correct' : 'Not this time'}: ${winner} is higher. ${q.explain}${game.state.streak >= 3 ? ` Streak of ${game.state.streak}.` : ''}`);
  next.focus({ preventScroll: true });
  res.scrollIntoView?.({ block: 'nearest', behavior: reduceMotion() ? 'auto' : 'smooth' });
}

function countUp(node, display, numeric) {
  if (!numeric || reduceMotion() || typeof requestAnimationFrame !== 'function') { node.textContent = display; return; }
  const t0 = performance.now(), dur = 650;
  const step = () => {
    const t = Math.min(1, (performance.now() - t0) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    node.textContent = t >= 1 ? display : tweenDisplay(display, eased);
    if (t < 1) requestAnimationFrame(step);
  };
  node.textContent = tweenDisplay(display, 0);
  requestAnimationFrame(step);
}

function nextQuestion() {
  if (!game?.locked) return;
  game.i += 1;
  game.locked = false;
  if (game.i >= game.round.length) renderEnd();
  else renderQuestion(true);
}

/* ---------- end screen ---------- */

function renderEnd() {
  const { score } = game.state;
  const total = game.round.length;
  const prev = getBest();
  const isBest = prev == null || score > prev;
  if (isBest) setBest(score);
  const link = roundLink(location, game.seed);
  const text = shareText(score, total, link);

  root.textContent = '';
  const heading = el('h2', { class: 'play-end-title', tabindex: '-1', text: `You scored ${score} out of ${total}` });
  const status = el('span', { class: 'play-status', role: 'status', 'aria-live': 'polite' });
  const linkInput = el('input', { type: 'text', id: 'play-link', class: 'play-link-input', readonly: true, value: link, onfocus: (e) => e.target.select() });

  const list = el('ol', { class: 'play-review' }, game.answers.map(({ q, pick, correct }) =>
    el('li', { class: correct ? 'is-correct' : 'is-wrong' },
      el('p', { class: 'play-review-head' },
        el('span', { class: 'play-icon', 'aria-hidden': 'true', text: correct ? '✓' : '✗' }),
        el('strong', { text: correct ? 'Correct' : 'Wrong' }),
        el('span', { text: ` — ${q.measure}` })),
      el('p', { class: 'play-review-body', text: `You picked ${q[pick].name}; ${q[q.answer].name} is higher. ${q.explain}` }),
      el('a', { href: q.link, target: '_blank', rel: 'noopener', text: 'See the data' },
        el('span', { class: 'play-sr', text: ` for “${q.measure}” (opens in a new tab)` })))));

  root.append(el('section', { class: 'play-end', 'aria-labelledby': 'play-end-title' },
    el('div', { class: 'play-end-card' },
      Object.assign(heading, { id: 'play-end-title' }),
      el('p', { class: 'play-end-verdict', text: verdict(score, total) }),
      el('p', { class: 'play-end-best', text: isBest && prev != null ? `New personal best — your previous best was ${prev}/${total}.`
        : prev == null ? `Longest streak: ${game.state.bestStreak}.` : `Your best so far: ${Math.max(prev, score)}/${total}. Longest streak this round: ${game.state.bestStreak}.` }),
      el('div', { class: 'play-actions' },
        el('button', { type: 'button', class: 'btn primary', text: 'Play again', onclick: () => start(newSeed(), { focus: true }) }),
        el('button', { type: 'button', class: 'btn', text: 'Challenge a friend', onclick: () => challenge(text, link, status, linkInput) }),
        status),
      el('label', { class: 'play-link-label', for: 'play-link', text: 'Link to this exact round (same ten questions)' }),
      linkInput),
    el('h3', { class: 'play-review-title', text: 'Your answers' }),
    list));
  say(`Round over. You scored ${score} out of ${total}.`);
  heading.focus();
}

async function challenge(text, link, status, input) {
  status.textContent = '';
  if (navigator.share) {
    try { await navigator.share({ title: 'Higher or lower? — Apprentix', text }); status.textContent = 'Shared.'; return; }
    catch (e) { if (e?.name === 'AbortError') return; }
  }
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = 'Copied — paste it to a friend.';
  } catch {
    input.focus();
    input.select();
    status.textContent = 'Copy the link below to share it.';
  }
}

/* ---------- keyboard ---------- */

document.addEventListener('keydown', (e) => {
  if (!game || e.altKey || e.ctrlKey || e.metaKey) return;
  const t = e.target;
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
  if (game.i >= game.round.length) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (!game.locked) {
    if (k === 'ArrowLeft' || k === 'a') { e.preventDefault(); choose('a'); }
    else if (k === 'ArrowRight' || k === 'b') { e.preventDefault(); choose('b'); }
  } else if (k === 'n') {
    e.preventDefault(); nextQuestion();
  }
});

/* ---------- boot ---------- */

async function boot() {
  try {
    const r = await fetch(url('data/published/play/questions.json'));
    if (!r.ok) throw new Error(`${r.status}`);
    const data = await r.json();
    POOL = data.questions || [];
    if (POOL.length < ROUND) throw new Error('too few questions');
  } catch {
    root.setAttribute('aria-busy', 'false');
    root.textContent = '';
    root.append(el('p', { class: 'play-loading', text: 'The questions could not be loaded. Please try again later — the figures are also on the Indicators page.' }));
    return;
  }
  start(parseSeed(location.search) || newSeed());
}

boot();
