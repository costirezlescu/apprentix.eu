/* Apprentix — pure helpers for the country duel (no DOM; tested with node).
   Formatting mirrors pipeline/render_pages.py fmt_value so numbers read the
   same as on the country pages. */

const nf = (digits) => new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: 0 });

/** Same rules as render_pages.fmt_value. */
export function fmtValue(v, unit) {
  if (v == null || Number.isNaN(v)) return '—';
  let u = (unit || '').trim();
  if (u.includes('%')) {
    const rest = u.replace('%', '').trim();
    return new Intl.NumberFormat('en-GB', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(v) + '%' + (rest ? ` ${rest}` : '');
  }
  if (u === '1000s' || u === '1000 PPS') u = 'thousand' + u.slice(4);
  let num;
  if (v === Math.trunc(v) && Math.abs(v) >= 10) num = nf(0).format(v);
  else if (Math.abs(v) >= 100) num = nf(0).format(v);
  else if (Math.abs(v) >= 10) num = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(v);
  else num = nf(2).format(v);
  if (u === 'EUR') return `EUR ${num}`;
  return `${num} ${u}`.trim();
}

/** "EUR 19.3 million" / "EUR 832 million" / "EUR 79". */
export function fmtEur(v) {
  if (v == null) return '—';
  if (Math.abs(v) >= 1e6) {
    const m = v / 1e6;
    return `EUR ${nf(m >= 100 ? 0 : 1).format(m)} million`;
  }
  return `EUR ${nf(0).format(v)}`;
}

export const fmtInt = (v) => (v == null ? '—' : nf(0).format(v));

/** Accent- and case-insensitive text for search. */
export const fold = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

const yearNum = (y) => parseInt(String(y || '').slice(0, 4), 10);

/** Max year gap allowed for two values to count as comparable. */
export const MAX_YEAR_GAP = 1;

/**
 * Compare one key-figure measure for two profiles.
 * Returns {a, b, comparable, reason, edge} where edge is 'a', 'b' or null.
 * Comparable = same indicator, both values present, years at most MAX_YEAR_GAP apart.
 * An edge is only given for measures with a defined direction (higher/lower).
 */
export function compareMeasure(measure, A, B) {
  const a = A?.figures?.[measure.key] || null;
  const b = B?.figures?.[measure.key] || null;
  const out = { a, b, comparable: false, reason: '', edge: null, directional: measure.better === 'higher' || measure.better === 'lower' };
  if (!a || !b) { out.reason = 'missing'; return out; }
  if (a.id !== b.id) { out.reason = 'different-source'; return out; }
  if (Math.abs(yearNum(a.y) - yearNum(b.y)) > MAX_YEAR_GAP) { out.reason = 'years'; return out; }
  out.comparable = true;
  if (out.directional && a.v !== b.v) {
    const aHigher = a.v > b.v;
    out.edge = (measure.better === 'higher') === aHigher ? 'a' : 'b';
  }
  return out;
}

/** Scorecard over directional, comparable measures only. */
export function scorecard(measures, A, B) {
  let n = 0, a = 0, b = 0, tie = 0;
  for (const m of measures) {
    const c = compareMeasure(m, A, B);
    if (!c.comparable || !c.directional) continue;
    n++;
    if (c.edge === 'a') a++; else if (c.edge === 'b') b++; else tie++;
  }
  return { n, a, b, tie };
}

/** Neutral one-line phrasing of a scorecard. */
export function scorecardText(sc, nameA, nameB) {
  if (!sc.n) return `No measure with a defined direction has comparable data for both ${nameA} and ${nameB}.`;
  const of = `of ${sc.n} comparable measure${sc.n === 1 ? '' : 's'}`;
  const tie = sc.tie ? `, level on ${sc.tie}` : '';
  if (sc.a === sc.b) return `${nameA} and ${nameB} are each ahead on ${sc.a} ${of}${tie}.`;
  const [hi, hn, lo, ln] = sc.a > sc.b ? [nameA, sc.a, nameB, sc.b] : [nameB, sc.b, nameA, sc.a];
  return `${hi} is ahead on ${hn} ${of}; ${lo} on ${ln}${tie}.`;
}

/** Values in `mine` that are not in `other` (both arrays; null other → none differ). */
export function onlyIn(mine, other) {
  if (!mine || !other) return new Set();
  const o = new Set(other);
  return new Set(mine.filter(x => !o.has(x)));
}

/** Pick EU-27 reference for an indicator: same year as both sides if they agree, else latest. */
export function euFor(euRef, id, ya, yb) {
  const s = euRef?.[id];
  if (!s) return null;
  if (ya && ya === yb && s[ya]) return s[ya];
  const ys = Object.keys(s).sort();
  return ys.length ? s[ys[ys.length - 1]] : null;
}

/** Scale max for a dot plot: covers all values with a little headroom; 0-based. */
export function scaleMax(vals) {
  const xs = vals.filter(v => v != null && !Number.isNaN(v)).map(Math.abs);
  const m = Math.max(0, ...xs);
  if (!m) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(m)));
  for (const k of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (k * p >= m * 1.04) return k * p;
  return 10 * p;
}

/** Parse ?a=&b= against the available codes; fall back to defaults; never the same twice. */
export function pickFromParams(search, codes, defA = 'AT', defB = 'FR') {
  const p = new URLSearchParams(search);
  const norm = (v) => String(v || '').trim().toUpperCase().replace(/^EU-?27$/, 'EU27');
  let a = norm(p.get('a')), b = norm(p.get('b'));
  if (!codes.includes(a)) a = codes.includes(defA) ? defA : codes[0];
  if (!codes.includes(b) || b === a) b = [defB, defA, ...codes].find(c => codes.includes(c) && c !== a);
  return { a, b };
}
