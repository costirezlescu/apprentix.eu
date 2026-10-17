"""The Occupation lens: "Want to be an electrician?" across Europe.

For each occupation in data/reference/occupation-lens.json (ESCO-linked, with title patterns
checked by hand) this collects, per country:

  - the national VET qualifications published to Europass whose title matches the occupation
    (data/published/vet-qualifications), grouped by EQF level, with the apprenticeship flag;
  - the country's apprenticeship schemes and whether it has official "find an apprenticeship" links;
  - Cedefop's short-term employment forecast for the occupation's ISCO major group.

  python -m pipeline.occupations

  data/published/occupations/occupations.json

Deterministic: no clock. Rendered by pipeline/render_occupations.py.
"""

from __future__ import annotations

import html
import re
import unicodedata

from .common import INDICATORS, PUBLISHED, REFERENCE, geo_code, read_json, write_json

OUT = PUBLISHED / "occupations" / "occupations.json"
LENS = REFERENCE / "occupation-lens.json"
LENS_ESCO = REFERENCE / "occupation-lens-esco.json"
STAS = INDICATORS / "cedefop-stas-employment-growth.json"

ISCO_MAJOR = {
    "1": "Managers", "2": "Professionals", "3": "Technicians and associate professionals",
    "4": "Clerical support workers", "5": "Service and sales workers",
    "6": "Skilled agricultural, forestry and fishery workers", "7": "Craft and related trades workers",
    "8": "Plant and machine operators and assemblers", "9": "Elementary occupations",
}
# ISCO-08 unit groups that ESCO only reaches through a broader occupation.
ISCO_UNIT = {"3115": "Mechanical engineering technicians"}
SKILLS_SHOWN = 12


def norm(s: str | None) -> str:
    s = html.unescape(s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def clean_title(s: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def eqf_int(v: str | None) -> int | None:
    m = re.search(r"\d", v or "")
    return int(m.group()) if m else None


def matcher(o: dict, global_exclude: list[str]):
    inc = [re.compile(p) for p in o["match"]["include"]]
    exc = [re.compile(p) for p in o["match"].get("exclude", []) + global_exclude]

    def test(rec: dict) -> bool:
        t = norm(rec.get("title")) + " || " + norm(rec.get("title_original"))
        return any(p.search(t) for p in inc) and not any(p.search(t) for p in exc)
    return test


def stas_growth() -> dict:
    """{isco major: {geo: {time: value}}} from Cedefop STAS, % growth."""
    if not STAS.exists():
        return {}, None
    ind = read_json(STAS)
    out: dict[str, dict] = {}
    for o in ind["series"]:
        occ = (o.get("dims") or {}).get("occupation")
        out.setdefault(occ, {}).setdefault(o["geo"], {})[o["time"]] = o["value"]
    return out, ind


def build() -> dict:
    lens = read_json(LENS)
    esco = read_json(LENS_ESCO)["occupations"] if LENS_ESCO.exists() else {}
    quals = read_json(PUBLISHED / "vet-qualifications" / "records.json")
    qmeta = read_json(PUBLISHED / "vet-qualifications" / "meta.json")
    schemes = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")
    opp = read_json(REFERENCE / "opportunities.json")["countries"]
    ref = read_json(REFERENCE / "countries.json")
    names = {c["code"]: c["name"] for c in ref["countries"]}
    growth, stas = stas_growth()
    stas_year = max((t for g in growth.values() for s in g.values() for t in s), default=None)

    schemes_by: dict[str, list] = {}
    for s in schemes:
        g = geo_code(s.get("country_code") or "")
        if g:
            schemes_by.setdefault(g, []).append({"id": s["id"], "name": s.get("name_en"), "flag": s.get("flag")})
    qdr_countries = sorted({geo_code(q["country_code"]) for q in quals} - {None})
    has_find = {g for g, v in opp.items() if any(l.get("kind") == "find" for l in v.get("links", []))}

    occupations = []
    for o in lens["occupations"]:
        test = matcher(o, lens.get("global_exclude", []))
        by_country: dict[str, dict] = {}
        for q in quals:
            if not test(q):
                continue
            g = geo_code(q["country_code"])
            title = clean_title(q.get("title"))
            key = (title.lower(), eqf_int(q.get("eqf_level")))
            c = by_country.setdefault(g, {})
            if key not in c:
                orig = clean_title(q.get("title_original"))
                c[key] = {"title": title, "title_original": orig if orig and orig != title else None,
                          "eqf": key[1], "apprenticeship": q.get("apprenticeship") == "Apprenticeship / dual",
                          "url": q.get("europass_url"), "records": 0}
            item = c[key]
            item["records"] += 1
            item["apprenticeship"] = item["apprenticeship"] or q.get("apprenticeship") == "Apprenticeship / dual"
            if q.get("europass_url") and (item["url"] or "") > q["europass_url"]:
                item["url"] = q["europass_url"]  # stable choice among duplicates

        countries = []
        for g, items in by_country.items():
            qs = sorted(items.values(), key=lambda x: (not x["apprenticeship"], x["eqf"] or 0, x["title"].lower()))
            levels: dict[str, int] = {}
            for x in qs:
                levels[str(x["eqf"])] = levels.get(str(x["eqf"]), 0) + 1
            countries.append({
                "code": g, "name": names.get(g, g),
                "count": len(qs), "records": sum(x["records"] for x in qs),
                "levels": dict(sorted(levels.items())),
                "apprenticeship": sum(1 for x in qs if x["apprenticeship"]),
                "qualifications": [{k: v for k, v in x.items() if v not in (None, 0) or k == "eqf"} for x in qs],
                "schemes": schemes_by.get(g, []),
                "find": g in has_find,
            })
        countries.sort(key=lambda c: (-c["count"], c["name"]))
        found = {c["code"] for c in countries}
        no_qdr = sorted((g for g in schemes_by if g not in qdr_countries),
                        key=lambda g: names.get(g, g))
        qdr_no_match = [g for g in qdr_countries if g not in found]

        e = esco.get(o["esco_uri"], {})
        isco_unit = (e.get("isco_group") or {}).get("code") or o.get("isco08")
        isco_title = (e.get("isco_group") or {}).get("title") or ISCO_UNIT.get(isco_unit)
        major = (isco_unit or "")[:1]
        outlook = None
        if major in growth and stas_year:
            rows = [{"geo": g, "name": names.get(g, g), "value": round(v[stas_year], 2)}
                    for g, v in growth[major].items() if stas_year in v and g != "EU27"]
            rows.sort(key=lambda r: -r["value"])
            eu = growth[major].get("EU27", {}).get(stas_year)
            outlook = {"isco_major": major, "isco_major_title": ISCO_MAJOR.get(major), "year": stas_year,
                       "eu": round(eu, 2) if eu is not None else None, "rows": rows,
                       "indicator": "cedefop-stas-employment-growth"}

        related = [esco[u] for u in o.get("related_uris", []) if u in esco]
        levels_all = sorted({int(l) for c in countries for l in c["levels"]})
        occupations.append({
            "slug": o["slug"], "name": o["name"], "with_article": o["with_article"], "note": o.get("note"),
            "esco": {
                "uri": o["esco_uri"], "label": e.get("label") or o.get("esco_label"), "code": e.get("code") or o["esco_code"],
                "description": e.get("description"),
                "isco_unit": isco_unit, "isco_unit_title": isco_title,
                "labels": e.get("labels", {}),
                "skills": [s["title"] for s in e.get("essential_skills", [])[:SKILLS_SHOWN]],
                "skills_total": len(e.get("essential_skills", [])),
                "related": [{"uri": r["uri"], "label": r["label"]} for r in related],
            },
            "summary": {
                "countries": len(countries), "qualifications": sum(c["count"] for c in countries),
                "apprenticeship": sum(c["apprenticeship"] for c in countries),
                "levels": levels_all,
            },
            "countries": countries,
            "qdr_no_match": [{"code": g, "name": names.get(g, g)} for g in qdr_no_match],
            "schemes_no_qdr": [{"code": g, "name": names.get(g, g), "schemes": schemes_by[g], "find": g in has_find}
                               for g in no_qdr],
            "outlook": outlook,
        })

    doc = {
        "description": "The Occupation lens: for each occupation, the national VET qualifications published to Europass that lead to it (matched by title), by country and EQF level, with Cedefop's employment forecast for its occupation group.",
        "method": lens["method"],
        "checked": lens.get("checked"),
        "qdr_countries": [{"code": g, "name": names.get(g, g)} for g in qdr_countries],
        "sources": {
            "qualifications": {"name": qmeta["source"]["name"], "url": qmeta["source"]["url"],
                               "retrieved": qmeta["source"].get("retrieved"), "dataset": "vet-qualifications"},
            "esco": {"name": "ESCO — European Skills, Competences, Qualifications and Occupations (European Commission)",
                     "url": "https://esco.ec.europa.eu/", "acknowledgement": "This service uses the ESCO classification of the European Commission."},
            "outlook": {"name": stas["provenance"]["publisher"] + ", " + stas["provenance"]["dataset_code"],
                        "url": stas["provenance"]["source_url"]} if stas else None,
        },
        "occupations": occupations,
    }
    write_json(OUT, doc)
    return doc


if __name__ == "__main__":
    d = build()
    for o in d["occupations"]:
        s = o["summary"]
        print(f'{o["slug"]:26s} {s["qualifications"]:4d} quals in {s["countries"]:2d} countries, EQF {s["levels"]}, appr {s["apprenticeship"]}')
