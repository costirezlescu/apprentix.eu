"""Scroll-driven stories: a few findings told step by step, with a chart that changes as you scroll.

  python -m pipeline.stories

  data/published/stories/stories.json

Every number in the text is computed here from published data, so the stories stay current when
the sources update. Policy context (laws, aid amounts) is fixed text with its sources listed.
Rendered by pipeline/render_stories.py; the chart steps are drawn by assets/js/story.js.
Deterministic: no clock.
"""

from __future__ import annotations

import statistics as st

from .common import INDICATORS, PUBLISHED, plain, read_json, write_json

OUT = PUBLISHED / "stories" / "stories.json"


def fmt(n: float) -> str:
    return f"{n:,.0f}"


def pct(a: float, b: float) -> str:
    v = 100 * (b / a - 1)
    return f"{v:+.0f}%".replace("-", "−")


# ---------------------------------------------------------------- France --

def french_boom() -> dict | None:
    path = INDICATORS / "fr-dares-apprentices-stock.json"
    if not path.exists():
        return None
    ind = read_json(path)
    dec: dict[str, dict[str, float]] = {}
    monthly: dict[str, dict[str, float]] = {}
    for o in ind["series"]:
        scope = (o.get("dims") or {}).get("scope", "TOTAL")
        monthly.setdefault(scope, {})[o["time"]] = o["value"]
        if o["time"].endswith("-12"):
            dec.setdefault(scope, {})[o["time"][:4]] = o["value"]
    T, S, H = dec["TOTAL"], dec.get("SECONDARY", {}), dec.get("HIGHER", {})
    years = sorted(T)
    first, last = years[0], years[-1]
    peak = max(years, key=lambda y: T[y])
    share_h = 100 * H[last] / (H[last] + S[last]) if last in H and last in S else None

    # The latest month against the same month a year earlier (the series is strongly seasonal).
    lm = max(monthly["TOTAL"])
    prev = f"{int(lm[:4]) - 1}{lm[4:]}"
    latest_line = ""
    if prev in monthly["TOTAL"] and lm[:4] > last:
        latest_line = (f" The latest monthly figure, for {lm}, is {fmt(monthly['TOTAL'][lm])}, "
                       f"{pct(monthly['TOTAL'][prev], monthly['TOTAL'][lm])} on a year earlier.")

    trends = next((i for i in read_json(PUBLISHED / "insights" / "insights.json")["items"]
                   if i["id"] == "national-trajectories"), None)
    index_series = trends["chart"]["series"] if trends else []
    others = []
    for s in index_series:
        if s["label"].startswith("France"):
            continue
        p = s["points"][-1]
        others.append(f"{s['label'].split(' — ')[0]} {p['value'] - 100:+.0f}% (to {p['time']})".replace("-", "−", 1) if p["value"] < 100
                      else f"{s['label'].split(' — ')[0]} {p['value'] - 100:+.0f}% (to {p['time']})")

    lv = lambda scope, data: {"key": scope, "points": [{"time": y, "value": data[y]} for y in sorted(data)]}
    series = {"TOTAL": lv("TOTAL", T), "SECONDARY": lv("SECONDARY", S), "HIGHER": lv("HIGHER", H)}
    labels = {"TOTAL": "All apprentices", "SECONDARY": "Secondary-level diplomas", "HIGHER": "Higher-education diplomas"}

    steps = [
        {"text": f"At the end of 2017, <strong>{fmt(T['2017'])}</strong> people in France were training under an apprenticeship contract. "
                 f"The number had hardly moved in years: {fmt(T[first])} at the end of {first}.",
         "chart": {"view": "level", "series": ["TOTAL"], "upto": "2017", "mark": "2017"}},
        {"text": "In September 2018 a new law, “for the freedom to choose one’s professional future”, changed how apprenticeship works. "
                 "Any training organisation could now open an apprentice training centre, and centres were funded for each contract they signed. "
                 f"By the end of 2019 there were <strong>{fmt(T['2019'])}</strong> apprentices, {pct(T['2017'], T['2019'])} in two years.",
         "chart": {"view": "level", "series": ["TOTAL"], "upto": "2019", "mark": "2019", "notes": [{"time": "2018", "label": "2018 reform"}]}},
        {"text": "In July 2020, in the middle of the pandemic, the government added an exceptional hiring aid: up to €5,000 for an apprentice under 18 "
                 f"and €8,000 for an adult in the first year. Instead of collapsing, the count jumped to <strong>{fmt(T['2020'])}</strong> "
                 f"at the end of 2020, {pct(T['2019'], T['2020'])} in a single year.",
         "chart": {"view": "level", "series": ["TOTAL"], "upto": "2020", "mark": "2020",
                   "notes": [{"time": "2018", "label": "2018 reform"}, {"time": "2020", "label": "Hiring aid"}]}},
        {"text": f"The growth went on. At its peak, at the end of {peak}, France had <strong>{fmt(T[peak])}</strong> apprentices: "
                 f"{T[peak] / T['2017']:.1f} times the 2017 level.",
         "chart": {"view": "level", "series": ["TOTAL"], "upto": peak, "mark": peak,
                   "notes": [{"time": "2018", "label": "2018 reform"}, {"time": "2020", "label": "Hiring aid"}]}},
        {"text": "Who are the new apprentices? Mostly students in higher education. Apprentices preparing a higher-education diploma "
                 f"(BTS, bachelor, master, engineering degree) went from {fmt(H['2017'])} to <strong>{fmt(H[last])}</strong>; "
                 f"those preparing a secondary-level diploma (CAP, vocational baccalaureate…) from {fmt(S['2017'])} to {fmt(S[last])}."
                 + (f" In {last}, {share_h:.0f}% of apprentices were in higher education." if share_h else ""),
         "chart": {"view": "level", "series": ["SECONDARY", "HIGHER"], "upto": last, "mark": last}},
        {"text": f"At the end of {last} the count fell for the first time in the series: <strong>{fmt(T[last])}</strong>, "
                 f"{pct(T[str(int(last) - 1)], T[last])} on a year earlier. The hiring aid had been cut, most recently in February 2025 "
                 f"to €5,000 for firms with fewer than 250 employees and €2,000 for larger ones.{latest_line}",
         "chart": {"view": "level", "series": ["TOTAL"], "upto": last, "mark": last,
                   "notes": [{"time": "2018", "label": "2018 reform"}, {"time": "2020", "label": "Hiring aid"}, {"time": "2025", "label": "Aid cut"}]}},
    ]
    if index_series:
        steps.append({"text": "Nothing comparable happened in the other countries with long national series. Since 2017: "
                              + "; ".join(others) + ". France also counts higher-education apprentices, which most countries do not, "
                              "so compare the direction, not the levels.",
                      "chart": {"view": "index"}})
    return {
        "id": "french-apprenticeship-boom",
        "title": "The French apprenticeship boom",
        "dek": f"How France went from {fmt(T['2017'])} to over {fmt(T[peak] // 100_000 * 100_000)} apprentices in seven years, who they are, and why the count is now falling.",
        "kicker": "France",
        "chart": {"type": "lines", "unit": "apprentices under contract, end of December",
                  "series": series, "labels": labels,
                  "index": {"unit": "index, 2017 = 100", "series": index_series}},
        "steps": steps,
        "sources": [
            {"label": "DARES, apprentices under contract (POEM), on Apprentix", "url": "pages/indicators/fr-dares-apprentices-stock.html"},
            {"label": "Loi n° 2018-771 du 5 septembre 2018 (Légifrance)", "url": "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000037367660"},
            {"label": "Hiring aid from 1 July 2020: Assemblée nationale, written question 33143", "url": "https://questions.assemblee-nationale.fr/dyn/15/questions/QANR5L15QE33143.pdf"},
            {"label": "2025 cut: Centre Inffo", "url": "https://www.centre-inffo.fr/site-centre-inffo/actualites-centre-inffo/le-quotidien-de-la-formation-actualite-formation-professionnelle-apprentissage/articles-2025/le-gouvernement-diminue-laide-au-recrutement-dapprentis-en-2025"},
            {"label": "National apprenticeship trends (insight)", "url": "pages/insights.html#national-trajectories"},
        ],
        "method": "End-of-December stocks of apprenticeship contracts from DARES (private and public employers, all levels). DARES treats the most recent 48 months as provisional. The comparison uses each country's own series indexed to 2017 = 100.",
    }


# ---------------------------------------------------------------- families --

def two_families() -> dict | None:
    R = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")

    def has(r, k, v):
        x = r.get(k)
        return v in (x if isinstance(x, list) else [x])

    def family(r):
        if has(r, "q_origin", "Grew out of school-based VET"):
            return "school"
        if has(r, "q_learner_status", "Specific apprentice status"):
            return "employer"
        return "other"

    dots = [{"id": r["id"], "cc": "EL" if r["country_code"] == "GR" else r["country_code"], "name": r.get("name_en"),
             "country": r["country"], "family": family(r),
             "old": has(r, "q_introduced", "Before 2000"), "new": has(r, "q_introduced", "After 2012"),
             "craft": has(r, "q_origin", "Craft tradition"),
             "old_craft": has(r, "q_introduced", "Before 2000") and has(r, "q_origin", "Craft tradition"), "school_origin": has(r, "q_origin", "Grew out of school-based VET"),
             "student": has(r, "q_learner_status", "Student"),
             "agreement": has(r, "q_contract_type", "Formal agreement, not a contract"),
             "only_route": has(r, "q_qualification_route", "Only through apprenticeship")}
            for r in sorted(R, key=lambda r: (r["country"], r["id"]))]
    n = len(dots)
    count = lambda k, fam=None: sum(1 for d in dots if d[k] and (fam is None or d["family"] == fam))
    fam_n = {f: sum(1 for d in dots if d["family"] == f) for f in ("employer", "school", "other")}

    ins = next((i for i in read_json(PUBLISHED / "insights" / "insights.json")["items"] if i["id"] == "two-families"), None)
    outcome = ""
    if ins:
        # Reuse the insight's computed outcome sentence (same data, same method).
        f = ins["finding"]
        cut = f.find("Neither group")
        outcome = f[cut:] if cut >= 0 else ""

    other_names = [d["name"] + " (" + d["country"] + ")" for d in dots if d["family"] == "other"]
    steps = [
        {"text": f"Cedefop’s database describes <strong>{n} apprenticeship schemes</strong> in Europe, each coded on the same questions: "
                 "where it came from, who the learner is, what contract they sign, what qualification they get. Each dot is one scheme.",
         "chart": {"layout": "grid", "on": None}},
        {"text": f"<strong>{count('old')}</strong> schemes are old: introduced before 2000, {count('old_craft')} of them from a craft tradition, "
                 "like Germany’s, Austria’s or Denmark’s dual systems.",
         "chart": {"layout": "grid", "on": "old"}},
        {"text": f"Another <strong>{count('new')}</strong> were introduced after 2012, and {count('school_origin')} schemes in all grew out of "
                 "school-based vocational education: schools adding long periods of work to their programmes.",
         "chart": {"layout": "grid", "on": "school_origin"}},
        {"text": f"Sort the schemes by those answers and two families appear: <strong>{fam_n['employer']} employer-based</strong> apprenticeships, "
                 f"where the learner has the status of an apprentice, and <strong>{fam_n['school']} school-based dual tracks</strong>."
                 + (f" {len(other_names)} fit neither: {', '.join(other_names)}." if other_names else ""),
         "chart": {"layout": "families", "on": None}},
        {"text": f"In the school-based family the learner often stays a student: in {count('student', 'school')} of {fam_n['school']} "
                 f"schemes, against {count('student', 'employer')} of {fam_n['employer']} employer-based ones.",
         "chart": {"layout": "families", "on": "student"}},
        {"text": f"A training agreement can replace the contract in {count('agreement', 'school')} of {fam_n['school']} school-based schemes, "
                 f"against {count('agreement', 'employer')} of {fam_n['employer']} employer-based ones.",
         "chart": {"layout": "families", "on": "agreement"}},
        {"text": f"And only employer-based schemes lead to a qualification you can get <strong>only</strong> through apprenticeship: "
                 f"{count('only_route', 'employer')} of them, against {count('only_route', 'school')} school-based ones. "
                 "In the others, the same qualification can also be earned in a school-based programme.",
         "chart": {"layout": "families", "on": "only_route"}},
    ]
    if outcome:
        steps.append({"text": "So which family works better? " + plain(outcome),
                      "chart": {"layout": "families", "on": None, "outcome": True}})
    return {
        "id": "two-families-of-apprenticeship",
        "title": "Two families of apprenticeship",
        "dek": f"Europe’s {n} apprenticeship schemes look alike from afar. Sorted by Cedefop’s own answers, they split into two families with different histories, contracts and qualifications.",
        "kicker": "Europe",
        "chart": {"type": "dots", "dots": dots,
                  "families": {"employer": "Employer-based", "school": "School-based dual", "other": "Neither"},
                  "flags": {"old": "Introduced before 2000", "school_origin": "Grew out of school-based vocational education",
                            "student": "Learner is a student", "agreement": "Training agreement, not a contract",
                            "only_route": "Qualification only through apprenticeship"}},
        "steps": steps,
        "sources": [
            {"label": "Cedefop European database on apprenticeship schemes, on Apprentix", "url": "pages/datasets/apprenticeship-schemes.html"},
            {"label": "Compare all schemes", "url": "pages/compare.html"},
            {"label": "The insight behind this story", "url": "pages/insights.html#two-families"},
        ],
        "method": "Families from Cedefop's coded answers (2026 update): school-based dual = the scheme grew out of school-based vocational education; "
                  "employer-based = the learner has a specific apprentice status and the scheme did not grow out of school-based vocational education. "
                  "Outcomes compare countries whose schemes all fall in one family; they reflect all vocational education and training, not only apprentices.",
    }


def build() -> list[dict]:
    stories = [s for s in (french_boom(), two_families()) if s]
    write_json(OUT, {"description": "Scroll-driven stories: step texts with the chart state for each step. Numbers computed from published data.",
                     "stories": stories})
    return stories


if __name__ == "__main__":
    for s in build():
        print(s["id"], len(s["steps"]), "steps")
        for st_ in s["steps"]:
            print("  -", st_["text"][:200])
