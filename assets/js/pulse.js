/* Apprentix — "Policy pulse" card on the home page: apprenticeship policies that started or
   changed stage in the latest year of Cedefop's Timeline of VET policies
   (data/published/pulse/pulse.json, built by pipeline/pulse.py). Text via textContent only.

   Usage: mountPulse(document.getElementById('pulse')) */

import { url } from './data.js?v=0246fca6';

const LABELS = { new: 'New', completed: 'Completed', moved: 'Moved on', discontinued: 'Discontinued' };

function el(tag, cls, parent, txt) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  if (parent) parent.appendChild(e);
  return e;
}

export async function mountPulse(host) {
  if (!host) return;
  let d;
  try {
    const r = await fetch(url('data/published/pulse/pulse.json'));
    if (!r.ok) return;
    d = await r.json();
  } catch { return; }
  const kinds = Object.keys(LABELS).filter(k => d.items?.[k]?.length);
  if (!kinds.length) return;

  host.replaceChildren();
  host.hidden = false;
  const head = el('div', 'pulse-head', host);
  el('span', 'start-kicker', head, 'Policy pulse');
  el('h2', null, head, `Apprenticeship reforms in ${d.year}`);
  const c = d.counts;
  el('p', 'hint', head, `Across Europe, ${c.new} apprenticeship policies were first reported in ${d.year}, ${c.completed} were completed, `
    + `${c.moved} moved to another stage and ${c.discontinued} were discontinued; ${c.ongoing} more were being implemented.`);

  const tabs = el('div', 'pulse-tabs', host);
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-label', 'Kind of change');
  const panel = el('ul', 'pulse-list', host);
  panel.setAttribute('role', 'tabpanel');
  const buttons = kinds.map(k => {
    const b = el('button', 'chip', tabs, `${LABELS[k]} (${c[k]})`);
    b.type = 'button';
    b.setAttribute('role', 'tab');
    b.addEventListener('click', () => select(k));
    return b;
  });

  function select(k) {
    buttons.forEach((b, j) => {
      const on = kinds[j] === k;
      b.setAttribute('aria-selected', String(on));
      b.setAttribute('aria-pressed', String(on));
    });
    panel.replaceChildren();
    for (const it of d.items[k]) {
      const li = el('li', null, panel);
      const flag = el('span', 'pulse-flag', li, it.flag || '');
      flag.setAttribute('aria-hidden', 'true');
      const body = el('div', null, li);
      const a = el('a', 'pulse-title', body, it.title);
      a.href = url(it.link);
      const meta = [it.country, it.type, it.from ? `${it.from} → ${it.to}` : ''].filter(Boolean).join(' · ');
      el('div', 'pulse-meta', body, meta);
    }
    if (c[k] > d.items[k].length) el('li', 'pulse-more', panel, `…and ${c[k] - d.items[k].length} more`);
  }
  select(kinds[0]);

  const foot = el('p', 'pulse-foot', host);
  const all = el('a', null, foot, `All apprenticeship policies active in ${d.year}`);
  all.href = url(d.all_link);
  foot.append(' · Source: ');
  const src = el('a', null, foot, d.source?.name || 'Cedefop, Timeline of VET policies in Europe');
  src.href = d.source?.url || 'https://www.cedefop.europa.eu/en/tools/timeline-vet-policies-europe';
  src.target = '_blank';
  src.rel = 'noopener';
}
