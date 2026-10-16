/* Apprentix — "Scheme of the week" (home page).
   Each ISO week shows one of Cedefop's apprenticeship schemes, in a fixed shuffled
   order so neighbouring weeks come from different countries. It changes on Monday
   (UTC) by itself; no rebuild is needed. Text is set with textContent, except the scheme's
   portrait, which is HTML generated and escaped by pipeline/portraits.py.

   Usage: mountSchemeOfWeek(document.getElementById('scheme-week')) */

import { loadDataset, url } from './data.js?v=0246fca6';

const WEEK = 7 * 864e5;
const MONDAY0 = Date.UTC(2024, 0, 1);   // a Monday: week 0 of the rotation

function el(tag, cls, parent, txt) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  if (parent) parent.appendChild(e);
  return e;
}

/** ISO 8601 week number and the Monday that starts it (UTC). */
export function isoWeek(date) {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const day = d.getUTCDay() || 7;
  const monday = new Date(d.getTime() - (day - 1) * 864e5);
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = Date.UTC(d.getUTCFullYear(), 0, 1);
  return { week: Math.ceil(((d - yearStart) / 864e5 + 1) / 7), monday };
}

/* Small stable string hash (FNV-1a), for a fixed shuffle that does not depend on file order. */
function hash(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return h >>> 0;
}

/** Records in rotation order: shuffled by id hash, then nudged so no two neighbours share a country. */
export function rotation(records) {
  const list = [...records].sort((a, b) => hash(a.id) - hash(b.id) || a.id.localeCompare(b.id));
  for (let i = 1; i < list.length; i++) {
    if (list[i].country_code !== list[i - 1].country_code) continue;
    const j = list.findIndex((r, k) => k > i && r.country_code !== list[i - 1].country_code);
    if (j > 0) [list[i], list[j]] = [list[j], list[i]];
  }
  return list;
}

export function schemeFor(records, date = new Date()) {
  const order = rotation(records);
  const { week, monday } = isoWeek(date);
  const n = Math.floor((monday.getTime() - MONDAY0) / WEEK);
  const i = ((n % order.length) + order.length) % order.length;
  return { scheme: order[i], next: order[(i + 1) % order.length], week, monday };
}

export async function mountSchemeOfWeek(host) {
  if (!host) return;
  let data, portraits = {};
  try { data = await loadDataset('apprenticeship-schemes'); } catch { return; }
  try {
    const r = await fetch(url('data/published/portraits/portraits.json'));
    if (r.ok) portraits = (await r.json()).portraits || {};
  } catch { /* the card works without the portrait */ }
  const records = data.records.filter(r => r.id && r.name_en);
  if (!records.length) return;
  const { scheme: s, next, week } = schemeFor(records);
  const fields = Object.fromEntries(data.meta.fields.map(f => [f.key, f.label]));

  host.replaceChildren();
  host.hidden = false;
  const card = el('article', 'sow-card', host);
  const head = el('div', 'sow-head', card);
  el('span', 'start-kicker', head, `Scheme of the week · week ${week}`);
  const h = el('h2', 'sow-title', head);
  el('span', 'sow-flag', h, s.flag || '').setAttribute('aria-hidden', 'true');
  h.append(` ${s.name_en}`);
  const sub = [s.country, s.name_original && s.name_original !== s.name_en ? s.name_original : ''].filter(Boolean).join(' · ');
  el('p', 'sow-sub', head, sub);

  if (s.overview) el('p', 'sow-overview', card, s.overview);

  const portrait = portraits[s.id]?.html;
  if (portrait) {
    const box = el('div', 'sow-portrait', card);
    box.innerHTML = portrait;            // generated and escaped by pipeline/portraits.py
  }
  const facts = portrait ? [] : [
    ['duration', s.duration],
    ['workplace_time', s.workplace_time],
    ['compensation', s.compensation],
    ['education_level', s.education_level],
    ['learners', s.learners],
  ].filter(([, v]) => v);
  if (facts.length) {
    const dl = el('dl', 'sow-facts', card);
    for (const [k, v] of facts) {
      const row = el('div', null, dl);
      el('dt', null, row, (fields[k] || k).replace(/ \(.*\)$/, ''));
      el('dd', null, row, Array.isArray(v) ? v.join(', ') : v);
    }
  }

  const actions = el('p', 'cp-links sow-actions', card);
  const a = (href, text, cls = 'btn', ext = false) => {
    const link = el('a', cls, actions, text);
    link.href = href;
    if (ext) { link.target = '_blank'; link.rel = 'noopener'; }
    return link;
  };
  a(url(`pages/explore.html?dataset=apprenticeship-schemes&open=${encodeURIComponent(s.id)}`), 'Read about this scheme', 'btn primary');
  const cc = s.country_code === 'EL' ? 'GR' : s.country_code;
  a(url(`pages/find.html?c=${encodeURIComponent(cc)}`), 'Would it suit me?');
  if (s.source_url) a(s.source_url, 'Cedefop fiche ↗', 'btn', true);

  const foot = el('p', 'sow-foot', card);
  foot.append('Source: ');
  const src = el('a', null, foot, 'Cedefop — European database on apprenticeship schemes');
  src.href = 'https://www.cedefop.europa.eu/en/tools/apprenticeship-schemes';
  src.target = '_blank';
  src.rel = 'noopener';
  foot.append(`. A new scheme every Monday${next && next.id !== s.id ? ` — next week, ${next.country}` : ''}.`);
}
