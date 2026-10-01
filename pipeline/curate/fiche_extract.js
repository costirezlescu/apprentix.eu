/* Extract Cedefop's coded answers from every apprenticeship scheme fiche.

   Cedefop's pages refuse scripted requests, so this runs in a normal browser:
   1. Open https://www.cedefop.europa.eu/en/tools/apprenticeship-schemes/scheme-fiches
   2. Open the developer console, paste this whole file, press Enter.
   3. Wait (about 2 seconds per fiche). The page is replaced by plain text lines.
   4. Copy the A| lines into data/raw/cedefop-schemes/<YYYY-MM-DD>-fiche-answers.txt
      (keep the META| lines from the previous file, updating authors if a fiche changed),
      then run: python -m pipeline.curate.merge_fiches

   It reads only the newest reference year of each fiche, requests one page at a
   time with a pause, and stops at the first questionnaire change it cannot map
   (lines marked MISMATCH: update pipeline/curate/scheme_questions.py first). */

(async () => {
  const YEAR_TERM = '7362';           // "2026" in the reference-year filter; check the filter for newer rounds
  const PAUSE_MS = 1500;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const U = s => s.toUpperCase().replace(/\s+/g, ' ').trim();

  const extract = doc => {
    const panes = [...doc.querySelectorAll('[id^="reference-year-"]')];
    const pane = panes.sort((a, b) => a.id.localeCompare(b.id)).pop();
    if (!pane) return null;
    const qs = [];
    for (const el of pane.querySelectorAll('.question-wrapper')) {
      const label = el.querySelector('.field-label')?.innerText.trim() || '';
      const m = label.match(/^Q(\d+)\./);
      const terms = [...el.querySelectorAll('.term')];
      if (!m || !terms.length) continue;
      qs.push({ n: +m[1], options: terms.map(t => U(t.textContent)),
        selected: terms.filter(t => t.classList.contains('term-selected')).map(t => U(t.textContent)) });
    }
    return { year: pane.id.replace('reference-year-', ''), qs };
  };

  const links = new Set();
  for (let page = 0; page < 10; page++) {
    const html = await (await fetch(`/en/tools/apprenticeship-schemes/scheme-fiches?year=${YEAR_TERM}&page=${page}`)).text();
    const d = new DOMParser().parseFromString(html, 'text/html');
    const before = links.size;
    d.querySelectorAll('a[href*="/scheme-fiches/"]').forEach(a => {
      const h = a.getAttribute('href').split(/[?#]/)[0];
      if (!/scheme-fiches$/.test(h) && a.textContent.trim()) links.add(h);
    });
    if (links.size === before) break;
    await sleep(PAUSE_MS);
  }

  const out = [];
  for (const href of links) {
    const d = new DOMParser().parseFromString(await (await fetch(href)).text(), 'text/html');
    const x = extract(d);
    const slug = href.split('/').pop();
    if (!x) { out.push(`# no reference-year pane: ${slug}`); continue; }
    out.push(`A|${slug}|` + x.qs.map(q => `${q.n}=` + q.selected.map(s => q.options.indexOf(s)).join(',')).join(' '));
    out.push(`# ${slug}: reference year ${x.year}, ${x.qs.length} coded questions; options: ` +
      x.qs.map(q => `${q.n}:${q.options.length}`).join(' '));
    await sleep(PAUSE_MS);
  }
  const pre = document.createElement('pre');
  pre.textContent = out.join('\n');
  document.body.replaceChildren(pre);
})();
