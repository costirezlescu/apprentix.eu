"""The Occupation lens pages, from data/published/occupations/occupations.json (pipeline/occupations.py).

  pages/occupations/index.html          "Want to be …?": every occupation in the lens
  pages/occupations/<slug>.html         one page per occupation: where you can qualify, at which
                                        EQF level, through which qualifications, and the job outlook

Plain static HTML (no JavaScript needed), deterministic, rewritten only when content changes.

Run on its own with:  python -m pipeline.render_occupations
"""

from __future__ import annotations

import math

from .common import DATA, PUBLISHED, REFERENCE, ROOT, read_json
from .render_pages import SITE, breadcrumb, e, page, plural, tile_map, website, write_text

SRC = PUBLISHED / "occupations" / "occupations.json"
OUT = ROOT / "pages" / "occupations"
LEVELS = [2, 3, 4, 5]
LEVEL_HINT = {
    2: "basic vocational skills",
    3: "skilled worker, often a 2–3-year vocational programme",
    4: "vocational upper secondary school or apprenticeship; often opens the way to further study",
    5: "higher vocational training, master craftsperson or specialist",
}
SHOWN = 5  # qualifications listed before "show all"
LANG = {
    "bg": "Bulgarian", "cs": "Czech", "da": "Danish", "de": "German", "el": "Greek", "en": "English",
    "es": "Spanish", "et": "Estonian", "fi": "Finnish", "fr": "French", "ga": "Irish", "hr": "Croatian",
    "hu": "Hungarian", "is": "Icelandic", "it": "Italian", "lt": "Lithuanian", "lv": "Latvian", "mt": "Maltese",
    "nl": "Dutch", "no": "Norwegian", "pl": "Polish", "pt": "Portuguese", "ro": "Romanian", "sk": "Slovak",
    "sl": "Slovenian", "sv": "Swedish",
}


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def fmt_pct(v: float) -> str:
    return f"{v:+.1f}%".replace("-", "−")


def country_link(code: str, frag: str = "") -> str:
    return f"../countries/{code.lower()}.html{frag}"


# ---------------------------------------------------------------- parts --

def level_matrix(o: dict, flags: dict) -> str:
    """Countries × EQF levels. Dot area follows the number of qualifications; a ring marks levels
    with qualifications the register flags as apprenticeship. A real table, so it reads without the dots."""
    peak = max((n for c in o["countries"] for n in c["levels"].values()), default=1)
    rows = []
    for c in o["countries"]:
        appr_levels = {q["eqf"] for q in c["qualifications"] if q.get("apprenticeship")}
        cells = []
        for lv in LEVELS:
            n = c["levels"].get(str(lv), 0)
            if not n:
                cells.append('<td class="oc-cell oc-none"><span class="oc-sr">none</span></td>')
                continue
            size = 10 + 26 * math.sqrt(n / peak)
            ring = " oc-appr" if lv in appr_levels else ""
            note = " (some flagged as apprenticeship)" if ring else ""
            cells.append(f'<td class="oc-cell"><span class="oc-dot{ring}" style="--d:{size:.0f}px" aria-hidden="true"></span>'
                         f'<span class="oc-n">{n}</span><span class="oc-sr"> qualification{"s" if n != 1 else ""} at EQF {lv}{note}</span></td>')
        rows.append(f'<tr><th scope="row"><a href="#c-{c["code"].lower()}">{flags.get(c["code"], "")} {e(c["name"])}</a></th>{"".join(cells)}</tr>')
    head = "".join(f'<th scope="col"><abbr title="{e(LEVEL_HINT[lv])}">EQF {lv}</abbr></th>' for lv in LEVELS)
    return f"""<div class="oc-matrix-wrap">
<table class="oc-matrix">
  <caption class="oc-sr">Qualifications for {e(o["with_article"])} by country and EQF level</caption>
  <thead><tr><th scope="col">Country</th>{head}</tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>
</div>
<p class="oc-legend"><span class="oc-dot" style="--d:12px" aria-hidden="true"></span> number of distinct qualifications (dot area) ·
<span class="oc-dot oc-appr" style="--d:12px" aria-hidden="true"></span> includes qualifications the register flags as apprenticeship.
EQF 2 {e(LEVEL_HINT[2])}; EQF 3 {e(LEVEL_HINT[3])}; EQF 4 {e(LEVEL_HINT[4])}; EQF 5 {e(LEVEL_HINT[5])}.</p>"""


def qual_li(q: dict) -> str:
    tags = f'<span class="oc-eqf">EQF {q["eqf"]}</span>'
    if q.get("apprenticeship"):
        tags += '<span class="oc-tag">Apprenticeship</span>'
    title = e(q["title"])
    link = f'<a href="{e(q["url"])}" target="_blank" rel="noopener">{title}</a>' if q.get("url") else title
    orig = f'<span class="oc-orig" lang="">{e(q["title_original"])}</span>' if q.get("title_original") else ""
    return f'<li>{tags}<span class="oc-qt">{link}{orig}</span></li>'


def country_card(c: dict, flags: dict, the: str) -> str:
    qs = c["qualifications"]
    first = "".join(qual_li(q) for q in qs[:SHOWN])
    more = ""
    if len(qs) > SHOWN:
        more = (f'<details class="oc-more"><summary>All {len(qs)} qualifications</summary>'
                f'<ul class="oc-quals">{"".join(qual_li(q) for q in qs[SHOWN:])}</ul></details>')
    levels = " · ".join(f'EQF {lv}: {n}' for lv, n in c["levels"].items())
    appr = f' · {c["apprenticeship"]} flagged as apprenticeship' if c["apprenticeship"] else ""
    links = []
    for s in c["schemes"]:
        links.append(f'<a href="{country_link(c["code"], "#scheme-" + s["id"])}">{e(s["name"])}</a>')
    scheme_line = (f'<p class="oc-schemes"><span class="mono">Apprenticeship schemes</span> {" · ".join(links)}</p>'
                   if links else "")
    find = (f'<a class="btn" href="{country_link(c["code"], "#find")}">Find an apprenticeship in {e(the)} →</a>'
            if c["find"] else f'<a class="btn" href="{country_link(c["code"])}">About {e(the)} →</a>')
    return f"""<article class="panel oc-country" id="c-{c["code"].lower()}">
  <h3><span class="oc-flag" aria-hidden="true">{flags.get(c["code"], "")}</span> {e(c["name"])} <span class="cp-count">{plural(c["count"], "qualification")}</span></h3>
  <p class="oc-meta">{levels}{appr}</p>
  <ul class="oc-quals">{first}</ul>
  {more}
  {scheme_line}
  <div class="cp-links">{find}</div>
</article>"""


def outlook_html(o: dict, flags: dict) -> str:
    out = o.get("outlook")
    if not out or not out["rows"]:
        return ""
    peak = max(abs(r["value"]) for r in out["rows"]) or 1
    rows = []
    for r in out["rows"]:
        w = 50 * abs(r["value"]) / peak
        side = "pos" if r["value"] >= 0 else "neg"
        rows.append(f'<li class="oc-bar-row"><span class="oc-bar-name">{flags.get(r["geo"], "")} {e(r["name"])}</span>'
                    f'<span class="oc-bar-track"><span class="oc-bar oc-{side}" style="--w:{w:.1f}%"></span></span>'
                    f'<span class="oc-bar-val">{fmt_pct(r["value"])}</span></li>')
    eu = (f' In the EU as a whole: <strong>{fmt_pct(out["eu"])}</strong>.' if out.get("eu") is not None else "")
    return f"""<section class="cp-sec" id="outlook" aria-labelledby="h-outlook">
  <h2 id="h-outlook">Job outlook</h2>
  <p class="sub">This occupation belongs to the ISCO major group <strong>{e(out["isco_major"])} {e(out["isco_major_title"])}</strong>. Cedefop’s short-term forecast for employment in that whole group in {e(out["year"])}, per country:{eu}</p>
  <ul class="oc-bars" aria-label="Forecast employment change in {e(out['year'])}, ISCO group {e(out['isco_major'])}">{"".join(rows)}</ul>
  <p class="provenance">A forecast for the broad group, not for this occupation alone, and growth is not the same as job openings: people retiring also need replacing. Source: Cedefop STAS short-term projections; <a href="../indicators/{e(out["indicator"])}.html">see the indicator</a>.</p>
</section>"""


def names_html(o: dict) -> str:
    labels = o["esco"]["labels"]
    if not labels:
        return ""
    items = "".join(f'<div class="row"><div class="k">{e(LANG.get(l, l))}</div><div lang="{e(l)}">{e(v)}</div></div>'
                    for l, v in sorted(labels.items(), key=lambda kv: LANG.get(kv[0], kv[0])))
    return f"""<section class="cp-sec" id="names" aria-labelledby="h-names">
  <h2 id="h-names">What it is called across Europe</h2>
  <p class="sub">ESCO’s preferred term in each language. Useful when you search for training or jobs in another country; national qualification titles can differ.</p>
  <div class="kv oc-names">{items}</div>
</section>"""


def skills_html(o: dict) -> str:
    s = o["esco"]
    if not s["skills"]:
        return ""
    chips = "".join(f'<li class="chip">{e(x)}</li>' for x in s["skills"])
    more = s["skills_total"] - len(s["skills"])
    rel = ""
    if s["related"]:
        rel = " Related ESCO occupation" + ("s" if len(s["related"]) > 1 else "") + ": " + ", ".join(
            f'<a href="{e(r["uri"])}" target="_blank" rel="noopener">{e(r["label"])}</a>' for r in s["related"]) + "."
    isco = (f' ISCO-08 unit group {e(s["isco_unit"])}' + (f' “{e(s["isco_unit_title"])}”' if s.get("isco_unit_title") else "") + ".") if s.get("isco_unit") else ""
    return f"""<section class="cp-sec" id="skills" aria-labelledby="h-skills">
  <h2 id="h-skills">What the work involves</h2>
  <p class="sub">{e(s["description"] or "")}</p>
  <ul class="chips oc-skills" aria-label="Essential skills in ESCO">{chips}</ul>
  {shares_line(o)}
  <p class="oc-meta">{f"And {more} more essential skills. " if more > 0 else ""}From ESCO, the European classification of skills and occupations: <a href="{e(s["uri"])}" target="_blank" rel="noopener">{e(s["label"])} ({e(s["code"])})</a>.{isco}{rel}</p>
</section>"""


def shares_line(o: dict) -> str:
    sh = [x for x in o.get("shares", []) if x["n"] >= 2]
    if not sh:
        return ""
    links = ", ".join(f'<a href="{x["slug"]}.html" title="{e("; ".join(x["skills"]))}">{e(x["name"].lower())} ({x["n"]})</a>' for x in sh)
    return f'<p class="oc-shares"><strong>Shares essential skills with:</strong> {links}. <a href="./#skills">All shared skills</a></p>'


def shared_matrix(doc: dict) -> str:
    sh = doc.get("shared_skills") or {}
    if not sh.get("skills"):
        return ""
    head = "".join(f'<th scope="col"><span title="{e(k["title"])}">{e(k["title"])}</span></th>' for k in sh["skills"])
    rows = "".join(
        f'<tr><th scope="row"><a href="{r["slug"]}.html">{e(r["name"])}</a></th>'
        + "".join(f'<td>{"<span class=oc-skdot aria-label=essential></span>" if h else ""}</td>' for h in r["has"]) + "</tr>"
        for r in sh["rows"])
    return f"""<section class="cp-sec" id="skills" aria-labelledby="h-skills">
  <h2 id="h-skills">Skills shared across trades</h2>
  <p class="sub">The {len(sh["skills"])} ESCO skills that appear in the most occupation profiles here. A dot means the skill is essential for that occupation: safety, measuring, reading plans and serving customers carry over from one trade to another.</p>
  <div class="cp-table oc-sk-wrap"><table class="oc-sk">
    <caption class="oc-sr">Essential ESCO skills shared by several occupations</caption>
    <thead><tr><th scope="col">Occupation</th>{head}</tr></thead><tbody>{rows}</tbody></table></div>
  <p class="provenance">From ESCO, the European classification of skills and occupations. This service uses the ESCO classification of the European Commission.</p>
</section>"""


def elsewhere_html(o: dict, flags: dict) -> str:
    rows = o["schemes_no_qdr"]
    if not rows:
        return ""
    items = "".join(f'<li><a href="{country_link(r["code"], "#find" if r["find"] else "")}">{flags.get(r["code"], "")} {e(r["name"])}</a></li>'
                    for r in rows)
    return f"""<section class="cp-sec" id="elsewhere" aria-labelledby="h-elsewhere">
  <h2 id="h-elsewhere">Other countries with apprenticeships</h2>
  <p class="sub">These countries have apprenticeship schemes but do not yet publish their vocational qualifications to Europass, so they cannot be searched here. Their pages link to official services where you can look for {e(o["with_article"].split(" ", 1)[1])} apprenticeship.</p>
  <ul class="cp-more">{items}</ul>
</section>"""


# ---------------------------------------------------------------- pages --

def occupation_page(o: dict, doc: dict, D: dict) -> str:
    flags, countries = D["flags"], D["countries"]
    slug, s = o["slug"], o["summary"]
    page_url = f"{SITE}pages/occupations/{slug}.html"
    found = {c["code"] for c in o["countries"]}
    tmap = tile_map(countries, found, None, "../countries/")
    lv = s["levels"]
    lv_txt = f"EQF {lv[0]}–{lv[-1]}" if len(lv) > 1 else (f"EQF {lv[0]}" if lv else "")
    top = o["countries"][:3]
    lede = (f"{o['esco']['description'] or ''} Below: every qualification for {o['with_article']} that "
            f"{len(doc['qdr_countries'])} European countries publish to Europass, at which level, and where to look for an apprenticeship.")
    the = lambda c: ("the " if c["code"] in ("NL", "UK") else "") + c["name"]
    cards = "".join(country_card(c, flags, the(c)) for c in o["countries"])
    stats = f"""<dl class="oc-stats">
  <div><dt>Qualifications</dt><dd>{s["qualifications"]}</dd></div>
  <div><dt>Countries</dt><dd>{s["countries"]}</dd></div>
  <div><dt>Levels</dt><dd>{e(lv_txt)}</dd></div>
</dl>"""
    note = f'<p class="oc-note">{e(o["note"])}</p>' if o.get("note") else ""
    toc = [("where", "Where and at which level"), ("countries", "Country by country"), ("skills", "The work")]
    if o["esco"]["labels"]:
        toc.append(("names", "Names across Europe"))
    if o.get("outlook"):
        toc.append(("outlook", "Job outlook"))
    toc_html = "".join(f'<li><a href="#{k}">{v}</a></li>' for k, v in toc)
    others = "".join(f'<li><a href="{x["slug"]}.html">{e(x["name"])}</a></li>' for x in doc["occupations"] if x["slug"] != slug)
    src = doc["sources"]
    no_match = ", ".join(c["name"] for c in o["qdr_no_match"])
    body = f"""<nav class="cp-crumbs" aria-label="Breadcrumb"><a href="../../">Apprentix</a> <span aria-hidden="true">›</span> <a href="./">Occupations</a> <span aria-hidden="true">›</span> <span aria-current="page">{e(o["name"])}</span></nav>
<header class="cp-head oc-head">
  <div>
    <div class="mono cp-group">Occupation lens</div>
    <h1>Want to be <span class="h-accent">{e(o["with_article"])}?</span></h1>
    <p class="lede">{e(lede)}</p>
    {note}
    {stats}
    <ul class="cp-toc" aria-label="On this page">{toc_html}</ul>
  </div>
  <div class="cp-mapbox-lg" aria-hidden="true">{tmap}<p class="oc-maphint">Highlighted: countries with matching qualifications</p></div>
</header>

<section class="cp-sec" id="where" aria-labelledby="h-where">
  <h2 id="h-where">Where you can qualify, and at which level</h2>
  <p class="sub">{e(cap(o["name"]))} qualifications in {s["countries"]} countries; the most in {e(", ".join(c["name"] for c in top))}. The European Qualifications Framework (EQF) puts each one on a common scale, so you can compare levels across countries.</p>
  {level_matrix(o, flags)}
</section>

<section class="cp-sec" id="countries" aria-labelledby="h-countries">
  <h2 id="h-countries">Country by country</h2>
  <p class="sub">Each title links to its official Europass record. Qualifications marked <span class="oc-tag">Apprenticeship</span> are named as apprenticeships in the register; for the others the route is not stated, and many can also be obtained through an apprenticeship.</p>
  <div class="oc-grid">{cards}</div>
</section>

{elsewhere_html(o, flags)}
{skills_html(o)}
{names_html(o)}
{outlook_html(o, flags)}

<section class="cp-sec" id="method" aria-labelledby="h-method">
  <h2 id="h-method">How this page is made</h2>
  <p class="sub">{e(doc["method"])}{f" No match in: {e(no_match)}." if no_match else ""}</p>
  <p class="provenance">Qualifications: <a href="{e(src["qualifications"]["url"])}" target="_blank" rel="noopener">{e(src["qualifications"]["name"])}</a>, retrieved {e(src["qualifications"]["retrieved"] or "")}; <a href="../datasets/{e(src["qualifications"]["dataset"])}.html">the full dataset on Apprentix</a>. {e(src["esco"]["acknowledgement"])} The matching patterns are open: <a href="https://github.com/costirezlescu/apprentix.eu/blob/main/data/reference/occupation-lens.json">data/reference/occupation-lens.json</a>.</p>
</section>

<section class="cp-sec" aria-labelledby="h-other">
  <h2 id="h-other">Other occupations</h2>
  <ul class="cp-more">{others}</ul>
  <p><a href="./">All occupations</a></p>
</section>"""
    desc = (f"Want to be {o['with_article']}? {s['qualifications']} vocational qualifications in {s['countries']} European countries "
            f"({lv_txt}), with the apprenticeship routes, official links and the job outlook.")
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": page_url, "url": page_url, "name": f"Want to be {o['with_article']}?", "description": desc,
         "about": {"@type": "Occupation", "name": o["esco"]["label"], "description": o["esco"]["description"],
                   "occupationalCategory": {"@type": "CategoryCode", "codeValue": o["esco"]["isco_unit"], "inCodeSet": "ISCO-08"},
                   "sameAs": o["esco"]["uri"]},
         "dateModified": D["updated"]},
        website(), breadcrumb([("Apprentix", SITE), ("Occupations", SITE + "pages/occupations/"), (o["name"], page_url)], page_url)]}
    return page(title=f"Want to be {o['with_article']}? Qualifications across Europe — Apprentix", description=desc,
                canonical=page_url, root="../../", body=body, json_ld_obj=ld, current="occupations", updated=D["updated"])


def index_page(doc: dict, D: dict) -> str:
    page_url = f"{SITE}pages/occupations/"
    cards = []
    for o in doc["occupations"]:
        s = o["summary"]
        cards.append(f"""<li><a class="oc-card" href="{o["slug"]}.html">
  <span class="oc-card-q">Want to be {e(o["with_article"])}?</span>
  <span class="oc-card-meta">{s["qualifications"]} qualifications · {s["countries"]} countries · EQF {s["levels"][0]}–{s["levels"][-1]}</span>
</a></li>""")
    qdr = ", ".join(c["name"] for c in doc["qdr_countries"])
    body = f"""<nav class="cp-crumbs" aria-label="Breadcrumb"><a href="../../">Apprentix</a> <span aria-hidden="true">›</span> <span aria-current="page">Occupations</span></nav>
<header class="in-head">
  <div class="mono">Occupation lens</div>
  <h1>What do you want to be?</h1>
  <p class="lede">Pick an occupation to see where in Europe you can qualify for it, at which level, through which national qualifications, and where to look for an apprenticeship. Built from the qualifications {len(doc["qdr_countries"])} countries publish to Europass, linked to ESCO, the European classification of occupations.</p>
</header>
<ul class="oc-cards">{"".join(cards)}</ul>
{shared_matrix(doc)}
<p class="provenance">Countries covered by the qualification register so far: {e(qdr)}. Other countries’ apprenticeships are on their <a href="../countries/">country pages</a>. Looking for an occupation that is not here? Search all {D["qual_total"]:,} national vocational qualifications in the <a href="../datasets/vet-qualifications.html">qualifications dataset</a>.</p>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": page_url, "url": page_url, "name": "Occupation lens", "dateModified": D["updated"],
         "hasPart": [{"@type": "WebPage", "url": f"{page_url}{o['slug']}.html", "name": f"Want to be {o['with_article']}?"} for o in doc["occupations"]]},
        website(), breadcrumb([("Apprentix", SITE), ("Occupations", page_url)], page_url)]}
    return page(title="Occupation lens: what do you want to be? — Apprentix",
                description="Electrician, cook, carpenter, software developer…: where in Europe you can qualify for each occupation, at which EQF level, and where to look for an apprenticeship.",
                canonical=page_url, root="../../", body=body, json_ld_obj=ld, current="occupations", updated=D["updated"])


def render_all() -> tuple[list, list[tuple[str, str]]]:
    if not SRC.exists():
        return [], []
    doc = read_json(SRC)
    ref = read_json(REFERENCE / "countries.json")
    D = {"flags": {c["code"]: c.get("flag", "") for c in ref["countries"]},
         "countries": [c for c in ref["countries"] if c["group"] != "aggregate"],
         "updated": read_json(DATA / "datasets.json")["site"].get("updated", ""),
         "qual_total": len(read_json(PUBLISHED / "vet-qualifications" / "records.json"))}
    written, urls, expected = [], [], {"index.html"}
    for o in doc["occupations"]:
        path = OUT / f"{o['slug']}.html"
        expected.add(path.name)
        if write_text(path, occupation_page(o, doc, D)):
            written.append(path)
        urls.append((f"{SITE}pages/occupations/{o['slug']}.html", D["updated"]))
    if write_text(OUT / "index.html", index_page(doc, D)):
        written.append(OUT / "index.html")
    urls.insert(0, (f"{SITE}pages/occupations/", D["updated"]))
    for p in OUT.glob("*.html"):
        if p.name not in expected:
            p.unlink()
            written.append(p)
    return written, urls


if __name__ == "__main__":
    w, _ = render_all()
    print(f"Rendered occupation lens: {len(w)} file(s) changed")
