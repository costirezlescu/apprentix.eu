"""Denmark — Ministry of Children and Education / STIL, Uddannelsesstatistik API:
monthly apprenticeship-place statistics (Lærepladsstatistik) — new training agreements.

API: https://api.uddannelsesstatistik.dk (OpenAPI: /swagger/v1/swagger.json).
  POST /Api/v1/skema      discover område → emne → underemne → nøgletal/detaljering
  POST /Api/v1/statistik  {område, emne, underemne, nøgletal[], detaljering[], filtre{}}
  Header: Authorization: Bearer <key>. A free key is issued after registering at
  https://api.uddannelsesstatistik.dk ("Opret bruger").

UNTESTED: written from the OpenAPI document and the published code examples
without a key. The dataset path is discovered at runtime by matching names
(område 'Erhvervsuddannelser', emne 'Lærepladsstatistik' as listed in the
service's DCAT-AP-DK metadata); if the names or response shapes differ, the
connector stops with an error that lists what the API offered.

Licence: the DCAT-AP-DK metadata (https://api.uddannelsesstatistik.dk/Metadata/v1/DCAT-AP-DK)
declares CC BY 4.0 for the Lærepladsstatistik distributions and the API data service;
STIL's terms of use (https://api.uddannelsesstatistik.dk/Terms) grant a free,
worldwide, non-exclusive right of use and require the credit "Kilde:
Uddannelsesstatistik.dk" (or "Baseret på data fra Uddannelsesstatistik.dk og
efterfølgende bearbejdet") and the retrieval time.
"""

from __future__ import annotations

import json
import os
import re

from ..common import fetch, provenance, rel, save_raw, write_indicator

API = "https://api.uddannelsesstatistik.dk/Api/v1/"
KEY_ENV = "DK_UDDANNELSESSTATISTIK_KEY"
PAGE = "https://uddannelsesstatistik.dk/Pages/Topics/22.aspx"
LICENCE = ("CC BY 4.0 (as declared in the service's DCAT-AP-DK metadata); STIL terms of use require "
           "the credit 'Kilde: Uddannelsesstatistik.dk' and the retrieval date")
PUBLISHER = "Børne- og Undervisningsministeriet / Styrelsen for IT og Læring (STIL), Uddannelsesstatistik.dk"

SOURCE = {
    "id": "dk-uvm",
    "name": "Uddannelsesstatistik.dk — Lærepladsstatistik (Denmark)",
    "publisher": PUBLISHER,
    "homepage": PAGE,
    "description": "Monthly number of new training agreements (indgåede uddannelsesaftaler) in Danish vocational education (EUD), from the Ministry's apprenticeship-place statistics.",
    "access": "api",
    "browser_cors": False,
    "licence": LICENCE,
    "cadence": "monthly",
    "secret": KEY_ENV,
    "outputs": ["indicators/dk-uvm-training-agreements"],
}

AREA = r"^erhvervsuddannelse"
TOPIC = r"l[æa]replads|praktikplads"
SUBTOPIC_PREFS = [r"indg[åa]ede", r"aftale", r"n[øo]gletal", r"l[æa]replads"]
MEASURE = r"indg[åa]ede.*aftale|aftale.*indg[åa]ede"
MONTHS_DA = {"januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5, "juni": 6, "juli": 7,
             "august": 8, "september": 9, "oktober": 10, "november": 11, "december": 12}


def _post(endpoint: str, payload: dict, key: str) -> tuple[object, bytes]:
    body = fetch(API + endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
                 headers={"Content-Type": "application/json", "Accept": "application/json",
                          "Authorization": f"Bearer {key}", "Annotation": "apprentix.eu data pipeline"},
                 timeout=180)
    obj = json.loads(body)
    # The OpenAPI document types responses as string; tolerate JSON wrapped in a string.
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except ValueError:
            pass
    return obj, body


def _names(obj, *keys) -> list[str]:
    """Pull a list of names out of whatever shape the skema endpoint returns."""
    if isinstance(obj, dict):
        for k in keys:
            for kk, v in obj.items():
                if kk.lower().startswith(k):
                    return _names(v)
        return [k for k in obj if isinstance(k, str)]
    out = []
    for it in obj or []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            for k in ("navn", "name", "titel", "title", "værdi", "value"):
                if isinstance(it.get(k), str):
                    out.append(it[k])
                    break
            else:
                s = next((v for v in it.values() if isinstance(v, str)), None)
                if s:
                    out.append(s)
    return out


def _pick(options: list[str], *patterns: str, what: str) -> str:
    for p in patterns:
        hits = [o for o in options if re.search(p, o, re.I)]
        if hits:
            return sorted(hits, key=len)[0]
    raise ValueError(f"Uddannelsesstatistik: no {what} matching {patterns}; API offered: {options}")


def _time(row: dict, fields: list[str]) -> str | None:
    vals = [str(row.get(f, "")).strip() for f in fields]
    s = " ".join(v for v in vals if v)
    m = re.search(r"(\d{4})\s*[-/M]?\s*(\d{1,2})\b", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    y = re.search(r"\b(\d{4})\b", s)
    mo = next((n for name, n in MONTHS_DA.items() if name in s.lower()), None)
    if y and mo:
        return f"{y.group(1)}-{mo:02d}"
    return None


def _number(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):      # Danish thousands separators: 1.234,5
        s = s.replace(".", "")
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None   # discretionised / blank


def run() -> list[str]:
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(f"{KEY_ENV} is not set")

    areas = _names(_post("skema", {}, key)[0], "område", "omraade")
    area = _pick(areas, AREA, what="område")
    topics = _names(_post("skema", {"område": area}, key)[0], "emne")
    topic = _pick(topics, TOPIC, what="emne")
    subs = _names(_post("skema", {"område": area, "emne": topic}, key)[0], "underemne")
    sub = _pick(subs, *SUBTOPIC_PREFS, r".", what="underemne")
    schema, _ = _post("skema", {"område": area, "emne": topic, "underemne": sub}, key)
    measures = _names(schema, "nøgletal", "noegletal")
    details = _names(schema, "detaljering")
    measure = _pick(measures, MEASURE, r"indg[åa]ede", what="nøgletal (new agreements)")
    time_fields = [d for d in details if re.search(r"^(år|måned|kvartal)|måned|periode|tid", d, re.I)]
    month_fields = [d for d in time_fields if re.search(r"måned", d, re.I)]
    year_fields = [d for d in time_fields if re.search(r"^år$|^år\b", d, re.I)]
    fields = month_fields + [y for y in year_fields if y not in month_fields]
    if not month_fields:
        raise ValueError(f"Uddannelsesstatistik: no month detail among {details}")

    query = {"område": area, "emne": topic, "underemne": sub, "nøgletal": [measure],
             "detaljering": fields, "filtre": {}, "indlejret": False, "tomme_rækker": False,
             "formattering": "json", "side": 1, "side_størrelse": 100000}
    data, body = _post("statistik", query, key)
    raw, digest = save_raw("dk-uvm", "laerepladsstatistik-indgaaede-aftaler.json", body)
    rows = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])

    totals = {}
    for r in rows:
        t = _time(r, fields)
        v = _number(r.get(measure))
        if t and v is not None:
            totals[t] = totals.get(t, 0) + v   # sums over any remaining breakdown rows
    if not totals:
        raise ValueError(f"Uddannelsesstatistik: could not parse any month/value from {rows[:3]}")

    ind = {
        "id": "dk-uvm-training-agreements",
        "title": "New training agreements in Danish vocational education (monthly)",
        "description": "Number of new training agreements (indgåede uddannelsesaftaler) between vocational students and employers in Denmark each month, from the Ministry's Lærepladsstatistik.",
        "unit": "agreements",
        "topic": "Participation",
        "national": True,
        "source_label": f"Uddannelsesstatistik.dk — {area} / {topic} / {sub}: {measure}",
        "comparability": (
            "Denmark, national source (STIL apprenticeship-place statistics). Flow: training agreements "
            "concluded in the month between a vocational (EUD) student and an approved company, "
            "covering all agreement types the ministry counts (ordinary, short, rest and combination "
            "agreements). Upper-secondary/post-secondary VET only (EUD; no higher-education "
            "apprenticeships). Not a count of apprentices in training (stock). The ministry "
            "discretionises small cells. Do not sum with other countries."),
        "provenance": provenance(
            publisher=PUBLISHER, dataset_code=f"{area}/{topic}/{sub}", source_url=PAGE,
            api_url=API + "statistik", licence=LICENCE,
            citation="Kilde: Uddannelsesstatistik.dk (Lærepladsstatistik).",
            raw=raw, raw_sha256=digest),
        "series": [{"geo": "DK", "time": t, "value": v} for t, v in totals.items()],
    }
    return [rel(write_indicator(ind))]
