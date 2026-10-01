/* Apprentix — "What changed this week" panel.
   Reads data/published/changes/log.json (written by pipeline/changes.py).

   import { mountChanges } from './assets/js/changes.js';
   mountChanges(document.getElementById('changes'), { limit: 5 });

   All text is set with textContent; nothing from the log is parsed as HTML. */

import { url } from './data.js';

const LOG_PATH = 'data/published/changes/log.json';
const FEED_PATH = 'data/feed.xml';

/* kind -> [glyph, tone, label for screen readers] */
const KINDS = {
  'new-period':        ['↗', 'new',  'New data'],
  'new-data':          ['+', 'new',  'More countries'],
  'new-indicator':     ['★', 'new',  'New indicator'],
  'new-dataset':       ['★', 'new',  'New dataset'],
  'new-records':       ['+', 'new',  'Added'],
  'policy-stage':      ['→', 'info', 'Policy stage'],
  'updated-records':   ['✎', 'info', 'Updated'],
  'revision':          ['↻', 'warn', 'Revised'],
  'removed-records':   ['−', 'warn', 'Removed'],
  'removed-indicator': ['−', 'warn', 'Withdrawn'],
  'removed-dataset':   ['−', 'warn', 'Withdrawn'],
  'baseline':          ['●', 'info', 'Started'],
};

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function fmtDate(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(d);
}

function daysSince(iso) {
  const d = new Date(`${iso}T00:00:00Z`).getTime();
  return Number.isNaN(d) ? Infinity : (Date.now() - d) / 864e5;
}

function timeEl(iso) {
  const t = el('time', 'changes-date', fmtDate(iso));
  t.dateTime = iso;
  return t;
}

/* Only follow repo-relative links (the pipeline writes nothing else). */
function safeHref(link) {
  if (typeof link !== 'string' || !link || /^[a-z][a-z0-9+.-]*:/i.test(link) || link.startsWith('//')) return null;
  return url(link.replace(/^\/+/, ''));
}

function itemEl(it) {
  const [glyph, tone, label] = KINDS[it.kind] || ['•', 'info', 'Change'];
  const li = el('li', `change change--${tone}`);
  li.dataset.kind = it.kind || '';
  const icon = el('span', 'change-icon', glyph);
  icon.setAttribute('aria-hidden', 'true');
  li.append(icon);

  const body = el('div', 'change-body');
  const sr = el('span', 'changes-sr', `${label}: `);
  const href = safeHref(it.link);
  const title = href ? el('a', 'change-title', it.title || '') : el('span', 'change-title', it.title || '');
  if (href) title.href = href;
  const head = el('p', 'change-head');
  head.append(sr, title);
  body.append(head);
  if (it.text) body.append(el('p', 'change-text', it.text));
  const cs = Array.isArray(it.countries) ? it.countries.filter(c => typeof c === 'string') : [];
  if (cs.length) {
    const shown = cs.slice(0, 8).join(' · ') + (cs.length > 8 ? ` +${cs.length - 8}` : '');
    const c = el('p', 'change-countries', shown);
    c.title = cs.join(', ');
    body.append(c);
  }
  li.append(body);
  return li;
}

function listEl(items) {
  const ul = el('ul', 'changes-list');
  for (const it of items) ul.append(itemEl(it));
  return ul;
}

export async function mountChanges(host, { limit = 5, earlier = 4, heading = true } = {}) {
  if (!host) return;
  let log;
  try {
    const r = await fetch(url(LOG_PATH));
    if (!r.ok) throw new Error(`${r.status}`);
    log = await r.json();
  } catch {
    host.hidden = true;            // no log yet: show nothing rather than an error
    return;
  }
  const entries = Array.isArray(log?.entries) ? log.entries.filter(e => e && Array.isArray(e.items)) : [];
  if (!entries.length) { host.hidden = true; return; }

  const [latest, ...older] = entries;
  host.replaceChildren();
  host.hidden = false;
  host.classList.add('changes');

  const head = el('div', 'changes-head');
  if (heading) {
    const h = el('h2', 'changes-title', latest.baseline || daysSince(latest.date) > 10 ? 'Latest data changes' : 'What changed this week');
    h.id = host.id ? `${host.id}-title` : 'changes-title';
    host.setAttribute('aria-labelledby', h.id);
    head.append(h);
  }
  head.append(timeEl(latest.date));
  host.append(head);

  const items = latest.items;
  const first = listEl(items.slice(0, limit));
  host.append(first);
  if (items.length > limit) {
    const rest = items.slice(limit);
    const btn = el('button', 'changes-more', `Show ${rest.length} more change${rest.length === 1 ? '' : 's'}`);
    btn.type = 'button';
    btn.addEventListener('click', () => {
      for (const it of rest) first.append(itemEl(it));
      btn.remove();
    });
    host.append(btn);
  }

  if (latest.baseline && !older.length) {
    host.append(el('p', 'changes-note', 'Updates appear here when the weekly refresh finds new data.'));
  }

  if (earlier > 0 && older.length) {
    const det = el('details', 'changes-earlier');
    det.append(el('summary', null, `Earlier updates (${older.length})`));
    for (const e of older.slice(0, earlier)) {
      const block = el('div', 'changes-entry');
      block.append(timeEl(e.date));
      block.append(listEl(e.items.slice(0, limit)));
      if (e.items.length > limit) block.append(el('p', 'changes-note', `and ${e.items.length - limit} more`));
      det.append(block);
    }
    if (older.length > earlier) {
      det.append(el('p', 'changes-note', `${older.length - earlier} older update${older.length - earlier === 1 ? '' : 's'} in the change log below.`));
    }
    host.append(det);
  }

  const foot = el('p', 'changes-foot');
  const feed = el('a', null, 'Updates feed (Atom)');
  feed.href = url(FEED_PATH);
  const all = el('a', null, 'Change log (JSON)');
  all.href = url(LOG_PATH);
  foot.append(feed, document.createTextNode(' · '), all);
  host.append(foot);
}
