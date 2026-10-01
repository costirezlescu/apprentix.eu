"""Pre-rendered country profile pages, sitemap.xml and robots.txt.

  pages/countries/index.html        every country with content, grouped
  pages/countries/<code>.html       one profile per country (schemes, key figures,
                                    national statistics, policies, open datasets)
  pages/indicators/, pages/datasets/, data/feed.xml, the DataCatalog block in
  pages/data.html                   see render_datasets.py (called from here)
  sitemap.xml, robots.txt           at the repository root

Plain static HTML generated from data/published/, so crawlers and visitors without
JavaScript see the full content. Output is deterministic: the only dates written
are data-driven (data/datasets.json site.updated, indicator retrieval dates), and
files are rewritten only when their content changes.

Run on its own with:  python -m pipeline.render_pages
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode

from .common import DATA, INDICATORS, LICENCES, PUBLISHED, REFERENCE, ROOT, geo_code, read_json

SITE = "https://apprentix.eu/"
OUT = ROOT / "pages" / "countries"
FEED_PATH = "data/feed.xml"
FONTS = ("https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600"
         "&family=Public+Sans:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap")

# Indicators shown under "Key figures", in this order. Each entry lists alternatives
# measuring the same thing: the first one with data for the country is shown.
KEY_FIGURES = [
    ["eurostat-tps00215", "cedefop-kivet-2066"],
    ["eurostat-ed3sw-share-of-vet", "cedefop-kivet-1020", "oecd-share-vet-sw"],
    ["eurostat-educ_uoe_enrs04-ed3sw"],
    ["cedefop-kivet-1010", "uis-gtvp-3-v"],
    ["eurostat-edat_lfse_24-vet", "cedefop-kivet-2080a"],
    ["cedefop-kivet-2090a"],
    ["oecd-emp-rate-upper-secondary"],
    ["eurostat-trng_cvt_34s"],
    ["cedefop-kivet-1026"],
    ["erasmus-ka1-vet-projects"],
    ["cedefop-kivet-3010"],
    ["cedefop-kivet-3030"],
]

GROUPS = [
    ("eu", "EU Member States"),
    ("efta", "EFTA countries"),
    ("candidate", "Candidate and potential candidate countries"),
    ("other", "Other countries"),
]

MAX_POLICIES = 8
THE = {"UK", "NL"}  # names that take "the" in running text


# ---------------------------------------------------------------- helpers --

def e(v) -> str:
    return escape("" if v is None else str(v), quote=True)


def write_text(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def explore_url(dataset: str, filters: list[tuple[str, str]] = (), **extra) -> str:
    """Relative link (from pages/countries/) to the explorer, with ?f.<key>=<value> filters."""
    params = [("dataset", dataset)] + [(f"f.{k}", v) for k, v in filters]
    params += [(k, v) for k, v in extra.items() if v]
    return "../explore.html?" + urlencode(params, quote_via=quote)


def indicator_page_url(ind_id: str, prefix: str = "../indicators/") -> str:
    """Relative link to the static page of an indicator (pages/indicators/<id>.html)."""
    return prefix + quote(ind_id) + ".html"


def indicator_url(ind_id: str, geo: str | None = None) -> str:
    params = [("id", ind_id)] + ([("geo", geo)] if geo else [])
    return "../indicators.html?" + urlencode(params, quote_via=quote)


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def fmt_value(v: float, unit: str | None) -> str:
    u = (unit or "").strip()
    if "%" in u:
        rest = u.replace("%", "", 1).strip()
        return f"{v:,.1f}%" + (f" {rest}" if rest else "")
    if u in ("1000s", "1000 PPS"):
        u = "thousand" + u[4:]
    if v == int(v) and abs(v) >= 10:
        num = f"{v:,.0f}"
    elif abs(v) >= 100:
        num = f"{v:,.0f}"
    elif abs(v) >= 10:
        num = f"{v:,.1f}"
    else:
        num = f"{v:,.2f}".rstrip("0").rstrip(".")
    if u == "EUR":
        return f"EUR {num}"
    return f"{num} {u}".strip()


def licence_html(lic: str | None, url: str | None = None) -> str:
    if not lic:
        return "see source"
    url = url or LICENCES.get(lic)
    return f'<a href="{e(url)}" rel="license noopener" target="_blank">{e(lic)}</a>' if url else e(lic)


def json_ld(obj) -> str:
    s = json.dumps(obj, ensure_ascii=False, indent=1)
    return s.replace("</", "<\\/")


# ---------------------------------------------------------------- page shell --

OG_DEFAULT = "assets/og/site.png"
OG_DEFAULT_ALT = "Apprentix — European apprenticeship and VET data, made searchable."


def og_meta(*, title: str, description: str, url: str, image: str | None = None, alt: str | None = None,
            og_type: str = "website") -> str:
    """Open Graph + Twitter card tags. `image` is a path from the site root (pipeline/og.py)."""
    img = SITE + quote(image or OG_DEFAULT)
    return f"""<meta property="og:type" content="{e(og_type)}">
<meta property="og:site_name" content="Apprentix">
<meta property="og:locale" content="en_GB">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(img)}">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{e(alt or OG_DEFAULT_ALT)}">
<meta name="twitter:card" content="summary_large_image">"""


def page(*, title: str, description: str, canonical: str, root: str, body: str, json_ld_obj,
         current: str | None, updated: str, og_type: str = "website", og_image: str | None = None,
         og_image_alt: str | None = None, head_extra: str = "") -> str:
    def nav(href, label, key):
        cur = ' aria-current="page"' if key == current else ""
        return f'<a href="{href}"{cur}>{label}</a>'
    pages = root + "pages/"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(canonical)}">
{og_meta(title=title, description=description, url=canonical, image=og_image, alt=og_image_alt, og_type=og_type)}
<link rel="stylesheet" href="{FONTS.replace('&', '&amp;')}">
<link rel="stylesheet" href="{root}assets/css/site.css">
<link rel="alternate" type="application/atom+xml" title="Apprentix data updates" href="{root}{FEED_PATH}">
<script type="application/ld+json">
{json_ld(json_ld_obj)}
</script>{chr(10) + head_extra if head_extra else ""}
</head>
<body data-root="{root}">

<a class="skip" href="#main">Skip to content</a>

<div class="indep">
  <div class="wrap">
    <span class="tag">Independent project</span>
    <p>Not affiliated with, or endorsed by, any European institution or agency. Built on publicly available data.</p>
  </div>
</div>

<header class="site-head">
  <div class="wrap head-inner">
    <a class="brand" href="{root}">Apprenti<span class="x">x</span><span class="eu">.eu</span></a>
    <nav class="site-nav">
      {nav(root, "Datasets", "datasets")}
      {nav(pages + "indicators.html", "Indicators", "indicators")}
      {nav(pages + "insights.html", "Insights", "insights")}
      {nav(pages + "countries/", "Countries", "countries")}
      {nav(pages + "ask.html", "Ask", "ask")}
      {nav(pages + "about.html", "About", "about")}
      {nav(pages + "data.html", "Data &amp; sources", "data")}
    </nav>
  </div>
</header>

<main id="main" class="wrap cp">
{body}
</main>

<footer class="site-foot">
  <div class="wrap">
    <div class="rowlinks">
      <a href="{root}">Datasets</a>
      <a href="{pages}indicators.html">Indicators</a>
      <a href="{pages}insights.html">Insights</a>
      <a href="{pages}countries/">Countries</a>
      <a href="{pages}ask.html">Ask</a>
      <a href="{pages}find.html">Find my apprenticeship</a>
      <a href="{pages}duel.html">Compare countries</a>
      <a href="{pages}play.html">Higher or lower?</a>
      <a href="{pages}glossary.html">Glossary</a>
      <a href="{pages}about.html">About</a>
      <a href="{pages}data.html">Data &amp; sources</a>
      <a href="{root}{FEED_PATH}">Updates feed (Atom)</a>
      <a href="https://github.com/costirezlescu/apprentix.eu">Source code</a>
    </div>
    <p><strong>Apprentix</strong> is an independent, non-commercial project. It republishes publicly available information; it does not create or verify it. Each figure and record names its publisher, which remains authoritative.</p>
    <p>Last updated {e(updated)}.</p>
  </div>
</footer>

<script type="module">import {{ initGlossary }} from '{root}assets/js/glossary.js'; initGlossary();</script>
</body>
</html>
"""


def breadcrumb(items: list[tuple[str, str]], page_url: str) -> dict:
    return {
        "@type": "BreadcrumbList",
        "@id": page_url + "#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
            for i, (name, url) in enumerate(items)
        ],
    }


def website() -> dict:
    return {"@type": "WebSite", "@id": SITE + "#website", "name": "Apprentix", "url": SITE}


def tile_map(countries: list[dict], has_page: set[str], current: str | None, link_prefix: str) -> str:
    """Static SVG tile map. Each tile with a page links to it; the current one is highlighted.
    Decorative for assistive tech (aria-hidden): the same links exist as text on every page."""
    tiles = [c for c in countries if c.get("tile")]
    size, gap = 44, 3
    cols = max(c["tile"][0] for c in tiles) + 1
    rows = max(c["tile"][1] for c in tiles) + 1
    out = [f'<svg class="viz cp-map" viewBox="0 0 {cols * (size + gap)} {rows * (size + gap)}" aria-hidden="true" focusable="false">']
    for c in sorted(tiles, key=lambda c: (c["tile"][1], c["tile"][0])):
        x, y = c["tile"][0] * (size + gap), c["tile"][1] * (size + gap)
        cls = "on" if c["code"] == current else ("has" if c["code"] in has_page else "none")
        tile = (f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="4"/>'
                f'<text x="{x + size / 2:g}" y="{y + size / 2 + 4:g}" text-anchor="middle">{e(c["code"])}</text>')
        if c["code"] in has_page and c["code"] != current:
            out.append(f'<a class="{cls}" href="{link_prefix}{c["code"].lower()}.html" tabindex="-1"><title>{e(c["name"])}</title>{tile}</a>')
        else:
            out.append(f'<g class="{cls}"><title>{e(c["name"])}</title>{tile}</g>')
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- data --

def load():
    ref = read_json(REFERENCE / "countries.json")
    manifest = read_json(DATA / "datasets.json")
    index = read_json(INDICATORS / "index.json")["indicators"]
    by_id = {i["id"]: i for i in index}

    def dataset(did):
        p = PUBLISHED / did
        if not (p / "records.json").exists():
            return None, []
        return read_json(p / "meta.json"), read_json(p / "records.json")

    def by_country(records):
        out: dict[str, list] = {}
        for r in records:
            g = geo_code(r.get("country_code") or "")
            if g:
                out.setdefault(g, []).append(r)
        return out

    schemes_meta, schemes = dataset("apprenticeship-schemes")
    policy_meta, policies = dataset("vet-policy-timeline")
    cat_meta, catalogue = dataset("data-catalogue")
    extra = {}
    for did in ("vet-systems", "financing-instruments", "nqf-qualification-levels",
                "recognition-vet-qualifications", "erasmus-vet-organisations", "cove-projects"):
        m, recs = dataset(did)
        extra[did] = {"meta": m, "by_country": by_country(recs), "all": recs}
    # CoVE: by coordinator, and by every participating country (names).
    cove = extra["cove-projects"]
    cove["by_country"] = {}
    names_to_code = {c["name"]: c["code"] for c in ref["countries"]}
    for r in cove["all"]:
        for n in r.get("countries") or []:
            g = names_to_code.get(n)
            if g:
                cove["by_country"].setdefault(g, []).append(r)

    # Latest default-dimension observations for the indicators we show.
    wanted = [i for alts in KEY_FIGURES for i in alts if i in by_id] + [i["id"] for i in index if i.get("national")]
    latest: dict[str, dict] = {}
    for iid in wanted:
        ind = read_json(INDICATORS / f"{iid}.json")
        dims = ind.get("dims") or []
        best: dict[tuple, dict] = {}
        for o in ind["series"]:
            if not all((o.get("dims") or {}).get(d["key"], d.get("default")) == d.get("default") for d in dims):
                continue
            best[(o["geo"], o["time"])] = o
        per_geo: dict[str, dict] = {}
        for (g, t), o in best.items():
            if g not in per_geo or t > per_geo[g]["time"]:
                per_geo[g] = o
        latest[iid] = {"ind": ind, "latest": per_geo, "by_time": best}

    return {
        "ref": ref,
        "countries": [c for c in ref["countries"] if c["group"] != "aggregate"],
        "updated": manifest["site"].get("updated", ""),
        "manifest": manifest,
        "index": index,
        "by_id": by_id,
        "latest": latest,
        "schemes_meta": schemes_meta, "schemes": by_country(schemes),
        "policy_meta": policy_meta, "policies": by_country(policies),
        "cat_meta": cat_meta, "catalogue": by_country(catalogue),
        "extra": extra,
    }


def country_facts(D, code: str) -> dict:
    inds = [i for i in D["index"] if code in (i.get("coverage") or {}).get("geos", [])]
    national = [i for i in inds if i.get("national") and i["coverage"]["geos"] == [code]]
    pols = D["policies"].get(code, [])
    return {
        "schemes": D["schemes"].get(code, []),
        "policies": pols,
        "app_policies": [p for p in pols if p.get("concerns_apprenticeship") == "Yes"],
        "catalogue": D["catalogue"].get(code, []),
        "indicators": inds,
        "national": national,
        **{k.replace("-", "_"): v["by_country"].get(code, []) for k, v in D["extra"].items()},
    }


def has_content(f: dict) -> bool:
    return bool(f["schemes"] or f["policies"] or f["catalogue"] or f["indicators"]
                or f["vet_systems"] or f["nqf_qualification_levels"] or f["erasmus_vet_organisations"])


def record_values(records: list[dict], key: str) -> list[str]:
    """Distinct values of a field (as the explorer filters on them), in first-seen order."""
    seen = []
    for r in records:
        v = r.get(key)
        for x in (v if isinstance(v, list) else [v]):
            if x and x not in seen:
                seen.append(x)
    return seen


# ---------------------------------------------------------------- country page --

def key_figures(D, code: str) -> tuple[list[dict], list[dict]]:
    rows, national = [], []
    for alts in KEY_FIGURES:
        for iid in alts:
            L = D["latest"].get(iid)
            if not L or code not in L["latest"]:
                continue
            o = L["latest"][code]
            eu = L["by_time"].get(("EU27", o["time"]))
            rows.append({"ind": L["ind"], "obs": o, "eu": eu})
            break
    for meta in D["index"]:
        if not meta.get("national") or meta["coverage"]["geos"] != [code]:
            continue
        L = D["latest"].get(meta["id"])
        if L and code in L["latest"]:
            national.append({"ind": L["ind"], "obs": L["latest"][code], "eu": None})
    return rows, national


def flag_html(ind: dict, flag: str | None) -> str:
    if not flag:
        return ""
    label = (ind.get("flags") or {}).get(flag, "")
    return f' <abbr class="cp-flag" title="{e(label or "flag " + flag)}">{e(flag)}</abbr>'


def dims_note(ind: dict) -> str:
    """Describe the default breakdown when it is not simply the total (e.g. 'Vocational …; 25 to 64')."""
    out = []
    for d in ind.get("dims") or []:
        label = (d.get("values") or {}).get(d.get("default"), "")
        if label and not re.match(r"(total|all\b)", label, re.I):
            out.append(label)
    return "; ".join(out)


def figures_table(rows: list[dict], code: str, name: str, with_eu: bool) -> str:
    head = (f'<thead><tr><th scope="col">Indicator</th><th scope="col" class="num">{e(name)}</th>'
            + ('<th scope="col" class="num">EU-27</th>' if with_eu else "")
            + '<th scope="col" class="num">Year</th></tr></thead>')
    body = []
    for r in rows:
        ind, o, eu = r["ind"], r["obs"], r["eu"]
        p = ind.get("provenance", {})
        src = p.get("publisher", "")
        code_ = p.get("dataset_code") or ""
        if code_ and len(code_) <= 30 and not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", code_):
            src += f" · {code_}"
        body.append(
            f'<tr><th scope="row"><a href="{e(indicator_url(ind["id"], code))}">{e(ind["title"])}</a>'
            + (f'<span class="cp-dims">{e(note)}</span>' if (note := dims_note(ind)) else "")
            + f'<span class="cp-src">{e(src)} · <a href="{e(indicator_page_url(ind["id"]))}">about &amp; cite</a></span></th>'
            f'<td class="num"><strong>{e(fmt_value(o["value"], ind.get("unit")))}</strong>{flag_html(ind, o.get("flag"))}</td>'
            + (f'<td class="num">{e(fmt_value(eu["value"], ind.get("unit"))) + flag_html(ind, eu.get("flag")) if eu else "—"}</td>' if with_eu else "")
            + f'<td class="num">{e(o["time"])}</td></tr>')
    return f'<div class="cp-table"><table class="data cp-figures">{head}<tbody>{"".join(body)}</tbody></table></div>'


def sources_line(rows: list[dict]) -> str:
    seen = {}
    for r in rows:
        p = r["ind"].get("provenance", {})
        k = (p.get("publisher"), p.get("licence"))
        seen.setdefault(k, p.get("licence_url"))
    return "; ".join(f"{e(pub)} ({licence_html(lic, url)})" for (pub, lic), url in seen.items())


def scheme_block(s: dict, meta: dict) -> str:
    def row(label, value):
        return f'<div class="row"><div class="k">{e(label)}</div><div>{e(value)}</div></div>' if value else ""
    level = s.get("education_level_detail") or s.get("education_level")
    work = s.get("workplace_time")
    if s.get("workplace_time_detail"):
        work = f"{work} — {s['workplace_time_detail']}" if work else s["workplace_time_detail"]
    region = ""
    if "—" in (s.get("country") or ""):
        region = f'<div class="cp-region">{e(s["country"])}</div>'
    links = [f'<a class="btn" href="{e(explore_url("apprenticeship-schemes", [("country", s["country"])], open=s["id"]))}">Full record</a>',
             f'<a class="btn" href="../compare.html">Compare with all schemes</a>']
    if s.get("source_url"):
        links.append(f'<a class="btn" href="{e(s["source_url"])}" target="_blank" rel="noopener">Cedefop fiche ↗</a>')
    return f"""<article class="panel cp-scheme" id="scheme-{e(s['id'])}">
  {region}<h3>{e(s.get('name_en'))}</h3>
  {f'<p class="cp-orig">{e(s["name_original"])}</p>' if s.get("name_original") else ""}
  {f'<p>{e(s["overview"])}</p>' if s.get("overview") else ""}
  <div class="kv">
    {row("Education level", level)}
    {row("Duration", s.get("duration"))}
    {row("Time at the workplace", work)}
    {row("Apprentice compensation", s.get("compensation"))}
    {row("Pay (as stated)", s.get("compensation_detail"))}
    {row("Apprentices", s.get("learners"))}
    {row("Qualification", s.get("qualification"))}
  </div>
  <div class="cp-links">{"".join(links)}</div>
</article>"""


def policy_sort_key(p: dict):
    return (p.get("latest_year") or "", p.get("first_year") or "", p.get("policy_id") or p["id"])


def render_country(D, c: dict, f: dict, has_page: set[str]) -> str:
    code, name = c["code"], c["name"]
    the_name = ("the " if code in THE else "") + name
    slug = code.lower()
    page_url = f"{SITE}pages/countries/{slug}.html"
    updated = D["updated"]
    figures, national = key_figures(D, code)
    ns, npol, napp, ncat = len(f["schemes"]), len(f["policies"]), len(f["app_policies"]), len(f["catalogue"])
    nind = len(f["indicators"])

    summary_bits = []
    if ns:
        summary_bits.append(plural(ns, "apprenticeship scheme"))
    if npol:
        summary_bits.append(f"{plural(npol, 'VET policy', 'VET policies')} ({napp:,} on apprenticeship)")
    if nind:
        summary_bits.append(plural(nind, "indicator") + " with data")
    if ncat:
        summary_bits.append(plural(ncat, "open dataset"))
    summary = " · ".join(summary_bits) or "No data yet."

    # Meta description from real content.
    desc = [f"Apprenticeships and vocational education in {the_name}:"]
    if ns:
        names = ", ".join(s.get("name_en", "") for s in f["schemes"][:3])
        desc.append(f"{plural(ns, 'scheme')} ({names}),")
    if npol:
        desc.append(f"{plural(npol, 'VET policy', 'VET policies')} since 2015,")
    lead = next((r for r in figures if r["ind"]["id"] in ("eurostat-tps00215", "cedefop-kivet-1010", "uis-gtvp-3-v")), None)
    if lead:
        t = lead["ind"]["title"]
        t = t[0].lower() + t[1:] if t[1:2].islower() else t
        desc.append(f"{nind} indicators — e.g. {t}: "
                    f"{fmt_value(lead['obs']['value'], lead['ind'].get('unit'))} ({lead['obs']['time']}).")
    else:
        desc.append(f"{nind} indicators, with sources and downloads.")
    description = re.sub(r",$", ".", " ".join(desc))

    sections, nav = [], []

    # b. Schemes
    if f["schemes"]:
        sm = D["schemes_meta"]
        src = sm["source"]
        nav.append(("schemes", "Apprenticeship schemes"))
        sections.append(f"""<section class="cp-sec" id="schemes" aria-labelledby="h-schemes">
  <h2 id="h-schemes">Apprenticeship schemes</h2>
  <p class="sub">{e(the_name[0].upper() + the_name[1:])} has {plural(ns, 'mainstream apprenticeship scheme')} in Cedefop's European database on apprenticeship schemes.</p>
  <div class="cp-schemes">{"".join(scheme_block(s, sm) for s in f["schemes"])}</div>
  <p class="provenance">Source: <a href="{e(src['url'])}" target="_blank" rel="noopener">{e(src['name'])}</a>. {e(src.get('caveat', ''))}</p>
</section>""")

    # System, qualifications and recognition (Cedefop VET in Europe, NQF tool, recognition mapping).
    X = D["extra"]
    vs, nq, rc = f["vet_systems"], f["nqf_qualification_levels"], f["recognition_vet_qualifications"]
    if vs or nq or rc:
        nav.append(("system", "System and qualifications"))
        parts = []
        for v in vs:
            links = [f'<a class="btn primary" href="{e(v["source_url"])}" target="_blank" rel="noopener">Read the system description ↗</a>']
            if v.get("spotlight_pdf"):
                links.append(f'<a class="btn" href="{e(v["spotlight_pdf"])}" target="_blank" rel="noopener">Spotlight on VET (PDF) ↗</a>')
            if v.get("system_chart"):
                links.append(f'<a class="btn" href="{e(v["system_chart"])}" target="_blank" rel="noopener">System chart (PDF) ↗</a>')
            parts.append(f'<h3>How VET is organised</h3><p>Cedefop’s VET in Europe database has a detailed description of {e(the_name)}’s VET system ({e(v.get("version", ""))}), written by {e(v.get("refernet_partner", "the national ReferNet partner"))}.</p><p class="cp-links">{"".join(links)}</p>')
        app_q = [q for q in nq if q.get("apprenticeship_or_craft") == "Yes"]
        if nq:
            items = "".join(f'<li>{e(q["qualification_type"])}<span class="cp-meta">National level {e(q.get("nqf_level", ""))} · {e(", ".join(q.get("eqf_level", [])) or "EQF level not stated")}</span></li>' for q in app_q[:10])
            nq_country = record_values(nq, "country")
            parts.append(f'''<h3>Where apprenticeship qualifications sit</h3>
  <p>{e(the_name[0].upper() + the_name[1:])}'s qualifications framework places {plural(len(nq), "qualification type")} on its levels{f"; {len(app_q)} of them are named as apprenticeship or craft qualifications" if app_q else ""}.</p>
  {f'<ul class="cp-list">{items}</ul>' if items else ''}
  <p class="cp-links"><a class="btn" href="{e(explore_url("nqf-qualification-levels", [("country", v) for v in nq_country]))}">All {plural(len(nq), "qualification type")}</a>{f'<a class="btn" href="{e(explore_url("nqf-qualification-levels", [("country", v) for v in nq_country] + [("apprenticeship_or_craft", "Yes")]))}">Apprenticeship and craft only</a>' if app_q else ''}</p>''')
        if rc:
            links = "".join(f'<a class="btn" href="{e(explore_url("recognition-vet-qualifications", [], open=r["id"]))}">{e(r.get("system") or r["country"])}</a>' for r in rc)
            parts.append(f'<h3>Recognising foreign VET qualifications</h3><p>Who informs, who decides and under which law foreign VET qualifications are recognised in {e(the_name)}.</p><p class="cp-links">{links}</p>')
        srcs = [X[k]["meta"]["source"] for k, recs in (("vet-systems", vs), ("nqf-qualification-levels", nq), ("recognition-vet-qualifications", rc)) if recs and X[k]["meta"]]
        sections.append(f"""<section class="cp-sec" id="system" aria-labelledby="h-system">
  <h2 id="h-system">System and qualifications</h2>
  {"".join(parts)}
  <p class="provenance">Sources: {"; ".join(f'<a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["name"])}</a>' for s in srcs)}.</p>
</section>""")

    # Financing (Cedefop financing apprenticeships database, 2016–17).
    fi = f["financing_instruments"]
    if fi:
        nav.append(("financing", "Financing"))
        items = "".join(f'<li><a href="{e(explore_url("financing-instruments", [], open=r["id"]))}">{e(r["title"])}</a><span class="cp-meta">{e(", ".join(r.get("type", [])))}{" · " + e(r["scope"]) if r.get("scope") else ""}</span></li>' for r in fi)
        src = X["financing-instruments"]["meta"]["source"]
        sections.append(f"""<section class="cp-sec" id="financing" aria-labelledby="h-financing">
  <h2 id="h-financing">Financing apprenticeships</h2>
  <p class="sub">{plural(len(fi), "financing instrument")} for apprenticeships in {e(the_name)}, as recorded by Cedefop for 2016–17 (the database has not been updated since).</p>
  <ul class="cp-list">{items}</ul>
  <p class="provenance">Source: <a href="{e(src['url'])}" target="_blank" rel="noopener">{e(src['name'])}</a>.</p>
</section>""")

    # Erasmus+ accredited VET organisations and Centres of Vocational Excellence.
    eo, cv = f["erasmus_vet_organisations"], f["cove_projects"]
    if eo or cv:
        nav.append(("erasmus", "Erasmus+ and excellence"))
        bits = []
        if eo:
            eo_country = record_values(eo, "country")
            bits.append(f'<p>{plural(len(eo), "organisation")} in {e(the_name)} {"holds" if len(eo) == 1 else "hold"} an Erasmus accreditation for vocational education and training (calls 2021–2025).</p><p class="cp-links"><a class="btn primary" href="{e(explore_url("erasmus-vet-organisations", [("country", v) for v in eo_country]))}">Browse accredited organisations</a></p>')
        if cv:
            coord = [r for r in cv if r.get("coordinator_country_code") == code or r.get("coordinator_country") == name]
            bits.append(f'<p>Organisations from {e(the_name)} take part in {plural(len(cv), "Centre of Vocational Excellence project")}{f", coordinating {len(coord)}" if coord else ""}.</p><p class="cp-links"><a class="btn" href="{e(explore_url("cove-projects", [("countries", name)]))}">Browse CoVE projects</a></p>')
        sections.append(f"""<section class="cp-sec" id="erasmus" aria-labelledby="h-erasmus">
  <h2 id="h-erasmus">Erasmus+ and excellence</h2>
  {"".join(bits)}
  <p class="provenance">Source: European Commission, Erasmus+ project results and DG EMPL CoVE participants (CC BY 4.0).</p>
</section>""")

    # c. Key figures
    if figures:
        nav.append(("figures", "Key figures"))
        with_eu = any(r["eu"] for r in figures)
        sections.append(f"""<section class="cp-sec" id="figures" aria-labelledby="h-figures">
  <h2 id="h-figures">Key figures</h2>
  <p class="sub">Latest value for {e(the_name)} on the main measures of vocational education and work-based learning, with the EU-27 figure for the same year where one is published. Select an indicator for its map, ranking, trend and downloads.</p>
  {figures_table(figures, code, name, with_eu)}
  <p class="provenance">Sources: {sources_line(figures)}. Totals only (default breakdown). Letters after a value are the publisher's flags; hover for their meaning.</p>
</section>""")

    # d. National statistics
    if national:
        nav.append(("national", "National statistics"))
        sections.append(f"""<section class="cp-sec" id="national" aria-labelledby="h-national">
  <h2 id="h-national">National statistics</h2>
  <p class="sub">Series from {e(the_name)}'s own statistical sources. Definitions differ from country to country, so these figures should not be compared with other countries'.</p>
  {figures_table(national, code, name, False)}
  <p class="provenance">Sources: {sources_line(national)}.</p>
</section>""")

    # All other indicators with data (links only), so every series for the country is reachable.
    shown = {r["ind"]["id"] for r in figures + national}
    others = sorted((i for i in f["indicators"] if i["id"] not in shown), key=lambda i: (i.get("topic") or "", i["title"]))
    if others:
        nav.append(("more-indicators", "More indicators"))
        items = "".join(
            f'<li><a href="{e(indicator_url(i["id"], code))}">{e(i["title"])}</a>'
            f'<span class="cp-meta">{e((i.get("provenance") or {}).get("publisher", ""))} · {e(i.get("topic") or "")}</span></li>'
            for i in others)
        sections.append(f"""<section class="cp-sec" id="more-indicators" aria-labelledby="h-more-indicators">
  <h2 id="h-more-indicators">More indicators</h2>
  <p class="sub">{plural(len(others), 'further indicator')} {'has' if len(others) == 1 else 'have'} data for {e(the_name)}, each with a map, ranking, trend and downloads.</p>
  <details class="cp-details"{' open' if len(others) <= 6 else ''}><summary>Show {plural(len(others), 'indicator')}</summary><ul class="cp-list cp-cols">{items}</ul></details>
</section>""")

    # e. Policies
    if f["policies"]:
        pm = D["policy_meta"]
        src = pm["source"]
        nav.append(("policies", "Apprenticeship policies"))
        pol_country = record_values(f["policies"], "country")
        recent = sorted(f["app_policies"], key=policy_sort_key, reverse=True)[:MAX_POLICIES]
        items = "".join(
            f'<li><a href="{e(explore_url("vet-policy-timeline", [("country", p["country"])], open=p["id"]))}">{e(p.get("title"))}</a>'
            f'<span class="cp-meta">{e(" · ".join(x for x in (p.get("type"), (p.get("latest_stage") or "") + (f" ({p["latest_year"]})" if p.get("latest_year") else "")) if x))}</span></li>'
            for p in recent)
        all_app = explore_url("vet-policy-timeline", [("country", v) for v in pol_country] + [("concerns_apprenticeship", "Yes")])
        all_pol = explore_url("vet-policy-timeline", [("country", v) for v in pol_country])
        sections.append(f"""<section class="cp-sec" id="policies" aria-labelledby="h-policies">
  <h2 id="h-policies">Recent apprenticeship policies</h2>
  <p class="sub">Cedefop and ReferNet track {plural(npol, 'VET policy', 'VET policies')} in {e(the_name)} since 2015, of which {napp:,} concern apprenticeship or work-based learning.{' The most recently reported:' if recent else ''}</p>
  {f'<ol class="cp-list">{items}</ol>' if recent else ''}
  <p class="cp-links">{f'<a class="btn primary" href="{e(all_app)}">All {napp:,} apprenticeship policies</a>' if napp else ''}<a class="btn" href="{e(all_pol)}">All {npol:,} VET policies</a></p>
  <p class="provenance">Source: <a href="{e(src['url'])}" target="_blank" rel="noopener">{e(src['name'])}</a> ({licence_html(src.get('licence_id'))}).</p>
</section>""")

    # f. Open datasets
    if f["catalogue"]:
        cm = D["cat_meta"]
        src = cm["source"]
        nav.append(("datasets", "Open datasets"))
        capp = sum(1 for r in f["catalogue"] if r.get("concerns_apprenticeship") == "Yes")
        cat_country = record_values(f["catalogue"], "country")
        sections.append(f"""<section class="cp-sec" id="datasets" aria-labelledby="h-datasets">
  <h2 id="h-datasets">Open datasets</h2>
  <p class="sub">{plural(ncat, 'open dataset')} on apprenticeship and VET from {e(the_name)} {'is' if ncat == 1 else 'are'} listed on Europe's open-data portals{f", {capp:,} of them specifically about apprenticeship" if capp else ""}.</p>
  <p class="cp-links"><a class="btn primary" href="{e(explore_url("data-catalogue", [("country", v) for v in cat_country]))}">Browse {plural(ncat, 'dataset')}</a></p>
  <p class="provenance">Source: <a href="{e(src['url'])}" target="_blank" rel="noopener">{e(src['name'])}</a> ({licence_html(src.get('licence_id'))}). Each dataset keeps its own licence.</p>
</section>""")

    # g. Sources
    src_rows = []
    if f["schemes"]:
        s = D["schemes_meta"]["source"]
        src_rows.append(("Apprenticeship schemes", f'<a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["name"])}</a>. {e(s.get("licence", ""))} Read {e(s.get("retrieved", ""))}.'))
    if figures:
        src_rows.append(("Key figures", sources_line(figures) + "."))
    if national:
        src_rows.append(("National statistics", sources_line(national) + "."))
    if f["policies"]:
        s = D["policy_meta"]["source"]
        src_rows.append(("Policies", f'<a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["name"])}</a>. {e(s.get("licence", ""))}'))
    if f["catalogue"]:
        s = D["cat_meta"]["source"]
        src_rows.append(("Open datasets", f'<a href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["name"])}</a>. {e(s.get("licence", ""))}'))
    src_rows.append(("Last updated", e(updated)))
    sections.append(f"""<section class="cp-sec" id="sources" aria-labelledby="h-sources">
  <h2 id="h-sources">Sources and licences</h2>
  <div class="kv">{"".join(f'<div class="row"><div class="k">{e(k)}</div><div>{v}</div></div>' for k, v in src_rows)}</div>
  <p class="provenance">Apprentix republishes these figures and records; the publishers' own versions remain authoritative. See <a href="../data.html">Data &amp; sources</a> for reuse conditions.</p>
</section>""")

    # Other countries in the same group (internal links).
    same = [x for x in D["countries"] if x["group"] == c["group"] and x["code"] in has_page and x["code"] != code]
    more = "".join(f'<li><a href="{x["code"].lower()}.html"><span aria-hidden="true">{x.get("flag", "")}</span> {e(x["name"])}</a></li>' for x in same)
    group_label = dict(GROUPS).get(c["group"], "Other countries")

    toc = "".join(f'<li><a href="#{k}">{e(v)}</a></li>' for k, v in nav)
    body = f"""<nav class="cp-crumbs" aria-label="Breadcrumb"><a href="../../">Apprentix</a> <span aria-hidden="true">›</span> <a href="./">Countries</a> <span aria-hidden="true">›</span> <span aria-current="page">{e(name)}</span></nav>

<header class="cp-head">
  <div>
    <div class="mono cp-group">{e(group_label)}</div>
    <h1><span class="cp-flag-emoji" aria-hidden="true">{c.get('flag', '')}</span> {e(name)}</h1>
    <p class="lede">Apprenticeships and vocational education and training (VET) in {e(the_name)}: {e(summary)}.</p>
    {f'<ul class="cp-toc" aria-label="On this page">{toc}</ul>' if toc else ''}
    <p class="cp-links cp-actions"><a class="btn primary" href="../duel.html?a={e(code)}">Compare {e(name)} with another country</a><a class="btn" href="../find.html?c={e('GR' if code == 'EL' else code)}">Find an apprenticeship in {e(name)}</a></p>
  </div>
  <div class="cp-mapbox">{tile_map(D["countries"], has_page, code, "")}</div>
</header>

{chr(10).join(sections)}

{f'<section class="cp-sec" aria-labelledby="h-more"><h2 id="h-more">More {e(group_label.lower() if c["group"] != "other" else "countries")}</h2><ul class="cp-more">{more}</ul><p><a href="./">All countries</a></p></section>' if more else '<p><a href="./">All countries</a></p>'}"""

    title = f"{name} — apprenticeships and VET | Apprentix"
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": page_url,
                "url": page_url,
                "name": title,
                "description": description,
                "inLanguage": "en",
                "dateModified": updated,
                "isPartOf": {"@id": SITE + "#website"},
                "breadcrumb": {"@id": page_url + "#breadcrumb"},
                "about": {"@type": "Country", "name": name, "identifier": c.get("iso2", code)},
            },
            website(),
            breadcrumb([("Apprentix", SITE), ("Countries", SITE + "pages/countries/"), (name, page_url)], page_url),
        ],
    }
    from . import og
    return page(title=title, description=description, canonical=page_url, root="../../", body=body,
                json_ld_obj=ld, current=None, updated=updated, og_image=og.country_path(code),
                og_image_alt=og.alt_for(f"country:{code}", f"{name}: apprenticeship and VET profile on Apprentix."))


# ---------------------------------------------------------------- index page --

def render_index(D, facts: dict[str, dict]) -> str:
    updated = D["updated"]
    page_url = SITE + "pages/countries/"
    has_page = set(facts)
    groups_html = []
    item_list = []
    for gkey, glabel in GROUPS:
        cs = sorted((c for c in D["countries"] if c["group"] == gkey and c["code"] in facts), key=lambda c: c["name"])
        if not cs:
            continue
        cards = []
        for c in cs:
            f = facts[c["code"]]
            bits = []
            if f["schemes"]:
                bits.append(plural(len(f["schemes"]), "scheme"))
            if f["policies"]:
                bits.append(plural(len(f["policies"]), "policy", "policies"))
            bits.append(plural(len(f["indicators"]), "indicator"))
            if f["catalogue"]:
                bits.append(plural(len(f["catalogue"]), "dataset"))
            cards.append(f'<li><a class="cp-card" href="{c["code"].lower()}.html"><span class="cp-card-flag" aria-hidden="true">{c.get("flag", "")}</span>'
                         f'<span class="cp-card-name">{e(c["name"])}</span><span class="cp-card-meta">{e(" · ".join(bits))}</span></a></li>')
            item_list.append(c)
        groups_html.append(f'<section class="cp-sec" aria-labelledby="g-{gkey}"><h2 id="g-{gkey}">{e(glabel)} <span class="cp-count">{len(cs)}</span></h2>'
                           f'<ul class="cp-grid">{"".join(cards)}</ul></section>')

    n = len(facts)
    nschemes = sum(len(f["schemes"]) for f in facts.values())
    npol = sum(len(f["policies"]) for f in facts.values())
    description = (f"Country profiles of apprenticeship and vocational education in {n} European countries: "
                   f"{nschemes} apprenticeship schemes, {npol:,} VET policies and key statistics, with sources.")
    body = f"""<nav class="cp-crumbs" aria-label="Breadcrumb"><a href="../../">Apprentix</a> <span aria-hidden="true">›</span> <span aria-current="page">Countries</span></nav>

<header class="cp-head">
  <div>
    <h1>Apprenticeships by country</h1>
    <p class="lede">One page per country gathering everything Apprentix holds on its apprenticeship and VET system: schemes, key figures against the EU average, national statistics, recent policies and open datasets.</p>
    <div class="stats">
      <div class="stat"><div class="n">{n}</div><div class="l">Countries</div></div>
      <div class="stat"><div class="n">{nschemes}</div><div class="l">Apprenticeship schemes</div></div>
      <div class="stat"><div class="n">{npol:,}</div><div class="l">VET policies</div></div>
    </div>
  </div>
  <div class="cp-mapbox cp-mapbox-lg">{tile_map(D["countries"], has_page, None, "")}</div>
</header>

{chr(10).join(groups_html)}

<p class="provenance">Country names and groupings follow Eurostat conventions. {e(D["ref"].get("notes", {}).get("XK", ""))}</p>"""

    title = "Apprenticeships and VET by country | Apprentix"
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": page_url,
                "url": page_url,
                "name": title,
                "description": description,
                "inLanguage": "en",
                "dateModified": updated,
                "isPartOf": {"@id": SITE + "#website"},
                "breadcrumb": {"@id": page_url + "#breadcrumb"},
                "mainEntity": {
                    "@type": "ItemList",
                    "numberOfItems": len(item_list),
                    "itemListElement": [
                        {"@type": "ListItem", "position": i + 1, "name": c["name"],
                         "url": f"{SITE}pages/countries/{c['code'].lower()}.html"}
                        for i, c in enumerate(item_list)
                    ],
                },
            },
            website(),
            breadcrumb([("Apprentix", SITE), ("Countries", page_url)], page_url),
        ],
    }
    from . import og
    return page(title=title, description=description, canonical=page_url, root="../../", body=body,
                json_ld_obj=ld, current="countries", updated=updated, og_image=og.section_path("countries"),
                og_image_alt=og.alt_for("countries", "Apprenticeships by country — Apprentix."))


# ---------------------------------------------------------------- sitemap --

def sitemap(D, codes: list[str], extra: list[tuple[str, str]] = ()) -> str:
    updated = D["updated"]
    urls: list[tuple[str, str]] = [
        (SITE, updated),
        (SITE + "pages/indicators.html", updated),
        (SITE + "pages/insights.html", updated),
        (SITE + "pages/find.html", updated),
        (SITE + "pages/duel.html", updated),
        (SITE + "pages/play.html", updated),
        (SITE + "pages/glossary.html", updated),
        (SITE + "pages/compare.html", updated),
        (SITE + "pages/ask.html", updated),
        (SITE + "pages/countries/", updated),
        (SITE + "pages/about.html", updated),
        (SITE + "pages/data.html", updated),
    ]
    urls += [(f"{SITE}pages/countries/{c.lower()}.html", updated) for c in codes]
    for d in D["manifest"]["datasets"]:
        meta_path = PUBLISHED / d["id"] / "meta.json"
        lastmod = updated
        if meta_path.exists():
            r = str(read_json(meta_path).get("source", {}).get("retrieved", ""))
            lastmod = r if re.fullmatch(r"\d{4}-\d{2}-\d{2}", r) else updated
        urls.append((f"{SITE}pages/explore.html?" + urlencode({"dataset": d["id"]}), lastmod))
    # Static indicator and dataset pages (render_datasets). The interactive
    # indicators.html?id=… views are not listed: the static page is canonical.
    urls += list(extra)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, mod in urls:
        lines.append(f"  <url><loc>{escape(loc)}</loc><lastmod>{escape(mod)}</lastmod></url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


ROBOTS = f"""User-agent: *
Allow: /

Sitemap: {SITE}sitemap.xml
"""


# ---------------------------------------------------------------- entry --

def render_all() -> list[Path]:
    D = load()
    facts = {}
    for c in D["countries"]:
        f = country_facts(D, c["code"])
        if has_content(f):
            facts[c["code"]] = f
    has_page = set(facts)
    written = []
    expected = {"index.html"}
    for c in D["countries"]:
        if c["code"] not in facts:
            continue
        path = OUT / f"{c['code'].lower()}.html"
        expected.add(path.name)
        if write_text(path, render_country(D, c, facts[c["code"]], has_page)):
            written.append(path)
    if write_text(OUT / "index.html", render_index(D, facts)):
        written.append(OUT / "index.html")
    # Remove pages for countries that no longer have content.
    for p in OUT.glob("*.html"):
        if p.name not in expected:
            p.unlink()
            written.append(p)
    from . import render_datasets
    extra_written, extra_urls = render_datasets.render_all(D)
    written += extra_written
    codes = [c["code"] for c in D["countries"] if c["code"] in facts]
    if write_text(ROOT / "sitemap.xml", sitemap(D, codes, extra_urls)):
        written.append(ROOT / "sitemap.xml")
    if write_text(ROOT / "robots.txt", ROBOTS):
        written.append(ROOT / "robots.txt")
    print(f"Rendered: {len(facts)} country pages + index, sitemap.xml ({len(written)} file(s) changed in total)")
    return written


if __name__ == "__main__":
    render_all()
