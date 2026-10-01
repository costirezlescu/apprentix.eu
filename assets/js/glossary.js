/* Apprentix — plain-language glossary popovers.

   initGlossary({ root }) loads data/reference/glossary.json once and marks the FIRST
   occurrence on the page of each glossary term inside `root` (default: <main>) with a
   dotted underline. Hover, keyboard focus, click or tap shows a small popover with a
   short definition, an optional "More" text, the source and a link to the glossary page.

   - Text is only ever read and written through text nodes / textContent (no innerHTML).
   - Skipped: headings, links, buttons, form controls, code, SVG, numeric table cells,
     <abbr> (publisher flags), nav/header/footer, hidden content and anything inside
     [data-no-glossary]. Attribute values are never touched.
   - Content rendered later (explorer, duel, find …) is picked up by a throttled
     MutationObserver. Terms already marked stay marked; if the marked element is removed
     from the page, the next occurrence is marked instead.
   - Matching: one regular expression built from every alias, longest first, with
     word boundaries that treat letters, digits, "_" and "-" as part of a word (so "VET"
     never matches inside "IVET" or "VET-specific", and "ISCED 3" not inside "ISCED 35").
     Aliases containing an upper-case letter match exactly; lower-case ones ignore case. */

const SKIP = [
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'button', 'input', 'textarea', 'select', 'option',
  'label', 'legend', 'summary', 'code', 'pre', 'kbd', 'samp', 'script', 'style', 'noscript',
  'template', 'svg', 'math', 'abbr', 'nav', '.site-head', '.site-foot', 'dialog', 'title',
  'td.num', 'th.num', '[contenteditable]', '[role="button"]', '[role="link"]', '[role="tab"]',
  '[role="option"]', '[role="menuitem"]', '[role="dialog"]', '[hidden]', '[aria-hidden="true"]',
  '[data-no-glossary]', '.gl-term', '.gl-pop', 'details:not([open]) > :not(summary)'
].join(',');

const HIDDEN = '[hidden], details:not([open]) > :not(summary)';
const SCAN_DELAY = 150;   // ms to batch mutations before rescanning
const HOVER_OPEN = 250;   // ms hover before opening
const HOVER_CLOSE = 300;  // ms grace when the pointer leaves

let dataPromise = null;

function siteRoot() {
  return (document.body && document.body.dataset.root) || './';
}

function resolve(path) {
  return new URL(siteRoot() + path, location.href).href;
}

function loadGlossary(url) {
  if (!dataPromise) {
    dataPromise = fetch(url).then(r => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText} — glossary`);
      return r.json();
    });
  }
  return dataPromise;
}

const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Build the matcher: one regex over every alias, longest first. */
export function buildMatcher(terms) {
  const exact = new Map();  // alias -> term (case-sensitive aliases)
  const loose = new Map();  // lower-cased alias -> term
  const aliases = [];
  for (const t of terms) {
    for (const a of t.aliases || []) {
      if (!a) continue;
      if (/[A-Z]/.test(a)) { if (!exact.has(a)) exact.set(a, t); }
      else if (!loose.has(a.toLowerCase())) loose.set(a.toLowerCase(), t);
      aliases.push(a);
    }
  }
  if (!aliases.length) return null;
  const uniq = [...new Set(aliases)].sort((a, b) => b.length - a.length);
  // Flexible whitespace inside multi-word aliases; word boundaries on both sides.
  const body = uniq.map(a => reEsc(a).replace(/ /g, '\\s+')).join('|');
  const re = new RegExp(`(?<![\\p{L}\\p{N}_-])(?:${body})(?![\\p{L}\\p{N}_]|-[\\p{L}\\p{N}])`, 'giu');
  const lookup = (text) => {
    const norm = text.replace(/\s+/g, ' ');
    return exact.get(norm) || loose.get(norm.toLowerCase()) || null;
  };
  return { re, lookup };
}

/* ---------------------------------------------------------------- popover -- */

let pop = null;          // the single shared popover element
let popParts = null;
let current = null;      // the .gl-term the popover belongs to
let pinned = false;
let hoverTimer = 0;
let byId = new Map();

function ensurePopover() {
  if (pop) return pop;
  pop = document.createElement('div');
  pop.className = 'gl-pop';
  pop.id = 'gl-pop';
  pop.setAttribute('role', 'dialog');
  pop.setAttribute('aria-modal', 'false');
  pop.setAttribute('aria-labelledby', 'gl-pop-title');
  pop.tabIndex = -1;
  pop.hidden = true;

  const head = document.createElement('div');
  head.className = 'gl-pop-head';
  const title = document.createElement('p');
  title.className = 'gl-pop-title';
  title.id = 'gl-pop-title';
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'gl-pop-close';
  close.setAttribute('aria-label', 'Close definition');
  close.textContent = '×';
  head.append(title, close);

  const short = document.createElement('p');
  short.className = 'gl-pop-short';
  const long = document.createElement('p');
  long.className = 'gl-pop-long';
  long.id = 'gl-pop-long';
  long.hidden = true;

  const foot = document.createElement('p');
  foot.className = 'gl-pop-foot';
  const more = document.createElement('button');
  more.type = 'button';
  more.className = 'gl-pop-more';
  more.setAttribute('aria-expanded', 'false');
  more.setAttribute('aria-controls', 'gl-pop-long');
  more.textContent = 'More';
  const src = document.createElement('a');
  src.className = 'gl-pop-src';
  src.target = '_blank';
  src.rel = 'noopener';
  const all = document.createElement('a');
  all.className = 'gl-pop-all';
  all.textContent = 'Glossary';
  foot.append(more, src, all);

  pop.append(head, short, long, foot);
  popParts = { title, short, long, more, src, all, close };

  close.addEventListener('click', () => closePopover(true));
  more.addEventListener('click', () => {
    const open = more.getAttribute('aria-expanded') !== 'true';
    more.setAttribute('aria-expanded', String(open));
    more.textContent = open ? 'Less' : 'More';
    long.hidden = !open;
    place();
  });
  pop.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') { ev.stopPropagation(); closePopover(true); }
  });
  pop.addEventListener('pointerenter', () => clearTimeout(hoverTimer));
  pop.addEventListener('pointerleave', (ev) => {
    if (ev.pointerType === 'mouse' && !pinned) scheduleClose();
  });
  pop.addEventListener('focusout', (ev) => {
    const to = ev.relatedTarget;
    if (to && (pop.contains(to) || to === current)) return;
    if (to) closePopover(false);
  });
  return pop;
}

function fill(term) {
  const p = popParts;
  p.title.textContent = term.term;
  p.short.textContent = term.short;
  p.long.textContent = term.long || '';
  p.long.hidden = true;
  p.more.hidden = !term.long;
  p.more.setAttribute('aria-expanded', 'false');
  p.more.textContent = 'More';
  if (term.source && term.source.url) {
    p.src.hidden = false;
    p.src.href = term.source.url;
    p.src.textContent = 'Source ↗';
    p.src.title = term.source.label || '';
  } else {
    p.src.hidden = true;
  }
  p.all.href = resolve('pages/glossary.html') + '#' + encodeURIComponent(term.id);
  p.all.textContent = 'Glossary';
  p.all.setAttribute('aria-label', `${term.term} in the glossary`);
}

function place() {
  if (!pop || pop.hidden || !current) return;
  const vw = document.documentElement.clientWidth || window.innerWidth;
  const vh = document.documentElement.clientHeight || window.innerHeight;
  const margin = 8;
  const r = current.getBoundingClientRect();
  pop.style.maxWidth = `${Math.max(160, Math.min(352, vw - 2 * margin))}px`;
  const w = pop.offsetWidth;
  const h = pop.offsetHeight;
  let left = Math.min(Math.max(margin, r.left), Math.max(margin, vw - w - margin));
  let top = r.bottom + 6;
  if (top + h > vh - margin && r.top - h - 6 >= margin) top = r.top - h - 6;
  pop.style.left = `${Math.round(left)}px`;
  pop.style.top = `${Math.round(top)}px`;
}

function openPopover(el, { pin = false, focus = false } = {}) {
  const term = byId.get(el.dataset.gl);
  if (!term) return;
  ensurePopover();
  clearTimeout(hoverTimer);
  const same = current === el && !pop.hidden;
  if (current && current !== el) current.setAttribute('aria-expanded', 'false');
  current = el;
  pinned = pin || (same && pinned);
  fill(term);
  // Insert right after the term so keyboard users Tab straight into it.
  if (el.nextSibling !== pop) el.after(pop);
  pop.hidden = false;
  el.setAttribute('aria-expanded', 'true');
  place();
  if (focus) pop.focus({ preventScroll: true });
}

function closePopover(returnFocus) {
  clearTimeout(hoverTimer);
  if (!pop || pop.hidden) return;
  const el = current;
  pop.hidden = true;
  pinned = false;
  if (el) {
    el.setAttribute('aria-expanded', 'false');
    if (returnFocus) el.focus({ preventScroll: true });
  }
  current = null;
}

function scheduleClose() {
  clearTimeout(hoverTimer);
  hoverTimer = setTimeout(() => { if (!pinned) closePopover(false); }, HOVER_CLOSE);
}

let globalsBound = false;
function bindGlobals() {
  if (globalsBound) return;
  globalsBound = true;
  const termOf = (t) => (t instanceof Element ? t.closest('.gl-term') : null);

  // Capture phase: a tap on a term opens its definition and does not also trigger
  // click handlers of the card or row around it.
  document.addEventListener('click', (ev) => {
    const el = termOf(ev.target);
    if (el) {
      ev.preventDefault();
      ev.stopPropagation();
      if (current === el && pinned) closePopover(false);
      else openPopover(el, { pin: true });
      return;
    }
    if (pop && !pop.hidden && !pop.contains(ev.target)) closePopover(false);
  }, true);
  document.addEventListener('keydown', (ev) => {
    const el = termOf(ev.target);
    if (el && (ev.key === 'Enter' || ev.key === ' ')) {
      ev.preventDefault();
      ev.stopPropagation();
      if (current === el && pinned) closePopover(true);
      else openPopover(el, { pin: true, focus: true });
    } else if (ev.key === 'Escape' && pop && !pop.hidden) {
      closePopover(pop.contains(document.activeElement) || document.activeElement === current);
    }
  }, true);
  document.addEventListener('pointerover', (ev) => {
    if (ev.pointerType !== 'mouse') return;
    const el = termOf(ev.target);
    if (!el || (current === el && !pop.hidden)) return;
    if (pinned) return;
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => openPopover(el), HOVER_OPEN);
  });
  document.addEventListener('pointerout', (ev) => {
    if (ev.pointerType !== 'mouse') return;
    const el = termOf(ev.target);
    if (!el || (ev.relatedTarget && el.contains(ev.relatedTarget))) return;
    if (pinned) return;
    if (current === el) scheduleClose(); else clearTimeout(hoverTimer);
  });
  document.addEventListener('focusin', (ev) => {
    const el = termOf(ev.target);
    if (!el || current === el) return;
    let keyboard = true;
    try { keyboard = el.matches(':focus-visible'); } catch { /* old browsers */ }
    if (keyboard) openPopover(el);
  });
  document.addEventListener('focusout', (ev) => {
    const el = termOf(ev.target);
    if (!el || el !== current || pinned) return;
    const to = ev.relatedTarget;
    if (to && pop && pop.contains(to)) return;
    closePopover(false);
  });
  const reflow = () => { if (pop && !pop.hidden) requestAnimationFrame(place); };
  window.addEventListener('scroll', reflow, { passive: true, capture: true });
  window.addEventListener('resize', reflow, { passive: true });
}

/* ---------------------------------------------------------------- annotate -- */

function makeTerm(text, term) {
  const el = document.createElement('span');
  el.className = 'gl-term';
  el.dataset.gl = term.id;
  el.tabIndex = 0;
  el.setAttribute('role', 'button');
  el.setAttribute('aria-expanded', 'false');
  el.setAttribute('aria-controls', 'gl-pop');
  el.setAttribute('aria-haspopup', 'dialog');
  el.textContent = text;
  return el;
}

/** Annotate the first unseen occurrence of each term in the text nodes under `node`. */
function annotate(node, matcher, seen) {
  if (!node || !node.isConnected) return 0;
  const skipCache = new Map();
  const skipped = (el) => {
    if (!el) return true;
    let v = skipCache.get(el);
    if (v === undefined) { v = !!el.closest(SKIP); skipCache.set(el, v); }
    return v;
  };
  if (node.nodeType === 1 && skipped(node)) return 0;
  if (node.nodeType === 3 && skipped(node.parentElement)) return 0;

  const texts = [];
  if (node.nodeType === 3) texts.push(node);
  else {
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.nodeValue.trim().length > 1 && !skipped(n.parentElement)
        ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT)
    });
    for (let n = walker.nextNode(); n; n = walker.nextNode()) texts.push(n);
  }

  let added = 0;
  const { re, lookup } = matcher;
  for (const tn of texts) {
    const s = tn.nodeValue;
    re.lastIndex = 0;
    let m, last = 0, frag = null;
    while ((m = re.exec(s))) {
      const term = lookup(m[0]);
      if (!term || seen.has(term.id)) continue;
      seen.add(term.id);
      frag ??= document.createDocumentFragment();
      if (m.index > last) frag.append(s.slice(last, m.index));
      frag.append(makeTerm(m[0], term));
      last = m.index + m[0].length;
      added++;
    }
    if (frag) {
      if (last < s.length) frag.append(s.slice(last));
      tn.replaceWith(frag);
    }
  }
  return added;
}

/**
 * Start the glossary on this page.
 * @param {{root?: Element, url?: string}} [opts]
 * @returns {Promise<{scan: () => number, disconnect: () => void, count: () => number} | null>}
 */
export async function initGlossary({ root, url } = {}) {
  root = root || document.querySelector('main') || document.body;
  if (!root || root.closest('[data-no-glossary]')) return null;
  if (root.__glossary) return root.__glossary;

  let data;
  try { data = await loadGlossary(url || resolve('data/reference/glossary.json')); }
  catch (err) { console.warn('Glossary not loaded:', err); return null; }
  const terms = data.terms || [];
  for (const t of terms) byId.set(t.id, t);
  const matcher = buildMatcher(terms);
  if (!matcher) return null;

  bindGlobals();

  // Terms already marked in visible content. A mark inside hidden content (a filtered-out
  // card, a closed <details>) does not count, so the visible occurrence gets one too.
  const seenNow = () => new Set([...root.querySelectorAll('.gl-term[data-gl]')]
    .filter(el => !el.closest(HIDDEN)).map(el => el.dataset.gl));
  let observer = null;
  const pending = new Set();
  let timer = 0;

  const run = (nodes) => {
    observer && observer.disconnect();
    const seen = seenNow();
    let n = 0;
    try {
      for (const node of nodes) if (node.isConnected && root.contains(node)) n += annotate(node, matcher, seen);
    } finally {
      observer && observer.observe(root, OBS);
    }
    return n;
  };

  const flush = () => {
    timer = 0;
    // Drop nodes contained in other pending nodes; scanning the outer one covers them.
    const nodes = [...pending].filter(n => n.isConnected);
    pending.clear();
    const outer = nodes.filter(n => !nodes.some(o => o !== n && o.contains(n)));
    if (outer.length) run(outer);
  };

  const OBS = { childList: true, subtree: true, attributes: true, attributeFilter: ['open', 'hidden'] };
  observer = new MutationObserver((records) => {
    for (const r of records) {
      // Showing or hiding content changes which occurrence is "first visible": rescan all.
      if (r.type === 'attributes') { pending.add(root); continue; }
      for (const n of r.addedNodes) {
        if (n.nodeType === 1 && (n.classList.contains('gl-pop') || n.classList.contains('gl-term'))) continue;
        if (n.nodeType === 1 || n.nodeType === 3) pending.add(n);
      }
    }
    if (pending.size && !timer) timer = setTimeout(flush, SCAN_DELAY);
  });

  run([root]);
  observer.observe(root, OBS);

  const api = {
    scan: () => run([root]),
    flush: () => { clearTimeout(timer); flush(); },
    count: () => root.querySelectorAll('.gl-term').length,
    disconnect: () => { observer.disconnect(); clearTimeout(timer); delete root.__glossary; }
  };
  root.__glossary = api;
  return api;
}
