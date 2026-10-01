"""UNESCO Institute for Statistics (UIS): vocational-education indicators via the UIS Data API.

API docs: https://api.uis.unesco.org/api/public/documentation/
No key, no rate limit, CORS open. Data are versioned: we read the current default
version once and pin every data call to it, so a rerun against the same release
returns identical data.
Licence (API docs and https://databrowser.uis.unesco.org/terms-and-conditions):
"The work of the UIS is licensed under the Creative Commons Attribution-ShareAlike
4.0 International license." Required credit: "Source: UNESCO Institute for
Statistics (UIS), complete URL, date of extraction."
"""

from __future__ import annotations

import json

from ..common import countries, fetch, fetch_json, provenance, rel, save_raw, write_indicator

API = "https://api.uis.unesco.org/api/public"
BROWSER = "https://databrowser.uis.unesco.org/"
LICENCE = "CC-BY-SA-4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

SOURCE = {
    "id": "uis",
    "name": "UNESCO Institute for Statistics (UIS)",
    "publisher": "UNESCO Institute for Statistics",
    "homepage": "https://databrowser.uis.unesco.org/",
    "description": "Global education statistics: share of students in vocational programmes by ISCED level, share of 15–24-year-olds in vocational education, and government spending on vocational education. Fills gaps for candidate countries (AL, BA, GE, MD, ME, MK, RS, TR, UA).",
    "access": "api",
    "browser_cors": True,
    "licence": "CC BY-SA 4.0 (UIS terms and conditions; credit 'Source: UNESCO Institute for Statistics (UIS)', URL and date of extraction)",
    "cadence": "two data releases a year (typically February/March and September)",
    "secret": None,
    "outputs": ["indicators/uis-gtvp-3-v", "indicators/uis-gtvp-4-v", "indicators/uis-gtvp-5-v",
                "indicators/uis-gtvp-2t3-v", "indicators/uis-ev1524p-2t5-v", "indicators/uis-xgdp-2t4-v-fsgov"],
}

UOE_NOTE = ("For EU, EFTA and OECD countries these figures come from the same joint UNESCO-OECD-Eurostat (UOE) "
            "collection as Eurostat's education statistics; UIS adds candidate countries. 'Vocational' includes "
            "school-based as well as work-based (apprenticeship-type) programmes, so this measures the weight of VET, "
            "not of apprenticeship.")

SPECS = [
    {"code": "GTVP.3.V", "unit": "%", "topic": "Participation",
     "title": "Share of upper-secondary students in vocational programmes (UIS)",
     "description": "Students enrolled in vocational programmes at upper-secondary level (ISCED 3) as a percentage of all upper-secondary students, both sexes.",
     "comparability": UOE_NOTE},
    {"code": "GTVP.4.V", "unit": "%", "topic": "Participation",
     "title": "Share of post-secondary non-tertiary students in vocational programmes (UIS)",
     "description": "Students enrolled in vocational programmes at post-secondary non-tertiary level (ISCED 4) as a percentage of all students at that level, both sexes.",
     "comparability": UOE_NOTE + " ISCED 4 is small or absent in some systems, so shares can swing between 0 and 100%."},
    {"code": "GTVP.5.V", "unit": "%", "topic": "Participation",
     "title": "Share of short-cycle tertiary students in vocational programmes (UIS)",
     "description": "Students enrolled in vocational programmes at short-cycle tertiary level (ISCED 5) as a percentage of all short-cycle tertiary students, both sexes.",
     "comparability": UOE_NOTE + " Many countries have no short-cycle tertiary level or report it only from 2011 (ISCED 2011)."},
    {"code": "GTVP.2T3.V", "unit": "%", "topic": "Participation",
     "title": "Share of secondary students in vocational programmes (UIS)",
     "description": "Students enrolled in vocational programmes in lower and upper secondary education combined (ISCED 2–3) as a percentage of all secondary students, both sexes.",
     "comparability": UOE_NOTE + " Includes lower secondary, so it is lower than the upper-secondary share and long series mix ISCED 1997 and ISCED 2011."},
    {"code": "EV1524P.2T5.V", "unit": "% of age group", "topic": "Participation",
     "title": "Share of 15–24-year-olds enrolled in vocational education (UIS)",
     "description": "Enrolment in vocational programmes (ISCED 2–5) of people aged 15–24 as a percentage of the population aged 15–24, both sexes.",
     "comparability": UOE_NOTE + " The denominator is a population estimate (UN or Eurostat), so it reflects both VET popularity and how long young people stay in education."},
    {"code": "XGDP.2T4.V.FSGOV", "unit": "% of GDP", "topic": "Expenditure",
     "title": "Government expenditure on vocational secondary and post-secondary education (UIS)",
     "description": "Government expenditure on vocational programmes in secondary and post-secondary non-tertiary education (ISCED 2–4) as a percentage of GDP.",
     "comparability": "Public spending only (all levels of government); excludes employer spending on apprentices' wages and in-company training, which is the larger share of apprenticeship cost in dual systems. Country coverage is patchy."},
]

FLAGS = {
    "NAT_EST": "National estimation",
    "UIS_EST": "UIS estimation",
    "NIL": "Magnitude nil or negligible",
}


def ind_id(code: str) -> str:
    return "uis-" + code.lower().replace(".", "-")


def run() -> list[str]:
    version = fetch_json(f"{API}/versions/default")
    ver = version["version"]
    edu = next((t for t in version.get("themeDataStatus", []) if t.get("theme") == "EDUCATION"), {})
    updated = None
    if edu.get("lastUpdate"):  # MM/DD/YYYY
        m, d, y = edu["lastUpdate"].split("/")
        updated = f"{y}-{m}-{d}"

    geos = sorted(c["iso3"] for c in countries()["by_code"].values() if c.get("group") != "aggregate")
    params = [("indicator", s["code"]) for s in SPECS] + [("geoUnit", g) for g in geos]
    params += [("indicatorMetadata", "false"), ("footnotes", "false"), ("version", ver)]
    body = fetch(f"{API}/data/indicators", params=params, headers={"Accept": "application/json"}, timeout=120)
    js = json.loads(body)
    raw, digest = save_raw("uis", "vocational-indicators.json", body)
    query = "&".join(f"{k}={v}" for k, v in params)

    by_code = {}
    for r in js.get("records", []):
        by_code.setdefault(r["indicatorId"], []).append(r)

    written = []
    for spec in SPECS:
        series, used = [], set()
        for r in by_code.get(spec["code"], []):
            if r.get("value") is None:
                continue
            flag = r.get("qualifier") or r.get("magnitude")
            if flag:
                used.add(flag)
            series.append({"geo": r["geoUnit"], "time": r["year"], "value": r["value"],
                           **({"flag": flag} if flag else {})})
        if not series:
            continue
        prov = provenance(
            publisher="UNESCO Institute for Statistics (UIS)", dataset_code=f"{spec['code']} (data version {ver})",
            source_url=BROWSER, api_url=f"{API}/data/indicators?{query}",
            licence=LICENCE,
            citation=f"Source: UNESCO Institute for Statistics (UIS), indicator {spec['code']}, {BROWSER}, data version {ver}.",
            source_updated=updated, raw=raw, raw_sha256=digest)
        prov["licence_url"] = LICENCE_URL
        ind = {
            "id": ind_id(spec["code"]),
            "title": spec["title"],
            "description": spec["description"],
            "unit": spec["unit"],
            "topic": spec["topic"],
            "source_label": spec["code"],
            "comparability": spec["comparability"],
            "flags": {k: v for k, v in FLAGS.items() if k in used},
            "provenance": prov,
            "series": series,
        }
        ind = {k: v for k, v in ind.items() if v not in (None, [], {})}
        written.append(rel(write_indicator(ind)))
    return written
