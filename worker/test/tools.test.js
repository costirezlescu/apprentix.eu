import test, { beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { clearCaches, runTool, SourceLog } from '../src/tools.js';
import { ENV, siteFetch } from './fixtures.js';

let ctx;
beforeEach(() => {
  clearCaches();
  ctx = { sources: new SourceLog(), fetch: siteFetch() };
});

test('search_site returns ranked chunks and logs sources', async () => {
  const r = await runTool(ENV, 'search_site', JSON.stringify({ query: 'recent VET graduates employment', k: 3 }), ctx);
  assert.equal(r.results[0].id, 'indicator:eurostat-edat_lfse_24-vet');
  assert.ok(r.results.length <= 3);
  assert.ok(ctx.sources.list().some(s => s.url.endsWith('eurostat-edat_lfse_24-vet.html')));
});

test('search_site filters by country_code and kind', async () => {
  const r = await runTool(ENV, 'search_site', { query: 'apprenticeship', country_code: 'de' }, ctx);
  assert.ok(r.results.length > 0);
  assert.ok(r.results.every(x => x.country_code === 'DE'));
  const s = await runTool(ENV, 'search_site', { query: 'apprenticeship', kind: 'scheme' }, ctx);
  assert.deepEqual(s.results.map(x => x.kind), ['scheme']);
});

test('the index is fetched once per isolate', async () => {
  await runTool(ENV, 'search_site', { query: 'France' }, ctx);
  await runTool(ENV, 'search_site', { query: 'Germany' }, ctx);
  assert.equal(ctx.fetch.calls.filter(u => u.endsWith('search-index.json')).length, 1);
});

test('get_country accepts a code or a name', async () => {
  const a = await runTool(ENV, 'get_country', { code: 'de' }, ctx);
  assert.equal(a.country.id, 'country:DE');
  assert.equal(a.nqf.length, 1);
  const b = await runTool(ENV, 'get_country', { code: 'France' }, ctx);
  assert.equal(b.country.id, 'country:FR');
  const c = await runTool(ENV, 'get_country', { code: 'Atlantis' }, ctx);
  assert.match(c.error, /No country page/);
});

test('get_indicator uses default dims, filters geos/years, returns provenance', async () => {
  const r = await runTool(ENV, 'get_indicator', { id: 'eurostat-edat_lfse_24-vet', geos: ['DE', 'EU'], from_year: '2025' }, ctx);
  assert.deepEqual(r.observations, [['DE', '2025', 91.0], ['EU27', '2025', 80.1]]);
  assert.equal(r.provenance.publisher, 'Eurostat');
  assert.equal(r.breakdown_used.sex, 'T');
  const f = await runTool(ENV, 'get_indicator', { id: 'eurostat-edat_lfse_24-vet', dims: { sex: 'F' } }, ctx);
  assert.deepEqual(f.observations, [['DE', '2025', 89.0]]);
  const all = await runTool(ENV, 'get_indicator', { id: 'eurostat-edat_lfse_24-vet' }, ctx);
  assert.ok(all.observations.some(o => o[0] === 'FR' && o[3] === 'd'));
});

test('get_indicator rejects unknown or unsafe ids', async () => {
  assert.match((await runTool(ENV, 'get_indicator', { id: '../../secrets' }, ctx)).error, /invalid/);
  assert.match((await runTool(ENV, 'get_indicator', { id: 'nope' }, ctx)).error, /Unknown indicator/);
});

test('query_records filters (multi-value, partial), text, count_by, limit', async () => {
  const r = await runTool(ENV, 'query_records', { dataset_id: 'apprenticeship-schemes', filters: { q_compensation: 'wage', q_min_workplace_share: '50% or more' } }, ctx);
  assert.deepEqual(r.records.map(x => x.id), ['de-dual']);
  assert.ok(r.records[0].overview.length <= 400);
  assert.match(r.records[0].apprentix_url, /open=de-dual/);
  const t = await runTool(ENV, 'query_records', { dataset_id: 'apprenticeship-schemes', text: 'allowance' }, ctx);
  assert.deepEqual(t.records.map(x => x.id), ['be-fl']);
  const c = await runTool(ENV, 'query_records', { dataset_id: 'apprenticeship-schemes', count_by: 'q_compensation', limit: 1 }, ctx);
  assert.deepEqual(c.counts, { Wage: 2, Allowance: 1 });
  assert.equal(c.records.length, 1);
  assert.equal(c.matched, 3);
});

test('query_records validates dataset and fields', async () => {
  assert.match((await runTool(ENV, 'query_records', { dataset_id: 'nope' }, ctx)).error, /Unknown dataset/);
  assert.match((await runTool(ENV, 'query_records', { dataset_id: 'apprenticeship-schemes', filters: { salary: 'x' } }, ctx)).error, /Unknown field/);
});

test('query_records on vet-qualifications needs a country and reads the shard', async () => {
  const no = await runTool(ENV, 'query_records', { dataset_id: 'vet-qualifications' }, ctx);
  assert.deepEqual(no.available_country_codes, ['DE']);
  const r = await runTool(ENV, 'query_records', { dataset_id: 'vet-qualifications', filters: { country_code: 'DE', apprenticeship: 'Apprenticeship' }, count_by: 'eqf_level' }, ctx);
  assert.equal(r.matched, 2);
  assert.ok(r.records[0].europass_url.endsWith('/1'));
  assert.ok(ctx.fetch.calls.some(u => u.endsWith('vet-qualifications/DE.json')));
  assert.ok(!ctx.fetch.calls.some(u => u.endsWith('vet-qualifications/records.json')));
  const ns = await runTool(ENV, 'query_records', { dataset_id: 'vet-qualifications', filters: { country_code: 'DE', apprenticeship: 'Not stated' } }, ctx);
  assert.deepEqual(ns.records.map(x => x.id), ['qdr-3']);
});

test('list_datasets lists datasets and indicators', async () => {
  const r = await runTool(ENV, 'list_datasets', {}, ctx);
  assert.equal(r.datasets.length, 2);
  assert.equal(r.indicators[0].id, 'eurostat-edat_lfse_24-vet');
});

test('runTool reports bad JSON, unknown tools and upstream failures', async () => {
  assert.match((await runTool(ENV, 'search_site', '{bad', ctx)).error, /valid JSON/);
  assert.match((await runTool(ENV, 'rm_rf', {}, ctx)).error, /Unknown tool/);
  const broken = { sources: new SourceLog(), fetch: async () => new Response('x', { status: 500 }) };
  assert.match((await runTool(ENV, 'list_datasets', {}, broken)).error, /Tool failed/);
});
