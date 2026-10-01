"""Ireland — CSO PX-Stat: Apprenticeship Outcomes (product AOQY), JSON-stat 2.0.

API: https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/<table>/JSON-stat/2.0/en
(no key). Tables are discovered from the product collection (ReadCollection,
product AOQY) so a renamed/withdrawn table fails loudly.

Licence (https://www.cso.ie/en/aboutus/whoweare/copyrightpolicy/): "Statistical
information on this website is accessible free of charge and licensed under
Creative Commons Attribution (CC BY 4.0)."

Note: the SOLAS FET tables on PX-Stat (product SOL) state "This data excludes
apprenticeship and eCollege provision", so SOLAS apprentice *registrations* are
not available there; this connector uses CSO's own apprenticeship-outcomes
release (qualified apprentices and their later employment), built from SOLAS
registration data linked to administrative records.
"""

from __future__ import annotations

import json

from ..common import fetch, provenance, rel, save_raw, write_indicator
from ._jsonstat import cells, labels

RPC = "https://ws.cso.ie/public/api.jsonrpc"
DATASET = "https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/{table}/JSON-stat/2.0/en"
TABLE_PAGE = "https://data.cso.ie/table/{table}"
RELEASE = "https://www.cso.ie/en/statistics/education/apprenticeshipoutcomesqualificationyear/"
LICENCE = "CC-BY-4.0"
PUBLISHER = "Central Statistics Office (CSO), Ireland"

SOURCE = {
    "id": "ie-cso",
    "name": "CSO Ireland — Apprenticeship Outcomes",
    "publisher": PUBLISHER,
    "homepage": RELEASE,
    "description": "Number of apprentices qualifying each year in Ireland (by sex and NFQ level) and the share in employment in the years after qualifying, from the CSO Apprenticeship Outcomes release.",
    "access": "api",
    "browser_cors": None,
    "licence": LICENCE,
    "cadence": "irregular (latest release April 2025, qualification years 2010–2020)",
    "secret": None,
    "outputs": ["indicators/ie-cso-qualified-apprentices", "indicators/ie-cso-apprentice-employment-rate"],
}

BASE_NOTE = (
    "Ireland, national source (CSO Apprenticeship Outcomes, from SOLAS apprenticeship records "
    "linked to CSO administrative data). Time is the year the apprentice qualified. Includes "
    "craft apprenticeships (NFQ level 6 Advanced Certificate) and the newer consortia-led "
    "apprenticeships (NFQ levels 5–8 in these tables), some of which are higher-education awards (NFQ 7–8, "
    "i.e. bachelor level). CSO rounds individual figures to the nearest five. "
)


def _collection() -> dict:
    body = json.dumps({"jsonrpc": "2.0", "method": "PxStat.Data.Cube_API.ReadCollection",
                       "params": {"language": "en", "datefrom": "2015-01-01", "product": "AOQY"},
                       "id": 1}).encode()
    js = json.loads(fetch(RPC, data=body, headers={"Content-Type": "application/json"},
                          method="POST", timeout=120))
    return {it["extension"]["matrix"]: it for it in js["result"]["link"]["item"]}


def _get(table: str, available: dict) -> tuple[dict, dict]:
    if table not in available:
        raise ValueError(f"CSO table {table} no longer listed in product AOQY")
    url = DATASET.format(table=table)
    body = fetch(url, headers={"Accept": "application/json"}, timeout=120)
    js = json.loads(body)
    raw, digest = save_raw("ie-cso", f"{table}.json", body)
    prov = provenance(
        publisher=PUBLISHER, dataset_code=table, source_url=TABLE_PAGE.format(table=table),
        api_url=url, licence=LICENCE,
        citation=f"Central Statistics Office, Ireland. {table}: {js.get('label')}. CC BY 4.0.",
        source_updated=(js.get("updated") or "")[:10] or None, raw=raw, raw_sha256=digest)
    return js, prov


def _c(code: str) -> str:
    """CSO uses '-' for the all-categories total; publish it as TOTAL."""
    return "TOTAL" if code == "-" else code


def _labels(js: dict, dim: str) -> dict:
    return {_c(k): v for k, v in labels(js, dim).items()}


def _dimkey(js: dict, label: str) -> str:
    return next(d for d in js["id"] if (js["dimension"][d].get("label") or "").lower().startswith(label.lower()))


def qualified(available: dict) -> dict:
    """AOQY02: qualified apprentices by sex and NFQ level (all ages)."""
    js, prov = _get("AOQY02", available)
    t, sex, age, nfq = _dimkey(js, "Qualification Year"), _dimkey(js, "Sex"), _dimkey(js, "Age"), _dimkey(js, "NFQ")
    series = []
    for c, v, st in cells(js):
        if v is None or c[age] != "-":
            continue
        series.append({"geo": "IE", "time": c[t], "value": v,
                       "dims": {"sex": _c(c[sex]), "nfq": _c(c[nfq])}, **({"flag": st} if st else {})})
    return {
        "id": "ie-cso-qualified-apprentices",
        "title": "Apprentices qualifying in Ireland",
        "description": "Number of apprentices who qualified (completed their apprenticeship) in Ireland each year, by sex and National Framework of Qualifications (NFQ) level.",
        "unit": "persons",
        "topic": "Outcomes",
        "national": True,
        "source_label": js.get("label"),
        "comparability": BASE_NOTE + "Completions (qualifications awarded), not registrations or stock; "
                         "includes records with missing or invalid PPSN. Do not sum with other countries.",
        "dims": [
            {"key": "sex", "label": "Sex", "values": _labels(js, sex), "default": "TOTAL"},
            {"key": "nfq", "label": "NFQ level", "values": _labels(js, nfq), "default": "TOTAL"},
        ],
        "provenance": prov,
        "series": series,
    }


def employment_rate(available: dict) -> dict:
    """AOQY13: share of qualified apprentices in employment N years after qualifying.

    Rate = (Employment only + Employment and Education) / All outcomes x 100,
    computed by Apprentix from CSO's rounded counts.
    """
    js, prov = _get("AOQY13", available)
    t, sex, out, yrs = (_dimkey(js, "Qualification Year"), _dimkey(js, "Sex"),
                        _dimkey(js, "Qualification Outcome"), _dimkey(js, "Years since"))
    counts = {}
    for c, v, _ in cells(js):
        if v is not None:
            counts[(c[t], c[sex], c[yrs], c[out])] = v
    series = []
    for (ty, sx, yr, o), total in counts.items():
        if o != "-" or not total:
            continue
        emp = [counts.get((ty, sx, yr, k)) for k in ("10", "20")]
        if None in emp:
            continue
        series.append({"geo": "IE", "time": ty, "value": 100 * sum(emp) / total,
                       "dims": {"sex": _c(sx), "years_since": yr}})
    return {
        "id": "ie-cso-apprentice-employment-rate",
        "title": "Qualified apprentices in employment in Ireland",
        "description": "Share of apprentices who qualified in a given year who were in employment (with or without further education) a number of years after qualifying, by sex. Calculated by Apprentix from CSO counts: (employment only + employment and education) ÷ all qualified apprentices × 100.",
        "unit": "%",
        "topic": "Outcomes",
        "national": True,
        "source_label": "Calculated from CSO " + str(js.get("label")) + " (AOQY13)",
        "comparability": BASE_NOTE + "Employment is derived from administrative (Revenue) records; "
                         "the denominator includes apprentices whose outcome was 'not captured' "
                         "(e.g. emigrated), and excludes records with missing or invalid PPSN. "
                         "Rates are computed from counts rounded to the nearest five. Time is the "
                         "qualification year; choose 'years since qualification' to compare cohorts "
                         "at the same distance. Not comparable with survey-based (LFS) employment "
                         "rates of VET graduates.",
        "dims": [
            {"key": "sex", "label": "Sex", "values": _labels(js, sex), "default": "TOTAL"},
            {"key": "years_since", "label": "Years since qualification", "values": labels(js, yrs), "default": "02"},
        ],
        "provenance": {**prov, "publisher": PUBLISHER + "; calculation by Apprentix"},
        "series": series,
    }


def run() -> list[str]:
    available = _collection()
    return [rel(write_indicator(qualified(available))), rel(write_indicator(employment_rate(available)))]
