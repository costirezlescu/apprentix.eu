"""Compact per-country profiles for the "Country vs country" duel page.

  data/published/duel/countries.json

  python -m pipeline.duel

One small JSON the duel page (pages/duel.html) loads once. For every country
with a profile page (plus the EU-27 aggregate as a comparator) it holds:

  figures    latest value of ~14 key indicators (default breakdown), with the
             same "first available alternative" rule as the country pages
             (render_pages.KEY_FIGURES), and a direction ("better") per measure
  schemes    Cedefop apprenticeship schemes and, per coded question, the set of
             answers across the country's schemes
  policy     VET / apprenticeship policy counts and the latest apprenticeship
             reform (Cedefop VET policy timeline)
  money      financing instruments by type, Erasmus+ VET grant and accredited
             organisations, CoVE participations
  nqf        apprenticeship and craft qualifications in the NQF, with EQF levels
  open_data  open datasets in the catalogue
  national   national statistics (NOT comparable between countries)

Deterministic: no timestamps beyond those already in the data.
"""

from __future__ import annotations

import json

from . import render_pages as rp
from .common import INDICATORS, PUBLISHED, RAW, read_json
from .curate.scheme_questions import QUESTIONS

OUT = PUBLISHED / "duel" / "countries.json"
EU = "EU27"

# Measures shown under "Key figures": (key, short label, better, alternatives).
# Alternatives follow render_pages.KEY_FIGURES (first one with data is used);
# two measures are added (access to tertiary, youth unemployment).
# better: "higher" / "lower" (a defined direction) or "neutral" (a description
# of the system, or a size-dependent count, where neither side is "ahead").
MEASURES = [
    ("wbl", "Recent VET graduates with work-based learning", "higher", rp.KEY_FIGURES[0]),
    ("wb_share", "Upper-secondary VET pupils in work-based programmes", "neutral", rp.KEY_FIGURES[1]),
    ("wb_pupils", "Pupils in combined school- and work-based VET", "neutral", rp.KEY_FIGURES[2]),
    ("ivet_share", "Upper-secondary students in vocational programmes", "neutral", rp.KEY_FIGURES[3]),
    ("vet_emp", "Employment rate of recent VET graduates", "higher", rp.KEY_FIGURES[4]),
    ("vet_premium", "Employment premium of VET graduates over general", "higher", rp.KEY_FIGURES[5]),
    ("adult_emp", "Employment rate of adults with a VET qualification", "higher", rp.KEY_FIGURES[6]),
    ("firms_ivet", "Enterprises employing initial-VET participants", "higher", rp.KEY_FIGURES[7]),
    ("mobility", "IVET learners with a learning mobility abroad", "higher", rp.KEY_FIGURES[8]),
    ("erasmus_proj", "Erasmus+ VET mobility projects", "neutral", rp.KEY_FIGURES[9]),
    ("he_access", "IVET students with direct access to tertiary education", "higher", ["cedefop-kivet-1025"]),
    ("early_leavers", "Early leavers from education and training", "lower", rp.KEY_FIGURES[10]),
    ("neet", "Young people (15–29) not in employment, education or training", "lower", rp.KEY_FIGURES[11]),
    ("youth_unemp", "Unemployment rate of 20–34-year-olds", "lower", ["cedefop-kivet-3040"]),
]

# Scheme questions summarised side by side (coded Cedefop answers).
SCHEME_QS = ["q_compensation", "q_min_workplace_share", "q_learner_status", "q_contract_type",
             "q_access_to_he", "q_typical_age", "q_financial_incentives", "q_pay_funded_by",
             "q_share_of_vet", "q_learner_incentives"]
SCHEME_FIELDS = ["duration", "workplace_time", "compensation", "education_level", "learners"]

# Headline national series per country, in order of preference (first with data wins).
NATIONAL_HEADLINE = [
    "fr-dares-apprentices-stock", "uk-dfe-apprenticeship-participation", "no-ssb-apprentices",
    "ch-bfs-learners-vet-form", "ch-bfs-learners-vet", "fi-statfin-apprenticeship-students",
    "nl-duo-bbl-students", "ie-cso-qualified-apprentices",
]

ERASMUS_GRANT = "erasmus-ka1-vet-grant"
ERASMUS_YEAR = "2025"
TYPE_RANK = {"Regulation/Legislation": 0, "Strategy/Action plan": 1, "Practical measure/Initiative": 2}


def _latest_per_geo(ind: dict) -> tuple[dict, dict]:
    """(latest observation per geo, {(geo, time): obs}) for the default breakdown."""
    dims = ind.get("dims") or []
    best = {}
    for o in ind["series"]:
        if all((o.get("dims") or {}).get(d["key"], d.get("default")) == d.get("default") for d in dims):
            best[(o["geo"], o["time"])] = o
    per_geo = {}
    for (g, t), o in best.items():
        if g not in per_geo or t > per_geo[g]["time"]:
            per_geo[g] = o
    return per_geo, best


def _num(v):
    """Round for a compact file without losing displayed precision."""
    if v is None:
        return None
    r = round(float(v), 3)
    return int(r) if r == int(r) and abs(r) >= 1 else r


def _obs(o: dict) -> dict:
    out = {"v": _num(o["value"]), "y": o["time"]}
    if o.get("flag"):
        out["f"] = o["flag"]
    return out


def _ed35_pupils() -> dict:
    """Upper-secondary VET pupils (Eurostat educ_uoe_enrs04, ED35), latest year per geo."""
    files = sorted((RAW / "eurostat").glob("*educ_uoe_enrs04-ed35.json"))
    if not files:
        return {}
    raw = read_json(files[-1])
    gidx = raw["dimension"]["geo"]["category"]["index"]
    tidx = raw["dimension"]["time"]["category"]["index"]
    ginv, tinv, nt = {v: k for k, v in gidx.items()}, {v: k for k, v in tidx.items()}, len(tidx)
    out = {}
    for k, v in raw["value"].items():
        k = int(k)
        g = {"EU27_2020": EU}.get(ginv[k // nt], ginv[k // nt])
        t = tinv[k % nt]
        if v is not None and (g not in out or t > out[g][1]):
            out[g] = (v, t)
    return out


def _option_order(qkey: str) -> list[str]:
    for _, (key, _label, _multi, opts) in QUESTIONS.items():
        if key == qkey:
            return list(dict.fromkeys(opts.values()))
    return []


def _q_label(qkey: str) -> str:
    for _, (key, label, _multi, _opts) in QUESTIONS.items():
        if key == qkey:
            return label
    return qkey


def _values(rec: dict, key: str) -> list[str]:
    v = rec.get(key)
    if v in (None, ""):
        return []
    return v if isinstance(v, list) else [v]


def _schemes(schemes: list[dict]) -> dict | None:
    if not schemes:
        return None
    answers = {}
    for q in SCHEME_QS:
        seen = {x for s in schemes for x in _values(s, q)}
        order = _option_order(q)
        answers[q] = [x for x in order if x in seen] + sorted(seen - set(order))
    return {
        "count": len(schemes),
        "list": [{
            "id": s["id"], "name": s.get("name_en", ""), "orig": s.get("name_original", ""),
            **{k: s[k] for k in SCHEME_FIELDS if s.get(k)},
            "q": {q: _values(s, q) for q in SCHEME_QS if _values(s, q)},
        } for s in schemes],
        "answers": answers,
    }


def _latest_reform(app_policies: list[dict]) -> dict | None:
    if not app_policies:
        return None
    p = sorted(app_policies, key=lambda p: (-(int(p.get("first_year") or 0)),
                                            TYPE_RANK.get(p.get("type"), 9), p.get("title", "")))[0]
    return {"id": p["id"], "title": p.get("title", ""), "year": p.get("first_year"),
            "type": p.get("type"), "stage": p.get("latest_stage"), "stage_year": p.get("latest_year")}


def build() -> dict:
    D = rp.load()
    ref = D["ref"]
    cmeta = {c["code"]: c for c in ref["countries"]}
    index_by_id = D["by_id"]

    # Latest values for every alternative of every measure.
    ind_ids = sorted({i for *_, alts in MEASURES for i in alts if i in index_by_id})
    L = {}
    for iid in ind_ids:
        ind = read_json(INDICATORS / f"{iid}.json")
        per_geo, by_time = _latest_per_geo(ind)
        L[iid] = {"ind": ind, "latest": per_geo, "by_time": by_time}

    # National series (one country each).
    national_ids = sorted(i["id"] for i in D["index"] if i.get("national"))
    NL_ = {}
    for iid in national_ids:
        ind = read_json(INDICATORS / f"{iid}.json")
        NL_[iid] = {"ind": ind, "latest": _latest_per_geo(ind)[0]}

    grant_ind = read_json(INDICATORS / f"{ERASMUS_GRANT}.json") if ERASMUS_GRANT in index_by_id else None
    grant_latest, grant_by_time = _latest_per_geo(grant_ind) if grant_ind else ({}, {})
    pupils = _ed35_pupils()

    indicators_used: dict[str, dict] = {}

    def use(ind: dict) -> None:
        if ind["id"] in indicators_used:
            return
        p = ind.get("provenance") or {}
        indicators_used[ind["id"]] = {
            "title": ind.get("title", ""),
            "unit": ind.get("unit", ""),
            "publisher": p.get("publisher", ""),
            **({"breakdown": n} if (n := rp.dims_note(ind)) else {}),
            **({"flags": ind["flags"]} if ind.get("flags") else {}),
        }

    def figures(code: str) -> dict:
        out = {}
        for key, _label, _better, alts in MEASURES:
            for iid in alts:
                if iid in L and code in L[iid]["latest"]:
                    use(L[iid]["ind"])
                    out[key] = {"id": iid, **_obs(L[iid]["latest"][code])}
                    break
        return out

    # EU-27 reference for every alternative (latest + recent years), so the page
    # can show the EU value of the very indicator both countries are compared on.
    eu_ref = {}
    for iid in ind_ids:
        years = sorted(t for (g, t) in L[iid]["by_time"] if g == EU)
        if years:
            use(L[iid]["ind"])
            eu_ref[iid] = {t: _obs(L[iid]["by_time"][(EU, t)]) for t in years[-8:]}

    def erasmus(code: str) -> dict | None:
        o = grant_by_time.get((code, ERASMUS_YEAR)) or grant_latest.get(code)
        if not o:
            return None
        out = {"eur": _num(round(o["value"])), "year": o["time"]}
        pp = pupils.get(code)
        if pp and pp[0]:
            out["pupils"] = int(pp[0])
            out["pupils_year"] = pp[1]
            out["per_pupil"] = _num(round(o["value"] / pp[0], 1))
        return out

    cove_all = D["extra"]["cove-projects"]["all"]

    countries = {}
    for c in D["countries"]:
        code = c["code"]
        f = rp.country_facts(D, code)
        if not rp.has_content(f):
            continue
        app_q = [q for q in f["nqf_qualification_levels"] if q.get("apprenticeship_or_craft") == "Yes"]
        eqf = sorted({lv for q in app_q for lv in q.get("eqf_level", []) if lv.startswith("EQF")},
                     key=lambda s: int(s.split()[1]) if s.split()[1].isdigit() else 99)
        fi = f["financing_instruments"]
        types = {}
        for r in fi:
            for t in r.get("type", []):
                types[t] = types.get(t, 0) + 1
        cove = f["cove_projects"]
        nat = []
        for iid in national_ids:
            Ln = NL_[iid]
            if code in Ln["latest"] and (index_by_id[iid].get("coverage") or {}).get("geos") == [code]:
                ind = Ln["ind"]
                p = ind.get("provenance") or {}
                nat.append({"id": iid, "title": ind.get("title", ""), "unit": ind.get("unit", ""),
                            "publisher": p.get("publisher", ""),
                            **({"breakdown": n} if (n := rp.dims_note(ind)) else {}),
                            **_obs(Ln["latest"][code])})
        rank = {iid: i for i, iid in enumerate(NATIONAL_HEADLINE)}
        nat.sort(key=lambda x: (rank.get(x["id"], 99), x["id"]))
        catalogue = f["catalogue"]
        countries[code] = {
            "name": c["name"],
            "flag": c.get("flag", ""),
            "group": c.get("group", ""),
            "page": f"pages/countries/{code.lower()}.html",
            "figures": figures(code),
            "schemes": _schemes(f["schemes"]),
            "policy": {
                "vet": len(f["policies"]),
                "apprenticeship": len(f["app_policies"]),
                "latest_reform": _latest_reform(f["app_policies"]),
            } if f["policies"] else None,
            "financing": {"count": len(fi), "types": dict(sorted(types.items()))} if fi else None,
            "erasmus": {
                "orgs": len(f["erasmus_vet_organisations"]),
                **({"grant": g} if (g := erasmus(code)) else {}),
            },
            "cove": {
                "projects": len(cove),
                "coordinated": sum(1 for r in cove_all if r.get("coordinator_country_code") == code),
            },
            "nqf": {
                "types": len(f["nqf_qualification_levels"]),
                "apprenticeship": [{"t": q["qualification_type"], "nqf": q.get("nqf_level", ""),
                                    "eqf": q.get("eqf_level", [])} for q in app_q],
                "eqf_levels": eqf,
            } if f["nqf_qualification_levels"] else None,
            "vet_system": ({"version": f["vet_systems"][0].get("version", ""),
                            "url": f["vet_systems"][0].get("source_url", "")} if f["vet_systems"] else None),
            "open_data": {
                "datasets": len(catalogue),
                "apprenticeship": sum(1 for r in catalogue if r.get("concerns_apprenticeship") == "Yes"),
            },
            "national": nat,
        }

    # EU-27 as a comparator: key figures and Erasmus+ totals only.
    eu_c = cmeta.get(EU, {"name": "European Union (27)", "flag": ""})
    eu_codes = {c["code"] for c in ref["countries"] if c.get("group") == "eu"}
    eu_orgs = sum(len(v) for g, v in D["extra"]["erasmus-vet-organisations"]["by_country"].items() if g in eu_codes)
    countries[EU] = {
        "name": "EU-27",
        "full_name": eu_c["name"],
        "flag": eu_c.get("flag", ""),
        "group": "aggregate",
        "page": None,
        "figures": figures(EU),
        "schemes": None, "policy": None, "financing": None,
        "erasmus": {"orgs": eu_orgs, **({"grant": g} if (g := erasmus(EU)) else {})},
        "cove": {"projects": len(cove_all), "coordinated": sum(
            1 for r in cove_all if r.get("coordinator_country_code") in eu_codes)},
        "nqf": None, "vet_system": None, "open_data": None, "national": [],
    }

    out = {
        "description": ("Compact per-country profiles for the Apprentix country duel (pages/duel.html). "
                        "Generated by pipeline/duel.py from data/published; every figure links back to its indicator."),
        "updated": D["updated"],
        "eu": EU,
        "measures": [{"key": k, "label": lbl, "better": b, "alts": [i for i in alts if i in index_by_id]}
                     for k, lbl, b, alts in MEASURES],
        "questions": {q: {"label": _q_label(q), "options": _option_order(q)} for q in SCHEME_QS},
        "indicators": dict(sorted(indicators_used.items())),
        "eu_ref": eu_ref,
        "erasmus_note": (f"EU grant to Erasmus+ KA1 VET mobility projects by coordinator country, {ERASMUS_YEAR} call; "
                         "per pupil = grant ÷ upper-secondary VET pupils (Eurostat educ_uoe_enrs04, ISCED 35, latest year)."),
        "countries": dict(sorted(countries.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\n"
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
        OUT.write_text(text, encoding="utf-8")
    return out


if __name__ == "__main__":
    o = build()
    print(f"{OUT.relative_to(PUBLISHED.parent.parent)}: {len(o['countries'])} profiles, "
          f"{OUT.stat().st_size / 1024:.0f} KB")
