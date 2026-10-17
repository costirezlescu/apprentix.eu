"""Render a Cedefop Daily edition → daily/<date>/index.html, daily/index.html, daily/archive.html.

  python -m pipeline.daily.render 2026-10-19

Input: daily/editions/<date>.json (the written edition) and daily/pool/<pool>.json (the
fetched sources it was written from). The renderer adds everything that must not be
written by hand:
  * the connection line under each story ("Relevant to: …"), by template from the
    item's tagged work areas and its source (a card may narrow the areas, never add);
  * dates, source names and links, taken from the pool;
  * the numbers in the top strip, counted from the pool by the rule the edition states;
  * charts, drawn from pool data.
Pages are unlisted: noindex, and not in sitemap.xml. No tracking; The number's guess
stays in the reader's browser.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import statistics
import sys
from pathlib import Path

from ..asset_version import stamp_html
from ..common import ROOT
from . import versions

HERE = Path(__file__).resolve().parent
DAILY = ROOT / "daily"
TOPICS = json.loads((HERE / "topics.json").read_text("utf-8"))
SITE = "https://apprentix.eu"

PILLARS = {
    "cedefop": "At Cedefop", "policy": "EU policy", "agencies": "Agencies", "countries": "Countries",
    "research": "Research", "data": "Data", "people": "People", "debate": "The wider debate",
}
LANGUAGES = {"de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch", "el": "Greek",
             "fi": "Finnish", "da": "Danish", "sv": "Swedish", "ro": "Romanian", "pl": "Polish", "pt": "Portuguese"}
COUNTRY = {"UK": "United Kingdom", "IE": "Ireland", "DE": "Germany", "AT": "Austria", "FR": "France", "ES": "Spain",
           "IT": "Italy", "NL": "Netherlands", "EL": "Greece", "FI": "Finland", "DK": "Denmark", "SE": "Sweden",
           "PL": "Poland", "RO": "Romania", "US": "United States", "EU": "Europe", "INT": "International"}
# Work areas in the order they are named in a connection line; governance only when alone.
AREA_ORDER = ["apprenticeships", "vet_policy", "skills_intelligence", "qualifications", "adult_learning",
              "inclusion", "teachers_trainers", "mobility", "future_of_work", "labour_market", "governance"]
SOURCE_LINE = {
    "cellar_recent": "Cedefop publication", "cellar_archive": "From the Cedefop archive",
    "openalex_fulltext": "Mentions Cedefop in its full text",
    "openalex_affiliation": "Author affiliation names Cedefop",
    "ec_presscorner": "European Commission", "council_press": "Council of the EU",
    "ep_press": "European Parliament", "eurlex_oj_l": "Official Journal of the EU",
    "eurostat_api": "Eurostat", "eurostat_updates": "Eurostat",
}
AGENCY_LINE = {
    "EU-OSHA": "EU-OSHA, the EU agency for safety and health at work",
    "ETF": "European Training Foundation, an EU agency",
    "ELA": "European Labour Authority, an EU agency",
    "EIGE": "European Institute for Gender Equality, an EU agency",
    "ILO": "International Labour Organization",
    "UNESCO-UNEVOC": "UNESCO-UNEVOC",
}
SOURCE_NAME = {
    "cedefop_rss": "Cedefop", "cellar_recent": "EU Publications Office", "cellar_archive": "EU Publications Office",
    "ec_presscorner": "European Commission", "council_press": "Council of the EU", "ep_press": "European Parliament",
    "eurlex_oj_l": "EUR-Lex", "euosha": "EU-OSHA", "etf": "ETF", "ela": "ELA", "eige": "EIGE", "ilo": "ILO",
    "unevoc": "UNESCO-UNEVOC", "eurostat_api": "Eurostat", "eurostat_updates": "Eurostat", "apprentix": "Apprentix",
    "openalex_fulltext": "OpenAlex", "openalex_journals": "OpenAlex", "openalex_affiliation": "OpenAlex",
}
SOURCE_STATUS_LABEL = {
    "cedefop_rss": "Cedefop RSS feed", "cellar_recent": "EU Publications Office catalogue (recent)",
    "cellar_archive": "EU Publications Office catalogue (archive)", "openalex_fulltext": "OpenAlex: full text",
    "openalex_affiliation": "OpenAlex: author affiliations", "openalex_journals": "OpenAlex: VET journals",
    "ec_presscorner": "Commission press corner", "ec_presscorner_doc": "Commission press corner (full texts)",
    "council_press": "Council press releases (feed)", "ep_press": "European Parliament press releases",
    "eurlex_oj_l": "Official Journal (L series)", "euosha": "EU-OSHA feed", "euosha_page": "EU-OSHA articles",
    "etf": "ETF news", "etf_page": "ETF articles", "ela": "ELA news", "ela_page": "ELA articles",
    "eige": "EIGE news", "eige_page": "EIGE articles", "ilo": "ILO news", "ilo_page": "ILO articles",
    "unevoc": "UNESCO-UNEVOC news", "eurostat_updates": "Eurostat dataset updates",
    "eurostat_api": "Eurostat data API", "apprentix": "Apprentix published data",
}
NOT_READ = [
    ("Cedefop website pages", "refuse scripts (bot check); the RSS feed is used instead"),
    ("Council of the EU pages", "refuse scripts; only the press-release feed is used"),
    ("Eurofound news", "rate-limited (429)"),
    ("OECD", "refuses scripts (403)"),
    ("Media monitoring", "not connected: no access yet"),
]


def e(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def fmt_date(d: str | None, year: bool = False) -> str:
    if not d:
        return ""
    x = dt.date.fromisoformat(d[:10])
    return f"{x.day} {x.strftime('%B')}" + (f" {x.year}" if year else "")


def long_date(d: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"{x.strftime('%A')} {x.day} {x.strftime('%B')} {x.year}"


def num(v) -> str:
    return f"{v:,}".replace(",", ",") if isinstance(v, int) else (f"{v:.1f}" if isinstance(v, float) else str(v))


def href(url: str) -> str:
    """Apprentix links become root-relative so the paper works on any host (and locally)."""
    return url[len(SITE):] if url.startswith(SITE + "/") else url


# ------------------------------------------------------------ data rules --

def connection(item: dict, override: list[str] | None = None) -> str | None:
    areas = item["work_areas"]
    if override:
        bad = [a for a in override if a not in areas]
        if bad:
            raise ValueError(f"card asks for work areas the item is not tagged with: {bad} ({item['id']})")
        areas = override
    else:
        areas = sorted(areas, key=AREA_ORDER.index)
        if len(areas) > 1:
            areas = [a for a in areas if a != "governance"]
        areas = areas[:2]
    if not areas:
        return None
    m = item["meta"]
    if item["source"] == "cedefop_rss":
        n = re.search(r"newsletter no\.? ?(\d+)", item["title"], re.I)
        head = f"From Cedefop newsletter no. {n.group(1)}" if n else "Cedefop"
    elif item["source"] == "openalex_journals":
        head = m.get("venue") or "Journal article"
    elif item["source"] == "apprentix":
        head = f"Apprentix analysis of data from {m['publisher']}" if m.get("publisher") else "Apprentix"
    elif m.get("agency"):
        head = AGENCY_LINE.get(m["agency"], m["agency"])
    elif m.get("outlet"):
        head = f"{m['outlet']} ({COUNTRY.get(m['country'], m['country'])})"
        if m.get("language") and m["language"] != "en":
            head += f" · translated from {LANGUAGES.get(m['language'], m['language'])}"
    else:
        head = SOURCE_LINE.get(item["source"], SOURCE_NAME.get(item["source"], ""))
    line = f"{head} · Relevant to: " + " · ".join(TOPICS["areas"][a]["label"] for a in areas)
    if item["policy_hooks"]:
        line += f" · {item['policy_hooks'][0]}"
    return line


HOOKS = json.loads((HERE / "hooks.json").read_text("utf-8"))["hooks"]


def line_areas(item: dict, override: list[str] | None = None) -> list[str]:
    if override:
        return override
    areas = sorted(item["work_areas"], key=AREA_ORDER.index)
    return ([a for a in areas if a != "governance"] if len(areas) > 1 else areas)[:2]


def conn_html(item: dict, override: list[str] | None = None) -> str:
    """The generated line under a story, ending with the Cedefop product it relates to."""
    line = connection(item, override)
    if not line:
        return ""
    hook = next((HOOKS[a] for a in line_areas(item, override) if a in HOOKS), None)
    if hook:
        return f'{e(line)} · Cedefop: <a href="{e(hook["url"])}">{e(hook["name"])}</a>'
    return e(line)


def strip_value(spec: dict, pool: list[dict]) -> str:
    if "count" in spec:
        c = spec["count"]
        n = sum(1 for i in pool
                if i["source"] == c["source"] and (not c.get("kind") or i["kind"] == c["kind"])
                and i["date"] and c["from"] <= i["date"] <= c["to"]
                and not (c.get("exclude_title") and i["title"].startswith(c["exclude_title"])))
        return str(n)
    if "count_press" in spec:
        c = spec["count_press"]
        return str(sum(1 for i in pool if i["circle"] in ("press", "4") and i["kind"] != "lives"
                       and i["date"] and c["from"] <= i["date"] <= c["to"]))
    v = spec["value"]
    item = next(i for i in pool if i["id"] == v["item"])
    return f"{item['meta'][v['field']]}{v.get('suffix', '')}"


# ------------------------------------------------------------- pieces --

POOL_INDEX: dict = {}


def link_url(l: dict) -> str:
    """A link names a pool item ({"item": id}) or, for anchors and legacy data, a URL."""
    return POOL_INDEX[l["item"]]["url"] if l.get("item") else l["url"]


def links_html(links: list[dict]) -> str:
    if not links:
        return ""
    parts = [f'<a href="{e(href(link_url(l)))}">{e(l["text"])}</a>' for l in links]
    return f'<p class="dc-links">{" · ".join(parts)}</p>'


def card(c: dict, P: dict, pillar: str, tag: str = "") -> str:
    it = P[c["item"]]
    first = link_url(c["links"][0]) if c.get("links") else ""
    url = first if first and not first.startswith("#") else it["url"]
    date = fmt_date(it["date"]) if c.get("show_date", True) else ""
    kicker = (f'<span class="dc-pill">{e(tag)}</span> ' if tag else "") + e(c.get("kicker", "")) \
        + (f' <span>· {e(date)}</span>' if date else "")
    body = "".join(f"<p>{e(p)}</p>" for p in c.get("body", []))
    size = " dc-card--small" if c.get("size") == "small" else ""
    anchor = f' id="{e(c["anchor"])}"' if c.get("anchor") else ""
    return f"""<article class="dc-card{size}" data-pillar="{pillar}"{anchor}>
  <p class="dc-kicker">{kicker}</p>
  <h3 class="dc-hl"><a href="{e(href(url))}">{e(c['headline'])}</a></h3>
  <p class="dc-stand">{e(c['standfirst'])}</p>
  {f'<div class="dc-body">{body}</div>' if body else ''}
  {links_html(c.get('links', []))}
  <p class="dc-conn">{conn_html(it, c.get('areas'))}</p>
</article>"""


def briefs(b: dict, P: dict, pillar: str) -> str:
    rows = []
    for r in b["items"]:
        it = P[r["item"]] if r.get("item") else None
        url = r.get("url") or it["url"]
        src = f'{it["meta"].get("outlet") or SOURCE_NAME.get(it["source"], "")}, {fmt_date(it["date"])}' if it else ""
        rows.append(f"""<li><a class="dc-brief-hl" href="{e(href(url))}">{e(r['headline'])}</a>
  <span class="dc-brief-text">{e(r['text'])}</span>{f' <span class="dc-brief-src">{e(src)}</span>' if src else ''}</li>""")
    line = connection(P[b["item"]]) if b.get("item") else None
    return f"""<div class="dc-briefs" data-pillar="{pillar}">
  <h3 class="dc-block-title">{e(b['title'])}</h3>
  <ul>{''.join(rows)}</ul>
  {f'<p class="dc-conn">{e(line)}</p>' if line else ''}
</div>"""


def reset_figure(f: dict, P: dict) -> str:
    """Horizontal bars as HTML (not SVG) so labels keep their size on a phone."""
    regions = {r["nuts2"]: r for r in P[f["item"]]["meta"]["regions"]}
    median = statistics.median(float(r["reset"]) for r in regions.values())
    short = {"Région de Bruxelles-Capitale": "Brussels-Capital", "Kentriki Makedonia": "Central Macedonia",
             "Attiki": "Attica"}
    rows = []
    for c in f["regions"]:
        r = regions[c]
        name = short.get(r["region"].split("/")[0].strip(), r["region"])
        hl = " is-hl" if c in f.get("highlight", []) else ""
        rows.append(f"""<li class="rb-row{hl}"><span class="rb-name">{e(name)} <span class="rb-cc">{e(r['country_code'])}</span></span>
  <span class="rb-track"><span class="rb-bar" style="width:{float(r['reset']):.1f}%"></span></span>
  <span class="rb-val">{e(r['reset'])} <span class="rb-rank">#{e(r['eu_rank'].split(' of ')[0])}</span></span></li>""")
    return f"""<figure class="dc-figure" style="--median:{median:.1f}%">
  <p class="rb-title">RESET score, 1–100</p>
  <p class="rb-sub">Axis from 0 to 100 · # is the rank among 244 EU regions · dashed line: median, {median:.1f}</p>
  <ol class="rb">{''.join(rows)}</ol>
  <figcaption>{e(f['caption'])}</figcaption>
</figure>"""


def portraits(b: dict, P: dict, pillar: str) -> str:
    cards = []
    for pid in b["items"]:
        it = P[pid]
        cards.append(f"""<article class="dc-portrait">
  <p class="dc-kicker">{e(it['meta']['country_code'])} · Typical apprentice</p>
  <h4><a href="{e(href(it['url']))}">{e(it['title'])}</a></h4>
  {it['meta']['html']}
</article>""")   # html: Apprentix's own escaped portrait snippet (pipeline/portraits.py)
    facts = "".join(f'<li><a href="{e(href(P[f]["url"]))}">{e(P[f]["title"])}</a></li>' for f in b.get("facts", []))
    line = connection(P[b["items"][0]])
    return f"""<div class="dc-wide" data-pillar="{pillar}">
  <h3 class="dc-block-title">{e(b['title'])}</h3>
  <p class="dc-intro">{e(b['intro'])}</p>
  <div class="dc-portraits">{''.join(cards)}</div>
  {f'<ul class="dc-facts">{facts}</ul>' if facts else ''}
  {links_html(b.get('links', []))}
  <p class="dc-conn">{e(line)}</p>
</div>"""


def pulse(b: dict, P: dict, pillar: str) -> str:
    rows = "".join(f"""<li><span class="dc-flag" aria-hidden="true">{P[i]['meta']['flag']}</span>
  <span><a href="{e(href(P[i]['url']))}">{e(P[i]['title'])}</a>
  <span class="dc-brief-src">{e(P[i]['meta']['country'])} · {e(P[i]['summary'].split(' · ')[1])}</span></span></li>"""
                   for i in b["items"])
    return f"""<div class="dc-wide" data-pillar="{pillar}">
  <h3 class="dc-block-title">{e(b['title'])}</h3>
  <p class="dc-intro">{e(b['intro'])}</p>
  <ul class="dc-pulse">{rows}</ul>
  <p class="dc-conn">{e(connection(P[b['items'][0]]) or '')}</p>
</div>"""


PROPER = {"europe", "european", "eu", "central", "eastern", "western", "northern", "southern", "ai", "vet", "tvet"}


def sentence_case(t: str) -> str:
    """Titles some journals print in capitals, in sentence case; other titles unchanged."""
    if not t.isupper():
        return t
    words = t.lower().split(" ")
    out = [w.upper() if w in {"ai", "vet", "tvet", "eu"} else w.capitalize() if w in PROPER else w for w in words]
    s = " ".join(out)
    return re.sub(r"(^|: )(\w)", lambda m: m.group(1) + m.group(2).upper(), s)


def cited(b: dict, P: dict, pillar: str) -> str:
    rows = []
    for i in b["items"]:
        it = P[i]
        venue = it["meta"].get("venue") or "No venue"
        rows.append(f"""<li><a class="dc-brief-hl" href="{e(it['url'])}">{e(sentence_case(it['title']))}</a>
  <span class="dc-brief-src">{e(venue)} · {e(fmt_date(it['date']))}</span>
  <span class="dc-brief-text">{e(b['notes'].get(i, ''))}</span></li>""")
    return f"""<div class="dc-briefs" data-pillar="{pillar}">
  <h3 class="dc-block-title">{e(b['title'])}</h3>
  <p class="dc-intro">{e(b['intro'])}</p>
  <ul>{''.join(rows)}</ul>
  <p class="dc-conn">Mentions Cedefop in its full text · OpenAlex</p>
</div>"""


def spark(series: dict) -> str:
    ys = list(series.items())
    W, H, pad = 260, 70, 6
    lo, hi = 0, max(v for _, v in ys) * 1.15
    pts = [(pad + (W - 2 * pad) * k / (len(ys) - 1), H - pad - (H - 2 * pad) * (v - lo) / (hi - lo)) for k, (_, v) in enumerate(ys)]
    path = " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(pts))
    lx, ly = pts[-1]
    return (f'<svg class="dc-spark" viewBox="0 0 {W} {H + 14}" role="img" aria-label="'
            + e("Trend: " + ", ".join(f"{y}: {v}%" for y, v in ys)) + f'"><path d="{path}"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5"/>'
            f'<text x="{pad}" y="{H + 12}">{ys[0][0]}</text><text x="{W - pad}" y="{H + 12}" text-anchor="end">{ys[-1][0]}</text>'
            f'<text class="dc-spark-axis" x="{W - pad}" y="10" text-anchor="end">axis starts at 0</text></svg>')


def number(b: dict, P: dict, pillar: str) -> str:
    it = P[b["item"]]
    m = it["meta"]
    v = m["latest_value"]
    opts = "".join(f'<button type="button" class="dc-opt" data-max="{o["max"]}">{e(o["label"])}</button>' for o in b["options"])
    fact = P[b["also_fact"]] if b.get("also_fact") else None
    return f"""<div class="dc-number" data-pillar="{pillar}" id="{e(b.get('anchor', 'the-number'))}" data-value="{v}">
  <p class="dc-block-title">The number <span>· guess first</span></p>
  <p class="dc-q">{e(b['question'])}</p>
  <div class="dc-opts" role="group" aria-label="Your guess">{opts}</div>
  <button type="button" class="linkbtn dc-skip">Just show me</button>
  <div class="dc-answer" hidden>
    <p class="dc-big">{e(num(v))}<span>%</span></p>
    <p class="dc-verdict" aria-live="polite"></p>
    {spark(m['series'])}
    <p>{e(b['answer'])}</p>
    {f'<p class="dc-also">Did you know? <a href="{e(href(fact["url"]))}">{e(fact["title"])}</a></p>' if fact else ''}
  </div>
  <p class="dc-conn">{e(m['api_label'])}, EU-27, {e(m['latest_year'])} · Eurostat <a href="{e(it['url'])}">{e(m['dataset'])}</a>, updated {e(fmt_date(it['date'], True))}</p>
</div>"""


def insight(b: dict, P: dict, pillar: str) -> str:
    it = P[b["item"]]
    return f"""<div class="dc-insight" data-pillar="{pillar}">
  <p class="dc-block-title">Insight <span>· from Apprentix</span></p>
  <h3 class="dc-hl"><a href="{e(href(it['url']))}">{e(it['title'])}</a></h3>
  <p>{e(it['summary'])}</p>
  <p class="dc-conn">Apprentix analysis of Eurostat data · <a href="{e(href(it['url']))}">Method, caveats and chart</a></p>
</div>"""


def dyk(b: dict, P: dict, pillar: str) -> str:
    it = P[b["item"]]
    text = e(it["title"])
    hl = it["meta"].get("highlight")
    if hl and e(hl) in text:
        text = text.replace(e(hl), f"<mark>{e(hl)}</mark>", 1)
    return f"""<div class="dc-dyk" data-pillar="{pillar}">
  <p class="dc-block-title">Did you know?</p>
  <p class="dc-dyk-text">{text}</p>
  <p class="dc-conn">{e(it['meta']['publisher'])} · <a href="{e(href(it['url']))}">Data on Apprentix</a></p>
</div>"""


def myth(b: dict, P: dict, pillar: str) -> str:
    it = P[b["item"]]
    verdict = {"myth": "Myth", "fact": "Fact", "partly": "Partly true"}[it["meta"]["verdict"]]
    return f"""<div class="dc-myth" data-pillar="{pillar}" data-verdict="{e(it['meta']['verdict'])}">
  <p class="dc-block-title">Myth or fact?</p>
  <p class="dc-q">“{e(it['title'])}”</p>
  <div class="dc-opts" role="group" aria-label="Your answer">
    <button type="button" class="dc-opt" data-v="myth">Myth</button><button type="button" class="dc-opt" data-v="fact">Fact</button>
  </div>
  <div class="dc-answer" hidden><p><strong>{e(verdict)}.</strong> {e(it['summary'])}</p>
    <p class="dc-conn">{e(it['meta']['publisher'])} · <a href="{e(href(it['url']))}">Nine more on Apprentix</a></p></div>
</div>"""


BLOCKS = {"card": card, "briefs": briefs, "portraits": portraits, "pulse": pulse, "cited": cited,
          "number": number, "insight": insight, "dyk": dyk, "myth": myth}


def section(s: dict, P: dict) -> str:
    inner = "".join(BLOCKS[b["type"]](b, P, s["pillar"]) for b in s["blocks"])
    return f"""<section class="dc-section" id="{e(s['id'])}" data-pillar="{e(s['pillar'])}" aria-labelledby="h-{e(s['id'])}">
  <h2 class="dc-sec-title" id="h-{e(s['id'])}">{e(s['title'])}</h2>
  <div class="dc-grid dc-grid--{e(s.get('layout', 'news'))}">{inner}</div>
</section>"""


def lead(c: dict, P: dict) -> str:
    it = P[c["item"]]
    body = "".join(f"<p>{e(p)}</p>" for p in c["body"])
    url = link_url(c["links"][0])
    return f"""<article class="dc-lead" data-pillar="{e(c['pillar'])}">
  <div class="dc-lead-text">
    <p class="dc-kicker">{e(c['kicker'])} <span>· {e(fmt_date(it['date']))}</span></p>
    <h1 class="dc-hl dc-hl--lead"><a href="{e(href(url))}">{e(c['headline'])}</a></h1>
    <p class="dc-stand">{e(c['standfirst'])}</p>
    <div class="dc-body">{body}</div>
    {links_html(c['links'])}
    <p class="dc-conn">{e(connection(P[c.get('connection_item', c['item'])], c.get('areas')))}</p>
  </div>
  {reset_figure(c['figure'], P) if c.get('figure', {}).get('type') == 'reset-bars' else ''}
</article>"""


def also_today(items: list[dict], sections: list[dict]) -> str:
    """Front-page teasers pointing into the paper; headlines are the cards' own."""
    cards = {b.get("anchor"): (s, b) for s in sections for b in s["blocks"] if b.get("anchor")}
    cells = []
    for a in items:
        s, b = cards[a]
        cells.append(f'<a class="dc-tease" data-pillar="{e(s["pillar"])}" href="#{e(a)}">'
                     f'<span class="dc-kicker">{e(s["title"])}</span><span class="dc-tease-hl">{e(b["headline"])}</span></a>')
    return f'<nav class="dc-teasers" aria-label="Also today">{"".join(cells)}</nav>'


def strip(s: dict, pool: list[dict]) -> str:
    cells = "".join(f"""<{'a' if x.get('link') else 'div'} class="dc-num"{f' href="{e(x["link"])}"' if x.get('link') else ''}><span class="dc-num-v">{e(strip_value(x, pool))}</span>
  <span class="dc-num-l">{e(x['label'])}</span><span class="dc-num-n">{e(x['note'])}</span></{'a' if x.get('link') else 'div'}>""" for x in s["items"])
    return f"""<section class="dc-strip" aria-labelledby="strip-t">
  <h2 class="dc-strip-title" id="strip-t">{e(s['title'])}</h2>
  <div class="dc-nums">{cells}</div>
</section>"""


def week_ahead(w: dict, P: dict, edition: str) -> str:
    days = []
    for d in w["days"]:
        ev = "".join(f'<li><a href="{e(P[x["item"]]["url"])}">{e(x["text"])}</a> <span class="dc-tag">{e(x["tag"])}</span></li>'
                     for x in d["events"])
        days.append(f'<div class="dc-day"><p class="dc-day-d">{e(long_date(d["date"]).rsplit(" ", 1)[0])}</p><ul>{ev}</ul></div>')
    more = "".join(f'<li><a href="{e(P[x["item"]]["url"])}">{e(x["text"])}</a></li>' for x in w.get("more", []))
    coming = []
    for x in w["coming"]:
        if x["date"] < edition:
            raise ValueError(f"past event in the diary: {x['text']} ({x['date']})")
        when = fmt_date(x["date"]) + (f"–{fmt_date(x['end'])}" if x.get("end") else "")
        if x.get("end") and x["date"][:7] == x["end"][:7]:
            when = f"{dt.date.fromisoformat(x['date']).day}–{fmt_date(x['end'])}"
        coming.append(f'<li><span class="dc-when">{e(when)}</span><span><a href="{e(x["url"])}">{e(x["text"])}</a>'
                      f' <span class="dc-brief-src">{e(x["where"])}</span></span></li>')
    return f"""<section class="dc-section dc-week" id="week" data-pillar="policy" aria-labelledby="h-week">
  <h2 class="dc-sec-title" id="h-week">{e(w['title'])}</h2>
  <div class="dc-week-grid">
    <div>{''.join(days)}<ul class="dc-more">{more}</ul></div>
    <div data-pillar="cedefop"><h3 class="dc-block-title">{e(w['coming_title'])}</h3><ul class="dc-coming">{''.join(coming)}</ul>
      <p class="dc-conn">From Cedefop newsletter no. 167, agenda</p></div>
  </div>
</section>"""


SCRIPT = """<script>
(() => {
  const store = (k, v) => { try { v === undefined ? (v = localStorage.getItem(k)) : localStorage.setItem(k, v); return v; } catch { return null; } };
  document.querySelectorAll('.dc-number').forEach(box => {
    const value = parseFloat(box.dataset.value), key = 'cedefop-daily:' + location.pathname + ':number';
    const reveal = (max) => {
      box.querySelector('.dc-answer').hidden = false;
      box.querySelectorAll('.dc-opt').forEach(b => { b.disabled = true; b.classList.toggle('is-pick', b.dataset.max === max); });
      const opts = [...box.querySelectorAll('.dc-opt')], right = opts.find(b => value < parseFloat(b.dataset.max));
      if (right) right.classList.add('is-right');
      const v = box.querySelector('.dc-verdict');
      if (max) v.textContent = right && right.dataset.max === max ? 'You got it.' : 'Not this time: the answer is ' + right.textContent + '.';
      box.querySelector('.dc-skip').hidden = true;
    };
    box.querySelectorAll('.dc-opt').forEach(b => b.addEventListener('click', () => { store(key, b.dataset.max); reveal(b.dataset.max); }));
    box.querySelector('.dc-skip').addEventListener('click', () => reveal(null));
    const saved = store(key); if (saved) reveal(saved);
  });
  document.querySelectorAll('.dc-myth').forEach(box => box.querySelectorAll('.dc-opt').forEach(b => b.addEventListener('click', () => {
    box.querySelectorAll('.dc-opt').forEach(x => { x.disabled = true; x.classList.toggle('is-right', x.dataset.v === box.dataset.verdict); x.classList.toggle('is-pick', x === b); });
    box.querySelector('.dc-answer').hidden = false;
  })));
})();
</script>"""


def css_version() -> str:
    return hashlib.sha256((DAILY / "assets" / "daily.css").read_bytes()).hexdigest()[:8]


def head(title: str, desc: str, canonical: str) -> str:
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="noindex, nofollow">
<link rel="canonical" href="{e(canonical)}">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&amp;family=Public+Sans:wght@400;500;700&amp;family=IBM+Plex+Mono:wght@400;500&amp;display=swap">
<link rel="stylesheet" href="/assets/css/site.css">
<link rel="stylesheet" href="/daily/assets/daily.css?v={css_version()}">
</head>
<body data-root="/">
<a class="skip" href="#main">Skip to content</a>
<div class="indep"><div class="wrap"><span class="tag">Independent project</span>
<p>Not affiliated with, or endorsed by, any European institution or agency. Built on publicly available data.</p></div></div>
<header class="site-head"><div class="wrap head-inner">
  <a class="brand" href="/">Apprenti<span class="x">x</span><span class="eu">.eu</span></a>
  <nav class="site-nav"><a href="/">Datasets</a><a href="/pages/indicators.html">Indicators</a><a href="/pages/insights.html">Insights</a><a href="/pages/countries/">Countries</a><a href="/pages/about.html">About</a></nav>
</div></header>"""


def masthead(ed: dict, nav: list[tuple[str, str, str]]) -> str:
    items = "".join(f'<li data-pillar="{e(p)}"><a href="#{e(i)}">{e(t)}</a></li>' for i, t, p in nav)
    focus = f'<span class="dm-focus">Today’s focus: {e(ed["day_focus"])}</span>' if ed.get("day_focus") else ""
    return f"""<header class="dm">
  <div class="wrap dm-inner">
    <div class="dm-brand"><a class="dm-title" href="/daily/">Cedefop Daily</a>
      <p class="dm-sub">Thessaloniki · Brussels</p></div>
    <div class="dm-meta"><strong>{e(long_date(ed['date']))}</strong>
      <span>No. {e(ed['number'])}</span>{focus}<span>Built from {e(ed['built_from'])}</span>
      <span class="dm-version">%%VERSION%%</span></div>
  </div>
  <nav class="dm-pillars" aria-label="Sections"><div class="wrap"><ul>{items}</ul></div></nav>
</header>"""


PRESS_FEEDS = {f["id"]: f for f in json.loads((HERE / "press.json").read_text("utf-8"))["feeds"]}


def footer(pool: dict) -> str:
    is_press = lambda k: k in PRESS_FEEDS or k.removesuffix("_page") in PRESS_FEEDS
    ok = [SOURCE_STATUS_LABEL.get(k, k) for k, v in pool["sources"].items() if v == "ok" and not is_press(k)]
    feeds_ok = [k for k, v in pool["sources"].items() if k in PRESS_FEEDS and v == "ok"]
    outlets = {PRESS_FEEDS[k]["name"] for k in feeds_ok}
    countries = {PRESS_FEEDS[k]["country"] for k in feeds_ok} - {"EU", "INT"}
    ok.append(f"press and field feeds from {len(outlets)} outlets in {len(countries)} countries")
    bad = [(SOURCE_STATUS_LABEL.get(k, k), v.split(":", 1)[1].strip() if ":" in v else v)
           for k, v in pool["sources"].items() if v != "ok" and not is_press(k)]
    paywalled = sorted({PRESS_FEEDS[k.removesuffix("_page")]["name"] for k, v in pool["sources"].items()
                        if k.endswith("_page") and is_press(k) and v != "ok"})
    if paywalled:
        bad.append(("Article pages of " + ", ".join(paywalled), "refuse scripts; only the feed’s summary is used"))
    not_read = "".join(f"<li>{e(n)}: {e(w)}</li>" for n, w in bad + NOT_READ)
    return f"""<footer class="dc-foot">
  <div class="wrap">
    <div class="dc-foot-grid">
      <div><h2>About this paper</h2>
        <p><strong>Cedefop Daily</strong> is a morning paper on what Cedefop works on: vocational education and training, apprenticeships, skills, qualifications, adult learning and the future of work. It is an independent publication on Apprentix and is not published or endorsed by Cedefop.</p>
        <p>Compiled from the linked public sources. Every story links to its source; figures are copied, not recalculated, and the line under each story is generated from the source data. <a href="/daily/about.html">How this paper is made</a> · <a href="/daily/archive.html">Editions</a></p>
        <p>Corrections: none. To report an error, <a href="https://github.com/costirezlescu/apprentix.eu/issues">open an issue</a>.</p></div>
      <div><h2>Read for this edition</h2><p>{e(' · '.join(ok))}.</p>
        <h2>Not read</h2><ul>{not_read}</ul>
        <p>No tracking. The number’s guess is kept only in your browser.</p></div>
    </div>
  </div>
</footer>"""


LIVES_LABEL = "Lives"
PILLAR_TITLE = {"cedefop": "At Cedefop", "field": "From the field", "debate": "The wider debate", "policy": "EU policy",
                "agencies": "Agencies", "research": "Research", "people": "People", "data": "Data"}


def lead2(s: dict, P: dict) -> str:
    it = P[s["item"]]
    body = "".join(f"<p>{e(p)}</p>" for p in s.get("body", []))
    url = link_url(s["links"][0]) if s.get("links") else it["url"]
    date = fmt_date(it["date"]) if s.get("show_date", True) else ""
    fig = reset_figure(s["figure"], P) if s.get("figure", {}).get("type") == "reset-bars" else ""
    return f"""<article class="dc-lead{'' if fig else ' dc-lead--text'}" data-pillar="{e(s['pillar'])}" id="lead">
  <div class="dc-lead-text">
    <p class="dc-kicker"><span class="dc-pill">The one thing</span> {e(s.get('kicker', ''))}{f' <span>· {e(date)}</span>' if date else ''}</p>
    <h1 class="dc-hl dc-hl--lead"><a href="{e(href(url))}">{e(s['headline'])}</a></h1>
    <p class="dc-stand">{e(s['standfirst'])}</p>
    {f'<div class="dc-body">{body}</div>' if body else ''}
    {links_html(s.get('links', []))}
    <p class="dc-conn dc-why"><strong>Why it matters to Cedefop:</strong> {conn_html(P[s.get('connection_item', s['item'])], s.get('areas'))}</p>
  </div>
  {fig}
</article>"""


def lives2(l: dict, P: dict) -> str:
    it = P[l["item"]]
    m = it["meta"]
    src = f"{m.get('outlet', '')} ({COUNTRY.get(m.get('country'), m.get('country', ''))})"
    if m.get("language") and m["language"] != "en":
        src += f" · translated from {LANGUAGES.get(m['language'], m['language'])}"
    body = "".join(f"<p>{e(p)}</p>" for p in l["body"])
    return f"""<section class="dc-lives{' dc-lives--long' if l.get('is_long') else ''}" id="lives" data-pillar="lives" aria-labelledby="h-lives">
  <p class="dc-lives-label" id="h-lives">{LIVES_LABEL}</p>
  <div class="dc-lives-inner">
    <h2 class="dc-lives-hl"><a href="{e(it['url'])}">{e(l['headline'])}</a></h2>
    <p class="dc-stand">{e(l['standfirst'])}</p>
    <div class="dc-body">{body}</div>
    <p class="dc-conn">{e(src)} · {e(fmt_date(it['date'], True))} · <a href="{e(it['url'])}">Read the original</a></p>
  </div>
</section>"""


def question2(q: dict, P: dict) -> str:
    title = {"number": "The number", "myth": "Myth or fact?", "dyk": "Did you know?", "insight": "Insight"}[q["type"]]
    inner = BLOCKS[q["type"]](q, P, "data")
    return f"""<section class="dc-section dc-question" id="question" data-pillar="data" aria-labelledby="h-question">
  <h2 class="dc-sec-title" id="h-question">Today’s question <span class="dc-sec-sub">· {e(title)}</span></h2>
  <div class="dc-question-inner">{inner}</div>
</section>"""


def more2(stories: list[dict], P: dict) -> str:
    if not stories:
        return ""
    rows = []
    for s in stories:
        it = P[s["item"]]
        url = link_url(s["links"][0]) if s.get("links") else it["url"]
        src = it["meta"].get("outlet") or SOURCE_NAME.get(it["source"], "")
        rows.append(f'<li data-pillar="{e(s["pillar"])}"><span class="dc-pill">{e(PILLAR_TITLE.get(s["pillar"], ""))}</span> '
                    f'<a href="{e(href(url))}">{e(s["more"])}</a> <span class="dc-brief-src">{e(src)}, {e(fmt_date(it["date"]))}</span></li>')
    return f"""<section class="dc-section" id="more" aria-labelledby="h-more">
  <details class="dc-more-today"><summary><h2 class="dc-sec-title" id="h-more">More today <span class="dc-sec-sub">· {len(stories)} links</span></h2></summary>
  <ul>{''.join(rows)}</ul></details>
</section>"""


def diary2(d: dict, P: dict, date: str) -> str:
    w = {"title": d["title"], "days": d["days"], "more": d["more"], "coming_title": "Coming up at Cedefop", "coming": d["coming"]}
    html_ = week_ahead(w, P, date)
    if not d["days"]:
        html_ = html_.replace('<div class="dc-week-grid">\n    <div><ul class="dc-more"></ul></div>', '<div class="dc-week-grid dc-week-grid--one">')
    return html_


def preview_banner(ed: dict) -> str:
    v = f"{'Fixed shape' if ed['layout'] == 'shape' else 'Sections, capped'}, {'with weekday rhythm' if ed['rhythm'] else 'no weekday rhythm'}"
    return (f'<div class="dc-preview" role="note"><strong>Preview · design comparison</strong> ({e(v)}). '
            f'Built on 17 October 2026 from the sources available then; a real edition adds that day’s news. '
            f'<a href="/daily/lab/">All variants</a></div>')


def know_title(ed: dict) -> str:
    return ["One", "Two", "Three", "Four", "Five", "Six", "Seven"][len(ed["know"]) - 1] + " to know"


def render_edition(ed: dict, pool: dict) -> str:
    P = {i["id"]: i for i in pool["items"]}
    POOL_INDEX.clear()
    POOL_INDEX.update(P)
    title = f"Cedefop Daily — {long_date(ed['date'])}" + (" (preview)" if ed.get("preview") else "")
    desc = ed["lead"]["headline"] + ". " + ed["lead"]["standfirst"]
    canonical = f"{SITE}/daily/{ed['date']}/" if not ed.get("preview") else f"{SITE}/daily/lab/"
    diary_label = ed["diary"]["title"]
    if ed["layout"] == "shape":
        nav = [("know", know_title(ed), "cedefop"), ("question", "Today’s question", "data"),
               ("week", diary_label, "policy"), ("more", "More today", "debate")]
    else:
        nav = [(x["id"], x["title"], x["pillar"]) for x in ed["sections"]] \
            + [("question", "Data", "data"), ("week", diary_label, "policy")]
    if ed.get("lives"):
        nav.insert(0, ("lives", "Lives", "lives"))
    out = [head(title, desc, canonical)]
    if ed.get("preview"):
        out.append(preview_banner(ed))
    out += [masthead(ed, nav), '<main id="main" class="wrap dc-main">', strip(ed["strip"], pool["items"])]
    top = [lead2(ed["lead"], P)] + ([lives2(ed["lives"], P)] if ed.get("lives") else [])
    out += top[::-1] if ed.get("lives_first") else top
    if ed["layout"] == "shape":
        cards = "".join(card(x, P, x["pillar"], PILLAR_TITLE.get(x["pillar"], "")) for x in ed["know"])
        out.append(f"""<section class="dc-section dc-five" id="know" aria-labelledby="h-know">
  <h2 class="dc-sec-title" id="h-know">{know_title(ed)}</h2>
  <div class="dc-grid">{cards}</div>
</section>""")
        out.append(question2(ed["question"], P))
        out.append(diary2(ed["diary"], P, ed["date"]))
        out.append(more2(ed.get("more", []), P))
    else:
        for x in ed["sections"]:
            cards = "".join(card(c, P, x["pillar"]) for c in x["stories"])
            out.append(f"""<section class="dc-section" id="{e(x['id'])}" data-pillar="{e(x['pillar'])}" aria-labelledby="h-{e(x['id'])}">
  <h2 class="dc-sec-title" id="h-{e(x['id'])}">{e(x['title'])}</h2>
  <div class="dc-grid">{cards}</div>
</section>""")
        out.append(question2(ed["question"], P).replace("Today’s question <span", "Data <span"))
        out.append(diary2(ed["diary"], P, ed["date"]))
    out += ["</main>", footer(pool), SCRIPT, "</body>\n</html>\n"]
    page = stamp_html("\n".join(out))
    if ed.get("preview"):
        return page.replace("%%VERSION%%", f"Preview No. {ed['number']}")
    n, hist = versions.current_number(ed["date"], page)
    earlier = f' · <a href="/daily/archive.html#ed-{e(ed["date"])}">earlier versions</a>' if n > 1 else ""
    return page.replace("%%VERSION%%", f"Version {n}{earlier}")


def render_archive(editions: list[dict]) -> str:
    rows = []
    for x in sorted(editions, key=lambda x: x["date"], reverse=True):
        d = x["date"]
        vs = " · ".join(f'<a href="/daily/{e(d)}/v{v["n"]}/">version {v["n"]}</a> '
                        f'<span class="dc-brief-src">({e(versions.when(v["time"]))})</span>'
                        for v in versions.history(d))
        rows.append(f'<li id="ed-{e(d)}"><a href="/daily/{e(d)}/">{e(long_date(d))}</a> · No. {e(x["number"])} · '
                    f'{e(x["lead"]["headline"])}{f"<br><span class=dc-versions>Published versions: {vs}</span>" if vs else ""}</li>')
    rows = "".join(rows)
    return stamp_html("\n".join([head("Cedefop Daily — Editions", "Every edition of Cedefop Daily.", f"{SITE}/daily/archive.html"),
                                 '<main id="main" class="wrap dc-main dc-page"><h1 class="dm-title">Editions</h1>',
                                 '<p class="dc-intro">Every version of every edition stays online. A new version is published when an edition is corrected or extended; each is kept as it was, with the stylesheets of the day.</p>',
                                 f'<ul class="dc-archive">{rows}</ul></main>', "</body>\n</html>\n"]))


ABOUT = """
<h1 class="dm-title">How this paper is made</h1>
<p class="dc-stand">Cedefop Daily is a morning paper on what Cedefop works on: vocational education and training, apprenticeships, skills, qualifications, adult learning and the future of work. It also follows the EU institutions, sister agencies, member states and researchers whose work touches those areas. It is an independent publication on Apprentix and is not published or endorsed by Cedefop.</p>

<h2>Five rules</h2>
<ol>
<li><strong>Relevant, or it doesn’t run.</strong> Under every story, a line says which of Cedefop’s work areas it touches. That line is generated from the source data by a template, never written by hand. If no line can be generated, the story is left out.</li>
<li><strong>Sourced.</strong> Every story links to its source. Figures are copied from the source, never recalculated into new claims. Quotations are checked word for word against the source.</li>
<li><strong>Neutral.</strong> The paper reports and does not editorialise. Evaluations are attributed to whoever made them. It never speaks for Cedefop.</li>
<li><strong>Short.</strong> Sections appear only when they have something worth running. A quiet day makes a shorter paper.</li>
<li><strong>Discreet about people.</strong> Nobody is searched for. People appear only in a public role, as named by an official source or as authors of the papers covered. News about colleagues will run only if it comes through approved channels, with consent and an opt-out.</li>
</ol>

<h2>How an edition is built</h2>
<ol>
<li><strong>Fetch.</strong> A script reads public sources over plain HTTP: Cedefop’s RSS feed and newsletter, the EU Publications Office catalogue, the Commission’s press corner, the Council’s press feed, the Official Journal, the news pages of EU and UN agencies, Eurostat, OpenAlex for research, Apprentix’s own data, and the press (below). A source that refuses automated reading is recorded as refused and skipped. Bot checks are never worked around.</li>
<li><strong>Tag.</strong> Each item is tagged with Cedefop work areas by keyword, in several languages.</li>
<li><strong>Write.</strong> Stories are drafted from the fetched text only, with help from software that includes a language model. Links, dates and the line under each story come from the data, not from the writing step.</li>
<li><strong>Check.</strong> Before publication, every link must come from the fetched sources, every number must appear in the story’s sources, and every quotation must be verbatim. Banned words, sensitive topics (which hold the edition for a person to decide), a person in more than one headline and past events in the diary are flagged.</li>
<li><strong>Publish.</strong> The checked edition is rendered as a static page.</li>
</ol>

<h2>The press and the field</h2>
<p>To see how things are on the ground, not only from the institutions, the paper reads national and local newspapers, trade press, teachers’, learners’ and employers’ outlets, international newspapers and magazines, popular science and economics columns. An article is kept only if it touches education, training and skills, or AI together with work and jobs, and only if it is from the last eight days.</p>
<p>Press articles are summarised in the paper’s own words and linked; at most a short phrase is quoted. Articles in other languages are summarised in English and labelled “translated from …”. Private individuals in press stories are not named; people appear only in a public role. Subscription articles are marked.</p>
{outlets}

<h2>Sections</h2>
<p>About twelve items a day, a five-minute read: <strong>The one thing</strong> (the day’s most important story, with a line on why it matters to Cedefop), <strong>Six to know</strong>, <strong>Today’s question</strong> (a number to guess, a myth to call, a fact or an insight), the <strong>Diary</strong>, and <strong>More today</strong> as a short list of links. On Fridays, <strong>Lives</strong> opens the paper: one real person whose life vocational education and training has shaped. Stories come from Cedefop, the field, the wider debate, EU policy, the agencies and research, each marked with its section colour. The top strip shows “Today at Cedefop” when there is a public agenda for the day, and “This week in numbers” otherwise.</p>
<p>Each weekday has a focus: Monday EU policy and Cedefop, with the week ahead in the diary; Tuesday research; Wednesday the field; Thursday AI and the future of work; Friday long reads.</p>
<h2>Lives</h2>
<p>Lives stories come from published profiles and interviews. A person is named only as printed, and only when the source is a profile or interview they chose to give, in which they are the subject. Minors are never named, and nothing about health, family or money is included beyond what the story itself is about.</p>

<h2>Privacy</h2>
<p>No cookies, no tracking and no analytics. If you guess The number, your guess is kept only in your browser.</p>

<h2>Corrections</h2>
<p>Every version of every edition stays online, exactly as it was published: when an edition is corrected or extended, the earlier version moves to its own address and is listed under <a href="/daily/archive.html">Editions</a>. Errors are corrected in the next edition, in the same place. To report one, <a href="https://github.com/costirezlescu/apprentix.eu/issues">open an issue</a>.</p>
"""


def render_about() -> str:
    by = {}
    for f in PRESS_FEEDS.values():
        by.setdefault(COUNTRY.get(f["country"], f["country"]), set()).add(f["name"])
    outlets = "<ul>" + "".join(f"<li><strong>{e(c)}</strong>: {e(', '.join(sorted(n)))}</li>" for c, n in sorted(by.items())) + "</ul>"
    return stamp_html("\n".join([head("How Cedefop Daily is made", "How Cedefop Daily is compiled, checked and published.",
                                      f"{SITE}/daily/about.html"),
                                 '<main id="main" class="wrap dc-main dc-page">', ABOUT.replace("{outlets}", outlets),
                                 '<p><a href="/daily/">Back to today’s paper</a></p></main>', "</body>\n</html>\n"]))


def sources_json(ed: dict, pool: dict) -> str:
    """The items this edition used, with where they came from: small enough to keep in git
    (the full pool, about 1 MB a day, is not committed)."""
    used = set(re.findall(r'"([0-9a-f]{10})"', json.dumps(ed)))
    items = [{k: i[k] for k in ("id", "source", "kind", "title", "url", "date", "work_areas")}
             for i in pool["items"] if i["id"] in used]
    return json.dumps({"edition": ed["date"], "fetched_at": pool["fetched_at"], "sources_status": pool["sources"],
                       "items": items}, ensure_ascii=False, indent=1) + "\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


LAB_LABEL = {"shape-plain": "Fixed shape, no rhythm", "shape-rhythm": "Fixed shape, weekday rhythm",
             "sections-plain": "Sections capped, no rhythm", "sections-rhythm": "Sections capped, weekday rhythm"}


def render_lab() -> None:
    lab = DAILY / "lab"
    pools: dict = {}
    grid: dict = {}
    for f in sorted(lab.glob("*/*/edition.json")):
        ed = json.loads(f.read_text("utf-8"))
        pool = pools.setdefault(ed["pool"], json.loads((DAILY / "pool" / f"{ed['pool']}.json").read_text("utf-8")))
        write(f.parent / "index.html", render_edition(ed, pool))
        grid.setdefault(ed["date"], {})[f.parent.parent.name] = ed
    cols = list(LAB_LABEL)
    head_row = "".join(f"<th scope=col>{e(LAB_LABEL[c])}</th>" for c in cols)
    rows = ""
    for d in sorted(grid):
        cells = ""
        for c in cols:
            ed = grid[d].get(c)
            if not ed:
                cells += "<td>–</td>"
                continue
            n = 1 + len(ed.get("know", [])) + len(ed.get("more", [])) + sum(len(x["stories"]) for x in ed.get("sections", []))
            top = ed["lives"]["headline"] if ed.get("lives_first") else ed["lead"]["headline"]
            cells += (f'<td><a href="/daily/lab/{c}/{d}/">{e(top)}</a>'
                      f'<span class="dc-brief-src">{n} stories{" · Lives" if ed.get("lives") else ""}{", opening the paper" if ed.get("lives_first") else ""}'
                      f'{" · focus: " + e(ed["day_focus"]) if ed.get("day_focus") else ""}</span></td>')
        rows += f"<tr><th scope=row>{e(long_date(d))}</th>{cells}</tr>"
    body = f"""<main id="main" class="wrap dc-main dc-page dc-lab"><h1 class="dm-title">Design comparison</h1>
<p class="dc-intro">Four ways to shape Cedefop Daily at about 12 items a day, over one week. Every variant is planned from the same story bank, written on 17 October 2026 from the sources available then, and never runs a story twice in the week, so later days show what earlier days left. Real editions would add each day’s news, so Tuesday to Friday are thinner here than they would be.</p>
<ul class="dc-intro">
<li><strong>Fixed shape:</strong> The one thing · Six to know · Today’s question · Diary · More today (collapsed links).</li>
<li><strong>Sections capped:</strong> the paper’s sections, at most two stories each (one for agencies), about ten stories in all, plus a data item and the diary.</li>
<li><strong>Weekday rhythm:</strong> Monday policy and Cedefop, Tuesday research, Wednesday the field, Thursday AI and the future of work, Friday long reads with Lives opening the paper.</li>
<li><strong>Lives</strong> runs in every variant once a week, on Fridays, at length.</li>
</ul>
<div class="dc-lab-scroll"><table class="dc-lab-table"><thead><tr><th></th>{head_row}</tr></thead><tbody>{rows}</tbody></table></div>
<p><a href="/daily/">The paper</a> uses the fixed shape with the weekday rhythm.</p></main>"""
    write(lab / "index.html", stamp_html("\n".join([head("Cedefop Daily — Design comparison", "Four layouts of Cedefop Daily compared over one week.",
                                                            f"{SITE}/daily/lab/"), body, "</body>\n</html>\n"])))


def main(argv: list[str]) -> int:
    if "--lab" in argv:
        render_lab()
        return 0
    editions = [json.loads(p.read_text("utf-8")) for p in sorted((DAILY / "editions").glob("*.json"))]
    want = argv[0] if argv else editions[-1]["date"]
    ed = next(x for x in editions if x["date"] == want)
    pool = json.loads((DAILY / "pool" / f"{ed['pool']}.json").read_text("utf-8"))
    page = render_edition(ed, pool)
    write(DAILY / ed["date"] / "index.html", page)
    write(DAILY / ed["date"] / "sources.json", sources_json(ed, pool))
    if ed["date"] == max(x["date"] for x in editions):
        write(DAILY / "index.html", page.replace(f'href="{SITE}/daily/{ed["date"]}/"', f'href="{SITE}/daily/"', 1))
    for x in editions:
        versions.build(x["date"])
    write(DAILY / "archive.html", render_archive(editions))
    write(DAILY / "about.html", render_about())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
