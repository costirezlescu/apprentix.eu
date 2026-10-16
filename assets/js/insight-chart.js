/* Apprentix — draws one insight's chart (data/published/insights/insights.json item)
   into a host element. Shared by the Insights page and the embeddable chart page. */

import { formatter, barChart, lineChart, lineLegend, scatterChart, pairedBars } from './charts.js';

const SERIES = ['--series-1', '--series-2', '--series-3', '--series-4'];

function legend(host, entries, shape = 'line') {
  const box = document.createElement('div');
  box.className = 'viz-legend';
  for (const [label, colorVar] of entries) {
    const li = document.createElement('span');
    li.className = 'li';
    const k = document.createElement('i');
    k.className = shape === 'line' ? 'line-key' : 'sw';
    k.style.background = `var(${colorVar})`;
    const l = document.createElement('span');
    l.textContent = label;
    li.append(k, l);
    box.appendChild(li);
  }
  host.appendChild(box);
}

export function drawInsight(host, item) {
  const c = item.chart;
  host.replaceChildren();
  const box = document.createElement('div');
  host.appendChild(box);
  switch (c.type) {
    case 'scatter': {
      const fx = formatter('%'), fy = formatter('%');
      scatterChart(box, c.points, { fmtX: fx, fmtY: fy, xLabel: c.x.label, yLabel: c.y.label, targets: c.targets,
        xShort: 'had work-based learning', yShort: 'employed', label: item.title });
      const note = document.createElement('p');
      note.className = 'in-note';
      note.textContent = 'Each dot is a country. Amber lines: EU targets (60% work-based learning, 82% employment).';
      host.appendChild(note);
      break;
    }
    case 'target-bars': {
      box.className = 'in-panels';
      for (const panel of c.panels) {
        const p = document.createElement('div');
        const h = document.createElement('h3');
        h.textContent = `${panel.title} (target ${panel.target}%)`;
        const ch = document.createElement('div');
        p.append(h, ch);
        box.appendChild(p);
        const rows = [{ code: 'EU27', name: 'EU-27', value: panel.eu, emphasis: true },
          ...panel.rows.map(r => ({ code: r.geo, name: r.name, value: r.value, flag: r.flag }))];
        barChart(ch, rows, { fmt: formatter('%'), target: { value: panel.target }, label: panel.title });
      }
      break;
    }
    case 'paired-bars':
      legend(host, [[c.groups[0], '--series-1'], [c.groups[1], '--series-2']], 'box');
      pairedBars(box, c.rows.map(r => ({ label: r.label, a: r.employer, b: r.school })), { groups: c.groups, label: item.title });
      host.appendChild(box);
      break;
    case 'bars': {
      const fmt = formatter(c.unit, c.rows.map(r => r.value));
      barChart(box, c.rows.map(r => ({ code: r.label, name: r.label, value: r.value })), { fmt, label: item.title, fitLabels: true });
      break;
    }
    case 'lines': {
      const series = c.series.map((s, i) => ({ key: s.label, label: s.label, colorVar: SERIES[i % SERIES.length],
        points: s.points.map(p => ({ time: p.time, value: p.value })) }));
      const lg = document.createElement('div');
      lg.className = 'viz-legend';
      host.insertBefore(lg, box);
      lineLegend(lg, series);
      lineChart(box, series, { fmt: formatter(c.unit.includes('%') ? '%' : '', series.flatMap(s => s.points.map(p => p.value))), label: item.title });
      break;
    }
    case 'level-strip': {
      box.className = 'in-levels';
      const levels = [...new Set(c.rows.map(r => r.eqf))].sort((a, b) => b - a);
      for (const lv of levels) {
        const col = document.createElement('div');
        col.className = 'in-level';
        const h = document.createElement('div');
        h.className = 'in-level-h';
        h.textContent = `EQF ${lv}`;
        col.appendChild(h);
        for (const r of c.rows.filter(r => r.eqf === lv)) {
          const it = document.createElement('div');
          it.className = 'in-level-item';
          it.textContent = r.name;
          it.title = r.label;
          col.appendChild(it);
        }
        box.appendChild(col);
      }
      break;
    }
  }
}
