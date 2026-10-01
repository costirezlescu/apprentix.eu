/* Small fixture of the site's JSON and a fake fetch that serves it. */

export const SITE = 'https://apprentix.test';

export const INDEX = {
  updated: '2026-10-01',
  count: 6,
  shards: { 'vet-qualifications': ['DE'] },
  chunks: [
    { id: 'country:DE', url: 'https://apprentix.eu/pages/countries/de.html', title: 'Germany — apprenticeships and VET', kind: 'country', country_code: 'DE',
      text: 'Country profile: Germany (DE). Apprenticeship schemes: Dual VET (Duale Berufsausbildung): pay Wage; minimum workplace share 50% or more.' },
    { id: 'country:FR', url: 'https://apprentix.eu/pages/countries/fr.html', title: 'France — apprenticeships and VET', kind: 'country', country_code: 'FR',
      text: 'Country profile: France (FR). Apprenticeship contract: pay Wage. Apprentices under contract 911,425 (2026-07).' },
    { id: 'scheme:it-type1', url: 'https://apprentix.eu/pages/countries/it.html#scheme-it-type1', title: 'Type 1 apprenticeship — Italy', kind: 'scheme', country_code: 'IT',
      text: 'Apprenticeship scheme in Italy. Apprentice pay (Cedefop): Wage. Minimum workplace share: Below 50%.' },
    { id: 'indicator:eurostat-edat_lfse_24-vet', url: 'https://apprentix.eu/pages/indicators/eurostat-edat_lfse_24-vet.html', title: 'Employment rate of recent VET graduates', kind: 'indicator',
      text: 'Indicator: Employment rate of recent VET graduates. Target: 82% by 2025. Latest value per country: DE 2025: 91.0%; FR 2025: 72.9%; EU27 2025: 80.1%' },
    { id: 'nqf:germany', url: 'https://apprentix.eu/pages/explore.html?dataset=nqf-qualification-levels&f.country=Germany', title: 'NQF qualification levels — Germany', kind: 'nqf', country_code: 'DE',
      text: 'Dual VET (3 and 3.5 years) — NQF 4 — EQF 4 — APPRENTICESHIP/CRAFT' },
    { id: 'guide:about', url: 'https://apprentix.eu/pages/about.html', title: 'About Apprentix', kind: 'guide',
      text: 'Apprentix is an independent project republishing public data on apprenticeship.' },
  ],
};

export const DATASETS = {
  site: { name: 'Apprentix', ask_endpoint: null },
  datasets: [
    { id: 'apprenticeship-schemes', path: 'data/published/apprenticeship-schemes', title: 'Apprenticeship schemes in Europe', tagline: 't', records: 3 },
    { id: 'vet-qualifications', path: 'data/published/vet-qualifications', title: 'National VET qualifications', tagline: 't', records: 3 },
  ],
};

export const SCHEMES_META = {
  id: 'apprenticeship-schemes',
  title: 'Apprenticeship schemes in Europe',
  source: { name: 'Cedefop', url: 'https://www.cedefop.europa.eu/', licence_id: 'Cedefop' },
  display: { title: 'name_en' },
  fields: [
    { key: 'country', type: 'category' },
    { key: 'country_code', type: 'hidden' },
    { key: 'name_en', type: 'title' },
    { key: 'q_compensation', type: 'category' },
    { key: 'q_min_workplace_share', type: 'category' },
    { key: 'overview', type: 'longtext' },
    { key: 'source_url', type: 'link' },
    { key: 'id', type: 'hidden' },
  ],
};

export const SCHEMES = [
  { id: 'de-dual', country: 'Germany', country_code: 'DE', name_en: 'Dual VET', q_compensation: ['Wage'], q_min_workplace_share: '50% or more', overview: 'Company-based training with part-time school. '.repeat(30) },
  { id: 'it-type1', country: 'Italy', country_code: 'IT', name_en: 'Type 1 apprenticeship', q_compensation: ['Wage'], q_min_workplace_share: 'Below 50%', overview: 'Upper secondary.' },
  { id: 'be-fl', country: 'Belgium — Flemish Community', country_code: 'BE', name_en: 'Dual learning', q_compensation: ['Allowance'], q_min_workplace_share: '50% or more', overview: 'Allowance.' },
];

export const VQ_META = {
  id: 'vet-qualifications', title: 'National VET qualifications', source: { name: 'Europass' }, display: { title: 'title' },
  fields: [
    { key: 'country', type: 'category' }, { key: 'eqf_level', type: 'category' }, { key: 'apprenticeship', type: 'category' },
    { key: 'title', type: 'title' }, { key: 'europass_url', type: 'link' }, { key: 'country_code', type: 'hidden' }, { key: 'id', type: 'hidden' },
  ],
};

export const VQ_DE = [
  { id: 'qdr-1', title: 'Watchmaker', eqf_level: 'EQF 4', apprenticeship: 'Apprenticeship / dual' },
  { id: 'qdr-2', title: 'Office manager', eqf_level: 'EQF 4', apprenticeship: 'Apprenticeship / dual' },
  { id: 'qdr-3', title: 'Master craftsman', eqf_level: 'EQF 6' },
];

export const IND_INDEX = {
  indicators: [
    { id: 'eurostat-edat_lfse_24-vet', title: 'Employment rate of recent VET graduates', topic: 'Outcomes', unit: '%', coverage: { time: ['2015', '2025'] } },
  ],
};

export const INDICATOR = {
  id: 'eurostat-edat_lfse_24-vet',
  title: 'Employment rate of recent VET graduates',
  unit: '%',
  description: 'Share of 20-34 year-olds...',
  comparability: 'EU-LFS.',
  dims: [{ key: 'sex', label: 'Sex', default: 'T', values: { T: 'Total', F: 'Females', M: 'Males' } }],
  flags: { d: 'definition differs' },
  target: { value: 82, year: '2025', geo: 'EU27' },
  provenance: { publisher: 'Eurostat', dataset_code: 'edat_lfse_24', source_url: 'https://ec.europa.eu/eurostat', licence: 'CC-BY-4.0', citation: 'Eurostat (edat_lfse_24).' },
  series: [
    { geo: 'DE', time: '2024', value: 90.5, dims: { sex: 'T' } },
    { geo: 'DE', time: '2025', value: 91.0, dims: { sex: 'T' } },
    { geo: 'DE', time: '2025', value: 89.0, dims: { sex: 'F' } },
    { geo: 'FR', time: '2025', value: 72.9, flag: 'd', dims: { sex: 'T' } },
    { geo: 'EU27', time: '2025', value: 80.1, dims: { sex: 'T' } },
  ],
};

export const FILES = {
  'data/ai/search-index.json': INDEX,
  'data/datasets.json': DATASETS,
  'data/published/apprenticeship-schemes/meta.json': SCHEMES_META,
  'data/published/apprenticeship-schemes/records.json': SCHEMES,
  'data/published/vet-qualifications/meta.json': VQ_META,
  'data/ai/records/vet-qualifications/DE.json': VQ_DE,
  'data/published/indicators/index.json': IND_INDEX,
  'data/published/indicators/eurostat-edat_lfse_24-vet.json': INDICATOR,
};

/** fetch() that serves FILES under SITE, records every URL, and delegates anything else. */
export function siteFetch(other) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push(String(url));
    const u = String(url);
    if (u.startsWith(SITE + '/')) {
      const path = u.slice(SITE.length + 1);
      if (path in FILES) return new Response(JSON.stringify(FILES[path]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      return new Response('not found', { status: 404 });
    }
    if (other) return other(u, init);
    throw new Error('unexpected fetch ' + u);
  };
  fn.calls = calls;
  return fn;
}

export const ENV = {
  SITE_BASE: SITE,
  MODEL: 'x-ai/grok-4.3',
  ALLOWED_ORIGINS: 'https://apprentix.eu,http://localhost:8080',
  DAILY_LIMIT: '1000',
  OPENROUTER_API_KEY: 'test-key',
};

/** Minimal KV stand-in. */
export function memoryKV() {
  const m = new Map();
  return {
    m,
    async get(k, type) { const v = m.get(k); return v == null ? null : (type === 'json' ? JSON.parse(v) : v); },
    async put(k, v) { m.set(k, v); },
  };
}
