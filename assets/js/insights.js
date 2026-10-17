/* Apprentix — Insights page: draws the charts over the static content and
   filters insights by audience. All text is already in the HTML; this only
   adds the visual layer. */

import { url } from './data.js?v=32ac435b';
import { drawInsight } from './insight-chart.js?v=32ac435b';
import { addShareControls } from './share.js?v=32ac435b';

let ITEMS = [];

const data = await fetch(url('data/published/insights/insights.json')).then(r => r.json());
ITEMS = data.items;
drawAll();
wireFilter();
let t;
window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(drawAll, 150); });

function drawAll() {
  document.querySelectorAll('.in-chart').forEach(host => {
    const item = ITEMS[Number(host.dataset.chart)];
    if (!item?.chart || host.closest('.in-card').hidden) return;
    drawInsight(host, item);
    if (host.querySelector('svg.viz')) {
      const card = host.closest('.in-card');
      addShareControls(host, {
        title: item.title,
        subtitle: item.finding.length > 220 ? item.finding.slice(0, item.finding.lastIndexOf(' ', 217)) + ' …' : item.finding,
        source: 'Apprentix analysis of ' + (item.sources || []).map(s => s.label).join('; '),
        url: `${location.origin}${location.pathname}#${card.id}`,
        embed: { path: `embed/chart.html?insight=${encodeURIComponent(item.id)}`, height: embedHeight(item) },
      });
    }
  });
}

/* Rough iframe height for an insight chart (the embed also reports its real height). */
function embedHeight(item) {
  const c = item.chart;
  const rows = c.rows?.length || 0;
  if (c.type === 'bars') return Math.min(1400, 230 + rows * 26);
  if (c.type === 'paired-bars') return Math.min(1400, 260 + rows * 40);
  if (c.type === 'target-bars') return Math.min(1800, 260 + c.panels.reduce((n, p) => n + 60 + (p.rows.length + 1) * 26, 0));
  if (c.type === 'level-strip') return 520;
  return 560;
}

function wireFilter() {
  const chips = document.querySelectorAll('.in-filter .chip');
  chips.forEach(ch => ch.addEventListener('click', () => {
    const aud = ch.dataset.aud;
    chips.forEach(c => c.setAttribute('aria-pressed', String(c === ch)));
    document.querySelectorAll('.in-card').forEach(card => {
      card.hidden = aud !== 'all' && !card.dataset.audience.split(' ').includes(aud);
    });
    drawAll();
  }));
}
