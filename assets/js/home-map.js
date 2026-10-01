/* Apprentix — "Europe over time": a compact time-lapse map for the home page.
   Cycles through a few headline indicators, playing each one year by year on a
   colour scale that is fixed across that indicator's years. It only plays by
   itself when the visitor has not asked for reduced motion, and only while the
   card is on screen and the tab is visible; a Pause button is always there.
   All text is set with textContent.

   Usage: mountHomeMap(document.getElementById('timelapse')) */

import { url } from './data.js';
import { formatter, tileMap, fixedScale, timeControls, prefersReducedMotion } from './charts.js';

// Headline indicators, in the order they are shown (ids from indicators/index.json).
const HEADLINES = [
  { id: 'eurostat-tps00215', chip: 'Work-based learning' },
  { id: 'eurostat-edat_lfse_24-vet', chip: 'Jobs after VET' },
  { id: 'cedefop-kivet-1010', chip: 'Students in VET' },
  { id: 'cedefop-kivet-3010', chip: 'Early leavers' },
];
const INTERVAL = 900;   // ms per year
const HOLD = 2600;      // ms on the last year before moving to the next indicator

const getJSON = p => fetch(url(p)).then(r => {
  if (!r.ok) throw new Error(`${r.status} — ${p}`);
  return r.json();
});

function el(tag, attrs = {}, parent, txt) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else e.setAttribute(k, v);
  }
  if (txt != null) e.textContent = txt;
  if (parent) parent.appendChild(e);
  return e;
}

/** Prepare one indicator: default-dimension observations, playable years, fixed scale. */
function prepare(ind, countries) {
  const isCountry = g => !!countries.byCode[g]?.tile;
  const obs = ind.series.filter(o => o.value != null &&
    (ind.dims || []).every(d => (o.dims?.[d.key] ?? d.default) === d.default));
  // Leave out sparse early years (fewer than half the usual number of countries).
  const counts = new Map();
  for (const o of obs) if (isCountry(o.geo)) counts.set(o.time, (counts.get(o.time) || 0) + 1);
  const maxc = Math.max(0, ...counts.values());
  const steps = [...counts.keys()].filter(t => counts.get(t) >= maxc * 0.5).sort();
  const inSteps = new Set(steps);
  const shown = obs.filter(o => inSteps.has(o.time));
  const byYear = new Map(steps.map(t => [t, new Map()]));
  const eu = new Map();
  for (const o of shown) {
    if (o.geo === 'EU27') eu.set(o.time, o);
    else if (isCountry(o.geo)) byYear.get(o.time).set(o.geo, o);
  }
  return {
    ind, steps, byYear, eu,
    fmt: formatter(ind.unit, ind.series.map(o => o.value)),
    scale: fixedScale(shown.filter(o => isCountry(o.geo)).map(o => o.value)),
  };
}

export async function mountHomeMap(host) {
  if (!host) return;
  host.replaceChildren();
  host.classList.add('tl-home');
  host.setAttribute('aria-labelledby', 'tl-home-title');

  const head = el('div', { class: 'tl-home-head' }, host);
  el('h2', { id: 'tl-home-title' }, head, 'Europe over time');
  el('p', { class: 'hint' }, head,
    'How a few headline figures changed, country by country. The colours use one scale for every year of an indicator.');
  const chips = el('div', { class: 'chips tl-chips', role: 'group', 'aria-label': 'Indicator shown' }, host);

  const body = el('div', { class: 'tl-home-body' }, host);
  const info = el('div', { class: 'tl-home-info' }, body);
  const topic = el('div', { class: 'mono tl-home-topic' }, info);
  const title = el('h3', { class: 'tl-home-title' }, info);
  const year = el('div', { class: 'tl-home-year' }, info);
  const euLine = el('p', { class: 'tl-home-eu' }, info);
  const euLab = el('span', {}, euLine, 'EU-27 ');
  const euVal = el('strong', {}, euLine);
  const targetLine = el('p', { class: 'tl-home-target' }, info);
  const explore = el('a', { class: 'tl-home-link' }, info, 'Explore this indicator →');
  const source = el('p', { class: 'tl-home-source' }, info);

  const stage = el('div', { class: 'tl-stage tl-home-map' }, body);
  const mapHost = el('div', {}, stage);
  const overlay = el('div', { class: 'tl-year', 'aria-hidden': 'true' }, stage);
  const ctlHost = el('div', { class: 'tl-home-controls' }, host);
  const status = el('p', { class: 'tl-home-status', role: 'status' }, host);

  let index, countries;
  try {
    [index, countries] = await Promise.all([
      getJSON('data/published/indicators/index.json'),
      getJSON('data/reference/countries.json'),
    ]);
  } catch (e) {
    status.textContent = 'The time-lapse could not be loaded.';
    console.error(e);
    return;
  }
  countries.byCode = Object.fromEntries(countries.countries.map(c => [c.code, c]));
  const list = HEADLINES.map(h => ({ ...h, meta: index.indicators.find(i => i.id === h.id) })).filter(h => h.meta);
  if (!list.length) { host.hidden = true; return; }

  const cache = new Map();
  const load = i => {
    if (!cache.has(i)) cache.set(i, getJSON(list[i].meta.path).then(ind => prepare(ind, countries)));
    return cache.get(i);
  };

  const reduce = prefersReducedMotion();
  let cur = 0;             // index into list
  let data = null;         // prepared indicator
  let cycle = !reduce;     // move on to the next indicator at the end
  let userPaused = false;  // the visitor paused (or took over with the slider)
  let autoPaused = false;  // we paused because the card left the screen / tab hid
  let visible = typeof IntersectionObserver !== 'function';
  let started = false;     // autoplay has started once
  let loading = 0;

  const chipEls = list.map((h, i) => {
    const b = el('button', { type: 'button', class: 'chip', 'aria-pressed': 'false' }, chips, h.chip);
    b.addEventListener('click', () => {
      cycle = false;
      const wasPlaying = controls.playing;
      controls.pause();
      show(i, wasPlaying ? 'first' : 'last', wasPlaying);
    });
    return b;
  });

  const map = tileMap(mapHost, { countries: countries.countries, values: new Map(), fmt: formatter('') });

  const controls = timeControls(ctlHost, {
    steps: ['—'], interval: INTERVAL, hold: HOLD,
    label: 'Year',
    onStep: i => paintYear(i),
    onPlayState: playing => host.classList.toggle('is-playing', playing),
    hasNext: () => cycle && list.length > 1,
    advance: () => show((cur + 1) % list.length, 'first', true),
  });
  controls.button.addEventListener('click', () => {
    userPaused = !controls.playing;
    autoPaused = false;
  });
  controls.slider.addEventListener('input', () => { userPaused = true; autoPaused = false; });

  function paintYear(i) {
    if (!data) return;
    const t = data.steps[i];
    const { ind, fmt } = data;
    year.textContent = t;
    overlay.textContent = t;
    const e = data.eu.get(t);
    euVal.textContent = e ? `${fmt(e.value)}${e.flag ? ` (${e.flag})` : ''}` : 'no EU figure';
    euLab.textContent = `EU-27 in ${t}: `;
    const tg = ind.target;
    if (tg) {
      const met = e ? e.value >= tg.value : null;
      targetLine.textContent = `EU target: at least ${fmt(tg.value)} by ${tg.year}` +
        (met == null ? '' : met ? ' · above target' : ' · below target');
      targetLine.dataset.met = met == null ? '' : String(met);
      targetLine.hidden = false;
    } else {
      targetLine.hidden = true;
    }
    explore.href = url(`pages/indicators.html?id=${encodeURIComponent(ind.id)}&year=${encodeURIComponent(t)}`);
    map.update({ values: data.byYear.get(t), year: t, fmt,
      label: `${ind.title}, ${t}: map of European countries` });
  }

  async function show(i, at = 'last', play = false) {
    const ticket = ++loading;
    cur = i;
    chipEls.forEach((b, k) => b.setAttribute('aria-pressed', String(k === i)));
    let d;
    try { d = await load(i); } catch (e) {
      status.textContent = 'This indicator could not be loaded.';
      console.error(e);
      return;
    }
    if (ticket !== loading) return; // a newer choice won
    status.textContent = '';
    data = d;
    const { ind, steps, scale, fmt } = d;
    topic.textContent = ind.topic || '';
    title.textContent = ind.title;
    const p = ind.provenance || {};
    source.textContent = `Source: ${p.publisher || ''}${p.dataset_code ? ` (${p.dataset_code})` : ''}${p.licence ? ` · ${p.licence}` : ''}`;
    map.update({ ...(scale || { domain: null, breaks: null }), fmt });
    controls.setSteps(steps, at === 'first' ? 0 : steps.length - 1);
    paintYear(controls.index);
    if (play && canAutoplay()) controls.play();
    // Warm the next one so the switch is instant.
    if (cycle && list.length > 1) load((i + 1) % list.length).catch(() => {});
  }

  const canAutoplay = () => visible && !document.hidden && !userPaused;

  function maybeStart() {
    if (reduce || userPaused || !data) return;
    if (!canAutoplay()) return;
    if (!started) { started = true; controls.play(); }
    else if (autoPaused) { autoPaused = false; controls.play(); }
  }
  function autoPause() {
    if (controls.playing) { controls.pause(); autoPaused = true; }
  }

  document.addEventListener('visibilitychange', () => (document.hidden ? autoPause() : maybeStart()));
  if (typeof IntersectionObserver === 'function') {
    new IntersectionObserver(entries => {
      for (const e of entries) {
        visible = e.isIntersecting;
        if (visible) maybeStart(); else autoPause();
      }
    }, { threshold: 0.35 }).observe(host);
  }

  await show(0, 'last', false);
  maybeStart();
}
