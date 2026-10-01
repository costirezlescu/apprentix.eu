"""OECD: Education at a Glance (EAG) tables via the OECD Data Explorer SDMX API.

API: https://sdmx.oecd.org/public/rest/data/{agency},{DSD@DF},{version}/{key}
No key; at most 60 data downloads per hour per IP, so this connector makes
exactly one call per dataflow (two in total) and filters server-side.
Format: SDMX-CSV with labels (format=csvfilewithlabels).
Licence: CC BY 4.0 by default for OECD content since 1 July 2024 (OECD Terms & Conditions).
"""

from __future__ import annotations

import csv
import io

from ..common import fetch, provenance, rel, save_raw, write_indicator

API = "https://sdmx.oecd.org/public/rest/data/"
EXPLORER = "https://data-explorer.oecd.org/vis?df[ds]=dsDisseminateFinalDMZ&df[id]={df}&df[ag]={agency}"
LICENCE = "CC-BY-4.0"

SOURCE = {
    "id": "oecd",
    "name": "OECD Education at a Glance",
    "publisher": "OECD",
    "homepage": "https://data-explorer.oecd.org/",
    "description": "Education at a Glance tables: share of VET students in combined school- and work-based programmes, and employment rates of adults with vocational versus general upper-secondary attainment. Adds non-EU comparators (CH, NO, IS, TR, UK).",
    "access": "api",
    "browser_cors": True,
    "licence": LICENCE,
    "cadence": "annual (Education at a Glance, September)",
    "secret": None,
    "outputs": ["indicators/oecd-share-vet-sw", "indicators/oecd-emp-rate-upper-secondary"],
}

SPECS = [
    {
        "id": "oecd-share-vet-sw",
        "agency": "OECD.EDU.IMEP",
        "flow": "DSD_EAG_UOE_NON_FIN_STUD@DF_UOE_NF_SHARE_VET",
        "version": "1.1",
        "key": "all",
        "params": {},
        # (column, key in our output, label, default)
        "dims": [("EDUCATION_LEV", "level", "Level", "ISCED11_35SW"),
                 ("SEX", "sex", "Sex", "_T")],
        "title": "Share of VET students in combined school- and work-based programmes (OECD)",
        "unit": "%",
        "topic": "Participation",
        "description": "Students enrolled in vocational programmes that combine school- and work-based learning (ISCED 35SW, 45SW, 55SW in the UOE data collection) as a percentage of all students in vocational programmes at the same ISCED level. From OECD Education at a Glance.",
        "comparability": "Same joint UNESCO-OECD-Eurostat (UOE) collection as Eurostat's educ_uoe_enrs tables, so for EU countries this mirrors the Eurostat-derived share; OECD adds non-EU members. 'School and work-based' is a programme classification made by each country (typically 10-25% or more of learning in the workplace), not a count of apprenticeship contracts; flag M means the category does not exist in the country's system.",
    },
    {
        "id": "oecd-emp-rate-upper-secondary",
        "agency": "OECD.EDU.IMEP",
        "flow": "DSD_EAG_LSO_EA@DF_LSO_NEAC_EMP",
        "version": "1.0",
        # REF_AREA.SEX.AGE.ATTAINMENT_LEV.EDUCATION_FIELD.MEASURE.INCOME.BIRTH_PLACE.MIGRATION_AGE.
        # EDU_STATUS.LABOUR_FORCE_STATUS.DURATION_UNEMP.UNIT_MEASURE.STATISTICAL_OPERATION.
        # WORK_TIME_ARNGMNT.QUESTIONNAIRE.FREQ
        "key": "..Y25T34+Y25T64.ISCED11A_35_45+ISCED11A_34_44+ISCED11A_3_4._T.EMPLOYMENT........OBS...",
        "params": {"startPeriod": "2010"},
        "dims": [("ATTAINMENT_LEV", "attainment", "Highest qualification", "ISCED11A_35_45"),
                 ("AGE", "age", "Age", "Y25T64"),
                 ("SEX", "sex", "Sex", "_T")],
        "title": "Employment rate of adults with vocational vs general upper-secondary qualifications (OECD)",
        "unit": "%",
        "topic": "Outcomes",
        "description": "Employment rate of adults whose highest qualification is upper-secondary or post-secondary non-tertiary, split into vocational (ISCED 35/45) and general (ISCED 34/44) orientation. From OECD Education at a Glance (labour-market outcomes, NEAC data collection).",
        "comparability": "Counts all adults in the age group (in or out of education) whose highest attainment is at this level, from national labour force surveys; it is not limited to recent graduates (unlike Eurostat's edat_lfse_24) and does not single out apprenticeship graduates. Some countries do not split by orientation; flag B marks series breaks and U low reliability.",
    },
]


def get(spec: dict) -> tuple[list[dict], bytes, list[str], str]:
    url = f"{API}{spec['agency']},{spec['flow']},{spec['version']}/{spec['key']}"
    params = {**spec["params"], "dimensionAtObservation": "AllDimensions", "format": "csvfilewithlabels"}
    body = fetch(url, params=params, timeout=180, headers={"Accept": "text/csv"})
    rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
    # csvfilewithlabels has code and label columns side by side: CODE,Label,CODE,Label...
    header = rows[0]
    out = []
    for r in rows[1:]:
        if not r:
            continue
        out.append(dict(zip(header, r)))
    api_url = url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return out, body, header, api_url


def label_col(header: list[str], code_col: str) -> str:
    return header[header.index(code_col) + 1]


def build(spec: dict, rows: list[dict], body: bytes, header: list[str], api_url: str) -> dict:
    raw, digest = save_raw("oecd", f"{spec['id']}.csv", body, keep=len(body) <= 5_000_000)
    dim_values = {key: {} for _, key, _, _ in spec["dims"]}
    flags = {}
    series, missing, seen = [], [], set()
    status_label = label_col(header, "OBS_STATUS")
    for r in rows:
        dims = {}
        for col, key, _, _ in spec["dims"]:
            dims[key] = r[col]
            dim_values[key][r[col]] = r[label_col(header, col)]
        base = {"geo": r["REF_AREA"], "time": r["TIME_PERIOD"], "dims": dims}
        ident = (r["REF_AREA"], r["TIME_PERIOD"], tuple(sorted(dims.items())))
        if ident in seen:
            raise ValueError(f"{spec['id']}: duplicate observation {ident}; tighten the key")
        seen.add(ident)
        flag = r.get("OBS_STATUS") or None
        if flag and flag != "A":
            flags[flag] = r[status_label]
        else:
            flag = None
        value = r.get("OBS_VALUE", "").strip()
        if value == "":
            # Only "data cannot exist" is informative; plain gaps (O) are left out.
            if flag == "M":
                missing.append({**base, "flag": flag})
            continue
        series.append({**base, "value": float(value), **({"flag": flag} if flag else {})})
    first = rows[0]
    ind = {
        "id": spec["id"],
        "title": spec["title"],
        "description": spec["description"],
        "unit": spec["unit"],
        "topic": spec["topic"],
        "source_label": first.get("STRUCTURE_NAME"),
        "comparability": spec["comparability"],
        "dims": [{"key": key, "label": label, "values": dict(sorted(dim_values[key].items())),
                  "default": default} for _, key, label, default in spec["dims"]],
        "flags": dict(sorted(flags.items())),
        "provenance": provenance(
            publisher="OECD", dataset_code=f"{spec['agency']}:{spec['flow']}({spec['version']})",
            source_url=EXPLORER.format(df=spec["flow"], agency=spec["agency"]), api_url=api_url,
            licence=LICENCE,
            citation=f"OECD, Education at a Glance: {first.get('STRUCTURE_NAME')} ({spec['flow']}). Retrieved via the OECD Data Explorer SDMX API.",
            raw=raw, raw_sha256=digest),
        "series": series,
    }
    if missing:
        ind["missing"] = missing
    return {k: v for k, v in ind.items() if v not in (None, [], {})}


def run() -> list[str]:
    written = []
    for spec in SPECS:
        rows, body, header, api_url = get(spec)
        written.append(rel(write_indicator(build(spec, rows, body, header, api_url))))
    return written
