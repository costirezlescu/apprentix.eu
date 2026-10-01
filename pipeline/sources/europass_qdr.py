"""Europass Qualifications Dataset Register (QDR): national VET qualifications at EQF levels 2–5.

Since 23 January 2026 the QDR (qualifications and learning opportunities that
national authorities publish in the European Learning Model, ELM) is open data,
listed on data.europa.eu as 'european-learning-data'. Access methods, as tested:

  * SPARQL endpoint  https://europa.eu/europass/qdr/open-data/sparql
      GET only (POST is refused with 403), JSON results, no row cap (121k rows
      came back in one response), but a ~60 s server limit (heavy joins or
      full-graph scans fail with HTTP 500). A web filter in front of it rejects
      any query containing the words "ORDER BY" (502 "Web Filter"), so we never
      sort on the server. CORS: requests carrying a foreign Origin header are
      refused (403 "Invalid CORS request"), so it is build-time only.
  * DCAT dumps       https://europa.eu/europass/qdr/open-data/dcat
      per-country ZIPs in Turtle (Germany ~1.6 GB in 9 parts, France ~240 MB)
      and JSON-LD; the JSON-LD ZIPs contain only empty files (checked Sept 2026).

So this connector asks the SPARQL endpoint a series of small questions (one
property at a time, one EQF level at a time) and joins the answers here. Only
the standard library is needed.

What is kept:
  * qualifications with status "released" (current) at EQF levels 2–5;
  * not the course offers that KURSNET (the German Federal Employment Agency's
    course database) publishes as "qualifications" — about 12,400 entries such
    as exam-preparation and language courses. Germany is represented by the
    DQR list (Federal–Länder coordination point);
  * not general-education school-leaving qualifications, recognised by title
    (Gymnázium, HAVO/VWO, general Matura, Hauptschulabschluss, Mittlerer
    Schulabschluss, Allgemeine Hochschulreife …). See GENERAL below.

'Apprenticeship / work-based route' is an Apprentix grouping, from the text of
each record (ELM has no apprenticeship field and qualifications carry no mode
of learning): see APPRENTICESHIP_TITLE, APPRENTICESHIP_TEXT and WBL_TEXT.

Licence: European Commission reuse notice (Decision 2011/833/EU), as stated on
the data.europa.eu record of 'european-learning-data'.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict

from ..common import (FetchError, RAW, fetch, geo_code, geo_name, html_to_text, now_iso, read_json,
                      rel, warn, write_json, PUBLISHED)

SOURCE_ID = "europass-qdr"
DATASET_ID = "vet-qualifications"
ENDPOINT = "https://europa.eu/europass/qdr/open-data/sparql"
DCAT = "https://europa.eu/europass/qdr/open-data/dcat"
PORTAL = "https://data.europa.eu/data/datasets/european-learning-data?locale=en"
# The persistent QDR identifier redirects a browser to the record's Europass page
# (…/eportfolio/screen/course/details/qualification?courseId=<uri>&lang=en), at half the length.
EUROPASS = "https://data.europa.eu/snb/data/qualification/{uuid}"
LABELS = RAW / SOURCE_ID / "vocabulary-labels.json"
LEVELS = (2, 3, 4, 5)
SUMMARY_MAX = 220

SOURCE = {
    "id": SOURCE_ID,
    "name": "Europass Qualifications Dataset Register (QDR)",
    "publisher": "European Commission (DG EMPL), Europass; data from national qualification authorities",
    "homepage": PORTAL,
    "description": "National qualifications published to Europass by designated national authorities in the European Learning Model: the vocational ones at EQF levels 2–5, with EQF/NQF level, field, awarding body, credits and a link to each Europass record.",
    "access": "api",
    "browser_cors": False,
    "licence": "EC-reuse",
    "cadence": "weekly (dumps regenerated weekly; national authorities publish continuously)",
    "secret": None,
    "outputs": [f"{DATASET_ID}/records.json", f"{DATASET_ID}/meta.json"],
}

PREFIXES = """PREFIX elm: <http://data.europa.eu/snb/model/elm/>
PREFIX dc: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX regorg: <http://www.w3.org/ns/regorg#>
"""

# Publishers whose "qualifications" are course offers, not qualifications.
EXCLUDED_PUBLISHERS = {
    "http://data.europa.eu/esco/qdr/organizations/9958f948-c9fa-43be-9eab-317e6eef2a2c":
        "KURSNET (Bundesagentur für Arbeit course database)",
}

# General-education school-leaving qualifications (matched on any title).
GENERAL = re.compile(r"""(?ix)
    gymn[aá]zium | \bgymnasium\b | gimnazij | dvojjazyčné\ gymn
  | \bhavo\b | \bvwo\b | hoger\ algemeen\ voortgezet | voorbereidend\ wetenschappelijk | pre-university\ education
  | splošn\w*\ matur | \bgeneral\ matura
  | ^\s*hauptschulabschluss | ^\s*mittlerer\ schulabschluss | allgemeine\ hochschulreife
  | general\ higher\ education\ entrance\ qualification
  | baccalaur[ée]at\ g[ée]n[ée]ral | general\ upper\ secondary | vispārējās\ vidējās
""")

# Apprenticeship or dual training, stated in a title …
APPRENTICESHIP_TITLE = re.compile(r"""(?ix)
    ^\s*lehre\b | ^\s*lehrberuf | ^\s*apprenticeship\b | \(apprenticeship\) | \bby\ apprenticeship
  | lärling | \bapprentissage\b | \bduale[rs]?\ (studium|ausbildung|berufsausbildung)
""")
# … or in the learning-outcome summary / description / notes.
APPRENTICESHIP_TEXT = re.compile(r"""(?ix)
    dual\ vocational\ education\ and\ training          # DQR list: "This qualification is a dual vocational education and training"
  | ^\W*im\ lehrberuf\b                               # Austria: "Im Lehrberuf … lernen die Lehrlinge"
  | abschluss:\ *lehrabschlussprüfung                 # Austria: final exam is the apprenticeship exam
  | (is\ on|industry-based|participate\ in)\ apprenticeship | \bdual\ system\ whereby
""")
NOT_APPRENTICESHIP = re.compile(r"(?i)access to apprenticeship|working with apprentices|formateur de l.alternance")
WBL_TEXT = re.compile(r"(?i)work[- ]based learning|in betrieb und schule|company-based training")

APP_YES = "Apprenticeship / dual"
APP_WBL = "Work-based learning mentioned"
APP_NONE = "Not stated"

# EU Publications Office language authority codes → (ISO 639-1, English name)
LANGS = {
    "BUL": ("bg", "Bulgarian"), "CES": ("cs", "Czech"), "DAN": ("da", "Danish"), "DEU": ("de", "German"),
    "ELL": ("el", "Greek"), "ENG": ("en", "English"), "EST": ("et", "Estonian"), "FIN": ("fi", "Finnish"),
    "FRA": ("fr", "French"), "GLE": ("ga", "Irish"), "HRV": ("hr", "Croatian"), "HUN": ("hu", "Hungarian"),
    "ISL": ("is", "Icelandic"), "ITA": ("it", "Italian"), "LAV": ("lv", "Latvian"), "LIT": ("lt", "Lithuanian"),
    "MLT": ("mt", "Maltese"), "NLD": ("nl", "Dutch"), "NOR": ("no", "Norwegian"), "POL": ("pl", "Polish"),
    "POR": ("pt", "Portuguese"), "RON": ("ro", "Romanian"), "SLK": ("sk", "Slovak"), "SLV": ("sl", "Slovenian"),
    "SPA": ("es", "Spanish"), "SRP": ("sr", "Serbian"), "SWE": ("sv", "Swedish"), "MKD": ("mk", "Macedonian"),
    "SQI": ("sq", "Albanian"), "TUR": ("tr", "Turkish"), "UKR": ("uk", "Ukrainian"),
}

# One query per property; joined client-side. {lvl} is the EQF level filter.
PROPS = {
    "publisher": "?q dc:publisher ?v",
    "title": "?q dc:title ?v",
    "language": "?q dc:language ?v",
    "modified": "?q dc:modified ?v",
    "isced": "?q elm:ISCEDFCode ?v",
    "nqf": "?q elm:NQFLevel ?v",
    "summary": "?q elm:learningOutcomeSummary/elm:noteLiteral ?v",
    "description": "?q dc:description ?v",
    "note": "?q elm:additionalNote/elm:noteLiteral ?v",
    "awarding": "?q elm:awardingOpportunity/elm:awardingBody ?f . ?f regorg:legalName ?v",
    "credit": "?q elm:creditPoint ?c . ?c elm:point ?v . ?c elm:framework ?f",
    "volume": "?q elm:volumeOfLearning ?v",
    "duration": "?q elm:maximumDuration ?v",
    "homepage": "?q foaf:homepage/elm:contentUrl ?v",
}


# ---------------------------------------------------------------- SPARQL --

def sparql(query: str) -> list[dict]:
    if re.search(r"(?i)order\s+by", query):
        raise ValueError("the QDR web filter rejects ORDER BY; sort client-side")
    body = fetch(ENDPOINT, params={"query": PREFIXES + query},
                 headers={"Accept": "application/sparql-results+json"}, timeout=180, polite_delay=0.3)
    js = json.loads(body)
    return [{k: (v["value"], v.get("xml:lang") or None) for k, v in b.items()}
            for b in js["results"]["bindings"]]


def collect() -> dict[str, dict[str, set]]:
    """{property: {qualification uri: {(value, lang[, extra])}}} for released EQF 2–5 qualifications."""
    data: dict[str, dict[str, set]] = {p: defaultdict(set) for p in PROPS}
    data["eqf"] = {}
    for lvl in LEVELS:
        base = f'?q elm:EQFLevel <http://data.europa.eu/snb/eqf/{lvl}> ; elm:status "released" .'
        for prop, pattern in PROPS.items():
            sel = "?q ?v ?f" if "?f" in pattern else "?q ?v"
            rows = sparql(f"SELECT {sel} WHERE {{ {base} {pattern} }}")
            for r in rows:
                q = r["q"][0]
                data[prop][q].add((r["v"][0], r["v"][1], r["f"][0]) if "f" in r else r["v"])
                if prop == "publisher":
                    data["eqf"].setdefault(q, set()).add(lvl)
    return data


def publishers(uris: set[str]) -> dict[str, dict]:
    vals = " ".join(f"<{u}>" for u in sorted(uris))
    rows = sparql("SELECT ?p ?c WHERE { VALUES ?p { " + vals + " } ?p elm:location/elm:address/elm:countryCode ?c }")
    out: dict[str, dict] = {u: {"countries": set()} for u in uris}
    for r in rows:
        out[r["p"][0]]["countries"].add(r["c"][0].rsplit("/", 1)[1])
    return out


# ---------------------------------------------------------------- labels --

def vocabulary_labels(uris: set[str]) -> dict[str, str]:
    """English labels for ISCED-F, NQF and credit-framework concepts, dereferenced from
    data.europa.eu/snb and cached in data/raw/europass-qdr/ (they rarely change)."""
    cache = read_json(LABELS) if LABELS.exists() else {}
    missing = sorted(u for u in uris if u not in cache)
    failed = 0
    for u in missing:
        try:
            xml = fetch(u, headers={"Accept": "application/rdf+xml"}, timeout=60, polite_delay=0.2).decode("utf-8", "replace")
        except FetchError:
            failed += 1
            continue
        m = re.search(r'<skos:prefLabel xml:lang="en">([^<]+)</skos:prefLabel>', xml)
        if m:
            cache[u] = html_to_text(m.group(1))
        else:
            failed += 1
    if failed:
        warn(f"{failed} vocabulary label(s) could not be fetched; codes shown instead")
    if missing:
        write_json(LABELS, dict(sorted(cache.items())))
    return cache


# ---------------------------------------------------------------- helpers -

def pick(values: set, prefer: list[str | None]) -> str | None:
    """A literal in the first preferred language present (deterministic among equals)."""
    vals = sorted({(v.strip(), l) for v, l in values if v and v.strip()}, key=lambda x: (x[1] or "", x[0]))
    for lang in prefer:
        for v, l in vals:
            if l == lang:
                return v
    return vals[0][0] if vals else None


def shorten(s: str | None, n: int = SUMMARY_MAX) -> str | None:
    s = html_to_text(s)
    if not s:
        return None
    s = re.sub(r"\s*\n\s*", " · ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ·")
    if len(s) <= n:
        return s
    cut = s[:n]
    end = cut.rfind(". ")
    if end > n * 0.6:
        return cut[:end + 1]
    return cut.rsplit(" ", 1)[0].rstrip(",;:·-– ") + " …"


_DUR = re.compile(r"^P(?:(\d+(?:\.\d+)?)Y)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)W)?(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?)?$")


def duration(iso: str | None) -> str | None:
    """'P3Y6M' -> '3 years 6 months', 'PT120H' -> '120 hours'; zero or unparsable -> None."""
    m = _DUR.match((iso or "").strip())
    if not m:
        return None
    parts = []
    for val, unit in zip(m.groups(), ("year", "month", "week", "day", "hour", "minute")):
        if val and float(val) > 0:
            x = float(val)
            x = int(x) if x == int(x) else x
            parts.append(f"{x:,} {unit}{'' if x == 1 else 's'}")
    return " ".join(parts) or None


# Lines that say nothing about this particular qualification (Austria's NQF notices and pointers).
BOILERPLATE = re.compile(r"""(?ix)
    qualifi\w*\ ?(framework|rahmen) | this\ qualification\ is\ on\ nqf | diese\ qualifikation\ ist\ auf\ nqr
  | ^\W*(for\ more\ information|siehe|see)\b.*https?:// | certificate\ supplement | zeugniserläuterung""")
DQR_GENERIC = re.compile(r"^(This qualification is an? (?:dual )?vocational education and training[^.]*\.)\s+The vocational education and training system is highly significant")


def clean_text(s: str | None) -> str | None:
    """Drop boilerplate: the DQR list's general description of the dual system (keep its first
    sentence, which gives the training type and length) and Austria's NQF-level notices."""
    s = html_to_text(s)
    if not s:
        return None
    m = DQR_GENERIC.match(s)
    if m:
        return m.group(1)
    lines = [ln for ln in s.split("\n") if not BOILERPLATE.search(ln)]
    return "\n".join(lines).strip() or None


def summary_of(data: dict, q: str, prefer: list) -> str | None:
    for prop in ("summary", "description"):
        vals = data[prop].get(q, set())
        for lang in [*prefer, "*"]:
            for v, l in sorted(vals, key=lambda x: (x[1] or "", x[0])):
                if lang == "*" or l == lang:
                    t = clean_text(v)
                    if t:
                        return shorten(t)
    return None


def credit_label(framework: str) -> str:
    f = framework.lower()
    if "vocational" in f:
        return "ECVET points"
    if "transfer and accumulation" in f or "ects" in f:
        return "ECTS credits"
    return framework


def apprenticeship_flag(titles: list[str], texts: list[str]) -> str:
    if any(NOT_APPRENTICESHIP.search(t) for t in titles):
        return APP_NONE
    if any(APPRENTICESHIP_TITLE.search(t) for t in titles) or any(APPRENTICESHIP_TEXT.search(t) for t in texts):
        return APP_YES
    if any(WBL_TEXT.search(t) for t in texts):
        return APP_WBL
    return APP_NONE


# ---------------------------------------------------------------- build ---

def build(data: dict, pubs: dict, labels: dict) -> tuple[list[dict], dict]:
    stats = defaultdict(int)
    records = []
    for q, levels in data["eqf"].items():
        pub_uris = {v for v, _ in data["publisher"].get(q, set())}
        if pub_uris & set(EXCLUDED_PUBLISHERS):
            stats["excluded_course_offers"] += 1
            continue
        if len(levels) != 1:
            stats["ambiguous_eqf"] += 1
            continue
        lvl = next(iter(levels))
        countries = sorted({c for p in pub_uris for c in pubs.get(p, {}).get("countries", ())})
        codes = sorted({geo_code(c) for c in countries} - {None})
        if len(codes) != 1:
            stats["no_country"] += 1
            continue
        cc = codes[0]

        langs = sorted(v.rsplit("/", 1)[1] for v, _ in data["language"].get(q, set()))
        orig = [LANGS.get(l, (l.lower()[:2], l))[0] for l in langs if l != "ENG"] or ["en"]
        titles_all = data["title"].get(q, set())
        title_en = pick({t for t in titles_all if t[1] == "en"}, ["en"])
        title_orig = pick({t for t in titles_all if t[1] in orig}, orig)
        title = title_en or title_orig or pick(titles_all, [])
        if not title:
            stats["no_title"] += 1
            continue
        title_list = [t for t, _ in titles_all if t and t.strip()]
        if any(GENERAL.search(t) for t in title_list):
            stats["excluded_general"] += 1
            continue

        texts = [v for k in ("summary", "description", "note") for v, _ in data[k].get(q, set()) if v]

        isced = sorted({v.rsplit("/", 1)[1] for v, _ in data["isced"].get(q, set())})
        broad = sorted({c[:2] for c in isced})
        field = [labels.get(f"http://data.europa.eu/snb/isced-f/{b}", f"ISCED-F {b}") for b in broad]
        field_detail = [f"{c} {labels[u]}" if (u := f"http://data.europa.eu/snb/isced-f/{c}") in labels else c
                        for c in isced if len(c) > 2]
        nqf = sorted({labels.get(v, v.rsplit("/", 1)[1]) for v, _ in data["nqf"].get(q, set())})

        bodies: dict[str, set] = defaultdict(set)
        for name, lang, body in data["awarding"].get(q, set()):
            bodies[body].add((name, lang))
        awarding = sorted({n for names in bodies.values() if (n := pick(names, ["en", *orig, None]))}) or None

        credits = sorted({(float(p), credit_label(labels.get(f, f))) for p, _, f in data["credit"].get(q, set())
                          if re.fullmatch(r"\d+(\.\d+)?", p or "") and float(p) > 0})
        credit = "; ".join(f"{(int(p) if p == int(p) else p):g} {lab}" for p, lab in credits) or None
        vol = sorted({d for v, _ in data["volume"].get(q, set()) if (d := duration(v))})
        dur = sorted({d for v, _ in data["duration"].get(q, set()) if (d := duration(v))})
        modified = max((v for v, _ in data["modified"].get(q, set())), default="")[:10] or None
        homepage = sorted(v for v, _ in data["homepage"].get(q, set()) if v.startswith("http"))

        rec = {
            "id": "qdr-" + q.rsplit("/", 1)[1],
            "title": title,
            "title_original": title_orig if title_orig and title_orig != title else None,
            "country": geo_name(cc),
            "country_code": cc,
            "eqf_level": f"EQF {lvl}",
            "nqf_level": nqf or None,
            "apprenticeship": apprenticeship_flag(title_list, texts),
            "field": field or None,
            "field_detail": field_detail or None,
            "awarding_body": awarding,
            "credits": credit,
            "volume": "; ".join(vol) or None,
            "duration": "; ".join(dur) or None,
            "summary": summary_of(data, q, ["en", *orig, None]),
            "language": sorted({LANGS.get(l, (None, l))[1] for l in langs}) or None,
            "updated": modified,
            "europass_url": EUROPASS.format(uuid=q.rsplit("/", 1)[1]),
            "source_page": homepage[0] if homepage else None,
        }
        records.append({k: v for k, v in rec.items() if v not in (None, [], "")})
    records.sort(key=lambda r: (r["country"], r["eqf_level"], r["title"].lower(), r["id"]))
    return records, dict(stats)


def write_compact(path, records: list[dict]) -> None:
    """JSON array, one record per line: about a third smaller than indented JSON, still diffs per record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "[\n" + ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records) + "\n]\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def _digest(records: list[dict]) -> str:
    return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def run() -> list[str]:
    data = collect()
    pub_uris = {v for vals in data["publisher"].values() for v, _ in vals}
    pubs = publishers(pub_uris)
    vocab = {v for k in ("nqf",) for vals in data[k].values() for v, _ in vals}
    vocab |= {f for vals in data["credit"].values() for _, _, f in vals}
    codes = {v.rsplit("/", 1)[1] for vals in data["isced"].values() for v, _ in vals}
    vocab |= {f"http://data.europa.eu/snb/isced-f/{c}" for c in codes}
    vocab |= {f"http://data.europa.eu/snb/isced-f/{c[:2]}" for c in codes}
    labels = vocabulary_labels(vocab)

    records, stats = build(data, pubs, labels)
    path = PUBLISHED / DATASET_ID / "records.json"
    if path.exists():
        old_n = len(read_json(path))
        if old_n and len(records) < old_n * 0.5:
            raise RuntimeError(f"only {len(records)} qualifications (previously {old_n}); not overwriting")
    print(f"  {len(records)} qualifications; skipped: {stats}")
    write_compact(path, records)

    meta_path = path.parent / "meta.json"
    digest = _digest(records)
    retrieved = now_iso()[:10]
    if meta_path.exists():
        old = read_json(meta_path)
        if old.get("source", {}).get("records_sha256") == digest:
            retrieved = old["source"].get("retrieved", retrieved)
    write_json(meta_path, meta(records, retrieved, digest))
    out = [rel(path), rel(meta_path)]
    if LABELS.exists():
        out.append(rel(LABELS))
    return out


def meta(records: list[dict], retrieved: str, digest: str) -> dict:
    n = len(records)
    countries = len({r["country_code"] for r in records})
    return {
        "id": DATASET_ID,
        "title": "National VET qualifications in Europe",
        "tagline": f"{n:,} vocational qualifications at EQF levels 2–5 from {countries} national registers, as published to Europass.",
        "description": "Vocational qualifications that national qualification authorities publish to the Europass Qualifications Dataset Register (QDR), with their EQF and national framework levels, field of education, awarding body, credits and a short learning-outcome summary. Filter to qualifications obtained through apprenticeship or dual training. Each entry links to its official Europass record.",
        "recordLabel": {"one": "qualification", "many": "qualifications"},
        "source": {
            "name": "European Commission, Europass — Qualifications Dataset Register (European Learning Data, SPARQL endpoint)",
            "url": PORTAL,
            "licence": "European Commission reuse notice (Decision 2011/833/EU): reuse allowed with acknowledgement of the source. Data published to the QDR by national qualification authorities.",
            "licence_id": "EC-reuse",
            "caveat": (
                "Coverage depends on what each national authority has published to Europass, and differs widely: some registers are "
                "complete (e.g. France's RNCP, Sweden's higher VET, Austria's qualifications register), Germany is represented by the DQR "
                "list (mostly dual vocational training), and several countries publish no VET qualifications at these levels yet. Included: current ('released') qualifications at EQF levels 2–5, which includes short-cycle higher "
                "education at level 5. Excluded: about 12,400 course offers that KURSNET (the German Federal Employment Agency's course "
                "database) registers as qualifications, records withdrawn from the register ('not published anymore'), and general-education "
                "school-leaving qualifications recognised by title (Gymnázium, HAVO/VWO, general Matura, Hauptschulabschluss, Mittlerer "
                "Schulabschluss, Allgemeine Hochschulreife). 'Apprenticeship / work-based route' is an Apprentix grouping, because the "
                "European Learning Model has no apprenticeship field: 'Apprenticeship / dual' when a title names an apprenticeship "
                "(Lehre, Apprenticeship, lärling, apprentissage, 'by apprenticeship') or the record's text says it is dual vocational "
                "training (Germany's DQR entries), an apprenticeship occupation (Austria's 'Lehrberuf', final exam 'Lehrabschlussprüfung') "
                "or delivered on apprenticeship (Malta); 'Work-based learning mentioned' when the text mentions work-based learning or "
                "training in a company. 'Not stated' does not mean the qualification cannot be taken as an apprenticeship — many school-based "
                "and apprenticeship routes lead to the same qualification (e.g. the Netherlands' BOL/BBL, France's RNCP titles). "
                "No ESCO occupation or skill links are published for these qualifications. Titles are the authorities' own; the English "
                "title is shown where one is published, otherwise the original. Learning-outcome summaries are shortened."
            ),
            "retrieved": retrieved,
            "api_url": ENDPOINT,
            "dump_url": DCAT,
            "records_sha256": digest,
        },
        "display": {
            "title": "title",
            "subtitle": "title_original",
            "group": "country",
            "badge": "eqf_level",
            "link": "europass_url",
            "summary": "summary",
            "facts": ["nqf_level", "field", "apprenticeship"],
        },
        "fields": [
            {"key": "country", "label": "Country", "type": "category", "facet": True, "collapse": 16},
            {"key": "eqf_level", "label": "EQF level", "type": "category", "facet": True,
             "order": ["EQF 2", "EQF 3", "EQF 4", "EQF 5"]},
            {"key": "apprenticeship", "label": "Apprenticeship / work-based route", "type": "category", "facet": True,
             "order": [APP_YES, APP_WBL, APP_NONE]},
            {"key": "field", "label": "Field of education (ISCED-F)", "type": "category", "facet": True, "collapse": 11},
            {"key": "awarding_body", "label": "Awarding body", "type": "category", "facet": True, "collapse": 8},
            {"key": "language", "label": "Language of the record", "type": "category", "facet": True, "collapse": 8},
            {"key": "title", "label": "Qualification", "type": "title"},
            {"key": "title_original", "label": "Original title", "type": "subtitle"},
            {"key": "summary", "label": "Learning outcomes (summary)", "type": "longtext"},
            {"key": "nqf_level", "label": "National framework level", "type": "text"},
            {"key": "field_detail", "label": "Detailed field (ISCED-F)", "type": "text"},
            {"key": "credits", "label": "Credit points", "type": "text"},
            {"key": "volume", "label": "Volume of learning", "type": "text"},
            {"key": "duration", "label": "Maximum duration", "type": "text"},
            {"key": "updated", "label": "Last updated in the register", "type": "text"},
            {"key": "europass_url", "label": "On Europass", "type": "link"},
            {"key": "source_page", "label": "National register page", "type": "link"},
            {"key": "country_code", "label": "Country code", "type": "hidden"},
            {"key": "id", "label": "Identifier", "type": "hidden"},
        ],
        "sections": [
            {"title": "At a glance", "fields": ["country", "eqf_level", "nqf_level", "apprenticeship", "field", "field_detail"]},
            {"title": "About the qualification", "fields": ["summary", "awarding_body", "credits", "volume", "duration", "language"]},
            {"title": "Links and provenance", "fields": ["europass_url", "source_page", "updated", "id"]},
        ],
    }
