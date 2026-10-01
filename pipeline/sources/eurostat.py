"""Eurostat: VET and work-based learning statistics via the Statistics API (JSON-stat 2.0).

API guide: https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started
No key; CORS is open; reuse with acknowledgement (CC BY 4.0, Commission Decision 2011/833/EU).
"""

from __future__ import annotations

import itertools
import json

from ..common import fetch, provenance, save_raw, write_indicator, rel

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
BROWSE = "https://ec.europa.eu/eurostat/databrowser/view/{code}/default/table?lang=en"

SOURCE = {
    "id": "eurostat",
    "name": "Eurostat",
    "publisher": "Eurostat (European Commission)",
    "homepage": "https://ec.europa.eu/eurostat",
    "description": "EU statistics on work-based learning, VET graduates' employment, and pupils in combined school- and work-based programmes — the closest EU-wide proxy for apprenticeship.",
    "access": "api",
    "browser_cors": True,
    "licence": "CC-BY-4.0",
    "cadence": "annual (LFS in September, UOE enrolment in August–September)",
    "secret": None,
}

LICENCE = "CC-BY-4.0"
CITE = "Eurostat ({code}), {label}. Retrieved via the Eurostat Statistics API."

# Each spec: which dataset, which fixed filters, which dimensions to keep as breakdowns.
SPECS = [
    {
        "id": "eurostat-tps00215",
        "code": "tps00215",
        "filters": {},
        "dims": ["sex"],
        "title": "Recent VET graduates who had work-based learning",
        "unit": "%",
        "topic": "Work-based learning",
        "description": "Share of 20–34-year-olds who completed a vocational upper-secondary or post-secondary qualification (ISCED 35/45) in the last three years and had at least one month of work-based learning during that programme.",
        "target": {"value": 60, "year": "2025", "geo": "EU27",
                   "label": "EU-level target: at least 60% by 2025 (Council Recommendation on VET, 2020)"},
        "comparability": "From the EU Labour Force Survey. Several countries carry low-reliability flags (u); check flags before ranking.",
    },
    {
        "id": "eurostat-edat_lfse_24-vet",
        "code": "edat_lfse_24",
        "filters": {"isced11": "ED35_45", "age": "Y20-34", "duration": "Y1-3", "unit": "PC"},
        "dims": ["sex"],
        "title": "Employment rate of recent VET graduates",
        "unit": "%",
        "topic": "Outcomes",
        "description": "Employment rate of 20–34-year-olds, not in education or training, whose highest qualification is vocational upper-secondary or post-secondary (ISCED 35/45), obtained 1–3 years before the survey.",
        "target": {"value": 82, "year": "2025", "geo": "EU27",
                   "label": "EU-level target: at least 82% by 2025 (Council Recommendation on VET, 2020)"},
        "comparability": "From the EU Labour Force Survey; same definition as the EU target indicator.",
    },
    {
        "id": "eurostat-edat_lfse_24-general",
        "code": "edat_lfse_24",
        "filters": {"isced11": "ED34_44", "age": "Y20-34", "duration": "Y1-3", "unit": "PC"},
        "dims": ["sex"],
        "title": "Employment rate of recent general-education graduates",
        "unit": "%",
        "topic": "Outcomes",
        "description": "As the VET graduates' employment rate, but for 20–34-year-olds whose highest qualification is general (not vocational) upper-secondary or post-secondary (ISCED 34/44). Useful as a comparison.",
        "comparability": "From the EU Labour Force Survey.",
    },
    {
        "id": "eurostat-educ_uoe_enrs04-ed3sw",
        "code": "educ_uoe_enrs04",
        "filters": {"isced11": "ED3SW", "sector": "TOT_SEC", "worktime": "TOTAL", "unit": "NR"},
        "dims": ["sex"],
        "title": "Pupils in combined school- and work-based upper-secondary VET",
        "unit": "pupils",
        "topic": "Participation",
        "description": "Number of pupils enrolled in upper-secondary vocational programmes that combine school- and work-based learning (ISCED 3, 'SW' category in the UOE data collection). This is the nearest EU-wide statistical proxy for apprentices — but it is not a count of apprenticeship contracts.",
        "comparability": "Countries map their programmes to the 'school- and work-based' category differently. Flag 'm' means Eurostat considers the category not applicable to the country's system (data cannot exist), not that there are no apprentices.",
    },
    {
        "id": "eurostat-educ_uoe_enrs07-ed4sw",
        "code": "educ_uoe_enrs07",
        "filters": {"isced11": "ED4SW", "sector": "TOT_SEC", "worktime": "TOTAL", "unit": "NR"},
        "dims": ["sex"],
        "title": "Pupils in combined school- and work-based post-secondary VET",
        "unit": "pupils",
        "topic": "Participation",
        "description": "Number of students in post-secondary non-tertiary vocational programmes combining school- and work-based learning (ISCED 4, 'SW' category).",
        "comparability": "As for the upper-secondary series: national programme mapping differs.",
    },
    {
        "id": "eurostat-trng_cvt_34s",
        "code": "trng_cvt_34s",
        "filters": {"unit": "PC"},
        "dims": ["size_emp"],
        "title": "Enterprises employing initial-VET participants",
        "unit": "% of enterprises",
        "topic": "Employers",
        "description": "Share of enterprises (10+ employees) that employed participants in initial vocational training (IVT) such as apprentices, by enterprise size. From the Continuing Vocational Training Survey (CVTS), every five years.",
        "comparability": "CVTS reference years 2005, 2010, 2015, 2020; the 2025 wave is expected around 2027.",
    },
]

# Derived: work-based share of upper-secondary VET = ED3SW / ED35 × 100.
DERIVED_SHARE = {
    "id": "eurostat-ed3sw-share-of-vet",
    "title": "Share of upper-secondary VET pupils in work-based programmes",
    "unit": "%",
    "topic": "Participation",
    "description": "Pupils in combined school- and work-based upper-secondary VET (ED3SW) as a percentage of all upper-secondary VET pupils (ED35). Calculated by Apprentix from Eurostat educ_uoe_enrs04; Cedefop publishes the same ratio as Key indicator 1020.",
    "comparability": "Inherits the caveats of the ED3SW category. Countries flagged 'm' have no work-based category in the UOE mapping.",
}


def decode(js: dict, keep: list[str]) -> tuple[list[dict], list[dict]]:
    """Flatten JSON-stat 2.0 into observations, keeping `keep` dims as breakdowns.

    Returns (observations, flagged_missing). Dimensions other than geo/time and
    `keep` must have size 1 (they were fixed by filters).
    """
    ids, sizes = js["id"], js["size"]
    cats = []
    for d in ids:
        idx = js["dimension"][d]["category"]["index"]
        order = sorted(idx, key=idx.get) if isinstance(idx, dict) else idx
        cats.append(order)
    for d, s in zip(ids, sizes):
        if d not in ("geo", "time", *keep) and s != 1:
            raise ValueError(f"dimension {d} has {s} values; add it to filters or dims")
    values, status = js.get("value", {}), js.get("status", {})
    if isinstance(values, list):
        values = {str(i): v for i, v in enumerate(values) if v is not None}
    obs, missing = [], []
    for i, combo in enumerate(itertools.product(*cats)):
        rec = dict(zip(ids, combo))
        v = values.get(str(i))
        flag = status.get(str(i)) if isinstance(status, dict) else None
        base = {"geo": rec["geo"], "time": rec["time"]}
        dims = {k: rec[k] for k in keep}
        if dims:
            base["dims"] = dims
        if v is None:
            if flag:
                missing.append({**base, "flag": flag})
            continue
        obs.append({**base, "value": v, **({"flag": flag} if flag else {})})
    return obs, missing


def dim_labels(js: dict, keep: list[str]) -> dict:
    return {d: js["dimension"][d]["category"]["label"] for d in keep}


def get(code: str, filters: dict) -> tuple[dict, bytes]:
    params = {"lang": "EN", **filters}
    body = fetch(API + code, params=params, timeout=120)
    return json.loads(body), body


def build(spec: dict, js: dict, body: bytes) -> dict:
    raw, digest = save_raw("eurostat", f"{spec['id']}.json", body)
    obs, missing = decode(js, spec["dims"])
    flags = js.get("extension", {}).get("status", {}).get("label", {})
    api_url = API + spec["code"] + ("?" + "&".join(f"{k}={v}" for k, v in spec["filters"].items()) if spec["filters"] else "")
    ind = {
        "id": spec["id"],
        "title": spec["title"],
        "description": spec["description"],
        "unit": spec["unit"],
        "topic": spec["topic"],
        "source_label": js.get("label"),
        "comparability": spec.get("comparability"),
        "dims": [{"key": k, "label": k.replace("_", " ").capitalize(), "values": v,
                  "default": next(iter(v))} for k, v in dim_labels(js, spec["dims"]).items()],
        "flags": flags,
        "provenance": provenance(
            publisher="Eurostat", dataset_code=spec["code"],
            source_url=BROWSE.format(code=spec["code"]), api_url=api_url,
            licence=LICENCE, citation=CITE.format(code=spec["code"], label=js.get("label")),
            source_updated=js.get("updated"), raw=raw, raw_sha256=digest),
        "series": obs,
    }
    if spec.get("target"):
        ind["target"] = spec["target"]
    if missing:
        ind["missing"] = missing
    # Default for sex breakdowns is the total.
    for d in ind["dims"]:
        if "T" in d["values"]:
            d["default"] = "T"
        if "TOTAL" in d["values"]:
            d["default"] = "TOTAL"
    return {k: v for k, v in ind.items() if v not in (None, [], {})}


def run() -> list[str]:
    written = []
    fetched = {}
    for spec in SPECS:
        js, body = get(spec["code"], spec["filters"])
        fetched[spec["id"]] = js
        written.append(rel(write_indicator(build(spec, js, body))))

    # Derived share needs ED35 too (sex = total only).
    js35, body35 = get("educ_uoe_enrs04", {"isced11": "ED35", "sector": "TOT_SEC", "worktime": "TOTAL", "unit": "NR", "sex": "T"})
    raw35, dig35 = save_raw("eurostat", "educ_uoe_enrs04-ed35.json", body35)
    sw, _ = decode(fetched["eurostat-educ_uoe_enrs04-ed3sw"], ["sex"])
    vet, _ = decode(js35, ["sex"])
    vet_by = {(o["geo"], o["time"]): o["value"] for o in vet}
    series = []
    for o in sw:
        if o["dims"]["sex"] != "T":
            continue
        denom = vet_by.get((o["geo"], o["time"]))
        if denom:
            series.append({"geo": o["geo"], "time": o["time"], "value": 100 * o["value"] / denom,
                           **({"flag": o["flag"]} if o.get("flag") else {})})
    _, missing = decode(fetched["eurostat-educ_uoe_enrs04-ed3sw"], ["sex"])
    ind = {
        **DERIVED_SHARE,
        "source_label": "Calculated from Eurostat educ_uoe_enrs04 (ED3SW ÷ ED35)",
        "flags": js35.get("extension", {}).get("status", {}).get("label", {}),
        "provenance": provenance(
            publisher="Eurostat; calculation by Apprentix", dataset_code="educ_uoe_enrs04",
            source_url=BROWSE.format(code="educ_uoe_enrs04"),
            api_url=API + "educ_uoe_enrs04?isced11=ED3SW&isced11=ED35&sector=TOT_SEC&worktime=TOTAL&sex=T",
            licence=LICENCE, citation="Apprentix calculation from Eurostat (educ_uoe_enrs04).",
            source_updated=js35.get("updated"), raw=raw35, raw_sha256=dig35),
        "series": series,
    }
    miss = [{k: v for k, v in m.items() if k != "dims"} for m in missing if m["dims"]["sex"] == "T"]
    if miss:
        ind["missing"] = miss
    written.append(rel(write_indicator(ind)))
    return written
