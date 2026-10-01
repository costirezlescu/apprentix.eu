/* Apprentix — "Did you know?" card and "Surprise me".

   Facts come from data/published/facts/facts.json (pipeline/facts.py): short,
   computed statements, each with the number to emphasise, a source and a link
   to the view that shows it.

     mountDidYouKnow(host, opts)  render a fact card into `host`
     surpriseMe(opts)             jump to a random fact's view (adds ?surprise=<id>)
     mountSurpriseBanner()        on the landing page, explain why the user is here

   Data text is always inserted with textContent, never as HTML. */

import { url } from './data.js';

const FACTS_PATH = 'data/published/facts/facts.json';
const SEEN_KEY = 'apprentix:facts-seen';
const PARAM = 'surprise';

const KIND_LABELS = {
  record: 'Record', contrast: 'Contrast', trend: 'Trend', design: 'Scheme design',
  qualification: 'Qualifications', mobility: 'Mobility', policy: 'Policy', outcome: 'Outcomes'
};

let factsPromise = null;

/** All facts (cached for the page). Resolves to [] if the file cannot be loaded. */
export function loadFacts() {
  factsPromise ||= fetch(url(FACTS_PATH))
    .then(r => (r.ok ? r.json() : Promise.reject(new Error(`${r.status} ${FACTS_PATH}`))))
    .then(d => (Array.isArray(d.items) ? d.items : []))
    .catch(err => { console.warn('Facts unavailable:', err); return []; });
  return factsPromise;
}

/* ---------- session memory (best effort; storage may be blocked) ---------- */

function seenIds() {
  try {
    const v = JSON.parse(sessionStorage.getItem(SEEN_KEY) || '[]');
    return Array.isArray(v) ? v : [];
  } catch { return []; }
}

function markSeen(id) {
  try {
    const s = seenIds().filter(x => x !== id);
    s.push(id);
    sessionStorage.setItem(SEEN_KEY, JSON.stringify(s.slice(-300)));
  } catch { /* storage unavailable: repeats are possible, nothing breaks */ }
}

function forgetSeen(ids) {
  try {
    const drop = new Set(ids);
    sessionStorage.setItem(SEEN_KEY, JSON.stringify(seenIds().filter(x => !drop.has(x))));
  } catch { /* ignore */ }
}

/* ---------- choosing ---------- */

function matchesOpts(f, opts) {
  if (opts.kinds?.length && !opts.kinds.includes(f.kind)) return false;
  if (opts.country && !(f.countries || []).includes(opts.country)) return false;
  return true;
}

/** Weighted random fact (weight 1–3), avoiding facts already shown this session. */
export function pickFact(items, opts = {}) {
  const exclude = new Set([].concat(opts.exclude || []));
  let pool = items.filter(f => f && f.id && f.text && !exclude.has(f.id) && matchesOpts(f, opts));
  if (!pool.length) pool = items.filter(f => f && f.id && !exclude.has(f.id));
  if (!pool.length) return null;
  const seen = new Set(seenIds());
  let fresh = pool.filter(f => !seen.has(f.id));
  if (!fresh.length) {           // everything seen: start a new round
    forgetSeen(pool.map(f => f.id));
    fresh = pool;
  }
  const total = fresh.reduce((s, f) => s + weightOf(f), 0);
  let r = Math.random() * total;
  for (const f of fresh) {
    r -= weightOf(f);
    if (r < 0) return f;
  }
  return fresh[fresh.length - 1];
}

const weightOf = (f) => Math.min(3, Math.max(1, Number(f.weight) || 1));

/* ---------- rendering helpers ---------- */

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

/** Fill `p` with the fact text, the highlight wrapped in <strong>. */
function fillText(p, fact) {
  p.replaceChildren();
  const text = String(fact.text || '');
  const hl = String(fact.highlight || '');
  const i = hl ? text.indexOf(hl) : -1;
  if (i < 0) { p.textContent = text; return; }
  if (i > 0) p.append(document.createTextNode(text.slice(0, i)));
  p.append(el('strong', 'dyk-hl', hl));
  if (i + hl.length < text.length) p.append(document.createTextNode(text.slice(i + hl.length)));
}

/** Absolute URL of a fact's link, optionally tagged with ?surprise=<id> (before any #hash). */
export function factHref(fact, surprise = false) {
  const u = new URL(url(fact.link || ''));
  if (surprise) u.searchParams.set(PARAM, fact.id);
  return u.href;
}

const reducedMotion = () => {
  try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return false; }
};

/* ---------- "Did you know?" card ---------- */

/**
 * Render a "Did you know?" card into `host`.
 * opts: { kinds: [..], country: 'FR', title: 'Did you know?', surprise: true }
 * Returns a promise of { next() } (or null when no facts are available; the host is then hidden).
 */
export async function mountDidYouKnow(host, opts = {}) {
  if (!host) return null;
  const items = await loadFacts();
  if (!items.length) { host.hidden = true; return null; }

  host.classList.add('dyk');
  host.replaceChildren();
  if (!host.hasAttribute('aria-label') && !host.hasAttribute('aria-labelledby')) {
    host.setAttribute('aria-label', opts.title || 'Did you know?');
  }

  const head = el('div', 'dyk-head');
  const eyebrow = el('span', 'dyk-eyebrow mono', opts.title || 'Did you know?');
  const kind = el('span', 'dyk-kind mono');
  head.append(eyebrow, kind);

  const body = el('div', 'dyk-body');
  const text = el('p', 'dyk-text');
  text.setAttribute('aria-live', 'polite');
  const source = el('p', 'dyk-source');
  body.append(text, source);

  const actions = el('div', 'dyk-actions');
  const show = el('a', 'btn primary dyk-show', 'Show me');
  show.append(el('span', 'dyk-arrow', ' →'));
  const another = el('button', 'btn dyk-next', 'Another fact');
  another.type = 'button';
  actions.append(show, another);
  if (opts.surprise !== false) {
    const surprise = el('button', 'btn dyk-surprise', 'Surprise me');
    surprise.type = 'button';
    surprise.title = 'Jump to a random finding somewhere on the site';
    surprise.addEventListener('click', () => surpriseMe({ exclude: current?.id }));
    actions.append(surprise);
  }

  host.append(head, body, actions);

  let current = null;
  const render = (fact) => {
    current = fact;
    markSeen(fact.id);
    kind.textContent = KIND_LABELS[fact.kind] || '';
    kind.hidden = !kind.textContent;
    fillText(text, fact);
    source.textContent = fact.source ? `Source: ${fact.source}` : '';
    show.href = factHref(fact);
    show.setAttribute('aria-label', `Show me: ${fact.text}`);
  };

  let busy = false;
  const next = () => {
    if (busy) return;
    const fact = pickFact(items, { ...opts, exclude: current?.id });
    if (!fact) return;
    if (reducedMotion()) { render(fact); return; }
    busy = true;
    body.classList.add('is-leaving');
    let done = false;
    const swap = () => {
      if (done) return;
      done = true;
      render(fact);
      body.classList.remove('is-leaving');
      body.classList.add('is-entering');
      requestAnimationFrame(() => requestAnimationFrame(() => {
        body.classList.remove('is-entering');
        busy = false;
      }));
    };
    body.addEventListener('transitionend', swap, { once: true });
    setTimeout(swap, 220);   // in case transitionend never fires
  };

  another.addEventListener('click', next);
  render(pickFact(items, opts));
  return { next };
}

/* ---------- Surprise me ---------- */

/** Pick a weighted-random fact and go to its view, tagged so the banner can explain why. */
export async function surpriseMe(opts = {}) {
  const items = await loadFacts();
  const fact = pickFact(items, opts);
  if (!fact) return;
  markSeen(fact.id);
  location.href = factHref(fact, true);
}

/**
 * On any page reached through "Surprise me" (?surprise=<fact id>), show a small
 * dismissible banner at the top of <main> with the fact that brought the user here.
 */
export async function mountSurpriseBanner() {
  let id;
  try { id = new URL(location.href).searchParams.get(PARAM); } catch { return null; }
  if (!id) return null;
  const items = await loadFacts();
  const fact = items.find(f => f.id === id);
  const main = document.querySelector('main') || document.body;
  if (!fact || !main) return null;

  const box = el('div', 'surprise-banner');
  box.setAttribute('role', 'status');
  const label = el('span', 'surprise-label mono', 'Surprise!');
  const text = el('p', 'surprise-text');
  fillText(text, fact);
  const src = el('span', 'surprise-source', fact.source ? ` Source: ${fact.source}.` : '');
  text.append(src);

  const again = el('button', 'linkbtn surprise-again', 'Another surprise');
  again.type = 'button';
  again.addEventListener('click', () => surpriseMe({ exclude: fact.id }));

  const close = el('button', 'surprise-close');
  close.type = 'button';
  close.setAttribute('aria-label', 'Dismiss');
  close.textContent = '×';
  close.addEventListener('click', () => {
    box.remove();
    try {   // drop the marker so a reload or shared link does not show it again
      const u = new URL(location.href);
      u.searchParams.delete(PARAM);
      history.replaceState(history.state, '', u.href);
    } catch { /* ignore */ }
  });

  const content = el('div', 'surprise-content');
  content.append(label, text, again);
  box.append(content, close);
  main.prepend(box);
  return box;
}
