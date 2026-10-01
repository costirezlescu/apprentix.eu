import test, { beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { handle, MAX_ROUNDS, OPENROUTER_URL, SYSTEM_PROMPT } from '../src/index.js';
import { clearCaches } from '../src/tools.js';
import { ENV, memoryKV, siteFetch } from './fixtures.js';

const ORIGIN = 'https://apprentix.eu';
const ask = (content) => new Request('https://ask.example/ask', {
  method: 'POST',
  headers: { Origin: ORIGIN, 'Content-Type': 'application/json', 'CF-Connecting-IP': '9.9.9.9' },
  body: JSON.stringify({ messages: [{ role: 'user', content }] }),
});

const completion = (message, usage = { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120 }) =>
  new Response(JSON.stringify({ model: 'x-ai/grok-4.3', choices: [{ message }], usage }), { status: 200, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => clearCaches());

test('full loop: one tool call, then an answer with sources and usage', async () => {
  const sent = [];
  const upstream = async (url, init) => {
    assert.equal(url, OPENROUTER_URL);
    assert.equal(init.headers.Authorization, 'Bearer test-key');
    assert.equal(init.headers['HTTP-Referer'], 'https://apprentix.eu');
    assert.equal(init.headers['X-Title'], 'Apprentix');
    const body = JSON.parse(init.body);
    sent.push(body);
    if (sent.length === 1) {
      return completion({
        role: 'assistant', content: null,
        tool_calls: [{ id: 'call_1', type: 'function', function: { name: 'search_site', arguments: JSON.stringify({ query: 'employment rate recent VET graduates' }) } }],
      });
    }
    return completion({
      role: 'assistant',
      content: 'In 2025, 80.1% of recent VET graduates in the EU-27 were employed (Eurostat), below the 82% target. See [Employment rate of recent VET graduates](https://apprentix.eu/pages/indicators/eurostat-edat_lfse_24-vet.html).',
    }, { prompt_tokens: 400, completion_tokens: 60, total_tokens: 460, cost: 0.001 });
  };
  const kv = memoryKV();
  const env = { ...ENV, BUDGET: kv };
  const waits = [];
  const res = await handle(ask('Which countries are furthest from the 82% target?'), env, { waitUntil: p => waits.push(p) }, { fetchImpl: siteFetch(upstream) });
  await Promise.all(waits);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Access-Control-Allow-Origin'), ORIGIN);
  const out = await res.json();
  assert.match(out.answer, /80\.1%/);
  assert.deepEqual(out.sources, [{ title: 'Employment rate of recent VET graduates', url: 'https://apprentix.eu/pages/indicators/eurostat-edat_lfse_24-vet.html' }]);
  assert.equal(out.model, 'x-ai/grok-4.3');
  assert.equal(out.usage.total_tokens, 580);
  assert.equal(out.usage.tool_calls, 1);
  assert.equal(out.usage.cost, 0.001);

  // First request: system prompt, the question, tools offered, low temperature, capped tokens.
  assert.equal(sent[0].model, 'x-ai/grok-4.3');
  assert.equal(sent[0].messages[0].content, SYSTEM_PROMPT);
  assert.equal(sent[0].tools.length, 5);
  assert.ok(sent[0].temperature <= 0.3);
  assert.equal(sent[0].max_tokens, 1200);
  // Second request carries the tool result back.
  const toolMsg = sent[1].messages.find(m => m.role === 'tool');
  assert.equal(toolMsg.tool_call_id, 'call_1');
  assert.match(toolMsg.content, /eurostat-edat_lfse_24-vet/);

  const day = new Date().toISOString().slice(0, 10);
  assert.deepEqual(JSON.parse(kv.m.get(`budget:${day}`)), { requests: 1, tokens: 580 });
});

test('sources fall back to pages the tools returned when the answer cites none', async () => {
  let n = 0;
  const upstream = async () => (++n === 1
    ? completion({ role: 'assistant', content: '', tool_calls: [{ id: 'a', type: 'function', function: { name: 'get_country', arguments: '{"code":"FR"}' } }] })
    : completion({ role: 'assistant', content: 'France has an apprenticeship contract.' }));
  const res = await handle(ask('France?'), ENV, {}, { fetchImpl: siteFetch(upstream) });
  const out = await res.json();
  assert.equal(out.sources[0].url, 'https://apprentix.eu/pages/countries/fr.html');
});

test('a model that keeps calling tools is forced to answer after MAX_ROUNDS', async () => {
  const bodies = [];
  const upstream = async (url, init) => {
    const body = JSON.parse(init.body);
    bodies.push(body);
    if (body.tools) {
      return completion({ role: 'assistant', content: '', tool_calls: [{ id: `c${bodies.length}`, type: 'function', function: { name: 'list_datasets', arguments: '{}' } }] });
    }
    return completion({ role: 'assistant', content: 'The data does not cover this.' });
  };
  const res = await handle(ask('loop'), ENV, {}, { fetchImpl: siteFetch(upstream) });
  const out = await res.json();
  assert.equal(bodies.length, MAX_ROUNDS + 1);
  assert.equal(bodies.at(-1).tools, undefined);
  assert.equal(out.answer, 'The data does not cover this.');
});

test('upstream 429 -> friendly 429; 5xx -> friendly 503; nothing leaks', async () => {
  const r429 = await handle(ask('q'), ENV, {}, { fetchImpl: siteFetch(async () => new Response('{"error":"rate"}', { status: 429 })) });
  assert.equal(r429.status, 429);
  assert.match((await r429.json()).error, /busy/);
  const r500 = await handle(ask('q'), ENV, {}, { fetchImpl: siteFetch(async () => new Response('boom secret', { status: 502 })) });
  assert.equal(r500.status, 503);
  const body = await r500.json();
  assert.match(body.error, /unavailable/);
  assert.ok(!JSON.stringify(body).includes('secret'));
  const net = await handle(ask('q'), ENV, {}, { fetchImpl: siteFetch(async () => { throw new TypeError('fetch failed'); }) });
  assert.equal(net.status, 503);
});
