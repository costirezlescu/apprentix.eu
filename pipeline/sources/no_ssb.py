"""Norway — Statistics Norway (SSB) StatBank via PxWebApi v2 (JSON-stat 2.0).

API docs: https://www.ssb.no/en/api/pxwebapiv2 — no key.
Licence (as stated on that page and https://www.ssb.no/en/diverse/lisens):
"The API use the license Creative Commons Attribution 4.0 International (CC BY 4.0)".

Tables (verified live, statistics "vgu", Upper secondary education):
  08947  Pupils, apprentices, students and participants in upper secondary education,
         by sex, age and type of school/institution (stock at 1 October)
  05376  Apprentices and new apprentices, by county of residence and age
  09012  Completed vocational examinations, by age, type of training and results
"""

from __future__ import annotations

import json

from ..common import fetch, fetch_json, provenance, rel, save_raw, write_indicator
from ._jsonstat import cells, labels

API = "https://data.ssb.no/api/pxwebapi/v2/tables/{table}"
TABLE_PAGE = "https://www.ssb.no/en/statbank/table/{table}"
LICENCE = "CC-BY-4.0"
PUBLISHER = "Statistics Norway (SSB)"

SOURCE = {
    "id": "no-ssb",
    "name": "Statistics Norway (SSB) — StatBank",
    "publisher": PUBLISHER,
    "homepage": "https://www.ssb.no/en/vgu",
    "description": "Norwegian apprentices (lærlinger) and training candidates (lærekandidater) at 1 October, new apprentices, and completed trade/journeyman examinations, from SSB's upper-secondary education statistics.",
    "access": "api",
    "browser_cors": None,
    "licence": LICENCE,
    "cadence": "annual (February)",
    "secret": None,
    "outputs": ["indicators/no-ssb-apprentices", "indicators/no-ssb-new-apprentices",
                "indicators/no-ssb-trade-certificates"],
}

STOCK_NOTE = (
    "Norway, national source (SSB table {table}). Stock of persons registered as apprentices "
    "(lærlinger) — and, in the 'type' breakdown, training candidates (lærekandidater, who sit a "
    "less comprehensive skills test instead of the full trade certificate) — in upper secondary "
    "education at 1 October of the year shown. SSB notes that apprentices include pupils in "
    "vocational training at school (Vg3) and trade certificate at work. Upper-secondary (EQF 4) "
    "apprenticeships only; there are no higher-education apprenticeships in this count. "
    "Not a count of contracts or starts; do not sum with other countries."
)


def _meta(table: str) -> dict:
    return fetch_json(API.format(table=table) + "/metadata", params={"lang": "en"})


def _data(table: str, select: dict) -> tuple[dict, bytes, str]:
    params = {"lang": "en", "outputFormat": "json-stat2"}
    params.update({f"valueCodes[{k}]": v for k, v in select.items()})
    url = API.format(table=table) + "/data"
    body = fetch(url, params=params, headers={"Accept": "application/json"}, timeout=120)
    api_url = url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return json.loads(body), body, api_url


def _prov(table: str, js: dict, body: bytes, api_url: str) -> dict:
    raw, digest = save_raw("no-ssb", f"{table}.json", body)
    return provenance(
        publisher=PUBLISHER, dataset_code=table, source_url=TABLE_PAGE.format(table=table),
        api_url=api_url, licence=LICENCE,
        citation=f"Statistics Norway (SSB), StatBank table {table}: {js.get('label', '').split(': ', 1)[-1]}. CC BY 4.0.",
        source_updated=js.get("updated"), raw=raw, raw_sha256=digest)


def _dim(key: str, label: str, values: dict, default: str) -> dict:
    return {"key": key, "label": label, "values": values, "default": default}


def apprentices() -> dict:
    """08947: apprentices (212) and training candidates (213), by sex and age, at 1 October."""
    table = "08947"
    meta = _meta(table)
    types = {"212": "Apprentices (lærlinger)", "213": "Training candidates (lærekandidater)"}
    missing = set(types) - set(meta["dimension"]["Skoleslag"]["category"]["label"])
    if missing:
        raise ValueError(f"SSB {table}: school-type codes {missing} no longer present")
    js, body, api_url = _data(table, {"Skoleslag": "212,213", "Kjonn": "*", "Alder": "*",
                                      "ContentsCode": "*", "Tid": "*"})
    sex = {"0": "Total", "2": "Females", "1": "Males"}
    ages = labels(js, "Alder")
    ages["999A"] = "All ages"
    series = []
    for c, v, st in cells(js):
        if v is None:
            continue
        series.append({"geo": "NO", "time": c["Tid"], "value": v,
                       "dims": {"type": c["Skoleslag"], "sex": c["Kjonn"], "age": c["Alder"]},
                       **({"flag": st} if st else {})})
    return {
        "id": "no-ssb-apprentices",
        "title": "Apprentices in Norway (1 October)",
        "description": "Number of apprentices (lærlinger) in Norwegian upper secondary education at 1 October each year, by sex and age group; training candidates (lærekandidater) are available as a separate type.",
        "unit": "persons",
        "topic": "Participation",
        "national": True,
        "source_label": js.get("label"),
        "comparability": STOCK_NOTE.format(table=table) + " Age is as at 31 December.",
        "dims": [
            _dim("type", "Type", types, "212"),
            _dim("sex", "Sex", sex, "0"),
            _dim("age", "Age", ages, "999A"),
        ],
        "provenance": _prov(table, js, body, api_url),
        "series": series,
    }


def new_apprentices() -> dict:
    """05376: new apprentices, whole country, by age (total computed as the sum of age groups)."""
    table = "05376"
    meta = _meta(table)
    contents = meta["dimension"]["ContentsCode"]["category"]["label"]
    code = next(k for k, v in contents.items() if v.lower().startswith("new apprentice"))
    js, body, api_url = _data(table, {"Region": "0", "Alder": "*", "ContentsCode": code, "Tid": "*"})
    ages = labels(js, "Alder")
    series, totals = [], {}
    for c, v, st in cells(js):
        if v is None:
            continue
        series.append({"geo": "NO", "time": c["Tid"], "value": v, "dims": {"age": c["Alder"]},
                       **({"flag": st} if st else {})})
        totals[c["Tid"]] = totals.get(c["Tid"], 0) + v
    series += [{"geo": "NO", "time": t, "value": v, "dims": {"age": "TOTAL"}} for t, v in totals.items()]
    return {
        "id": "no-ssb-new-apprentices",
        "title": "New apprentices in Norway",
        "description": "Number of new apprentices (nye lærlinger) in Norway per year, by age group. The all-ages total is the sum of SSB's age groups (calculated by Apprentix).",
        "unit": "persons",
        "topic": "Participation",
        "national": True,
        "source_label": js.get("label"),
        "comparability": (
            "Norway, national source (SSB table 05376, whole country). SSB's 'New apprentices' "
            "category: apprentices registered as new in the year, counted in the 1 October "
            "upper-secondary statistics; training candidates (lærekandidater) are not included. "
            "Upper-secondary (EQF 4) apprenticeships only. Age as at 31 December. This is an "
            "entry/flow measure, not the stock of apprentices; do not sum with other countries "
            "or with the stock series."),
        "dims": [_dim("age", "Age", {"TOTAL": "All ages (sum)", **ages}, "TOTAL")],
        "provenance": _prov(table, js, body, api_url),
        "series": series,
    }


def trade_certificates() -> dict:
    """09012: completed trade/journeyman examinations, by type of training and result."""
    table = "09012"
    js, body, api_url = _data(table, {"Alder": "999A", "Laereform": "*", "Resultat2": "*",
                                      "ContentsCode": "*", "Tid": "*"})
    series = []
    for c, v, st in cells(js):
        if v is None:
            continue
        series.append({"geo": "NO", "time": c["Tid"][:4], "value": v,
                       "dims": {"training": c["Laereform"], "result": c["Resultat2"]},
                       **({"flag": st} if st else {})})
    return {
        "id": "no-ssb-trade-certificates",
        "title": "Trade and journeyman examinations taken in Norway",
        "description": "Persons who completed a trade or journeyman's examination (fag-/svenneprøve) in Norway per school year, by type of training (apprentices, practice candidates, pupils) and result (all / passed).",
        "unit": "persons",
        "topic": "Outcomes",
        "national": True,
        "source_label": js.get("label"),
        "comparability": (
            "Norway, national source (SSB table 09012). Completions: persons who sat the trade or "
            "journeyman's examination in the school year; time is the start year of the school "
            "year (e.g. 2024 = 2024/25). 'Apprentices' are candidates who trained under an "
            "apprenticeship contract; 'practice candidates' (praksiskandidater) qualify through "
            "work experience without a contract. Upper-secondary level only. Do not sum with "
            "other countries."),
        "dims": [
            _dim("training", "Type of training", labels(js, "Laereform"), "01"),
            _dim("result", "Result", labels(js, "Resultat2"), "00"),
        ],
        "provenance": _prov(table, js, body, api_url),
        "series": series,
    }


def run() -> list[str]:
    return [rel(write_indicator(f())) for f in (apprentices, new_apprentices, trade_certificates)]
