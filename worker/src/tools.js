/* Tools the model can call. Each reads the site's own static JSON (SITE_BASE), never
   anything else, and returns compact JSON. Data is cached per isolate (in memory, with a
   TTL) and at Cloudflare's edge (fetch cf.cacheTtl). */

import { buildIndex, fold, search, stem, tokenize } from './bm25.js';

const TTL_MS = 60 * 60 * 1000;          // in-memory cache lifetime
const MAX_CACHED = 8;                   // JSON documents kept per isolate
const MAX_OBS = 300;                    // observations returned by get_indicator
const MAX_LONG = 400;                   // characters kept of long record fields
const HIT_TEXT = 1800;                  // characters of chunk text per search hit
const ID_RE = /^[a-z0-9][a-z0-9_.-]{0,80}$/i;

const memory = new Map();               // url -> {at, value: Promise}
let indexCache = null;                  // {at, base, data, bm25}

export function clearCaches() {
  memory.clear();
  indexCache = null;
}

export async function getJSON(env, path, fetchImpl = fetch) {
  const url = `${(env.SITE_BASE || 'https://apprentix.eu').replace(/\/$/, '')}/${path}`;
  const hit = memory.get(url);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.value;
  const value = (async () => {
    const r = await fetchImpl(url, { cf: { cacheTtl: 3600, cacheEverything: true } });
    if (!r.ok) {
      const e = new Error(`HTTP ${r.status} for ${path}`);
      e.status = r.status;
      throw e;
    }
    return r.json();
  })();
  memory.set(url, { at: Date.now(), value });
  value.catch(() => memory.delete(url));
  while (memory.size > MAX_CACHED) memory.delete(memory.keys().next().value);
  return value;
}

export async function loadIndex(env, fetchImpl = fetch) {
  const base = env.SITE_BASE;
  if (indexCache && indexCache.base === base && Date.now() - indexCache.at < TTL_MS) return indexCache;
  const data = await getJSON(env, 'data/ai/search-index.json', fetchImpl);
  indexCache = { at: Date.now(), base, data, bm25: buildIndex(data.chunks) };
  return indexCache;
}

const clip = (s, n) => {
  s = String(s ?? '');
  return s.length <= n ? s : s.slice(0, n - 1) + '…';
};

const norm = (v) => fold(v).trim();

/** Collects every page the model was shown, so the answer can list its sources. */
export class SourceLog {
  constructor() { this.map = new Map(); }
  add(url, title) {
    if (url && !this.map.has(url)) this.map.set(url, title || url);
  }
  list() { return [...this.map].map(([url, title]) => ({ title, url })); }
}

/* Overview content first, then records; and content about a country the question names. */
const KIND_WEIGHT = {
  country: 1.35, indicator: 1.3, insight: 1.25, guide: 1.1, scheme: 1.15, nqf: 1.1, dataset: 1.0,
  'qualifications-summary': 1.0, financing: 1.0, recognition: 1.0, policy: 0.9, 'policy-other': 0.6,
};

function countryNames(idx) {
  if (!idx.countryNames) {
    idx.countryNames = idx.data.chunks.filter(c => c.kind === 'country')
      .map(c => ({ cc: c.country_code, toks: tokenize(c.title.split(' — ')[0]) }));
  }
  return idx.countryNames;
}

export function boostFor(query, idx) {
  const q = new Set(tokenize(query));
  const named = new Set(countryNames(idx).filter(c => c.toks.length && c.toks.every(t => q.has(t))).map(c => c.cc));
  return (doc) => (KIND_WEIGHT[doc.kind] ?? 1) * (named.size && named.has(doc.country_code) ? 1.5 : 1);
}

/* ----------------------------------------------------------- tools -- */

export async function searchSite(env, args, ctx) {
  const query = String(args.query || '').slice(0, 300);
  if (!query.trim()) return { error: 'query is required' };
  const k = Math.min(8, Math.max(1, Number(args.k) || 5));
  const { bm25 } = await loadIndex(env, ctx.fetch);
  const kind = args.kind ? String(args.kind) : null;
  const cc = args.country_code ? String(args.country_code).toUpperCase() : null;
  const filter = (kind || cc) ? (d => (!kind || d.kind === kind) && (!cc || d.country_code === cc)) : undefined;
  const hits = search(bm25, query, { k, filter, boost: boostFor(query, await loadIndex(env, ctx.fetch)) });
  for (const h of hits) ctx.sources.add(h.doc.url, h.doc.title);
  return {
    query,
    results: hits.map(h => ({
      id: h.doc.id, title: h.doc.title, url: h.doc.url, kind: h.doc.kind,
      ...(h.doc.country_code ? { country_code: h.doc.country_code } : {}),
      score: Math.round(h.score * 100) / 100,
      text: clip(h.doc.text, HIT_TEXT),
    })),
    ...(hits.length ? {} : { note: 'No matching content. Try other words, or list_datasets.' }),
  };
}

export async function getCountry(env, args, ctx) {
  const q = String(args.code || '').trim();
  if (!q) return { error: 'code is required' };
  const { data } = await loadIndex(env, ctx.fetch);
  const countries = data.chunks.filter(c => c.kind === 'country');
  const wanted = norm(q);
  const main = countries.find(c => norm(c.country_code) === wanted)
    || countries.find(c => norm(c.title.split(' — ')[0]) === wanted)
    || countries.find(c => wanted.length > 3 && norm(c.title).startsWith(wanted));
  if (!main) {
    return { error: `No country page for '${q}'.`, available: countries.map(c => c.country_code).join(', ') };
  }
  const cc = main.country_code;
  ctx.sources.add(main.url, main.title);
  const related = data.chunks.filter(c => c.country_code === cc && c.id !== main.id);
  const nqf = related.filter(c => c.kind === 'nqf');
  for (const c of nqf) ctx.sources.add(c.url, c.title);
  return {
    country: { id: main.id, title: main.title, url: main.url, text: main.text },
    nqf: nqf.map(c => ({ title: c.title, url: c.url, text: clip(c.text, 2500) })),
    related: related.filter(c => c.kind !== 'nqf').slice(0, 60).map(c => ({ id: c.id, kind: c.kind, title: c.title, url: c.url })),
  };
}

export async function getIndicator(env, args, ctx) {
  const id = String(args.id || '').trim();
  if (!ID_RE.test(id)) return { error: 'invalid indicator id' };
  const list = (await getJSON(env, 'data/published/indicators/index.json', ctx.fetch)).indicators;
  if (!list.some(i => i.id === id)) {
    return { error: `Unknown indicator '${id}'. Use list_datasets or search_site to find ids.` };
  }
  const ind = await getJSON(env, `data/published/indicators/${id}.json`, ctx.fetch);
  const dims = ind.dims || [];
  const want = {};
  for (const d of dims) {
    const v = args.dims && args.dims[d.key] != null ? String(args.dims[d.key]) : d.default;
    want[d.key] = v;
  }
  const geos = Array.isArray(args.geos) && args.geos.length
    ? new Set(args.geos.map(g => String(g).toUpperCase().replace(/^EU$/, 'EU27').replace(/^GR$/, 'EL').replace(/^GB$/, 'UK')))
    : null;
  const from = args.from_year ? String(args.from_year) : null;
  const to = args.to_year ? String(args.to_year) : null;
  let obs = (ind.series || []).filter(o =>
    dims.every(d => ((o.dims || {})[d.key] ?? d.default) === want[d.key])
    && (!geos || geos.has(o.geo))
    && (!from || o.time.slice(0, 4) >= from)
    && (!to || o.time.slice(0, 4) <= to));
  obs.sort((a, b) => a.geo.localeCompare(b.geo) || a.time.localeCompare(b.time));
  let note;
  if (obs.length > MAX_OBS) {
    if (!geos) {
      // Too much: latest value per geography (ask again with geos for full series).
      const latest = new Map();
      for (const o of obs) latest.set(o.geo, o);
      obs = [...latest.values()];
      note = 'Too many observations: showing the latest value per geography. Pass geos (and years) for full series.';
    } else {
      obs = obs.slice(-MAX_OBS);
      note = `Truncated to the last ${MAX_OBS} observations.`;
    }
  }
  const page = `${(env.SITE_BASE || 'https://apprentix.eu').replace(/\/$/, '')}/pages/indicators/${encodeURIComponent(id)}.html`;
  ctx.sources.add(page, ind.title);
  const p = ind.provenance || {};
  return {
    id, title: ind.title, unit: ind.unit, page_url: page,
    description: ind.description, comparability: ind.comparability,
    ...(ind.national ? { national: 'National statistic: own definitions, not comparable with other countries.' } : {}),
    ...(ind.target ? { target: ind.target } : {}),
    breakdown_used: want,
    dims: dims.map(d => ({ key: d.key, label: d.label, default: d.default, values: Object.fromEntries(Object.entries(d.values || {}).slice(0, 40)) })),
    ...(ind.flags ? { flags: ind.flags } : {}),
    provenance: {
      publisher: p.publisher, dataset_code: p.dataset_code, source_url: p.source_url,
      licence: p.licence, citation: p.citation, retrieved_at: p.retrieved_at,
    },
    observations: obs.map(o => (o.flag ? [o.geo, o.time, o.value, o.flag] : [o.geo, o.time, o.value])),
    observation_format: '[geo, time, value, flag?]',
    ...(note ? { note } : {}),
  };
}

async function datasetEntry(env, id, ctx) {
  const manifest = await getJSON(env, 'data/datasets.json', ctx.fetch);
  return { manifest, entry: manifest.datasets.find(d => d.id === id) };
}

function matchValue(recValue, wanted) {
  const vals = Array.isArray(recValue) ? recValue : [recValue];
  const ws = (Array.isArray(wanted) ? wanted : [wanted]).map(norm).filter(Boolean);
  if (!ws.length) return true;
  return vals.some(v => {
    const nv = norm(v);
    return nv && ws.some(w => nv === w || nv.includes(w));
  });
}

export async function queryRecords(env, args, ctx) {
  const id = String(args.dataset_id || '');
  if (!ID_RE.test(id)) return { error: 'invalid dataset_id' };
  const { manifest, entry } = await datasetEntry(env, id, ctx);
  if (!entry) return { error: `Unknown dataset '${id}'.`, datasets: manifest.datasets.map(d => d.id) };
  const meta = await getJSON(env, `${entry.path}/meta.json`, ctx.fetch);
  const fields = new Map(meta.fields.map(f => [f.key, f]));
  const filters = (args.filters && typeof args.filters === 'object' && !Array.isArray(args.filters)) ? { ...args.filters } : {};
  for (const k of Object.keys(filters)) {
    if (!fields.has(k)) {
      return { error: `Unknown field '${k}' in ${id}.`, fields: [...fields.keys()] };
    }
  }
  const limit = Math.min(20, Math.max(1, Number(args.limit) || 10));

  let records;
  const base = (env.SITE_BASE || 'https://apprentix.eu').replace(/\/$/, '');
  if (id === 'vet-qualifications') {
    // 25k records: load one country's shard only.
    const { data } = await loadIndex(env, ctx.fetch);
    const avail = (data.shards && data.shards['vet-qualifications']) || [];
    let cc = filters.country_code ? String(filters.country_code).toUpperCase() : null;
    if (!cc && filters.country) {
      const c = data.chunks.find(x => x.kind === 'qualifications-summary' && matchValue(x.title.replace(/^VET qualifications in /, '').replace(/ \(Europass\)$/, ''), filters.country));
      cc = c ? c.country_code : null;
    }
    if (!cc || !avail.includes(cc)) {
      return { error: 'For vet-qualifications, filter by country_code first (one of the countries in the register).', available_country_codes: avail };
    }
    delete filters.country_code;
    delete filters.country;
    records = await getJSON(env, `data/ai/records/vet-qualifications/${cc}.json`, ctx.fetch);
    records = records.map(r => ({
      ...r, country_code: cc, apprenticeship: r.apprenticeship || 'Not stated',
      europass_url: `https://data.europa.eu/snb/data/qualification/${r.id.replace(/^qdr-/, '')}`,
    }));
  } else {
    records = await getJSON(env, `${entry.path}/records.json`, ctx.fetch);
  }

  let hits = records.filter(r => Object.entries(filters).every(([k, v]) => matchValue(r[k], v)));
  if (args.text) {
    const words = fold(String(args.text)).split(/[^\p{L}\p{N}]+/u).filter(w => w.length > 1);
    const searchable = meta.fields.filter(f => f.type !== 'link').map(f => f.key);
    hits = hits.filter(r => {
      const hay = fold(searchable.map(k => Array.isArray(r[k]) ? r[k].join(' ') : (r[k] ?? '')).join(' '));
      // every word must appear, either as typed or as its stem
      return words.every(w => hay.includes(w) || hay.includes(stem(w)));
    });
  }
  const out = {
    dataset_id: id, title: entry.title, matched: hits.length,
    dataset_page: `${base}/pages/datasets/${id}.html`,
    source: { name: meta.source?.name, url: meta.source?.url, licence: meta.source?.licence_id || meta.source?.licence },
  };
  if (args.count_by) {
    const key = String(args.count_by);
    if (!fields.has(key)) return { error: `Unknown count_by field '${key}'.`, fields: [...fields.keys()] };
    const counts = {};
    for (const r of hits) for (const v of (Array.isArray(r[key]) ? r[key] : [r[key] ?? '(none)'])) counts[v] = (counts[v] || 0) + 1;
    out.counts = Object.fromEntries(Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 60));
  }
  out.records = hits.slice(0, limit).map(r => {
    const o = {};
    for (const [k, v] of Object.entries(r)) {
      const f = fields.get(k);
      if (!f || (f.type === 'hidden' && k !== 'id' && k !== 'country_code')) continue;
      o[k] = f.type === 'longtext' ? clip(Array.isArray(v) ? v.join('; ') : v, MAX_LONG) : v;
    }
    o.apprentix_url = `${base}/pages/explore.html?dataset=${encodeURIComponent(id)}&open=${encodeURIComponent(r.id)}`;
    return o;
  });
  ctx.sources.add(out.dataset_page, entry.title);
  for (const r of out.records.slice(0, 5)) ctx.sources.add(r.apprentix_url, String(r[meta.display?.title] || r.id));
  if (hits.length > limit) out.note = `Showing ${limit} of ${hits.length}. Narrow the filters or use count_by.`;
  return out;
}

export async function listDatasets(env, args, ctx) {
  const manifest = await getJSON(env, 'data/datasets.json', ctx.fetch);
  const idx = await getJSON(env, 'data/published/indicators/index.json', ctx.fetch);
  return {
    datasets: manifest.datasets.map(d => ({ id: d.id, title: d.title, tagline: d.tagline, records: d.records, coverage: d.coverage })),
    indicators: idx.indicators.map(i => ({
      id: i.id, title: i.title, topic: i.topic, unit: i.unit,
      ...(i.national ? { national: true } : {}),
      years: (i.coverage?.time || []).join('–'),
    })),
    note: 'Use get_indicator for values, query_records for record datasets, search_site for text.',
  };
}

/* ----------------------------------------------------------- schema -- */

export const TOOL_SPECS = [
  {
    type: 'function',
    function: {
      name: 'search_site',
      description: 'Full-text (BM25) search over everything Apprentix publishes: country profiles, indicators (with latest values), datasets, apprenticeship schemes (with Cedefop coded answers), financing instruments, recognition arrangements, VET policies, NQF levels, CoVE projects, insights. Use English keywords for best results.',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Keywords, e.g. "apprentice wage workplace share 50%"' },
          k: { type: 'integer', minimum: 1, maximum: 8, description: 'Number of results (default 5)' },
          kind: { type: 'string', enum: ['country', 'indicator', 'dataset', 'scheme', 'financing', 'recognition', 'vet-system', 'policy', 'policy-other', 'cove', 'nqf', 'erasmus-summary', 'catalogue-summary', 'qualifications-summary', 'insight', 'guide'], description: 'Optional: restrict to one kind of content' },
          country_code: { type: 'string', description: 'Optional: restrict to a country (Eurostat code, e.g. DE, FR, EL for Greece)' },
        },
        required: ['query'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_indicator',
      description: 'Values of one statistical indicator with its definition, unit, comparability notes and provenance (publisher, licence, citation). Defaults to the default breakdown (usually the total).',
      parameters: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'Indicator id, e.g. eurostat-edat_lfse_24-vet' },
          geos: { type: 'array', items: { type: 'string' }, description: 'Country codes (EU27 for the EU). Omit for all.' },
          from_year: { type: 'string' },
          to_year: { type: 'string' },
          dims: { type: 'object', description: 'Optional breakdown values, e.g. {"sex": "F"}', additionalProperties: { type: 'string' } },
        },
        required: ['id'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_country',
      description: "A country's profile: schemes, key figures against the EU-27, national statistics, policies, financing, qualification levels, Erasmus+ and CoVE counts, VET system link.",
      parameters: {
        type: 'object',
        properties: { code: { type: 'string', description: 'Country code (e.g. AT) or English name' } },
        required: ['code'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'query_records',
      description: 'Filter a record dataset (e.g. apprenticeship-schemes, vet-policy-timeline, financing-instruments, nqf-qualification-levels, erasmus-vet-organisations, cove-projects, recognition-vet-qualifications, vet-systems, data-catalogue, vet-qualifications). Filters match field values (case-insensitive, partial). vet-qualifications needs a country_code filter. Use count_by to tally a field.',
      parameters: {
        type: 'object',
        properties: {
          dataset_id: { type: 'string' },
          filters: { type: 'object', description: 'field -> value (or list of values), e.g. {"country": "Germany", "concerns_apprenticeship": "Yes"}' },
          text: { type: 'string', description: 'Optional words that must all appear in the record' },
          count_by: { type: 'string', description: 'Optional field to count matching records by' },
          limit: { type: 'integer', minimum: 1, maximum: 20 },
        },
        required: ['dataset_id'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'list_datasets',
      description: 'List every record dataset and every indicator (id, title, topic, unit, years).',
      parameters: { type: 'object', properties: {} },
    },
  },
];

export const TOOLS = {
  search_site: searchSite,
  get_indicator: getIndicator,
  get_country: getCountry,
  query_records: queryRecords,
  list_datasets: listDatasets,
};

export async function runTool(env, name, rawArgs, ctx) {
  const fn = TOOLS[name];
  if (!fn) return { error: `Unknown tool '${name}'` };
  let args = {};
  try {
    args = typeof rawArgs === 'string' ? (rawArgs.trim() ? JSON.parse(rawArgs) : {}) : (rawArgs || {});
  } catch {
    return { error: 'Arguments were not valid JSON' };
  }
  try {
    return await fn(env, args, ctx);
  } catch (e) {
    return { error: `Tool failed: ${String(e.message || e).slice(0, 200)}` };
  }
}
