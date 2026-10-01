"""Render pages/insights.html from data/published/insights/insights.json.

Everything a reader needs — findings, details, method, caveats, sources and a
data table for every chart — is static HTML (crawlable, readable without JS).
assets/js/insights.js draws the charts on top and wires the audience filter.
"""

from __future__ import annotations

from .common import DATA, PUBLISHED, ROOT, read_json
from .render_pages import SITE, breadcrumb, e, page, website, write_text

OUT = ROOT / "pages" / "insights.html"
AUDIENCES = [("all", "Everything"), ("policy", "For decision-makers"), ("learners", "For learners"), ("employers", "For employers")]


def table_for(chart: dict | None) -> str:
    if not chart:
        return ""
    t = chart["type"]
    if t == "scatter":
        head = f"<tr><th>Country</th><th class=\"num\">{e(chart['x']['label'])}</th><th class=\"num\">{e(chart['y']['label'])}</th></tr>"
        body = "".join(f"<tr><td>{e(p['name'])}</td><td class=\"num\">{p['x']:.1f}</td><td class=\"num\">{p['y']:.1f}</td></tr>"
                       for p in sorted(chart["points"], key=lambda p: -p["x"]))
    elif t == "target-bars":
        parts = []
        for panel in chart["panels"]:
            rows = "".join(f"<tr><td>{e(r['name'])}</td><td class=\"num\">{r['value']:.1f}{(' ' + e(r['flag'])) if r.get('flag') else ''}</td></tr>" for r in panel["rows"])
            parts.append(f"<table class=\"data\"><caption>{e(panel['title'])} (target {panel['target']}%; EU-27 {panel['eu']:.1f}%)</caption><thead><tr><th>Country</th><th class=\"num\">%</th></tr></thead><tbody>{rows}</tbody></table>")
        return "".join(parts)
    elif t == "paired-bars":
        g = chart["groups"]
        head = f"<tr><th>Feature</th><th class=\"num\">{e(g[0])}</th><th class=\"num\">{e(g[1])}</th></tr>"
        body = "".join(f"<tr><td>{e(r['label'])}</td><td class=\"num\">{r['employer']}%</td><td class=\"num\">{r['school']}%</td></tr>" for r in chart["rows"])
    elif t == "bars":
        head = f"<tr><th></th><th class=\"num\">{e(chart.get('unit', ''))}</th></tr>"
        body = "".join(f"<tr><td>{e(r['label'])}</td><td class=\"num\">{r['value']:,}</td></tr>" for r in chart["rows"])
    elif t == "lines":
        times = sorted({p["time"] for s in chart["series"] for p in s["points"]})
        head = "<tr><th>Year</th>" + "".join(f"<th class=\"num\">{e(s['label'])}</th>" for s in chart["series"]) + "</tr>"
        body = ""
        for tm in times:
            cells = []
            for s in chart["series"]:
                v = next((p["value"] for p in s["points"] if p["time"] == tm), None)
                cells.append(f"<td class=\"num\">{'' if v is None else f'{v:,.1f}'}</td>")
            body += f"<tr><td>{e(tm)}</td>{''.join(cells)}</tr>"
    elif t == "level-strip":
        head = "<tr><th>Country</th><th>Qualification</th><th class=\"num\">EQF</th></tr>"
        body = "".join(f"<tr><td>{e(r['name'])}</td><td>{e(r['label'])}</td><td class=\"num\">{r['eqf']}</td></tr>" for r in chart["rows"])
    else:
        return ""
    return f"<table class=\"data\"><thead>{head}</thead><tbody>{body}</tbody></table>"


def card(i: dict, idx: int) -> str:
    aud = " ".join(i.get("audience", []))
    tags = "".join(f'<span class="in-tag">{e(dict(AUDIENCES).get(a, a))}</span>' for a in i.get("audience", []))
    details = "".join(f"<li>{e(d)}</li>" for d in i.get("detail", []))
    caveats = "".join(f"<li>{e(c)}</li>" for c in i.get("caveats", []))
    sources = " · ".join(f'<a href="../{e(s["url"])}">{e(s["label"])}</a>' for s in i.get("sources", []))
    chart = i.get("chart")
    return f"""<article class="in-card" id="{e(i['id'])}" data-audience="{e(aud)}">
  <div class="in-tags">{tags}</div>
  <h2><a href="#{e(i['id'])}">{e(i['title'])}</a></h2>
  <p class="in-finding">{e(i['finding'])}</p>
  {f'<div class="in-chart" data-chart="{idx}" role="img" aria-label="Chart: {e(i["title"])}"></div>' if chart else ''}
  {f'<ul class="in-detail">{details}</ul>' if details else ''}
  {f'<details class="in-data"><summary>Data behind this chart</summary><div class="in-table">{table_for(chart)}</div></details>' if chart else ''}
  <details class="in-method"><summary>Method and caveats</summary>
    <p>{e(i.get('method', ''))}</p>
    {f'<ul>{caveats}</ul>' if caveats else ''}
  </details>
  <p class="in-sources">Sources: {sources}</p>
</article>"""


def render_insights() -> list[str]:
    path = PUBLISHED / "insights" / "insights.json"
    if not path.exists():
        return []
    items = read_json(path)["items"]
    manifest = read_json(DATA / "datasets.json")
    updated = manifest["site"].get("updated", "")
    page_url = f"{SITE}pages/insights.html"
    chips = "".join(f'<button type="button" class="chip" data-aud="{k}" aria-pressed="{str(k == "all").lower()}">{e(v)}</button>' for k, v in AUDIENCES)
    toc = "".join(f'<li><a href="#{e(i["id"])}">{e(i["title"])}</a></li>' for i in items)
    body = f"""<nav class="cp-crumbs" aria-label="Breadcrumb"><a href="../">Apprentix</a> <span aria-hidden="true">›</span> <span aria-current="page">Insights</span></nav>
<header class="in-head">
  <div class="mono">Analysis</div>
  <h1>Insights</h1>
  <p class="lede">What the data on European apprenticeships says when you put the sources side by side. Every number below is recomputed from the published data whenever the sources update, and every finding links to its data, method and caveats.</p>
  <div class="chips in-filter" role="group" aria-label="Show insights for">{chips}</div>
  <details class="in-toc"><summary>All {len(items)} insights</summary><ol>{toc}</ol></details>
</header>
<div class="in-list">
{chr(10).join(card(i, n) for n, i in enumerate(items))}
</div>
<p class="provenance">These are descriptive analyses of public data by Apprentix, not official statistics. Associations between countries do not show cause and effect. Last computed {e(updated)}; the computation is open: <a href="https://github.com/costirezlescu/apprentix.eu/blob/main/pipeline/insights.py">pipeline/insights.py</a>.</p>
<script type="module" src="../assets/js/insights.js"></script>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Article", "@id": page_url + "#article", "headline": "Insights on apprenticeships in Europe",
         "description": items[0]["finding"] if items else "", "url": page_url, "dateModified": updated,
         "publisher": {"@type": "Organization", "name": "Apprentix", "url": SITE},
         "about": [{"@type": "Thing", "name": "Apprenticeship"}, {"@type": "Thing", "name": "Vocational education and training"}]},
        website(), breadcrumb([("Apprentix", SITE), ("Insights", page_url)], page_url)]}
    html = page(title="Insights on apprenticeships in Europe — Apprentix",
                description="What European data on apprenticeships says: EU targets, work-based learning and jobs, scheme families, national trends, financing, mobility and data gaps.",
                canonical=page_url, root="../", body=body, json_ld_obj=ld, current="insights", updated=updated)
    changed = write_text(OUT, html)
    return [str(OUT)] if changed else []
