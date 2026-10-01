"""data.europa.eu: a catalogue of apprenticeship and VET datasets published across Europe.

The official EU open-data portal harvests national, regional and EU catalogues
(DCAT-AP). Its search API (no key, CORS open) is used here as a discovery hub:

  https://data.europa.eu/api/hub/search/search?q=...&filter=dataset&limit=...&page=...&includes=...

We run a set of multilingual queries, keep only datasets whose title (English or
original language) or keywords actually mention apprenticeship / VET terms, drop
geodata map services, dedupe by dataset id and write a record dataset. The
portal's search also matches machine-translated text, so a query in one
language finds datasets in all others; the term filter keeps precision.

A second, small output, data/watch/cedefop-catalogue.json, lists the datasets in
the portal's "cedefop" catalogue: an update signal for Cedefop data, whose own
website blocks automated clients.

Licence: portal metadata is reusable under the European Commission reuse notice
(Decision 2011/833/EU); each listed dataset keeps its own licence, recorded per record.
"""

from __future__ import annotations

import json
import re

from ..common import DATA, fetch_json, geo_code, geo_name, html_to_text, now_iso, read_json, rel, write_json, write_records

API = "https://data.europa.eu/api/hub/search/search"
DATASET_API = "https://data.europa.eu/api/hub/search/datasets/"
PORTAL = "https://data.europa.eu/data/datasets/{id}?locale=en"
DATASET_ID = "data-catalogue"
WATCH = DATA / "watch" / "cedefop-catalogue.json"
PAGE = 1000  # the API's maximum page size
DESC_MAX = 600

SOURCE = {
    "id": "data-europa",
    "name": "data.europa.eu",
    "publisher": "Publications Office of the European Union",
    "homepage": "https://data.europa.eu/",
    "description": "The EU open-data portal, used as a discovery hub: a catalogue of apprenticeship and VET datasets published by national, regional and EU bodies, plus an update watch on Cedefop's catalogue.",
    "access": "api",
    "browser_cors": True,
    "licence": "EC-reuse",
    "cadence": "continuous (harvested daily from national portals); refreshed on each pipeline run",
    "secret": None,
    "outputs": [f"{DATASET_ID}/records.json", f"{DATASET_ID}/meta.json", "watch/cedefop-catalogue.json"],
}

# Queries sent to the portal. Single words are searched in titles only (all
# languages, fields=title.*), which keeps result sets small enough to fetch in
# full; quoted phrases cannot be field-restricted by the API and search all text.
# Every result set is fetched completely, sorted by id, so reruns are stable
# (relevance ranking differs between the portal's search replicas).
# "leerling" (Dutch for pupil) was tried and dropped: >1,200 school-pupil tables, few VET ones.
QUERIES = [
    "apprenticeship", "apprentice", "apprentices", "traineeship",
    '"vocational education and training"', '"vocational education"', '"vocational training"',
    '"work-based learning"', '"dual training"',
    "Ausbildung", "Lehrling", "Lehrlinge", "Lehrstellen", "Auszubildende", "Berufsbildung", "Berufsausbildung",
    "apprentissage", "apprentis", "alternance", '"formation professionnelle"',
    "apprendistato", '"formazione professionale"', "IeFP",
    "aprendizaje", "aprendices", '"formación profesional"', '"formação profissional"',
    "mbo", "bbl", "beroepsonderwijs", '"beroepsbegeleidende leerweg"',
    "lærling", "lærlinge", "erhvervsuddannelse", "yrkesfag", "lärling", "yrkesutbildning",
    "oppisopimus", "ammatillinen",
    "praktykant", '"kształcenie zawodowe"', "szakképzés", "vajeništvo", "ucenicie", "μαθητεία",
]

# A dataset is kept only if one of these matches its English or original-language
# title (keywords alone are too noisy: statistical tables tag every breakdown).
TERMS = re.compile(r"""(?ix)
    apprentic | \bvocational | \bt?vet\b | traineeship | work[- ]based\ learning
  | dual(e|en|es)?\ (training|education|study|studies|system|vocational|ausbildung|studium|berufsausbildung|bildung)
  | lehrling | lehrstelle | lehrvertr | lehrabschluss | lehrbetrieb | auszubildend | \bazubi
  | berufsausbildung | berufsbildung | berufliche[nrs]?\ (aus)?bildung | berufsschul | berufsfachschul | berufskolleg
  | ausbildungs(platz|plätze|stelle|vertr|verhältnis|beruf|betrieb|markt|quote|vergütung|bilanz|anf[äa]nger)
  | \bapprenti(e|s|es)?\b | apprentissage(?!\ (automatique|profond|tout\ au\ long|en\ ligne|des\ langues))
  | alternance | formation\ professionnelle | lyc[ée]e\ professionnel | \bcfa\b
  | apprendist | formazione\ professionale | \biefp\b | istituti?\ (tecnici|professionali)
  | formaci[oó]n\ (profesional|dual) | \baprendic | \bfp\ dual
  | forma[cç][aã]o\ profissional | ensino\ profissional | cursos\ de\ aprendizagem
  | \bbbl\b | beroepsbegeleidende | beroepsonderwijs | \bmbo\b | leerbedrij | leerwerk
  | l[æa]rling | l[æa]rebedrift | l[æa]rekontrakt | fagbrev | erhvervsuddann | \beud\b | yrkesfag
  | yrkesutbild | yrkesh[öo]gskol | yrkesprogram
  | oppisopimu | ammatillis | ammatillinen
  | praktykan | kszta[łl]ceni\w*\ zawodow | szko[łl]\w*\ bran[żz]ow | m[łl]odocian\w*\ pracownik
  | szakk[ée]pz | tanonc | du[áa]lis\ k[ée]pz
  | vajenc | vajeni | vajeništ | naukovanj | \bu[čc]e[ňn] | \bu[čc]ni | odborn\w*\ vzd[ěe]l | strukovn\w*\ obrazov | strokovn\w*\ izobra
  | ucenic | [îi]nv[ăa][țt][ăa]m[âa]nt\ profesional | formare\ profesional
  | μαθητε[ίι]α | επαγγελματικ\w*\ κατ[άα]ρτιση
  | pameistryst | profesinis\ mokym | m[āa]ceklī | profesion[āa]l[āa]\ izgl | [õo]pipois | kutse(haridus|[õo]pe)
""")

# Narrower: terms that specifically mean apprenticeship / dual work-based training.
# Used for the "Concerns apprenticeship" facet, and lets a keyword alone qualify a dataset.
APPRENTICESHIP = re.compile(r"""(?ix)
    apprentic | traineeship | work[- ]based\ learning
  | dual(e|en|es)?\ (training|education|study|system|vocational|ausbildung|studium|berufsausbildung|bildung)
  | lehrling | lehrstelle | lehrvertr | lehrabschluss | lehrbetrieb | auszubildend | \bazubi
  | ausbildungs(platz|plätze|stelle|vertr|verhältnis|betrieb|markt|vergütung|anf[äa]nger)
  | \bapprenti(e|s|es)?\b | apprentissage(?!\ (automatique|profond|tout\ au\ long|en\ ligne|des\ langues))
  | alternance | \bcfa\b
  | apprendist | \baprendic | formaci[oó]n\ dual | \bfp\ dual | cursos\ de\ aprendizagem
  | beroepsbegeleidende | leerbedrij
  | l[æa]rling | l[æa]rebedrift | l[æa]rekontrakt | fagbrev
  | oppisopimu | praktykan | m[łl]odocian\w*\ pracownik | tanonc | du[áa]lis\ k[ée]pz
  | vajenc | vajeni | vajeništ | naukovanj | \bu[čc]e[ňn] | \bu[čc]ni | ucenic
  | μαθητε[ίι]α | pameistryst | m[āa]ceklī | [õo]pipois
""")

# Geodata services and building plans that mention e.g. a "vocational school" site;
# Rotterdam neighbourhood tables by parents' education level ("oplniv ... mbo").
EXCLUDE = re.compile(r"(?i)^(wms|wfs|wcs|atom)\b|\b(wms|wfs)\b|xplanung|\binspire\b|\bbpl\b|bebauungsplan|machine learning|deep learning|oplniv")

INCLUDES = ",".join([
    "id", "title", "keywords.label", "catalog.id", "country.id", "publisher.name", "publisher.resource",
    "modified", "issued",
    "landing_page.resource", "distributions.format.id", "distributions.license.id", "distributions.license.label",
    "translation_meta.details", "description.en",
])

LICENCE_PATTERNS = [
    (r"creativecommons\.org/publicdomain/zero|\bCC0\b|cc-zero", "CC0 1.0"),
    (r"creativecommons\.org/licenses/by-sa/4|CC[- ]BY[- ]SA[- ]4", "CC BY-SA 4.0"),
    (r"creativecommons\.org/licenses/by-sa/3|CC[- ]BY[- ]SA[- ]3", "CC BY-SA 3.0"),
    (r"licenses/cc-by-sa|CC[- ]BY[- ]SA", "CC BY-SA"),
    (r"creativecommons\.org/licenses/by/4|CC[- ]BY[- ]4|cc-by-4|CC_BY_4|licenses/cc-by/4", "CC BY 4.0"),
    (r"creativecommons\.org/licenses/by/3|CC[- ]BY[- ]3", "CC BY 3.0"),
    (r"licenses/cc-by\b|opendefinition\.org/licenses/cc-by|^CC[- ]BY$", "CC BY"),
    (r"creativecommons\.org/licenses/by-nc", "CC BY-NC"),
    (r"COM_REUSE|2011/833", "European Commission reuse notice"),
    (r"dl-by-de|dl-de[-/]by", "Data licence Germany – attribution 2.0"),
    (r"dl-zero-de|dl-de[-/]zero", "Data licence Germany – zero 2.0"),
    (r"etalab|licence[- ]ouverte|/lo-2|\bLO\b|open[- ]licence", "Licence Ouverte / Etalab"),
    (r"open-government-licence|\bOGL\b|OGL-UK", "Open Government Licence (UK)"),
    (r"NLOD", "Norwegian licence for open government data (NLOD)"),
    (r"opendata\.swiss/terms|terms_open|terms_by", "opendata.swiss terms"),
    (r"\bODbL\b|odbl", "ODbL"),
    (r"iodl", "Italian Open Data Licence"),
    (r"other-closed", "Other (closed)"),
    (r"other-open", "Other (open)"),
    (r"not specified|notspecified|unknown", "Not stated"),
    (r"ine\.es/aviso_legal", "INE (Spain) legal notice"),
    (r"educacionyfp\.gob\.es", "Ministry of Education (Spain) legal notice"),
]


def licence_name(lic: dict | None) -> str | None:
    if not lic:
        return None
    raw = " ".join(str(lic.get(k) or "") for k in ("id", "label"))
    for pat, name in LICENCE_PATTERNS:
        if re.search(pat, raw, flags=re.I):
            return name
    label = (lic.get("label") or lic.get("id") or "").strip()
    m = re.match(r"https?://(?:www\.)?([^/]+)", label)
    if m:  # an unrecognised licence URL: name it by its site, the record links to the source
        return f"Publisher terms ({m.group(1)})"
    return label[:80] or None


def orig_langs(r: dict) -> list[str]:
    details = (r.get("translation_meta") or {}).get("details") or {}
    langs = sorted(l for l, d in details.items() if not d.get("machine_translated"))
    return langs or sorted((r.get("title") or {}).keys())[:1]


def pick_title(r: dict) -> str:
    t = r.get("title") or {}
    if t.get("en"):
        return t["en"].strip()
    for l in orig_langs(r):
        if t.get(l):
            return t[l].strip()
    return next((v.strip() for v in t.values() if v), r["id"])


def titles(r: dict) -> list[str]:
    """English title plus original-language titles. When English is itself an original
    (multilingual publishers such as Eurostat), only the English title is used, so that
    e.g. French 'apprentissage' meaning 'learning' does not count."""
    t = r.get("title") or {}
    langs = orig_langs(r)
    use = ["en"] if "en" in langs and t.get("en") else ["en", *langs]
    return [x for x in dict.fromkeys(t.get(l) for l in use) if x]


def kw_labels(r: dict) -> list[str]:
    return [k["label"] for k in r.get("keywords") or [] if k.get("label")]


def relevant(r: dict) -> bool:
    ts = titles(r)
    if any(EXCLUDE.search(t) for t in ts):
        return False
    return any(TERMS.search(t) for t in ts) or any(APPRENTICESHIP.search(k) for k in kw_labels(r))


def publisher_of(r: dict) -> str | None:
    p = r.get("publisher") or {}
    if (p.get("name") or "").strip():
        return p["name"].strip()
    res = p.get("resource") or ""
    if "/owms/terms/" in res:  # Dutch government organisation URIs
        return res.rsplit("/", 1)[1].replace("_", " ")
    return None


def search(q: str) -> tuple[int, list[dict]]:
    params = {"q": q, "filter": "dataset", "limit": PAGE, "sort": "id asc", "includes": INCLUDES}
    if not q.startswith('"'):
        params["fields"] = "title.*"
    out, page = [], 0
    while True:
        js = fetch_json(API, params={**params, "page": page}, timeout=180, polite_delay=1.0)
        res = js["result"]
        out.extend(res["results"])
        page += 1
        if not res["results"] or len(out) >= res["count"]:
            return res["count"], out


def truncate(s: str | None, n: int = DESC_MAX) -> str | None:
    s = html_to_text(s)
    if not s or len(s) <= n:
        return s
    cut = s[:n]
    end = max(cut.rfind(". "), cut.rfind(".\n"))
    if end > n * 0.6:
        return cut[:end + 1]
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + " …"


def country_of(r: dict) -> tuple[str | None, str]:
    cid = ((r.get("country") or {}).get("id") or "").upper()
    code = geo_code(cid)
    if code:
        return code, geo_name(code)
    if cid in ("EUROPE", "EU", "EUU"):
        return None, "EU / international"
    return None, "Other / unknown"


def build_record(r: dict, matched: list[str]) -> dict:
    code, country = country_of(r)
    dists = r.get("distributions") or []
    formats = sorted({(d.get("format") or {}).get("id", "").upper() for d in dists} - {""})
    licences = sorted({n for n in (licence_name(d.get("license")) for d in dists) if n})
    landing = next((lp.get("resource") for lp in r.get("landing_page") or [] if lp.get("resource")), None)
    seen, keywords = set(), []
    for k in sorted({(k.get("label") or "").strip() for k in r.get("keywords") or []} - {""}, key=lambda x: (x.lower(), x)):
        if k.lower() not in seen:
            seen.add(k.lower())
            keywords.append(k)
    return {
        "id": r["id"],
        "title": pick_title(r),
        "country": country,
        "country_code": code,
        "publisher": publisher_of(r) or "Not stated",
        "concerns_apprenticeship": "Yes" if any(APPRENTICESHIP.search(t) for t in titles(r) + kw_labels(r)) else "No",
        "catalogue": (r.get("catalog") or {}).get("id"),
        "description": truncate((r.get("description") or {}).get("en")),
        "formats": formats or None,
        "licence": licences or ["Not stated"],
        "modified": (r.get("modified") or "")[:10] or None,
        "issued": (r.get("issued") or "")[:10] or None,
        "year": ((r.get("modified") or r.get("issued") or "")[:4]) or None,
        "landing_page": landing,
        "portal_url": PORTAL.format(id=r["id"]),
        "keywords": keywords[:15] or None,
        "matched_queries": matched,
        "original_language": ", ".join(orig_langs(r)) or None,
    }


def fill_description(rec: dict) -> None:
    """Records without an English description: fetch the full record once for the original text."""
    try:
        full = fetch_json(DATASET_API + rec["id"], timeout=60)["result"]
    except Exception:
        return
    desc = full.get("description") or {}
    for l in orig_langs(full):
        if desc.get(l):
            rec["description"] = truncate(desc[l])
            return
    if desc:
        rec["description"] = truncate(next(iter(desc.values())))


def cedefop_watch() -> str:
    js = fetch_json(API, params={"filter": "dataset", "limit": 100,
                                 "facets": json.dumps({"catalog": ["cedefop"]}),
                                 "includes": "id,title.en,modified,issued,distributions.access_url,distributions.download_url,distributions.format.id,distributions.license.id,distributions.license.label"},
                    timeout=120)
    items = []
    for r in js["result"]["results"]:
        urls = set()
        for d in r.get("distributions") or []:
            urls.update(d.get("download_url") or [])
            urls.update(d.get("access_url") or [])
        items.append({
            "id": r["id"],
            "title": (r.get("title") or {}).get("en"),
            "modified": r.get("modified"),
            "issued": r.get("issued"),
            "licence": sorted({n for n in (licence_name(d.get("license")) for d in r.get("distributions") or []) if n}) or None,
            "distribution_urls": sorted(urls),
            "portal_url": PORTAL.format(id=r["id"]),
        })
    items.sort(key=lambda x: x["id"])
    doc = {
        "description": "Datasets in the 'cedefop' catalogue on data.europa.eu (publisher Cedefop). An update signal: a new id, or a changed 'modified'/'issued', means Cedefop published or revised a dataset. Cedefop's own site blocks automated clients.",
        "source": "data.europa.eu search API",
        "api_url": API + "?filter=dataset&limit=100&facets=" + json.dumps({"catalog": ["cedefop"]}, separators=(",", ":")),
        "checked_at": now_iso(),
        "count": len(items),
        "datasets": items,
    }
    if WATCH.exists():
        old = read_json(WATCH)
        if old.get("datasets") == items:
            doc["checked_at"] = old.get("checked_at", doc["checked_at"])
    write_json(WATCH, doc)
    return rel(WATCH)


def run() -> list[str]:
    found: dict[str, dict] = {}
    matched: dict[str, set] = {}
    for q in QUERIES:
        _, rows = search(q)
        for r in rows:
            if not relevant(r):
                continue
            found.setdefault(r["id"], r)
            matched.setdefault(r["id"], set()).add(q.strip('"'))

    records = [build_record(r, sorted(matched[i], key=str.lower)) for i, r in found.items()]
    for rec in records:
        if not rec["description"]:
            fill_description(rec)
    records.sort(key=lambda x: (x["country"], x["title"].lower(), x["id"]))
    records = [{k: v for k, v in rec.items() if v not in (None, [], "")} for rec in records]

    path = write_records(DATASET_ID, records)
    meta_path = path.parent / "meta.json"
    retrieved = now_iso()[:10]
    if meta_path.exists():
        old = read_json(meta_path)
        if old.get("source", {}).get("records_sha256") == _digest(records):
            retrieved = old["source"].get("retrieved", retrieved)
    write_json(meta_path, meta(len(records), retrieved, _digest(records)))
    return [rel(path), rel(meta_path), cedefop_watch()]


def _digest(records: list[dict]) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def meta(n: int, retrieved: str, digest: str) -> dict:
    return {
        "id": DATASET_ID,
        "title": "Apprenticeship and VET open-data catalogue",
        "tagline": f"{n:,} open datasets on apprenticeship and vocational training, found across Europe's national data portals.",
        "description": "Datasets about apprenticeships, vocational education and training published by statistics offices, ministries, regions and cities, as listed on data.europa.eu. Each entry links to the original publisher; Apprentix does not host the data.",
        "recordLabel": {"one": "dataset", "many": "datasets"},
        "source": {
            "name": "data.europa.eu — the official portal for European data (search API)",
            "url": "https://data.europa.eu/",
            "licence": "Catalogue metadata: European Commission reuse notice (Decision 2011/833/EU). Each dataset keeps its own licence, shown per entry.",
            "licence_id": "EC-reuse",
            "caveat": "Found automatically with multilingual searches (apprenticeship, Lehrling, apprentissage, apprendistato, lærling, oppisopimus, vocational training and others) and kept only when the title mentions apprenticeship or VET (or a keyword mentions apprenticeship). 'Concerns apprenticeship' is an Apprentix grouping: Yes when the title or keywords use an apprenticeship-specific term (apprentice, Lehrling, apprendistato, lærling, oppisopimus, dual training …); No for other VET datasets. Map services (WMS/WFS), building plans and machine-learning datasets are excluded. Titles and descriptions are the publishers' own; where there is no English version the original language is shown. Descriptions are shortened. Coverage depends on what national portals harvest into data.europa.eu.",
            "retrieved": retrieved,
            "api_url": API,
            "records_sha256": digest,
        },
        "display": {
            "title": "title",
            "group": "country",
            "badge": "year",
            "link": "portal_url",
            "summary": "description",
            "facts": ["publisher", "formats", "licence"],
        },
        "fields": [
            {"key": "country", "label": "Country", "type": "category", "facet": True},
            {"key": "concerns_apprenticeship", "label": "Concerns apprenticeship", "type": "category", "facet": True, "order": ["Yes", "No"]},
            {"key": "publisher", "label": "Publisher", "type": "category", "facet": True, "collapse": 8},
            {"key": "formats", "label": "Format", "type": "category", "facet": True, "collapse": 6},
            {"key": "licence", "label": "Licence", "type": "category", "facet": True, "collapse": 6},
            {"key": "year", "label": "Last updated", "type": "category", "facet": True, "collapse": 6},
            {"key": "title", "label": "Dataset", "type": "title"},
            {"key": "description", "label": "Description", "type": "longtext"},
            {"key": "catalogue", "label": "Source catalogue", "type": "text"},
            {"key": "modified", "label": "Modified", "type": "text"},
            {"key": "issued", "label": "Issued", "type": "text"},
            {"key": "keywords", "label": "Keywords", "type": "text"},
            {"key": "original_language", "label": "Original language", "type": "text"},
            {"key": "matched_queries", "label": "Found by searching for", "type": "text"},
            {"key": "landing_page", "label": "Publisher's page", "type": "link"},
            {"key": "portal_url", "label": "On data.europa.eu", "type": "link"},
            {"key": "country_code", "label": "Country code", "type": "hidden"},
            {"key": "id", "label": "Identifier", "type": "hidden"},
        ],
        "sections": [
            {"title": "At a glance", "fields": ["country", "publisher", "concerns_apprenticeship", "formats", "licence", "modified", "issued"]},
            {"title": "About", "fields": ["description", "keywords", "original_language"]},
            {"title": "Links and provenance", "fields": ["landing_page", "portal_url", "catalogue", "matched_queries", "id"]},
        ],
    }
