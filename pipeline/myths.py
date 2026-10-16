"""'Myth or fact?' statements about apprenticeship in Europe → data/published/myths/myths.json.

  python -m pipeline.myths

Each statement is answered from data the site publishes, and the verdict is computed, not
written: if a refresh changes the numbers enough, the verdict changes with them. Sources:
Cedefop's coded answers for the 34 apprenticeship schemes, Eurostat indicators and the
Insights page. Statements whose inputs are missing are left out. Deterministic: no clock.

Verdicts: "myth" (the data contradicts it), "fact" (the data supports it), "partly" (true
in some places only).
"""

from __future__ import annotations

from .common import INDICATORS, PUBLISHED, read_json, write_json

OUT = PUBLISHED / "myths" / "myths.json"


def as_list(v):
    return [x for x in (v if isinstance(v, list) else [v]) if x]


def has(s: dict, key: str, value: str) -> bool:
    return value in as_list(s.get(key))


def eu_latest(iid: str):
    """(year, value) of the EU-27 at the default breakdown, latest year."""
    path = INDICATORS / f"{iid}.json"
    if not path.exists():
        return None
    ind = read_json(path)
    dims = ind.get("dims") or []
    obs = [o for o in ind["series"] if o["geo"] == "EU27"
           and all((o.get("dims") or {}).get(d["key"], d["default"]) == d["default"] for d in dims)]
    if not obs:
        return None
    o = max(obs, key=lambda o: o["time"])
    return o["time"], o["value"]


def pct(v: float) -> str:
    return f"{v:.1f}%".replace(".0%", "%")


def build() -> list[dict]:
    schemes = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")
    n = len(schemes)
    items: list[dict] = []

    def add(id_, statement, verdict, answer, detail, link, source):
        items.append({"id": id_, "statement": statement, "verdict": verdict, "answer": answer,
                      "detail": detail, "link": link, "source": source})

    cedefop = "Cedefop, European database on apprenticeship schemes (2026 fiches, coded answers)"

    wage = sum(has(s, "q_compensation", "Wage") for s in schemes)
    allowance = sum(not has(s, "q_compensation", "Wage") and has(s, "q_compensation", "Allowance") for s in schemes)
    unpaid = n - wage - allowance
    add("paid", "Apprentices aren't paid.", "myth" if wage + allowance > n / 2 else "fact",
        f"In {wage} of {n} schemes apprentices earn a wage, and in {allowance} more an allowance.",
        f"Only {unpaid} scheme{'s' if unpaid != 1 else ''} has no pay required by law." if unpaid else
        "Every scheme pays something.",
        "pages/compare.html", cedefop)

    teen_only = sum(as_list(s.get("q_typical_age")) == ["15–18"] for s in schemes)
    over24 = sum(has(s, "q_typical_age", "Over 24") for s in schemes)
    known = sum(bool(as_list(s.get("q_typical_age"))) for s in schemes)
    add("teenagers", "Apprenticeship is only for teenagers.", "myth" if known - teen_only > known / 2 else "partly",
        f"In {known - teen_only} of {known} schemes the typical apprentice is 18 or older.",
        f"In {over24} schemes many apprentices are over 24 — apprenticeship is also a route for adults.",
        "pages/compare.html", cedefop)

    under_half = sum(s.get("workplace_time") == "Under half" for s in schemes)
    mostly = sum(s.get("workplace_time") == "Mostly at work (≥2/3)" for s in schemes)
    add("classroom", "Apprentices spend most of their time in a classroom.", "myth" if under_half < n / 2 else "fact",
        f"In {n - under_half} of {n} schemes apprentices spend about half their time or more at the company.",
        f"In {mostly} of them it is two-thirds or more.",
        "pages/compare.html", cedefop)

    he = sum(s.get("q_access_to_he") == "Yes" for s in schemes)
    add("university", "An apprenticeship rules out going to university.", "myth" if he > n / 2 else "partly",
        f"{he} of {n} schemes lead to a qualification that gives direct access to higher education.",
        f"In the other {n - he}, the qualification does not by itself open the way to higher education.",
        "pages/compare.html", cedefop)

    employer = sum(has(s, "q_pay_funded_by", "Employers") for s in schemes)
    state = sum(has(s, "q_pay_funded_by", "State") for s in schemes)
    both = sum(has(s, "q_pay_funded_by", "State") and has(s, "q_pay_funded_by", "Employers") for s in schemes)
    add("state-pays", "The state pays apprentices' wages.", "myth" if employer > n / 2 else "partly",
        f"Employers pay apprentices in {employer} of {n} schemes.",
        f"The state contributes to apprentices' pay in {state} schemes" + (f", {both} of them alongside employers." if both else "."),
        "pages/insights.html#who-pays", cedefop)

    written = sum(s.get("q_written_arrangement") == "Yes" for s in schemes)
    specific = sum(has(s, "q_contract_type", "Specific apprenticeship contract") for s in schemes)
    add("contract", "Apprentices work without a contract.", "myth" if written > n / 2 else "partly",
        f"{written} of {n} schemes require a written contract or agreement.",
        f"{specific} use a contract made specifically for apprentices.",
        "pages/compare.html", cedefop)

    shares = [s.get("q_share_of_vet") for s in schemes if s.get("q_share_of_vet")]
    small = sum(v in ("Under 10%", "10–30%") for v in shares)
    big = sum(v == "Over 60%" for v in shares)
    add("main-route", "Apprenticeship is the main route in vocational education everywhere.",
        "myth" if small > len(shares) / 2 else "partly",
        f"In {small} of {len(shares)} schemes with data, apprentices are under 30% of vocational learners.",
        f"Only in {big} {'is' if big == 1 else 'are'} they more than 60%: apprenticeship is the main route in a few countries, a minority route in most.",
        "pages/insights.html#small-schemes", cedefop)

    mentor = sum(has(s, "q_company_requirements", "Mentor or trainer") for s in schemes)
    add("mentor", "Companies must provide a mentor or trainer to take on apprentices.", "fact" if mentor > n / 2 else "partly",
        f"{mentor} of {n} schemes require training companies to have a mentor or in-company trainer.",
        f"{sum(has(s, 'q_company_requirements', 'Suitable learning environment') for s in schemes)} require a suitable learning environment at the workplace.",
        "pages/compare.html", cedefop)

    support = sum(bool(as_list(s.get("q_financial_incentives"))) and not has(s, "q_financial_incentives", "None") for s in schemes)
    subsidies = sum(has(s, "q_financial_incentives", "Subsidies") for s in schemes)
    add("incentives", "Employers can get financial support for training apprentices.", "fact" if support > n / 2 else "partly",
        f"In {support} of {n} schemes employers can get financial incentives for training apprentices.",
        f"Subsidies are the most common ({subsidies} schemes), then tax deductions ({sum(has(s, 'q_financial_incentives', 'Tax deductions') for s in schemes)}).",
        "pages/insights.html#who-pays", cedefop)

    partners = sum(has(s, "q_partners_design", "Design qualifications") for s in schemes)
    add("social-partners", "Employers' organisations and trade unions help design apprenticeship qualifications.",
        "fact" if partners > n / 2 else "partly",
        f"In {partners} of {n} schemes the social partners help design the qualifications.",
        f"They help design curricula in {sum(has(s, 'q_partners_design', 'Design curricula') for s in schemes)} schemes "
        f"and take part in final assessments in {sum(has(s, 'q_partners_implement', 'Final assessment') for s in schemes)}.",
        "pages/compare.html", cedefop)

    wbl = eu_latest("eurostat-tps00215")
    if wbl:
        y, v = wbl
        add("work-based", "Most recent VET graduates in the EU have learned at work.", "fact" if v > 50 else "myth",
            f"In {y}, {pct(v)} of recent VET graduates in the EU had work-based learning during their studies.",
            "The EU target for 2025 was 60%.",
            "pages/indicators/eurostat-tps00215.html", "Eurostat (tps00215)")

    vet, gen = eu_latest("eurostat-edat_lfse_24-vet"), eu_latest("eurostat-edat_lfse_24-general")
    if vet and gen and vet[0] == gen[0]:
        y = vet[0]
        add("jobs", "Vocational graduates find jobs less often than other young graduates.",
            "myth" if vet[1] > gen[1] else "fact",
            f"In {y}, {pct(vet[1])} of recent vocational graduates in the EU were employed, against {pct(gen[1])} of general-education graduates.",
            "Recent graduates are aged 20–34 and left education one to three years earlier.",
            "pages/insights.html#vet-advantage", "Eurostat (edat_lfse_24)")

    ins_path = PUBLISHED / "insights" / "insights.json"
    if ins_path.exists():
        ins = {i["id"]: i for i in read_json(ins_path).get("items", [])}
        mc = ins.get("master-craft-levels", {}).get("chart") or {}
        rows = mc.get("rows") or []
        levels = sorted({r["eqf"] for r in rows})
        if len(levels) > 1:
            hi = [r["name"] for r in rows if r["eqf"] == levels[-1]]
            lo = [r["name"] for r in rows if r["eqf"] == levels[0]]
            add("master", "A master craftsperson qualification is at the same level everywhere in Europe.", "myth",
                f"It sits anywhere from EQF {levels[0]} to EQF {levels[-1]}, depending on the country.",
                f"EQF {levels[-1]} in {' and '.join(hi[:2])}; EQF {levels[0]} in {' and '.join(lo[:2])}.",
                "pages/insights.html#master-craft-levels", "Cedefop, NQF online tool")

    write_json(OUT, {"description": "'Myth or fact?' statements with computed verdicts, generated by pipeline/myths.py.",
                     "items": items})
    print(f"Myths: {len(items)} statements")
    return items


if __name__ == "__main__":
    build()
