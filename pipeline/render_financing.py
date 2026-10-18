"""'Who pays for apprenticeships?': the financing instrument explorer.

  pages/financing.html   instrument type × country matrix, then every instrument by country,
                         from data/published/financing-instruments (Cedefop database on financing
                         apprenticeships). Static HTML; a few lines of script add the type filter.

Run on its own with:  python -m pipeline.render_financing
"""

from __future__ import annotations

import math

from .common import DATA, PUBLISHED, ROOT, read_json
from .render_pages import SITE, breadcrumb, e, page, plural, website, write_text

OUT = ROOT / "pages" / "financing.html"
TYPES = ["Grants for companies", "Tax incentives", "Grants for individuals", "Training funds"]
TYPE_NOTE = {
    "Grants for companies": "Money paid to companies that train apprentices.",
    "Tax incentives": "Tax relief or lower social contributions for training companies.",
    "Grants for individuals": "Money paid to apprentices or learners.",
    "Training funds": "Funds fed by employer levies that pay for training.",
}


def slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in s.lower()).strip("-")


def clip(s: str | None, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def render() -> list[str]:
    path = PUBLISHED / "financing-instruments" / "records.json"
    if not path.exists():
        return []
    recs = read_json(path)
    meta = read_json(PUBLISHED / "financing-instruments" / "meta.json")
    src = meta["source"]
    updated = read_json(DATA / "datasets.json")["site"].get("updated", "")
    page_url = f"{SITE}pages/financing.html"

    by_c: dict[str, list] = {}
    for r in recs:
        by_c.setdefault(r["country"], []).append(r)
    countries = sorted(by_c, key=lambda c: (-len(by_c[c]), c))
    count = lambda c, t: sum(1 for r in by_c[c] if t in (r.get("type") or []))
    per_type = {t: sum(1 for r in recs if t in (r.get("type") or [])) for t in TYPES}

    head = "".join(f'<th scope="col" data-type="{slug(t)}"><span>{e(t)}</span><small>{per_type[t]}</small></th>' for t in TYPES)
    rows = []
    for c in countries:
        flag = by_c[c][0].get("flag", "")
        cells = []
        for t in TYPES:
            n = count(c, t)
            if n:
                d = 10 + 8 * math.sqrt(n)
                cells.append(f'<td data-type="{slug(t)}"><a class="fx-dot" href="#c-{slug(c)}" style="--d:{d:.0f}px" '
                             f'title="{e(c)}: {n} {e(t.lower())} instrument{"s" if n > 1 else ""}"><span>{n}</span></a></td>')
            else:
                cells.append(f'<td data-type="{slug(t)}" class="fx-none"><span class="oc-sr">none</span></td>')
        rows.append(f'<tr data-types="{" ".join(slug(t) for t in TYPES if count(c, t))}"><th scope="row"><a href="#c-{slug(c)}">'
                    f'<span aria-hidden="true">{flag}</span> {e(c)}</a></th>{"".join(cells)}</tr>')

    def card(r):
        types = "".join(f'<span class="fx-type" data-type="{slug(t)}">{e(t)}</span>' for t in (r.get("type") or []))
        facts = [("Level", r.get("level")), ("Introduced", r.get("year_introduced")), ("Covers", r.get("scope")),
                 ("Paid by", r.get("financing_source")), ("Eligible costs", clip(r.get("eligible_costs"), 140))]
        kv = "".join(f'<div class="row"><div class="k">{e(k)}</div><div>{e(v)}</div></div>' for k, v in facts if v)
        return (f'<article class="panel fx-card" data-types="{" ".join(slug(t) for t in r.get("type") or [])}">'
                f'<div class="fx-types">{types}</div><h4>{e(r.get("name_en") or r["title"])}</h4>'
                f'<p>{e(clip(r.get("objectives"), 260))}</p><div class="kv">{kv}</div>'
                f'<p class="cp-links"><a class="btn" href="{e(r["source_url"])}" target="_blank" rel="noopener">Cedefop fiche ↗</a>'
                f'<a class="btn" href="explore.html?dataset=financing-instruments&amp;open={e(r["id"])}">Full record</a></p></article>')

    groups = "".join(
        f'<section class="fx-country" id="c-{slug(c)}" aria-labelledby="h-{slug(c)}"><h3 id="h-{slug(c)}">'
        f'<span aria-hidden="true">{by_c[c][0].get("flag", "")}</span> {e(c)} <span class="cp-count">{plural(len(by_c[c]), "instrument")}</span></h3>'
        f'<div class="fx-cards">{"".join(card(r) for r in by_c[c])}</div></section>' for c in countries)
    chips = '<button type="button" class="chip" data-f="" aria-pressed="true">All types</button>' + "".join(
        f'<button type="button" class="chip" data-f="{slug(t)}" aria-pressed="false" title="{e(TYPE_NOTE[t])}">{e(t)} <span class="n">{per_type[t]}</span></button>' for t in TYPES)
    notes = "".join(f"<li><strong>{e(t)}</strong>: {e(TYPE_NOTE[t])}</li>" for t in TYPES)

    body = f"""<nav class="cp-crumbs" aria-label="Breadcrumb"><a href="../">Apprentix</a> <span aria-hidden="true">›</span> <span aria-current="page">Who pays for apprenticeships?</span></nav>
<header class="in-head">
  <div class="mono">Financing</div>
  <h1>Who pays for apprenticeships?</h1>
  <p class="lede">Governments help pay for apprenticeships in four ways. This page shows which of {len(recs)} instruments in Cedefop’s database each of {len(countries)} countries and regions uses, and what each one pays for.</p>
  <ul class="fx-notes">{notes}</ul>
</header>

<section class="cp-sec" id="matrix" aria-labelledby="h-matrix">
  <h2 id="h-matrix">Instruments by type and country</h2>
  <p class="sub">Dot size: number of instruments. Choose a type to highlight the countries that use it; select a country to see its instruments.</p>
  <div class="chips fx-filter" role="group" aria-label="Highlight a type">{chips}</div>
  <div class="cp-table fx-wrap"><table class="fx-matrix" id="fx-matrix">
    <caption class="oc-sr">Financing instruments by type and country</caption>
    <thead><tr><th scope="col">Country or region</th>{head}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table></div>
</section>

<section class="cp-sec" id="instruments" aria-labelledby="h-instruments">
  <h2 id="h-instruments">Every instrument, by country</h2>
  {groups}
</section>
<p class="provenance">Source: <a href="{e(src['url'])}" target="_blank" rel="noopener">{e(src['name'])}</a>. The database describes instruments as researched in 2016–17; some may have changed or ended since. See the <a href="datasets/financing-instruments.html">dataset page</a> for the fields and downloads.</p>
<script>
(() => {{
  const chips = [...document.querySelectorAll('.fx-filter .chip')];
  const rows = [...document.querySelectorAll('#fx-matrix tbody tr')], cards = [...document.querySelectorAll('.fx-card')];
  const table = document.getElementById('fx-matrix');
  chips.forEach(c => c.addEventListener('click', () => {{
    const f = c.dataset.f;
    chips.forEach(x => x.setAttribute('aria-pressed', String(x === c)));
    table.dataset.on = f;
    rows.forEach(r => r.classList.toggle('fx-dim', !!f && !r.dataset.types.split(' ').includes(f)));
    cards.forEach(k => k.hidden = !!f && !k.dataset.types.split(' ').includes(f));
    document.querySelectorAll('.fx-country').forEach(s => s.hidden = ![...s.querySelectorAll('.fx-card')].some(k => !k.hidden));
  }}));
}})();
</script>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": page_url, "url": page_url, "name": "Who pays for apprenticeships?", "dateModified": updated},
        website(), breadcrumb([("Apprentix", SITE), ("Who pays for apprenticeships?", page_url)], page_url)]}
    html = page(title="Who pays for apprenticeships? Financing instruments in Europe — Apprentix",
                description=f"Grants, tax incentives, learner grants and training funds: {len(recs)} instruments that help pay for apprenticeships in {len(countries)} European countries and regions.",
                canonical=page_url, root="../", body=body, json_ld_obj=ld, current=None, updated=updated)
    return [str(OUT)] if write_text(OUT, html) else []


if __name__ == "__main__":
    print(render())
