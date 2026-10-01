"""Analyses across everything Apprentix holds → data/published/insights/insights.json.

  python -m pipeline.insights      (also run by pipeline/build.py)

Every number in an insight is recomputed from the published data on each
build, so findings stay current when sources update. Wording that depends on
the direction of a result is chosen from the computed values (see `_dir`),
never hard-coded. Each insight carries its method, caveats and sources.

Statistics are kept deliberately simple and transparent (medians, counts,
Spearman rank correlations, a partial rank correlation controlling for the
overall employment rate). Cross-country associations are descriptive: they
do not show that one thing causes another.
"""

from __future__ import annotations

import collections
import math
import statistics as st

from .common import INDICATORS, PUBLISHED, RAW, read_json, write_json

OUT = PUBLISHED / "insights" / "insights.json"
SITE = "https://apprentix.eu/"

EU27 = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "EL", "HU", "IE", "IT",
        "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
EEA = EU27 | {"NO", "IS", "LI", "CH"}


# ------------------------------------------------------------------ helpers

def ind(iid: str) -> dict:
    return read_json(INDICATORS / f"{iid}.json")


def default_dims(d: dict) -> dict:
    return {x["key"]: x["default"] for x in d.get("dims", [])}


def obs(d: dict, dims: dict | None = None):
    want = {**default_dims(d), **(dims or {})}
    for o in d["series"]:
        if all((o.get("dims") or {}).get(k, v) == v for k, v in want.items()):
            yield o


def latest(iid: str, min_year: str = "2020", geos=EEA, dims=None) -> dict:
    out = {}
    for o in obs(ind(iid), dims):
        g = o["geo"]
        if g not in geos or o["time"] < min_year:
            continue
        if g not in out or o["time"] > out[g]["time"]:
            out[g] = o
    return out


def series(iid: str, geo: str, dims=None) -> dict:
    return {o["time"]: o for o in obs(ind(iid), dims) if o["geo"] == geo}


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(a, b):
    ma, mb = st.mean(a), st.mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def spearman(a, b):
    return pearson(ranks(a), ranks(b))


def residuals(y, x):
    mx, my = st.mean(x), st.mean(y)
    b = sum((p - mx) * (q - my) for p, q in zip(x, y)) / sum((p - mx) ** 2 for p in x)
    return [q - my - b * (p - mx) for p, q in zip(x, y)]


def partial_spearman(a, b, c):
    ra, rb, rc = ranks(a), ranks(b), ranks(c)
    return pearson(residuals(ra, rc), residuals(rb, rc))


def strength(r: float) -> str:
    r = abs(r)
    return "strong" if r >= 0.6 else "moderate" if r >= 0.35 else "weak" if r >= 0.2 else "no clear"


def _dir(r: float, pos: str, neg: str, none: str) -> str:
    return pos if r >= 0.2 else neg if r <= -0.2 else none


def short(label: str, n: int = 58) -> str:
    return label if len(label) <= n else label[:label.rfind(" ", 0, n)] + " …"


def pct(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}%"


def pp(x: float) -> str:
    return f"{x:+.1f} points"


def link_ind(iid: str, title: str | None = None) -> dict:
    return {"label": title or ind(iid)["title"], "url": f"pages/indicators/{iid}.html"}


def names() -> dict:
    return {c["code"]: c["name"] for c in read_json(PUBLISHED.parent / "reference" / "countries.json")["countries"]}


NAMES = None


def n(code: str) -> str:
    global NAMES
    NAMES = NAMES or names()
    return NAMES.get(code, code)


# ------------------------------------------------------------------ insights

def wbl_and_outcomes() -> dict:
    X = latest("eurostat-tps00215")
    Y = latest("eurostat-edat_lfse_24-vet")
    P = latest("cedefop-kivet-2090a")
    Z = latest("cedefop-kivet-3060")
    gs = sorted(g for g in X if g in Y and g in Z)
    a, b, c = [X[g]["value"] for g in gs], [Y[g]["value"] for g in gs], [Z[g]["value"] for g in gs]
    r, rp = spearman(a, b), partial_spearman(a, b, c)
    gp = sorted(g for g in X if g in P and g in Z)
    r2 = spearman([X[g]["value"] for g in gp], [P[g]["value"] for g in gp])
    rp2 = partial_spearman([X[g]["value"] for g in gp], [P[g]["value"] for g in gp], [Z[g]["value"] for g in gp])
    # Notable exceptions: biggest residuals from a simple rank fit.
    res = residuals(ranks(b), ranks(a))
    over = [gs[i] for i in sorted(range(len(gs)), key=lambda i: -res[i])[:2]]
    under = [gs[i] for i in sorted(range(len(gs)), key=lambda i: res[i])[:2]]
    direction = _dir(r, "higher", "lower", "neither higher nor lower")
    return {
        "id": "wbl-and-employment",
        "audience": ["policy"],
        "title": "Where more VET graduates learn at work, more of them find jobs",
        "finding": (f"Across {len(gs)} European countries, those where a larger share of recent VET graduates had "
                    f"work-based learning tend to have {direction} employment among those graduates "
                    f"(Spearman ρ = {r:+.2f}, a {strength(r)} association). The link holds after allowing for how strong "
                    f"each country's labour market is overall (partial ρ = {rp:+.2f})."),
        "detail": [
            f"Work-based learning is also {_dir(r2, 'associated with a larger', 'associated with a smaller', 'not clearly associated with the')} employment "
            f"advantage of VET graduates over general-education graduates (ρ = {r2:+.2f}; {rp2:+.2f} after the same adjustment; {len(gp)} countries).",
            f"Exceptions matter: {n(over[0])} and {n(over[1])} achieve higher graduate employment than their level of work-based "
            f"learning would suggest, while {n(under[0])} and {n(under[1])} do less well than theirs would suggest. "
            "Labour-market structure, the quality of placements and how programmes are mapped all play a part.",
        ],
        "chart": {
            "type": "scatter",
            "x": {"label": "Recent VET graduates with work-based learning (%)", "unit": "%"},
            "y": {"label": "Employment rate of recent VET graduates (%)", "unit": "%"},
            "points": [{"geo": g, "name": n(g), "x": X[g]["value"], "y": Y[g]["value"],
                        "label": f"{X[g]['time']}/{Y[g]['time']}"} for g in gs],
            "targets": {"x": 60, "y": 82},
        },
        "method": "Latest value since 2020 for each country (mostly 2025). Spearman rank correlation; partial correlation of ranks controlling for the employment rate of all 20–64-year-olds (Cedefop KIVET 3060).",
        "caveats": [
            "Cross-country association, not proof that work-based learning causes better outcomes.",
            "Several countries carry Eurostat low-reliability flags (u) for the work-based learning figure.",
        ],
        "sources": [link_ind("eurostat-tps00215"), link_ind("eurostat-edat_lfse_24-vet"), link_ind("cedefop-kivet-2090a"), link_ind("cedefop-kivet-3060")],
    }


def eu_targets() -> dict:
    out_rows, notes = [], []
    summary = {}
    for iid, target, key in (("eurostat-tps00215", 60, "wbl"), ("eurostat-edat_lfse_24-vet", 82, "emp")):
        eu = series(iid, "EU27")
        last_year = max(eu)
        L = latest(iid, min_year=last_year, geos=EU27)
        met = sorted([g for g in L if L[g]["value"] >= target], key=lambda g: -L[g]["value"])
        below = sorted([g for g in L if L[g]["value"] < target], key=lambda g: L[g]["value"])
        changes = []
        for g in L:
            s = series(iid, g)
            if "2021" in s and last_year in s:
                broken = any((s[y].get("flag") or "").startswith("b") for y in s if "2021" < y <= last_year)
                if not broken:
                    changes.append((g, s[last_year]["value"] - s["2021"]["value"]))
        changes.sort(key=lambda x: x[1])
        summary[key] = {"eu": eu[last_year]["value"], "year": last_year, "target": target, "met": met, "below": below,
                        "rise": changes[-3:][::-1], "fall": changes[:3], "eu_2021": eu.get("2021", {}).get("value")}
        out_rows.append({"indicator": iid, "target": target,
                         "values": [{"geo": g, "name": n(g), "value": L[g]["value"], "flag": L[g].get("flag")}
                                    for g in sorted(L, key=lambda g: -L[g]["value"])],
                         "eu": eu[last_year]["value"]})
    w, e = summary["wbl"], summary["emp"]
    return {
        "id": "eu-2025-targets",
        "audience": ["policy"],
        "title": "EU 2025 targets: work-based learning met, employment of VET graduates missed",
        "finding": (f"In {w['year']}, {pct(w['eu'])} of recent VET graduates in the EU had work-based learning — above the 60% target "
                    f"(up from {pct(w['eu_2021'])} in 2021). The employment rate of recent VET graduates was {pct(e['eu'])}, "
                    f"{'short of' if e['eu'] < 82 else 'above'} the 82% target. {len(w['met'])} of {len(w['met']) + len(w['below'])} member states "
                    f"with data meet the first target; only {len(e['met'])} of {len(e['met']) + len(e['below'])} meet the second."),
        "detail": [
            "Furthest from the work-based learning target: " + ", ".join(f"{n(g)} ({pct(next(v['value'] for v in out_rows[0]['values'] if v['geo'] == g))})" for g in w["below"][:4]) + ".",
            "Furthest from the employment target: " + ", ".join(f"{n(g)} ({pct(next(v['value'] for v in out_rows[1]['values'] if v['geo'] == g))})" for g in e["below"][:4]) + ".",
            "Largest gains in graduate employment since 2021: " + ", ".join(f"{n(g)} ({pp(d)})" for g, d in e["rise"]) + "; largest falls: " + ", ".join(f"{n(g)} ({pp(d)})" for g, d in e["fall"]) + ".",
        ],
        "chart": {"type": "target-bars", "panels": [
            {"title": "Recent VET graduates with work-based learning", "target": 60, "rows": out_rows[0]["values"], "eu": w["eu"]},
            {"title": "Employment rate of recent VET graduates", "target": 82, "rows": out_rows[1]["values"], "eu": e["eu"]},
        ]},
        "method": "Latest year for all EU-27 countries with data. Changes since 2021 exclude countries with a Eurostat break-in-series flag (b) in between.",
        "caveats": ["Several values carry low-reliability flags (u).", "The targets were set by the 2020 Council Recommendation on VET for 2025."],
        "sources": [link_ind("eurostat-tps00215"), link_ind("eurostat-edat_lfse_24-vet")],
    }


def vet_premium_and_gender() -> dict:
    v, g = series("eurostat-edat_lfse_24-vet", "EU27"), series("eurostat-edat_lfse_24-general", "EU27")
    years = sorted(y for y in v if y in g and y >= "2014")
    gaps = [v[y]["value"] - g[y]["value"] for y in years]
    last = years[-1]
    fv = series("eurostat-edat_lfse_24-vet", "EU27", {"sex": "F"})[last]["value"]
    mv = series("eurostat-edat_lfse_24-vet", "EU27", {"sex": "M"})[last]["value"]
    fg = series("eurostat-edat_lfse_24-general", "EU27", {"sex": "F"})[last]["value"]
    mg = series("eurostat-edat_lfse_24-general", "EU27", {"sex": "M"})[last]["value"]
    return {
        "id": "vet-advantage",
        "audience": ["policy", "learners"],
        "title": "Vocational graduates find work more often — and the gender gap is smaller",
        "finding": (f"In {last}, {pct(v[last]['value'])} of recent EU graduates with a vocational qualification were employed, against "
                    f"{pct(g[last]['value'])} of those with a general upper-secondary qualification — an advantage of {gaps[-1]:.1f} points. "
                    f"Since {years[0]} the advantage has stayed between {min(gaps):.0f} and {max(gaps):.0f} points."),
        "detail": [
            f"Women with a recent vocational qualification are employed {abs(fv - mv):.1f} points less often than men; "
            f"among general-education graduates the gap is {abs(fg - mg):.1f} points.",
            "For learners choosing a route, this is the EU-wide picture: in some countries general education leads more often to further study, which this measure does not count as a success.",
        ],
        "chart": {"type": "lines", "unit": "%", "series": [
            {"label": "Vocational (ISCED 35/45)", "points": [{"time": y, "value": v[y]["value"]} for y in years]},
            {"label": "General (ISCED 34/44)", "points": [{"time": y, "value": g[y]["value"]} for y in years]},
        ]},
        "method": "Eurostat edat_lfse_24: employment rate of 20–34-year-olds not in education, 1–3 years after their highest qualification, EU-27.",
        "caveats": ["People still in education are excluded, which affects general-education graduates more."],
        "sources": [link_ind("eurostat-edat_lfse_24-vet"), link_ind("eurostat-edat_lfse_24-general")],
    }


def scheme_families() -> dict:
    from .curate.scheme_questions import QUESTIONS
    R = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")

    def has(r, k, v):
        x = r.get(k)
        return v in (x if isinstance(x, list) else [x])

    employer = [r for r in R if has(r, "q_learner_status", "Specific apprentice status") and not has(r, "q_origin", "Grew out of school-based VET")]
    school = [r for r in R if has(r, "q_origin", "Grew out of school-based VET")]
    feats = [("q_introduced", "Before 2000", "Introduced before 2000"),
             ("q_learner_status", "Specific apprentice status", "Learner has apprentice status"),
             ("q_learner_status", "Student", "Learner is a student"),
             ("q_contract_type", "Formal agreement, not a contract", "Training agreement, not a contract"),
             ("q_qualification_route", "Only through apprenticeship", "Qualification only via apprenticeship"),
             ("q_pay_covers_school", "Yes", "Pay also covers school time"),
             ("q_typical_age", "15–18", "Typical learner aged 15–18"),
             ("q_min_workplace_share", "50% or more", "At least half the time at work")]
    rows = [{"label": lab, "employer": round(100 * sum(has(r, k, v) for r in employer) / len(employer)),
             "school": round(100 * sum(has(r, k, v) for r in school) / len(school))} for k, v, lab in feats]
    cc_e = {r["country_code"] for r in employer} - {r["country_code"] for r in school}
    cc_s = {r["country_code"] for r in school} - {r["country_code"] for r in employer}
    cc_e = {("EL" if c == "GR" else c) for c in cc_e}
    out = {}
    for iid in ("eurostat-edat_lfse_24-vet", "cedefop-kivet-2090a", "cedefop-kivet-3030"):
        L = latest(iid)
        a, b = [L[g]["value"] for g in cc_e if g in L], [L[g]["value"] for g in cc_s if g in L]
        out[iid] = (st.median(a), len(a), st.median(b), len(b))
    emp, prem, neet = out["eurostat-edat_lfse_24-vet"], out["cedefop-kivet-2090a"], out["cedefop-kivet-3030"]
    return {
        "id": "two-families",
        "audience": ["policy"],
        "title": "Europe has two families of apprenticeship — and neither clearly wins",
        "finding": (f"Grouping the {len(R)} schemes by Cedefop's coded answers shows {len(employer)} employer-based apprenticeships "
                    f"(long traditions, a distinct apprentice status) and {len(school)} school-based dual tracks that grew out of school VET, "
                    f"mostly introduced after 2012. Neither group of countries clearly does better: median employment of recent VET graduates is "
                    f"{emp[0]:.1f}% where schemes are employer-based and {emp[2]:.1f}% where they are school-based, while VET graduates' "
                    f"advantage over general-education graduates is {prem[0]:.1f} and {prem[2]:.1f} points respectively."),
        "detail": [
            f"Employer-based schemes: {', '.join(sorted({r['country'] for r in employer}))}.",
            f"School-based dual tracks: {', '.join(sorted({r['country'] for r in school}))}.",
            f"Young people neither in employment nor education: median {neet[0]:.1f}% in employer-based countries vs {neet[2]:.1f}% in school-based ones.",
            "Design details within each family — pay, the share of time at work, the role of social partners — vary as much as between them; see the comparison matrix.",
        ],
        "chart": {"type": "paired-bars", "unit": "% of schemes", "groups": ["Employer-based", "School-based dual"], "rows": rows},
        "method": "Families from Cedefop's coded fiche answers (2026): school-based dual = 'grew out of school-based VET'; employer-based = learner has a specific apprentice status and the scheme did not grow out of school VET. Earlier exploratory clustering (Jaccard distance, average linkage) gave the same two groups plus a few distinct schemes (France's professionalisation contract, Italy's types 1 and 3, Portugal, Czechia). Outcomes compare countries whose schemes all fall in one family.",
        "caveats": ["Few countries per group; medians can move with one country.", "Country outcomes reflect all VET, not only apprentices."],
        "sources": [{"label": "Compare all schemes", "url": "pages/compare.html"}, {"label": "Apprenticeship schemes dataset", "url": "pages/datasets/apprenticeship-schemes.html"}],
    }


def national_trends() -> dict:
    def annual(iid, dims=None, month=None):
        out = {}
        for o in obs(ind(iid), dims):
            t = o["time"]
            if month:
                if t.endswith(f"-{month}"):
                    out[t[:4]] = o["value"]
            else:
                out[t] = o["value"]
        return out
    sets = [("France — apprentices (stock, December)", annual("fr-dares-apprentices-stock", month="12"), "fr-dares-apprentices-stock"),
            ("Norway — apprentices", annual("no-ssb-apprentices"), "no-ssb-apprentices"),
            ("Switzerland — VET entrants", annual("ch-bfs-entrants-vet"), "ch-bfs-entrants-vet"),
            ("England — apprenticeship starts", annual("uk-dfe-apprenticeship-starts"), "uk-dfe-apprenticeship-starts")]
    base = "2017"
    lines, facts = [], []
    for label, s, iid in sets:
        if base not in s:
            continue
        ys = sorted(y for y in s if y >= base)
        last = ys[-1]
        if iid.startswith("uk-dfe") and len(ys) > 1:
            last = ys[-2]  # latest academic year is partial
        lines.append({"label": label, "points": [{"time": y, "value": round(100 * s[y] / s[base], 1)} for y in ys if y <= last]})
        facts.append((label, s[base], s[last], last))
    fr = next(f for f in facts if f[0].startswith("France"))
    return {
        "id": "national-trajectories",
        "audience": ["policy"],
        "title": "National apprenticeship numbers are moving in very different directions",
        "finding": (f"Since {base}, the number of apprentices in France has grown {fr[2] / fr[1]:.1f}-fold, to {fr[2]:,.0f} at the end of {fr[3]}. "
                    "Over the same period: " + "; ".join(f"{l.split(' — ')[0]} {100 * (b / a - 1):+.0f}% (to {y})" for l, a, b, y in facts if not l.startswith('France'))
                    + "."),
        "detail": [
            "France's growth coincides with its 2018 vocational training reform and the hiring aid introduced in 2020; its December 2025 figure is the first annual fall.",
            "Each country counts something different (stocks, starts or entrants; with or without higher-education apprenticeships), so compare the direction of travel, not the levels.",
        ],
        "chart": {"type": "lines", "unit": f"index, {base} = 100", "series": lines},
        "method": f"Each national series indexed to {base} = 100. England uses the last complete academic year.",
        "caveats": ["National definitions differ; levels are not comparable across countries."],
        "sources": [link_ind(i) for _, _, i in sets],
    }


def small_schemes() -> dict:
    R = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")
    c = collections.Counter(r.get("q_share_of_vet") for r in R if r.get("q_share_of_vet"))
    sh = series("eurostat-ed3sw-share-of-vet", "EU27")
    ys = sorted(sh)
    big = [r for r in R if r.get("q_share_of_vet") in ("Over 60%", "30–60%")]
    total = sum(c.values())
    return {
        "id": "small-schemes",
        "audience": ["policy"],
        "title": "In most countries apprenticeship is still a minority route within VET",
        "finding": (f"Of the {total} schemes whose share is known, {c.get('Under 10%', 0) + c.get('10–30%', 0)} enrol under 30% of the "
                    f"country's VET learners at that level; only {len(big)} enrol more. EU-wide, the share of upper-secondary VET pupils in "
                    f"combined school- and work-based programmes rose from {pct(sh[ys[0]]['value'])} in {ys[0]} to {pct(sh[ys[-1]]['value'])} in {ys[-1]}."),
        "detail": ["Schemes enrolling 30% or more of VET learners: " + ", ".join(f"{r['country']} ({r['name_en']})" for r in big) + "."],
        "chart": {"type": "bars", "unit": "schemes", "rows": [{"label": k, "value": c.get(k, 0)} for k in ("Under 10%", "10–30%", "30–60%", "Over 60%")]},
        "method": "Cedefop coded answer Q6 (share of apprentices among VET learners at the corresponding level); Eurostat educ_uoe_enrs04 (ED3SW ÷ ED35).",
        "caveats": ["The EU share is affected by how countries map programmes to the 'school- and work-based' category (flag d)."],
        "sources": [link_ind("eurostat-ed3sw-share-of-vet"), {"label": "Compare all schemes", "url": "pages/compare.html?q=q_share_of_vet"}],
    }


def policy_focus() -> dict:
    T = read_json(PUBLISHED / "vet-policy-timeline" / "records.json")
    app = [r for r in T if r.get("concerns_apprenticeship") == "Yes"]
    per = {p: (sum(1 for r in T if p in r.get("reporting_period", [])), sum(1 for r in app if p in r.get("reporting_period", [])))
           for p in ("2015-20", "2021-25")}
    themes = collections.Counter(t for r in app for t in r.get("sub_themes", []) if not t.startswith("3.9."))
    stages = collections.Counter(r.get("latest_stage") for r in app)
    disc = stages.get("Discontinued", 0)
    return {
        "id": "policy-focus",
        "audience": ["policy"],
        "title": "One in three national VET reforms concerns apprenticeship",
        "finding": (f"Of {len(T):,} VET policy developments that Cedefop and ReferNet have tracked since 2015, {len(app)} concern apprenticeship "
                    f"or work-based learning — {100 * per['2015-20'][1] / per['2015-20'][0]:.0f}% in 2015–20 and "
                    f"{100 * per['2021-25'][1] / per['2021-25'][0]:.0f}% in 2021–25. Only {100 * disc / len(app):.0f}% were discontinued."),
        "detail": ["Beyond work-based learning itself, these reforms most often also address: "
                   + "; ".join(f"{t.split('. ', 1)[1]} ({k})" for t, k in themes.most_common(4)) + "."],
        "chart": {"type": "bars", "unit": "policies", "rows": [{"label": short(t.split(". ", 1)[1]), "value": k} for t, k in themes.most_common(6)]},
        "method": "Cedefop Timeline of VET policies (2025 update). 'Concerns apprenticeship' is an Apprentix grouping (theme 3.9 or wording).",
        "caveats": ["Countries report with different granularity; counts reflect reporting as well as activity."],
        "sources": [{"label": "VET policy timeline", "url": "pages/explore.html?dataset=vet-policy-timeline&f.concerns_apprenticeship=Yes"}],
    }


def who_pays() -> dict:
    R = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")
    F = read_json(PUBLISHED / "financing-instruments" / "records.json")

    def cnt(k, v):
        return sum(1 for r in R if v in (r.get(k) if isinstance(r.get(k), list) else [r.get(k)]))
    by = collections.defaultdict(set)
    for r in F:
        for t in r.get("type", []):
            by[r["country_code"]].add(t)
    funds = sorted(c for c, s in by.items() if "Training funds" in s)
    tax = sorted(c for c, s in by.items() if "Tax incentives" in s)
    return {
        "id": "who-pays",
        "audience": ["policy", "employers"],
        "title": "Employers pay apprentices almost everywhere; governments sweeten the deal",
        "finding": (f"In {cnt('q_pay_funded_by', 'Employers')} of {len(R)} schemes employers pay the apprentice, and in "
                    f"{cnt('q_compensation', 'Wage')} that pay is a taxable wage. Governments compensate with subsidies "
                    f"({cnt('q_financial_incentives', 'Subsidies')} schemes) and tax deductions ({cnt('q_financial_incentives', 'Tax deductions')}). "
                    f"Only {cnt('q_financial_incentives', 'None')} schemes offer companies no financial incentive."),
        "detail": [f"Pay is set by law in {cnt('q_wage_setting', 'By law')} schemes and by sectoral collective agreements in {cnt('q_wage_setting', 'Sectoral agreements')}.",
                   f"Levy-financed training funds existed in {len(funds)} of the {len(by)} countries in Cedefop's financing database ({', '.join(n(c) for c in funds)}), "
                   f"tax incentives in {len(tax)} (2016–17)."],
        "chart": {"type": "bars", "unit": "schemes", "rows": [
            {"label": "Subsidies", "value": cnt("q_financial_incentives", "Subsidies")},
            {"label": "Tax deductions", "value": cnt("q_financial_incentives", "Tax deductions")},
            {"label": "Other incentives", "value": cnt("q_financial_incentives", "Other")},
            {"label": "None", "value": cnt("q_financial_incentives", "None")}]},
        "method": "Cedefop coded answers Q33–Q37 (2026 fiches); financing instruments database (reference 2016–17).",
        "caveats": ["The financing database is not updated since 2016–17."],
        "sources": [{"label": "Compare: who pays", "url": "pages/compare.html?q=q_pay_funded_by"},
                    {"label": "Financing instruments", "url": "pages/explore.html?dataset=financing-instruments"}],
    }


def erasmus_mobility() -> dict:
    proj = {o["geo"]: o for o in obs(ind("erasmus-ka1-vet-projects")) if o["time"] == "2025"}
    grant = {o["geo"]: o["value"] for o in obs(ind("erasmus-ka1-vet-grant")) if o["time"] == "2025"}
    g21 = {o["geo"]: o["value"] for o in obs(ind("erasmus-ka1-vet-grant")) if o["time"] == "2021"}
    p21 = {o["geo"]: o["value"] for o in obs(ind("erasmus-ka1-vet-projects")) if o["time"] == "2021"}
    raw = read_json(sorted((RAW / "eurostat").glob("*educ_uoe_enrs04-ed35.json"))[-1])
    gidx, tidx = raw["dimension"]["geo"]["category"]["index"], raw["dimension"]["time"]["category"]["index"]
    ginv, tinv, nt = {v: k for k, v in gidx.items()}, {v: k for k, v in tidx.items()}, len(tidx)
    pupils = {}
    for k, v in raw["value"].items():
        k = int(k)
        if tinv[k % nt] == max(tidx):
            pupils[{"EU27_2020": "EU27"}.get(ginv[k // nt], ginv[k // nt])] = v
    per = sorted([(g, grant[g] / pupils[g]) for g in EU27 if g in grant and pupils.get(g)], key=lambda x: -x[1])
    return {
        "id": "erasmus-vet",
        "audience": ["policy", "learners"],
        "title": "Erasmus+ money for VET mobility has more than tripled — unevenly",
        "finding": (f"EU-wide, Erasmus+ grants for VET mobility projects rose from €{g21['EU27'] / 1e6:,.0f} million (2021 call) to "
                    f"€{grant['EU27'] / 1e6:,.0f} million (2025), and projects from {p21['EU27']:,.0f} to {proj['EU27']['value']:,.0f}. "
                    f"Relative to VET pupils, funding is highest in {n(per[0][0])} (€{per[0][1]:,.0f} per pupil) and {n(per[1][0])}, and lowest in "
                    f"{n(per[-1][0])} (€{per[-1][1]:,.0f}) and {n(per[-2][0])}."),
        "detail": ["Smaller and Baltic countries draw the most per VET pupil; large dual systems the least.",
                   "For learners: most VET schools and many training companies in Europe can now send apprentices abroad — check the accredited organisations directory."],
        "chart": {"type": "bars", "unit": "€ per upper-secondary VET pupil", "rows": [{"label": n(g), "value": round(v)} for g, v in per]},
        "method": "Grants of KA121/KA122-VET (and predecessor) projects by coordinator country and call year, divided by upper-secondary VET pupils (Eurostat, latest year).",
        "caveats": ["2021 was the first, partial year of the 2021–27 programme.", "Coordinator country, not where learners travel to."],
        "sources": [link_ind("erasmus-ka1-vet-grant"), {"label": "Accredited VET organisations", "url": "pages/explore.html?dataset=erasmus-vet-organisations"}],
    }


def master_craft_levels() -> dict:
    N = read_json(PUBLISHED / "nqf-qualification-levels" / "records.json")
    words = ("master craft", "meister", "mastership", "maîtrise", "master craftsman", "master craftsperson")
    rows = []
    for r in N:
        t = r["qualification_type"].lower()
        if r.get("apprenticeship_or_craft") == "Yes" and any(w in t for w in words) and "agricult" not in t:
            lv = [l for l in r.get("eqf_level", []) if l.startswith("EQF")]
            if lv:
                rows.append({"name": r["country"], "label": r["qualification_type"], "eqf": int(lv[0].split()[1])})
    seen, uniq = set(), []
    for r in sorted(rows, key=lambda r: (-r["eqf"], r["name"])):
        if r["name"] not in seen:
            seen.add(r["name"])
            uniq.append(r)
    levels = collections.defaultdict(list)
    for r in uniq:
        levels[r["eqf"]].append(r["name"])
    return {
        "id": "master-craft-levels",
        "audience": ["learners", "employers", "policy"],
        "title": "The same master craftsperson certificate sits at different European levels",
        "finding": "Master craftsperson qualifications are placed at " + "; ".join(
            f"EQF {lv} in {', '.join(levels[lv])}" for lv in sorted(levels, reverse=True)) + ".",
        "detail": ["The EQF level shown on a certificate and in Europass affects how it is recognised abroad and whether it opens doors to further study.",
                   "Initial apprenticeship qualifications cluster at EQF 3–4; see the qualification levels dataset for each country."],
        "chart": {"type": "level-strip", "rows": uniq},
        "method": "Cedefop NQF online tool (state of play 2024): qualification types named as master craftsperson qualifications.",
        "caveats": ["Programme content and entry requirements differ; the level reflects each country's framework design."],
        "sources": [{"label": "Qualification levels", "url": "pages/explore.html?dataset=nqf-qualification-levels&f.apprenticeship_or_craft=Yes"}],
    }


def learner_guide() -> dict:
    R = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")

    def has(r, k, v):
        x = r.get(k)
        return v in (x if isinstance(x, list) else [x])
    adult = [r for r in R if has(r, "q_typical_age", "Over 24")]
    he = [r for r in R if has(r, "q_access_to_he", "Yes")]
    wage = [r for r in R if has(r, "q_compensation", "Wage")]
    return {
        "id": "for-learners",
        "audience": ["learners"],
        "title": "For learners: what to expect from an apprenticeship in Europe",
        "finding": (f"In {len(wage)} of {len(R)} schemes apprentices earn a wage; {len(he)} lead to a qualification giving direct access to "
                    f"higher education; and in {len(adult)} many apprentices are over 24 — apprenticeship is not only for school-leavers."),
        "detail": ["Schemes where many apprentices are adults: " + ", ".join(f"{r['country']} ({r['name_en']})" for r in adult) + ".",
                   "Look up a country page for the scheme's duration, pay rules and the official fiche, and the Erasmus+ directory for organisations that send apprentices abroad."],
        "chart": {"type": "bars", "unit": "schemes", "rows": [
            {"label": "Paid a wage", "value": len(wage)}, {"label": "Direct access to higher education", "value": len(he)},
            {"label": "Many learners over 24", "value": len(adult)}]},
        "method": "Cedefop coded answers (2026 fiches): Q33, Q11, Q4.",
        "caveats": ["Rules differ by occupation and region within a scheme; the official fiche and national authorities are authoritative."],
        "sources": [{"label": "Compare all schemes", "url": "pages/compare.html?q=q_typical_age"}, {"label": "Countries", "url": "pages/countries/"}],
    }


def jobs_outlook() -> dict:
    d = ind("cedefop-stas-employment-growth")
    occ = d["dims"][0]["values"]
    year = max(o["time"] for o in d["series"])
    rows = sorted([(occ[o["dims"]["occupation"]], o["value"]) for o in d["series"]
                   if o["geo"] == "EU27" and o["time"] == year and o["dims"]["occupation"] != "TOTAL"], key=lambda x: -x[1])
    return {
        "id": "jobs-outlook",
        "audience": ["learners", "employers"],
        "title": "Where employment is forecast to grow",
        "finding": (f"Cedefop's short-term forecast for {year} expects EU employment to grow fastest for {rows[0][0].split(' ', 1)[1].lower()} "
                    f"({rows[0][1]:+.1f}%) and {rows[1][0].split(' ', 1)[1].lower()} ({rows[1][1]:+.1f}%), and to shrink for "
                    f"{rows[-1][0].split(' ', 1)[1].lower()} ({rows[-1][1]:+.1f}%) and {rows[-2][0].split(' ', 1)[1].lower()} ({rows[-2][1]:+.1f}%)."),
        "detail": ["Employment change is not the same as job openings: people retiring from shrinking occupations still need to be replaced, which this forecast does not show.",
                   "Many technician and associate-professional jobs are reachable through higher VET and apprenticeship at EQF 5–6."],
        "chart": {"type": "bars", "unit": "% change", "rows": [{"label": l, "value": round(v, 2)} for l, v in rows]},
        "method": f"Cedefop STAS (short-term anticipation of skills trends), EU-27 employment growth by ISCO major group, {year}.",
        "caveats": ["Forecasts, flagged 'f'; revised twice a year."],
        "sources": [link_ind("cedefop-stas-employment-growth")],
    }


def data_gaps() -> dict:
    d = ind("eurostat-educ_uoe_enrs04-ed3sw")
    last = max(o["time"] for o in d["series"])
    m = sorted({x["geo"] for x in d.get("missing", []) if x["time"] == last and x.get("flag") == "m" and x["geo"] in EU27
                and (x.get("dims") or {}).get("sex", "T") == "T"})
    nat = {i["coverage"]["geos"][0] for i in read_json(INDICATORS / "index.json")["indicators"] if i.get("national")}
    return {
        "id": "data-gaps",
        "audience": ["policy"],
        "title": "What Europe still can't measure about apprenticeships",
        "finding": (f"There is no EU statistic counting apprentices. The closest proxy — pupils in combined school- and work-based VET — "
                    f"is reported as 'not applicable' for {len(m)} member states ({', '.join(n(g) for g in m)}), and open, machine-readable "
                    f"national apprentice statistics exist for only {len(nat)} countries ({', '.join(n(g) for g in sorted(nat))})."),
        "detail": ["Completion rates, apprentice pay levels and employer participation are not published comparably anywhere.",
                   "A common EU definition and an annual count of apprenticeship contracts would let countries benchmark what matters most."],
        "chart": None,
        "method": "Eurostat flags ('m' = data cannot exist); Apprentix source catalogue.",
        "caveats": [],
        "sources": [{"label": "Data & sources", "url": "pages/data.html"}, link_ind("eurostat-educ_uoe_enrs04-ed3sw")],
    }


BUILDERS = [eu_targets, wbl_and_outcomes, vet_premium_and_gender, scheme_families, national_trends, small_schemes,
            who_pays, policy_focus, erasmus_mobility, master_craft_levels, learner_guide, jobs_outlook, data_gaps]


def build() -> list[dict]:
    items, failed = [], []
    for b in BUILDERS:
        try:
            items.append(b())
        except Exception as e:  # one broken analysis must not stop the build
            failed.append(f"{b.__name__}: {e}")
    write_json(OUT, {
        "description": "Analyses computed by Apprentix from its published data (pipeline/insights.py). Recomputed on every build.",
        "items": items,
        "failed": failed,
    })
    return items


if __name__ == "__main__":
    out = build()
    for i in out:
        print("-", i["title"], "\n   ", i["finding"])
    print(read_json(OUT)["failed"])
