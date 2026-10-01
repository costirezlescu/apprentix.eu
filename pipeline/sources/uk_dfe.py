"""United Kingdom (England only) — DfE Explore Education Statistics (EES) public API.

API docs: https://api.education.gov.uk/statistics/docs/ — no key.
Data set discovered from the "Apprenticeships" publication by title
("Headline Full year ..."), filter/indicator ids resolved from /meta by column
name, so the ids (which are opaque strings) are never hard-coded.

Licence: EES footer — "All content is available under the Open Government Licence
v3.0, except where otherwise stated" (© Crown copyright).
"""

from __future__ import annotations

import json

from ..common import fetch, fetch_json, provenance, rel, save_raw, write_indicator

API = "https://api.education.gov.uk/statistics/v1"
RELEASE = "https://explore-education-statistics.service.gov.uk/find-statistics/apprenticeships"
LICENCE = "OGL-UK-3.0"
PUBLISHER = "Department for Education (England), Explore Education Statistics"

SOURCE = {
    "id": "uk-dfe",
    "name": "DfE Explore Education Statistics — Apprenticeships (England)",
    "publisher": PUBLISHER,
    "homepage": RELEASE,
    "description": "Apprenticeship starts, achievements and participation in England by academic year, by apprenticeship level and age group.",
    "access": "api",
    "browser_cors": None,
    "licence": LICENCE,
    "cadence": "several releases a year; full-year final figures in November",
    "secret": None,
    "outputs": ["indicators/uk-dfe-apprenticeship-starts", "indicators/uk-dfe-apprenticeship-achievements",
                "indicators/uk-dfe-apprenticeship-participation"],
}

DATASET_TITLE = "Headline Full year"
TOTAL_FILTERS = ["funding_type", "provider_type"]   # fixed to 'Total'; level and age kept as dims

COMMON_NOTE = (
    "England only (DfE Individualised Learner Record), not the whole United Kingdom: Scotland, "
    "Wales and Northern Ireland run separate apprenticeship systems and statistics. Time is the "
    "start year of the academic year (August–July), e.g. 2024 = 2024/25. All ages 16+. Levels: "
    "Intermediate = level 2 (EQF 3), Advanced = level 3 (EQF 4), Higher = levels 4–7 (EQF 5–7, "
    "including degree apprenticeships, i.e. higher-education apprenticeships). Figures rounded to "
    "the nearest 10 by DfE. The most recent academic year is provisional and covers only the part "
    "of the year reported to date (e.g. August–April) until the November release; it is flagged "
    "'p' and must not be compared with full years. Do not sum with other countries."
)

SPECS = {
    "start_count": {
        "id": "uk-dfe-apprenticeship-starts",
        "title": "Apprenticeship starts in England",
        "description": "Number of apprenticeship programmes started in England in each academic year, by apprenticeship level and age group.",
        "unit": "starts",
        "topic": "Participation",
        "note": "Flow: programme starts (a learner starting two programmes counts twice). ",
    },
    "achievement_count": {
        "id": "uk-dfe-apprenticeship-achievements",
        "title": "Apprenticeship achievements in England",
        "description": "Number of apprenticeship programmes successfully completed (achieved) in England in each academic year, by apprenticeship level and age group.",
        "unit": "achievements",
        "topic": "Outcomes",
        "note": "Completions: programmes achieved in the academic year. ",
    },
    "participation_count": {
        "id": "uk-dfe-apprenticeship-participation",
        "title": "Apprenticeship participation in England",
        "description": "Number of learners participating in an apprenticeship at any point during each academic year in England, by apprenticeship level and age group.",
        "unit": "learners",
        "topic": "Participation",
        "note": "Participation: learners on an apprenticeship at any time in the academic year (not a "
                "point-in-time stock). DfE does not publish participation for every level × age "
                "combination. ",
    },
}


def _dataset() -> tuple[str, dict]:
    pubs = fetch_json(API + "/publications", params={"search": "apprenticeships", "pageSize": 20})["results"]
    pub = next(p for p in pubs if p["slug"] == "apprenticeships")
    sets = fetch_json(f"{API}/publications/{pub['id']}/data-sets", params={"pageSize": 20})["results"]
    hits = [d for d in sets if d["title"].startswith(DATASET_TITLE) and d.get("status") == "Published"]
    if len(hits) != 1:
        raise ValueError(f"EES: expected one '{DATASET_TITLE}' data set, found {len(hits)}")
    return hits[0]["id"], hits[0]


def _query(ds_id: str, criteria: dict, indicators: list[str]) -> tuple[list[dict], list[bytes]]:
    results, bodies, page = [], [], 1
    while True:
        q = {"criteria": criteria, "indicators": indicators, "page": page, "pageSize": 1000}
        body = fetch(f"{API}/data-sets/{ds_id}/query", data=json.dumps(q).encode(), method="POST",
                     headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=120)
        js = json.loads(body)
        results += js["results"]
        bodies.append(body)
        if page >= js["paging"]["totalPages"]:
            return results, bodies
        page += 1


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None   # DfE symbols: 'z' not applicable, 'low', 'c' confidential, 'x' unavailable


def run() -> list[str]:
    ds_id, ds = _dataset()
    meta = fetch_json(f"{API}/data-sets/{ds_id}/meta")
    filters = {f["column"]: f for f in meta["filters"]}
    opt = {col: {o["id"]: o["label"] for o in f["options"]} for col, f in filters.items()}
    fid = {col: f["id"] for col, f in filters.items()}

    def total(col: str) -> str:
        return next(i for i, l in opt[col].items() if l == "Total")

    nat = next(l for l in meta["locations"] if l["level"]["code"] == "NAT")["options"]
    if [o.get("code") for o in nat] != ["E92000001"]:
        raise ValueError("EES: national location is no longer England (E92000001) only")
    inds = {i["column"]: i["id"] for i in meta["indicators"]}
    periods = [p["period"] for p in meta["timePeriods"]]
    latest = max(periods)
    published = ds["latestVersion"]["published"]
    # The November release carries the finalised full year; every other release
    # adds the new academic year with only the quarters reported to date.
    latest_partial = published[5:7] not in ("11", "12")

    criteria = {"and": [{"geographicLevels": {"eq": "NAT"}},
                        *[{"filters": {"eq": total(col)}} for col in TOTAL_FILTERS]]}
    rows, bodies = _query(ds_id, criteria, [inds[c] for c in SPECS])
    # Row order across pages is not stable, so store the rows canonically sorted.
    canonical = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
    raw, digest = save_raw("uk-dfe", "apprenticeships-headline-full-year-nat.json",
                           json.dumps({"query": criteria, "results": canonical}, sort_keys=True,
                                      ensure_ascii=False, indent=1).encode())

    # Age groups are nested in the youth/adult split: (Total, Total) = all ages;
    # (Under 19, Total) = under 19; (19 plus, Total) = 19+; (19 plus, 19 to 24 | 25 plus).
    def age_code(youth: str, group: str) -> str | None:
        y, g = opt["age_youth_adult"][youth], opt["age_group"][group]
        if g == "Total":
            return {"Total": "TOTAL", "Under 19": "U19", "19 plus": "19+"}.get(y)
        if y == "19 plus":
            return {"19 to 24": "19-24", "25 plus": "25+"}.get(g)
        return None   # e.g. (Under 19, Under 19) duplicates U19

    levels = {i: ("TOTAL" if l == "Total" else l.split()[0].upper()) for i, l in opt["apprenticeship_level"].items()}
    level_labels = {"TOTAL": "Total", "INTERMEDIATE": "Intermediate (level 2)", "ADVANCED": "Advanced (level 3)",
                    "HIGHER": "Higher (levels 4–7, incl. degree apprenticeships)", "UNKNOWN": "Unknown"}
    dim_defs = [
        {"key": "level", "label": "Apprenticeship level",
         "values": {c: level_labels.get(c, c) for c in ["TOTAL", *sorted(set(levels.values()) - {"TOTAL"})]},
         "default": "TOTAL"},
        {"key": "age", "label": "Age", "values": {"TOTAL": "All ages (16+)", "U19": "Under 19", "19+": "19 and over",
                                                  "19-24": "19 to 24", "25+": "25 and over"}, "default": "TOTAL"},
    ]

    written = []
    for col, spec in SPECS.items():
        series = []
        for r in rows:
            v = _num(r["values"].get(inds[col]))
            if v is None:
                continue
            period = r["timePeriod"]["period"]
            f = r["filters"]
            age = age_code(f[fid["age_youth_adult"]], f[fid["age_group"]])
            if age is None:
                continue
            dims = {"level": levels[f[fid["apprenticeship_level"]]], "age": age}
            series.append({"geo": "UK", "time": period[:4], "value": v, "dims": dims,
                           **({"flag": "p"} if period == latest and latest_partial else {})})
        ind = {
            "id": spec["id"],
            "title": spec["title"],
            "description": spec["description"],
            "unit": spec["unit"],
            "topic": spec["topic"],
            "national": True,
            "source_label": f"DfE Apprenticeships — {ds['title']} (v{ds['latestVersion']['version']})",
            "comparability": spec["note"] + COMMON_NOTE,
            "dims": dim_defs,
            "flags": {"p": "provisional, partial academic year (quarters reported to date)"},
            "provenance": provenance(
                publisher=PUBLISHER, dataset_code=ds_id, source_url=RELEASE,
                api_url=f"{API}/data-sets/{ds_id}/query", licence=LICENCE,
                citation=f"Department for Education ({published[:4]}), Apprenticeships: {ds['title']}. Open Government Licence v3.0.",
                source_updated=published[:10], raw=raw, raw_sha256=digest),
            "series": series,
        }
        written.append(rel(write_indicator(ind)))
    return written
