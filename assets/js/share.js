/* Apprentix — shareable charts.
   addShareControls(host, meta) adds "Download image" and "Copy link" buttons
   to a chart container. The image is a PNG composed in the browser from the
   chart's SVG(s) and legend, with the title, the source credit, the licence and
   apprentix.eu written on it — so a shared chart always carries its source.
   With meta.embed ({path, height}) there is also an "Embed" button that shows an
   <iframe> snippet for embed/chart.html. Nothing is uploaded anywhere. */

const NS = 'http://www.w3.org/2000/svg';
const STYLE_PROPS = ['fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'opacity',
  'font-size', 'font-family', 'font-weight', 'visibility'];

function inlineStyles(src, dst) {
  const cs = getComputedStyle(src);
  const style = STYLE_PROPS.map(p => `${p}:${cs.getPropertyValue(p)}`).join(';');
  dst.setAttribute('style', style);
  const s = src.children, d = dst.children;
  for (let i = 0; i < s.length; i++) inlineStyles(s[i], d[i]);
}

function wrapText(str, max) {
  const words = String(str).split(/\s+/);
  const lines = [];
  let line = '';
  for (const w of words) {
    if ((line + ' ' + w).trim().length > max) { if (line) lines.push(line); line = w; } else line = (line + ' ' + w).trim();
  }
  if (line) lines.push(line);
  return lines;
}

function el(tag, attrs, parent, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}

/** Compose one standalone SVG string from a chart host. */
function compose(host, meta) {
  const svgs = [...host.querySelectorAll('svg.viz')];
  if (!svgs.length) return null;
  const root = getComputedStyle(document.documentElement);
  const bg = root.getPropertyValue('--surface').trim() || '#ffffff';
  const ink = root.getPropertyValue('--ink').trim() || '#14181b';
  const muted = root.getPropertyValue('--muted').trim() || '#5c6569';
  const accent = root.getPropertyValue('--accent').trim() || '#0f6b63';
  const font = root.getPropertyValue('--body').trim().replace(/"/g, "'") || 'Public Sans, Segoe UI, system-ui, sans-serif';

  const pad = 28;
  const parts = svgs.map(s => {
    const vb = (s.getAttribute('viewBox') || '').split(/\s+/).map(Number);
    const w = vb[2] || s.clientWidth, h = vb[3] || s.clientHeight;
    const clone = s.cloneNode(true);
    inlineStyles(s, clone);
    return { clone, w, h };
  });
  const contentW = Math.max(560, ...parts.map(p => p.w));
  const W = contentW + pad * 2;
  const titleLines = wrapText(meta.title || '', Math.floor(contentW / 10.5));
  const subLines = meta.subtitle ? wrapText(meta.subtitle, Math.floor(contentW / 7.2)) : [];

  // Legend items (HTML legends become SVG rows).
  const legendItems = [...host.querySelectorAll('.viz-legend .li')].map(li => {
    const key = li.querySelector('i');
    const colour = key ? getComputedStyle(key).backgroundColor : muted;
    return { label: li.textContent.replace('✕', '').trim(), colour, line: key?.classList.contains('line-key') };
  });

  let y = pad;
  const out = el('svg', { xmlns: NS, width: W, height: 10, viewBox: `0 0 ${W} 10` });
  el('rect', { x: 0, y: 0, width: W, height: '100%', fill: bg }, out);
  el('rect', { x: 0, y: 0, width: W, height: 5, fill: accent }, out);
  y += 6;
  for (const l of titleLines) { y += 24; el('text', { x: pad, y, 'font-family': font, 'font-size': 20, 'font-weight': 700, fill: ink }, out, l); }
  for (const l of subLines) { y += 18; el('text', { x: pad, y, 'font-family': font, 'font-size': 13, fill: muted }, out, l); }
  if (legendItems.length) {
    y += 14;
    let x = pad, rowY = y + 12;
    for (const it of legendItems) {
      const tw = it.label.length * 6.6 + 30;
      if (x + tw > W - pad) { x = pad; rowY += 18; }
      if (it.line) el('rect', { x, y: rowY - 5, width: 16, height: 2.5, fill: it.colour }, out);
      else el('rect', { x, y: rowY - 10, width: 12, height: 12, rx: 3, fill: it.colour }, out);
      el('text', { x: x + 20, y: rowY, 'font-family': font, 'font-size': 12, fill: muted }, out, it.label);
      x += tw;
    }
    y = rowY + 6;
  }
  y += 12;
  for (const p of parts) {
    p.clone.setAttribute('x', pad + (contentW - p.w) / 2);
    p.clone.setAttribute('y', y);
    p.clone.setAttribute('width', p.w);
    p.clone.setAttribute('height', p.h);
    out.appendChild(p.clone);
    y += p.h + 14;
  }
  // Footer credit.
  y += 6;
  el('line', { x1: pad, x2: W - pad, y1: y, y2: y, stroke: muted, 'stroke-opacity': .3 }, out);
  const credit = wrapText(`Source: ${meta.source || 'see apprentix.eu'}${meta.licence ? ' · ' + meta.licence : ''}`, Math.floor(contentW / 6.4));
  for (const l of credit) { y += 17; el('text', { x: pad, y, 'font-family': font, 'font-size': 12, fill: muted }, out, l); }
  y += 20;
  el('text', { x: pad, y, 'font-family': font, 'font-size': 13, 'font-weight': 700, fill: accent }, out, 'apprentix.eu');
  if (meta.url) el('text', { x: W - pad, y, 'font-family': font, 'font-size': 11, fill: muted, 'text-anchor': 'end' }, out,
    meta.url.replace(/^https?:\/\//, '').slice(0, 90));
  y += pad - 6;
  out.setAttribute('height', y);
  out.setAttribute('viewBox', `0 0 ${W} ${y}`);
  return { svg: new XMLSerializer().serializeToString(out), w: W, h: y };
}

async function toPng(composed, scale = 2) {
  const blob = new Blob([composed.svg], { type: 'image/svg+xml;charset=utf-8' });
  const src = URL.createObjectURL(blob);
  try {
    const img = new Image();
    img.decoding = 'async';
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = src; });
    const c = document.createElement('canvas');
    c.width = Math.round(composed.w * scale);
    c.height = Math.round(composed.h * scale);
    const ctx = c.getContext('2d');
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0);
    return await new Promise(res => c.toBlob(res, 'image/png'));
  } finally {
    URL.revokeObjectURL(src);
  }
}

function slug(s) {
  return String(s || 'chart').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'chart';
}

function flash(btn, text) {
  const old = btn.textContent;
  btn.textContent = text;
  setTimeout(() => { btn.textContent = old; }, 1800);
}

const SITE = 'https://apprentix.eu/';

/** Absolute URL of a site path: the live site when on apprentix.eu or a local copy otherwise. */
function siteUrl(path) {
  const root = document.body.dataset.root || './';
  const local = new URL(root + path, location.href);
  return /(^|\.)apprentix\.eu$/.test(location.hostname) ? SITE + path : local.href;
}

/** The <iframe> snippet for an embed (embed: {path, height, title}). */
export function embedCode(embed) {
  const src = siteUrl(embed.path);
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  return `<iframe src="${esc(src)}" title="${esc(embed.title || 'Apprentix chart')}" width="100%" height="${Number(embed.height) || 520}" `
    + 'style="border:0;max-width:900px" loading="lazy"></iframe>';
}

/**
 * meta: { title, subtitle?, source, licence?, url?, embed?: {path, height} }  (url defaults to the current page)
 * Buttons are added once per host; calling again only updates the metadata.
 */
export function addShareControls(host, meta) {
  if (!host) return;
  host._shareMeta = meta;
  if (host.querySelector(':scope > .share-bar')) { host._embedFill?.(); return; }
  const bar = document.createElement('div');
  bar.className = 'share-bar';
  const dl = document.createElement('button');
  dl.type = 'button';
  dl.className = 'share-btn';
  dl.textContent = 'Download image';
  dl.setAttribute('aria-label', 'Download this chart as an image, with its source');
  dl.addEventListener('click', async () => {
    const m = host._shareMeta || {};
    const composed = compose(host, { ...m, url: m.url || location.href });
    if (!composed) return flash(dl, 'No chart to save');
    dl.disabled = true;
    try {
      const png = await toPng(composed);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(png);
      a.download = `apprentix-${slug(m.title)}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      flash(dl, 'Saved ✓');
    } catch (e) {
      console.error(e);
      flash(dl, 'Could not save');
    } finally {
      dl.disabled = false;
    }
  });
  const cp = document.createElement('button');
  cp.type = 'button';
  cp.className = 'share-btn';
  cp.textContent = 'Copy link';
  cp.addEventListener('click', async () => {
    const m = host._shareMeta || {};
    const link = m.url || location.href;
    try {
      await navigator.clipboard.writeText(link);
      flash(cp, 'Link copied ✓');
    } catch {
      flash(cp, link);
    }
  });
  bar.append(dl, cp);
  host.appendChild(bar);
  addEmbed(host, bar);
}

function addEmbed(host, bar) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'share-btn';
  btn.textContent = 'Embed';
  btn.setAttribute('aria-expanded', 'false');
  btn.hidden = !host._shareMeta?.embed;
  const panel = document.createElement('div');
  panel.className = 'embed-panel';
  panel.hidden = true;
  const help = document.createElement('p');
  help.textContent = 'Paste this code into your web page to show this chart, with its source and licence. The chart updates when the data does.';
  const code = document.createElement('textarea');
  code.readOnly = true;
  code.setAttribute('aria-label', 'Embed code');
  const actions = document.createElement('div');
  actions.className = 'embed-actions';
  const copy = document.createElement('button');
  copy.type = 'button';
  copy.className = 'share-btn';
  copy.textContent = 'Copy code';
  const preview = document.createElement('a');
  preview.target = '_blank';
  preview.rel = 'noopener';
  preview.textContent = 'Preview ↗';
  actions.append(copy, preview);
  panel.append(help, code, actions);
  const fill = () => {
    const e = host._shareMeta?.embed;
    btn.hidden = !e;
    if (!e) { panel.hidden = true; return; }
    code.value = embedCode({ title: host._shareMeta.title, ...e });
    preview.href = siteUrl(e.path);
  };
  btn.addEventListener('click', () => {
    fill();
    panel.hidden = !panel.hidden;
    btn.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) code.select();
  });
  copy.addEventListener('click', async () => {
    fill();
    try { await navigator.clipboard.writeText(code.value); flash(copy, 'Copied ✓'); }
    catch { code.select(); flash(copy, 'Press Ctrl/⌘+C'); }
  });
  host._embedFill = fill;
  bar.appendChild(btn);
  host.appendChild(panel);
}

/** The PNG (as a Blob) that "Download image" would save — also usable for previews. */
export async function chartImage(host, meta) {
  const composed = compose(host, { ...meta, url: meta.url || location.href });
  return composed ? toPng(composed) : null;
}
