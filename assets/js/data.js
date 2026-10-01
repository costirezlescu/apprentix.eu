/* Apprentix — data layer.
   Everything uses RELATIVE paths so the site works both at
   apprentix.eu and at username.github.io/apprentix.eu/ */

/** Resolve a repo-relative path (e.g. "data/datasets.json") against the site root. */
export function url(path) {
  const root = document.body.dataset.root || './';
  return new URL(root + path, location.href).href;
}

const cache = new Map();

async function getJSON(path) {
  if (cache.has(path)) return cache.get(path);
  const p = fetch(url(path)).then(r => {
    if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${path}`);
    return r.json();
  });
  cache.set(path, p);
  return p;
}

export const loadManifest = () => getJSON('data/datasets.json');

export async function loadDataset(id) {
  const manifest = await loadManifest();
  const entry = manifest.datasets.find(d => d.id === id);
  if (!entry) throw new Error(`Unknown dataset: ${id}`);
  const [meta, records] = await Promise.all([
    getJSON(`${entry.path}/meta.json`),
    getJSON(`${entry.path}/records.json`)
  ]);
  return { entry, meta, records, site: manifest.site };
}

/* ---------- helpers ---------- */

export const esc = (v) => String(v ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;')
  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/** A field value is always treated as an array, so multi-value fields work. */
export const values = (rec, key) => {
  const v = rec[key];
  if (v == null || v === '') return [];
  return Array.isArray(v) ? v : [v];
};

export const field = (meta, key) => meta.fields.find(f => f.key === key);

export const facets = (meta) => meta.fields.filter(f => f.facet);

/** Distinct values for a facet, in declared order where given, else by frequency. */
export function facetValues(meta, records, key) {
  const f = field(meta, key);
  const counts = new Map();
  for (const r of records) {
    for (const v of values(r, key)) counts.set(v, (counts.get(v) || 0) + 1);
  }
  let keys = [...counts.keys()];
  if (f?.order) {
    const idx = new Map(f.order.map((v, i) => [v, i]));
    keys.sort((a, b) => (idx.get(a) ?? 999) - (idx.get(b) ?? 999) || a.localeCompare(b));
  } else {
    keys.sort((a, b) => counts.get(b) - counts.get(a) || a.localeCompare(b));
  }
  return keys.map(v => ({ value: v, count: counts.get(v) }));
}

/** Free-text haystack for a record (computed once per record). */
const hayCache = new WeakMap();
export function haystack(meta, rec) {
  if (hayCache.has(rec)) return hayCache.get(rec);
  const h = meta.fields
    .filter(f => f.type !== 'hidden' && f.type !== 'link')
    .flatMap(f => values(rec, f.key))
    .join(' ')
    .toLowerCase();
  hayCache.set(rec, h);
  return h;
}

/** Does a record match the active state? Multi-value safe (intersection). */
export function matches(meta, rec, state) {
  for (const [key, chosen] of Object.entries(state.filters)) {
    if (!chosen.size) continue;
    const has = values(rec, key).some(v => chosen.has(v));
    if (!has) return false;
  }
  if (state.q) {
    if (!haystack(meta, rec).includes(state.q)) return false;
  }
  return true;
}
