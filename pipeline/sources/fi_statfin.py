"""Finland — Statistics Finland (Tilastokeskus) StatFin PxWeb API, table 14rw:
students and qualifications in vocational education by mode of competence acquisition.

API: https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/opiskt/14rw.px (PxWeb v1, no key).
Licence (https://www.stat.fi/org/lainsaadanto/copyright_en.html): "Statistics
Finland's open data materials and public content of the web service are covered
by the Creative Commons Attribution 4.0 International licence."

Why not Vipunen: the Vipunen API (api.vipunen.fi) does carry an apprenticeship
flag (oppisopimuskoulutusKyllaEi) but only in the record-level funding resources
(amm_rahoitus_opiskelijavuodet: 41.5 million rows; ~95,000 rows for a single
month of apprenticeship) and offers filtering but no aggregation, which is
impractical for a static-site pipeline. Statistics Finland publishes the same
KOSKI-register population already aggregated.

Since the 2018 VET reform, apprenticeship (oppisopimus) is a mode of acquiring
competence within a vocational qualification, not a separate programme: a
student may combine school-based learning with training-agreement
(koulutussopimus, unpaid) and/or apprenticeship (paid employment) periods.
"""

from __future__ import annotations

import json
import re

from ..common import fetch, fetch_json, provenance, rel, save_raw, write_indicator
from ._jsonstat import cells, labels

TABLE = "14rw"
API = f"https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/opiskt/{TABLE}.px"
PAGE = f"https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__opiskt/{TABLE}.px/"
LICENCE = "CC-BY-4.0"
PUBLISHER = "Statistics Finland (Tilastokeskus)"

SOURCE = {
    "id": "fi-statfin",
    "name": "Statistics Finland — vocational students by mode of competence acquisition",
    "publisher": PUBLISHER,
    "homepage": "https://stat.fi/en/statistics/opiskt",
    "description": "Finnish vocational students, new students and qualifications whose studies included apprenticeship (oppisopimus) periods, by qualification type and sex, from Statistics Finland table 14rw.",
    "access": "api",
    "browser_cors": None,
    "licence": LICENCE,
    "cadence": "annual (May; revised in October)",
    "secret": None,
    "outputs": ["indicators/fi-statfin-apprenticeship-students", "indicators/fi-statfin-apprenticeship-new-students",
                "indicators/fi-statfin-apprenticeship-qualifications"],
}

QUALS = {"TOTAL": "All vocational qualifications", "INITIAL": "Initial vocational qualifications (EQF 4)",
         "FURTHER": "Further vocational qualifications (EQF 4)", "SPECIALIST": "Specialist vocational qualifications (EQF 5)"}
# Parenthetical in the StatFin category label -> mode code
MODE_TEXT = {
    "training agreement or apprenticeship training periods not included": "SCHOOL",
    "training agreement and apprenticeship training periods included": "BOTH",
    "training agreement periods included": "TA",
    "apprenticeship training periods included": "APPR",
}
MODES = {
    "ANY_APPR": "With apprenticeship periods (apprenticeship only + apprenticeship and training agreement)",
    "APPR_ONLY": "Apprenticeship periods only (no training-agreement periods)",
    "APPR_AND_TA": "Both apprenticeship and training-agreement periods",
    "ALL_VET": "All vocational students (any mode, for reference)",
}
MODE_PARTS = {"ANY_APPR": ("APPR", "BOTH"), "APPR_ONLY": ("APPR",), "APPR_AND_TA": ("BOTH",),
              "ALL_VET": ("SCHOOL", "TA", "APPR", "BOTH")}

MEASURES = {
    "opis_aop": {
        "id": "fi-statfin-apprenticeship-students",
        "title": "Vocational students with apprenticeship periods in Finland",
        "description": "Students in Finnish vocational education during the calendar year whose studies included apprenticeship training (oppisopimus) periods, by qualification type and sex.",
        "unit": "students",
        "topic": "Participation",
        "what": "Students who studied at any time during the calendar year (not a point-in-time stock). ",
    },
    "uusi_aop": {
        "id": "fi-statfin-apprenticeship-new-students",
        "title": "New vocational students with apprenticeship periods in Finland",
        "description": "Students who started vocational education in Finland during the calendar year and whose studies included apprenticeship training (oppisopimus) periods, by qualification type and sex.",
        "unit": "students",
        "topic": "Participation",
        "what": "New students who started during the calendar year. ",
    },
    "tut_aop": {
        "id": "fi-statfin-apprenticeship-qualifications",
        "title": "Vocational qualifications with apprenticeship periods in Finland",
        "description": "Vocational qualifications completed in Finland during the calendar year where the studies included apprenticeship training (oppisopimus) periods, by qualification type and sex.",
        "unit": "qualifications",
        "topic": "Outcomes",
        "what": "Qualifications completed during the calendar year (completions). ",
    },
}

NOTE = (
    "Finland, national source (Statistics Finland, KOSKI register). Since the 2018 VET reform "
    "apprenticeship is a mode of acquiring competence inside a vocational qualification: counts "
    "here are people whose studies included at least one apprenticeship (oppisopimus, paid "
    "employment) period, possibly combined with school-based learning and training-agreement "
    "(koulutussopimus, unpaid) periods — not a count of apprenticeship contracts. Covers initial "
    "(upper-secondary), further and specialist vocational qualifications; many apprentices are "
    "adults taking further/specialist qualifications. No higher-education apprenticeships. Series "
    "starts in 2019. Do not sum with other countries."
)


def _classify(meta_var: dict) -> dict:
    """Map each category code to (qualification, mode) by parsing its English label."""
    out = {}
    for code, text in zip(meta_var["values"], meta_var["valueTexts"]):
        if code == "SSS":
            continue
        m = re.match(r"^(Initial|Further|Specialist) vocational qualifications \((.+)\)$", text)
        if not m or m.group(2) not in MODE_TEXT:
            raise ValueError(f"StatFin {TABLE}: unexpected category {code!r} {text!r}")
        out[code] = (m.group(1).upper(), MODE_TEXT[m.group(2)])
    return out


def run() -> list[str]:
    meta = fetch_json(API)
    var = {v["code"]: v for v in meta["variables"]}
    mode_var = next(c for c in var if c.startswith("koullaji"))
    sex_var = next(c for c in var if c.startswith("sukupuoli"))
    others = [c for c in var if c.startswith(("koulutusala", "alue", "ikaryhma"))]
    cats = _classify(var[mode_var])
    query = {"query": [{"code": mode_var, "selection": {"filter": "item", "values": list(cats)}},
                       {"code": sex_var, "selection": {"filter": "item", "values": ["SSS", "1", "2"]}},
                       *[{"code": c, "selection": {"filter": "item", "values": ["SSS"]}} for c in others],
                       {"code": "contentscode", "selection": {"filter": "item", "values": list(MEASURES)}}],
             "response": {"format": "json-stat2"}}
    body = fetch(API, data=json.dumps(query).encode(), method="POST",
                 headers={"Content-Type": "application/json"}, timeout=120)
    js = json.loads(body)
    raw, digest = save_raw("fi-statfin", f"{TABLE}.json", body)
    time_var = next(d for d in js["id"] if d.startswith("timeperiod"))
    sexes = labels(js, sex_var)
    sexes["SSS"] = "Total"

    # value[(measure, year, sex, qual, mode)]
    val = {}
    for c, v, _ in cells(js):
        if v is None:
            continue
        q, mode = cats[c[mode_var]]
        val[(c["contentscode"], c[time_var], c[sex_var], q, mode)] = v

    written = []
    years = sorted({k[1] for k in val})
    for measure, spec in MEASURES.items():
        series = []
        for y in years:
            for sx in sexes:
                for mode, parts in MODE_PARTS.items():
                    for qual in QUALS:
                        quals = ("INITIAL", "FURTHER", "SPECIALIST") if qual == "TOTAL" else (qual,)
                        comps = [val.get((measure, y, sx, q, p)) for q in quals for p in parts]
                        if None in comps:
                            continue
                        series.append({"geo": "FI", "time": y, "value": sum(comps),
                                       "dims": {"mode": mode, "qualification": qual, "sex": sx}})
        ind = {
            "id": spec["id"],
            "title": spec["title"],
            "description": spec["description"] + " Totals are sums of Statistics Finland categories (calculated by Apprentix).",
            "unit": spec["unit"],
            "topic": spec["topic"],
            "national": True,
            "source_label": f"Statistics Finland, StatFin table {TABLE}: {meta['title']}",
            "comparability": spec["what"] + NOTE,
            "dims": [
                {"key": "mode", "label": "Mode of competence acquisition", "values": MODES, "default": "ANY_APPR"},
                {"key": "qualification", "label": "Qualification type", "values": QUALS, "default": "TOTAL"},
                {"key": "sex", "label": "Sex", "values": sexes, "default": "SSS"},
            ],
            "provenance": provenance(
                publisher=PUBLISHER, dataset_code=TABLE, source_url=PAGE, api_url=API, licence=LICENCE,
                citation=f"Source: Statistics Finland, StatFin table {TABLE} ({meta['title']}). CC BY 4.0.",
                source_updated=(js.get("updated") or "")[:10] or None, raw=raw, raw_sha256=digest),
            "series": series,
        }
        written.append(rel(write_indicator(ind)))
    return written
