/* Ask Apprentix — chat UI.
   The conversation lives in memory only (no storage). Questions go to the Worker named in
   data/datasets.json site.ask_endpoint; the model's markdown is rendered with DOM nodes
   (paragraphs, lists, bold, code, http(s) links) — never as HTML. */

import { loadManifest } from './data.js';

const $ = (id) => document.getElementById(id);
const form = $('ask-form');
const input = $('ask-input');
const send = $('ask-send');
const clear = $('ask-clear');
const status = $('ask-status');
const log = $('log');
const starters = [...document.querySelectorAll('#starters .chip')];

const MAX_SENT = 8;          // messages sent per request (the Worker keeps the last 8 too)
const MAX_CHARS = 2000;
const TIMEOUT_MS = 90000;

let endpoint = null;
let busy = false;
const messages = [];         // {role, content} — in memory only

/* ---------------- safe markdown ---------------- */

const INLINE = /\*\*([^*]+?)\*\*|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)|`([^`\n]+)`|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/g;

function link(href, text) {
  let url;
  try { url = new URL(href); } catch { return document.createTextNode(text); }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return document.createTextNode(text);
  const a = document.createElement('a');
  a.href = url.href;
  a.textContent = text;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  return a;
}

function inline(parent, text, depth = 0) {
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) parent.append(text.slice(last, m.index));
    if (m[1] !== undefined) {
      const b = document.createElement('strong');
      if (depth < 2) inline(b, m[1], depth + 1); else b.textContent = m[1];
      parent.append(b);
    } else if (m[2] !== undefined) {
      parent.append(link(m[3], m[2].replace(/\*\*/g, '')));
    } else if (m[4] !== undefined) {
      const c = document.createElement('code');
      c.textContent = m[4];
      parent.append(c);
    } else if (m[5] !== undefined) {
      parent.append(link(m[5], m[5]));
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parent.append(text.slice(last));
}

/** Markdown subset -> DocumentFragment. Everything else stays literal text. */
export function renderMarkdown(md) {
  const frag = document.createDocumentFragment();
  const lines = String(md || '').replace(/\r\n?/g, '\n').split('\n');
  let para = [];
  let list = null;
  const flushPara = () => {
    if (!para.length) return;
    const p = document.createElement('p');
    para.forEach((l, i) => { if (i) p.append(document.createElement('br')); inline(p, l); });
    frag.append(p);
    para = [];
  };
  const flushList = () => { if (list) { frag.append(list.el); list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*(?:[-*•])\s+(.*)$/);
    const num = line.match(/^\s*(\d{1,3})[.)]\s+(.*)$/);
    const heading = line.match(/^\s*#{1,6}\s+(.*)$/);
    if (!line.trim()) { flushPara(); flushList(); continue; }
    if (bullet || num) {
      flushPara();
      const type = bullet ? 'ul' : 'ol';
      if (!list || list.type !== type) { flushList(); list = { type, el: document.createElement(type) }; }
      const li = document.createElement('li');
      inline(li, (bullet || num)[bullet ? 1 : 2]);
      list.el.append(li);
      continue;
    }
    if (heading) {
      flushPara(); flushList();
      const p = document.createElement('p');
      const s = document.createElement('strong');
      inline(s, heading[1]);
      p.append(s);
      frag.append(p);
      continue;
    }
    flushList();
    para.push(line.trim());
  }
  flushPara(); flushList();
  return frag;
}

/* ---------------- UI ---------------- */

function bubble(role) {
  const el = document.createElement('article');
  el.className = `ask-msg ${role}`;
  const who = document.createElement('div');
  who.className = 'ask-who mono';
  who.textContent = role === 'user' ? 'You' : 'Apprentix assistant';
  el.append(who);
  log.append(el);
  return el;
}

function showUser(text) {
  const el = bubble('user');
  const p = document.createElement('p');
  p.textContent = text;
  el.append(p);
}

function showAnswer(data) {
  const el = bubble('assistant');
  const body = document.createElement('div');
  body.className = 'ask-body';
  body.append(renderMarkdown(data.answer));
  el.append(body);
  if (Array.isArray(data.sources) && data.sources.length) {
    const box = document.createElement('div');
    box.className = 'ask-sources';
    const h = document.createElement('div');
    h.className = 'mono';
    h.textContent = 'Sources';
    const ul = document.createElement('ul');
    for (const s of data.sources.slice(0, 10)) {
      if (!s || !s.url) continue;
      const li = document.createElement('li');
      li.append(link(String(s.url), String(s.title || s.url)));
      ul.append(li);
    }
    box.append(h, ul);
    el.append(box);
  }
  const foot = document.createElement('p');
  foot.className = 'ask-foot';
  foot.textContent = `Generated by ${data.model || 'an AI model'} from Apprentix data. Check the sources before relying on it.`;
  el.append(foot);
}

function showError(text) {
  const el = bubble('assistant');
  el.classList.add('error');
  const p = document.createElement('p');
  p.textContent = text;
  el.append(p);
}

function thinking(on) {
  let t = log.querySelector('.ask-thinking');
  if (on && !t) {
    t = document.createElement('p');
    t.className = 'ask-thinking';
    t.textContent = 'Looking it up in the data…';
    log.append(t);
  } else if (!on && t) {
    t.remove();
  }
}

function setBusy(on) {
  busy = on;
  input.disabled = on || !endpoint;
  send.disabled = on || !endpoint;
  starters.forEach(b => { b.disabled = on || !endpoint; });
  status.textContent = on ? 'Thinking…' : '';
  thinking(on);
}

async function ask(question) {
  question = question.trim().slice(0, MAX_CHARS);
  if (!question || busy || !endpoint) return;
  messages.push({ role: 'user', content: question });
  showUser(question);
  input.value = '';
  setBusy(true);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: messages.slice(-MAX_SENT) }),
      signal: ctrl.signal,
      credentials: 'omit',
      referrerPolicy: 'strict-origin',
    });
    let data = null;
    try { data = await r.json(); } catch { /* not JSON */ }
    if (!r.ok || !data || typeof data.answer !== 'string') {
      messages.pop();
      showError((data && typeof data.error === 'string' && data.error) || 'The assistant could not answer just now. Please try again later.');
      return;
    }
    messages.push({ role: 'assistant', content: data.answer.slice(0, MAX_CHARS) });
    showAnswer(data);
    clear.hidden = false;
  } catch (e) {
    messages.pop();
    showError(e.name === 'AbortError' ? 'That took too long. Please try again.' : 'Could not reach the assistant. Check your connection and try again.');
  } finally {
    clearTimeout(timer);
    setBusy(false);
    document.querySelector('.ask-msg:last-of-type')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    if (endpoint) input.focus();
  }
}

form.addEventListener('submit', (e) => { e.preventDefault(); ask(input.value); });
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(input.value); }
});
starters.forEach(b => b.addEventListener('click', () => ask(b.textContent)));
clear.addEventListener('click', () => {
  messages.length = 0;
  log.replaceChildren();
  clear.hidden = true;
  input.focus();
});

(async function init() {
  try {
    const manifest = await loadManifest();
    const ep = manifest.site && manifest.site.ask_endpoint;
    endpoint = typeof ep === 'string' && /^https:\/\/|^http:\/\/(localhost|127\.0\.0\.1)[:/]/.test(ep) ? ep : null;
  } catch {
    endpoint = null;
  }
  if (!endpoint) {
    form.classList.add('off');
    status.textContent = '';
    const off = document.createElement('p');
    off.className = 'ask-off';
    off.textContent = "The assistant isn't switched on yet.";
    form.prepend(off);
  }
  setBusy(false);
  // ?q=<question> (e.g. from the Find quiz) prefills the box; the visitor still presses Ask.
  const pre = new URLSearchParams(location.search).get('q');
  if (pre) {
    input.value = pre.trim().slice(0, MAX_CHARS);
    if (endpoint) input.focus();
  }
})();
