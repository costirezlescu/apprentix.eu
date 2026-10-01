/* Apprentix — pure helpers for the "Higher or lower?" game (no DOM; tested with node). */

export const ROUND = 10;
/** Difficulty of each slot in a round: starts easy, ends hard (3 easy, 4 medium, 3 hard). */
export const PLAN = [1, 1, 2, 1, 2, 3, 2, 3, 2, 3];

const SEED_RE = /^[a-z0-9]{4,16}$/;

/** A seed from the URL (lower-case letters and digits, 4–16 characters), or null. */
export function parseSeed(search) {
  const s = String(new URLSearchParams(search).get('seed') || '').trim().toLowerCase();
  return SEED_RE.test(s) ? s : null;
}

/** A fresh random seed (8 base-36 characters). `rand` is injectable for tests. */
export function newSeed(rand) {
  const r = rand || (() => {
    if (globalThis.crypto?.getRandomValues) return globalThis.crypto.getRandomValues(new Uint32Array(1))[0] / 2 ** 32;
    return Math.random();
  });
  let s = '';
  for (let i = 0; i < 8; i++) s += '0123456789abcdefghijklmnopqrstuvwxyz'[Math.floor(r() * 36)];
  return s;
}

/** String → 32-bit hash (FNV-1a). */
export function hashSeed(str) {
  let h = 0x811c9dc5;
  for (const ch of String(str)) {
    h ^= ch.codePointAt(0);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

/** Small, fast seeded PRNG (mulberry32) → function returning [0, 1). */
export function rng(seed) {
  let a = typeof seed === 'number' ? seed >>> 0 : hashSeed(seed);
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const pairKey = (q) => [q.a.geo, q.b.geo].sort().join('-');

/**
 * Draw a round from the pool, deterministically from the seed.
 * Mixed difficulty following PLAN; never the same question twice; tries to
 * avoid repeating an indicator, a country pair, or a country more than twice.
 * Constraints relax step by step if the pool is too small for them.
 */
export function drawRound(questions, seed, n = ROUND) {
  const pool = [...questions].sort((x, y) => (x.id < y.id ? -1 : x.id > y.id ? 1 : 0));
  const rand = rng(`round:${seed}`);
  const picked = [];
  const used = new Set(), inds = new Set(), pairs = new Set();
  const geoCount = new Map();
  const plan = Array.from({ length: n }, (_, i) => PLAN[i % PLAN.length]);
  const tiers = [
    (q, d) => q.difficulty === d && !inds.has(q.indicator) && !pairs.has(pairKey(q)) &&
      (geoCount.get(q.a.geo) || 0) < 2 && (geoCount.get(q.b.geo) || 0) < 2,
    (q, d) => q.difficulty === d && !inds.has(q.indicator) && !pairs.has(pairKey(q)),
    (q, d) => q.difficulty === d && !pairs.has(pairKey(q)),
    (q) => !inds.has(q.indicator),
    () => true,
  ];
  for (const d of plan) {
    let choice = null;
    for (const ok of tiers) {
      const c = pool.filter(q => !used.has(q.id) && ok(q, d));
      if (c.length) { choice = c[Math.floor(rand() * c.length)]; break; }
    }
    if (!choice) break;
    picked.push(choice);
    used.add(choice.id); inds.add(choice.indicator); pairs.add(pairKey(choice));
    for (const g of [choice.a.geo, choice.b.geo]) geoCount.set(g, (geoCount.get(g) || 0) + 1);
  }
  return picked;
}

/** Was the pick right? side is 'a' or 'b'. */
export const isCorrect = (q, side) => q.answer === side;

/** Score bookkeeping: returns a new state. */
export function record(state, correct) {
  const streak = correct ? state.streak + 1 : 0;
  return { score: state.score + (correct ? 1 : 0), streak, bestStreak: Math.max(state.bestStreak, streak), answered: state.answered + 1 };
}

export const freshState = () => ({ score: 0, streak: 0, bestStreak: 0, answered: 0 });

/** Friendly end-of-round line. */
export function verdict(score, total = ROUND) {
  const r = total ? score / total : 0;
  if (score === total) return 'A perfect round — you know Europe’s apprenticeship systems inside out.';
  if (r >= 0.8) return 'Excellent — you clearly know your way around vocational education in Europe.';
  if (r >= 0.6) return 'A good round: more right than wrong, and several of these are genuinely close.';
  if (r >= 0.4) return 'Not bad at all — a few of these figures surprise even people who work in the field.';
  return 'A tough round. Many of these numbers are surprising — have a look at the data and try another.';
}

/** "I scored 8/10 on European apprenticeships — apprentix.eu/pages/play.html?seed=…" */
export function shareText(score, total, link) {
  const bare = String(link).replace(/^https?:\/\//, '');
  return `I scored ${score}/${total} on European apprenticeships — ${bare}`;
}

/** Link to this round: the current page with only ?seed=. */
export function roundLink(loc, seed) {
  return `${loc.origin}${loc.pathname}?seed=${encodeURIComponent(seed)}`;
}

/**
 * Intermediate text while a value counts up: the number inside `display` is
 * replaced by `display`'s number × t, keeping its decimals and thousands commas.
 */
export function tweenDisplay(display, t) {
  const m = String(display).match(/-?\d[\d,]*(\.\d+)?/);
  if (!m) return display;
  const target = parseFloat(m[0].replace(/,/g, ''));
  const dec = m[1] ? m[1].length - 1 : 0;
  const v = target * Math.max(0, Math.min(1, t));
  const txt = new Intl.NumberFormat('en-GB', { minimumFractionDigits: dec, maximumFractionDigits: dec, useGrouping: m[0].includes(',') }).format(v);
  return display.slice(0, m.index) + txt + display.slice(m.index + m[0].length);
}

/** Bar widths (0–100) for two numeric values, relative to the larger. */
export function meterWidths(a, b) {
  if (typeof a !== 'number' || typeof b !== 'number') return null;
  const m = Math.max(Math.abs(a), Math.abs(b));
  if (!m) return [0, 0];
  return [Math.round((Math.abs(a) / m) * 1000) / 10, Math.round((Math.abs(b) / m) * 1000) / 10];
}
