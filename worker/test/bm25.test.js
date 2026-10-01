import test from 'node:test';
import assert from 'node:assert/strict';
import { buildIndex, fold, search, stem, tokenize } from '../src/bm25.js';
import { INDEX } from './fixtures.js';

test('fold removes accents and lower-cases', () => {
  assert.equal(fold('Österreich Ça Straße Ærø'), 'osterreich ca strasse aero');
});

test('stem unifies apprentice / apprentices / apprenticeship', () => {
  assert.equal(stem('apprentice'), stem('apprentices'));
  assert.equal(stem('apprenticeship'), stem('apprentice'));
  assert.equal(stem('qualifications'), stem('qualification'));
  assert.equal(stem('2025'), '2025');
});

test('tokenize drops stop words, maps multilingual terms, keeps ids and numbers', () => {
  const t = tokenize('Wie viele Lehrlinge gibt es in Österreich?');
  assert.ok(t.includes(stem('apprentices')), t.join(' '));
  assert.ok(t.includes('austria'));
  assert.ok(!t.includes('wie'));
  const ids = tokenize('eurostat-tps00215 EQF 4');
  assert.ok(ids.includes('eurostat-tps00215'));
  assert.ok(ids.includes('4'));
});

test('BM25 ranks the most specific chunk first', () => {
  const idx = buildIndex(INDEX.chunks);
  const r = search(idx, 'employment rate recent VET graduates target 82%');
  assert.equal(r[0].doc.id, 'indicator:eurostat-edat_lfse_24-vet');
  const g = search(idx, 'apprentissage France');
  assert.equal(g[0].doc.id, 'country:FR');
  const d = search(idx, 'Deutschland Lehre EQF');
  assert.ok(['country:DE', 'nqf:germany'].includes(d[0].doc.id), d.map(x => x.doc.id).join());
});

test('search respects k, filters and returns nothing for unknown words', () => {
  const idx = buildIndex(INDEX.chunks);
  assert.equal(search(idx, 'apprenticeship', { k: 2 }).length, 2);
  const only = search(idx, 'apprenticeship wage', { filter: d => d.kind === 'scheme' });
  assert.deepEqual(only.map(x => x.doc.id), ['scheme:it-type1']);
  assert.deepEqual(search(idx, 'zzzqqq'), []);
});

test('search is deterministic', () => {
  const idx = buildIndex(INDEX.chunks);
  const a = search(idx, 'apprenticeship pay').map(x => x.doc.id);
  const b = search(idx, 'apprenticeship pay').map(x => x.doc.id);
  assert.deepEqual(a, b);
});
