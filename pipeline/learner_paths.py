"""Learner path diagrams for the country pages: school → apprenticeship → qualification → work or
further study, one row per apprenticeship scheme.

Built only from published data:
  - the scheme record and Cedefop's coded answers (typical age, duration, time at work, pay,
    qualification and its level, whether the qualification is also reachable through school-based VET,
    access to higher education);
  - Cedefop's NQF online tool (data/published/nqf-qualification-levels): apprenticeship or craft
    qualifications at a higher EQF level in the same country, as a possible next step;
  - Eurostat's employment rate of recent VET graduates (edat_lfse_24), country and EU-27.

Used by render_pages.render_country(); returns escaped HTML.
"""

from __future__ import annotations

import re
from html import escape

from .common import INDICATORS, PUBLISHED, plain, read_json

EMPLOYMENT = "eurostat-edat_lfse_24-vet"
MASTER = re.compile(r"master|meister|maîtrise|majstor", re.I)
WORK_SHARE = {"Mostly at work (≥2/3)": 70, "Around half": 50, "Under half": 30}
_CACHE: dict = {}


def e(v) -> str:
    return escape(str(v if v is not None else ""), quote=True)


def _employment() -> dict:
    if "emp" not in _CACHE:
        path = INDICATORS / f"{EMPLOYMENT}.json"
        latest: dict[str, dict] = {}
        if path.exists():
            for o in read_json(path)["series"]:
                if (o.get("dims") or {}).get("sex", "T") != "T" or o.get("value") is None:
                    continue
                if o["geo"] not in latest or o["time"] > latest[o["geo"]]["time"]:
                    latest[o["geo"]] = o
        _CACHE["emp"] = latest
    return _CACHE["emp"]


def _craft_next() -> dict:
    """{country name: [(eqf, qualification type)]} for apprenticeship or craft qualifications."""
    if "nqf" not in _CACHE:
        out: dict[str, list] = {}
        path = PUBLISHED / "nqf-qualification-levels" / "records.json"
        if path.exists():
            for r in read_json(path):
                if r.get("apprenticeship_or_craft") != "Yes":
                    continue
                for lv in r.get("eqf_level") or []:
                    m = re.fullmatch(r"EQF (\d)", lv)
                    if m:
                        out.setdefault(r["country"], []).append((int(m.group(1)), r["qualification_type"]))
        _CACHE["nqf"] = out
    return _CACHE["nqf"]


def _nqf_to_eqf() -> dict:
    """{country: {national level: EQF level}} where the country's NQF level maps to exactly one EQF level."""
    if "map" not in _CACHE:
        seen: dict[str, dict[str, set]] = {}
        path = PUBLISHED / "nqf-qualification-levels" / "records.json"
        if path.exists():
            for r in read_json(path):
                for lv in r.get("eqf_level") or []:
                    m = re.fullmatch(r"EQF (\d)", lv)
                    if m and r.get("nqf_level"):
                        seen.setdefault(r["country"], {}).setdefault(str(r["nqf_level"]), set()).add(int(m.group(1)))
        _CACHE["map"] = {c: {n: min(v) for n, v in levels.items() if len(v) == 1} for c, levels in seen.items()}
    return _CACHE["map"]


def level_text(s: dict) -> tuple[str, int | None]:
    """The level as the record states it ('EQF 4', 'EQF 3–4', 'NQF 2–4', 'NFQ 5–10'), and the highest EQF level
    (for a national level, through the country's NQF–EQF referencing when it is one-to-one)."""
    # The education level first ("Upper secondary (NQF 2–4)"), then the qualification text, whose
    # asides ("EQF 5 possible") must not override it.
    for text in filter(None, [s.get("education_level_detail"), s.get("qualification")]):
        m = re.search(r"EQF (\d)(?:\s*[–-]\s*(\d))?", text)
        if m:
            top = int(m.group(2) or m.group(1))
            return (f"EQF {m.group(1)}–{m.group(2)}" if m.group(2) else f"EQF {m.group(1)}"), top
        m = re.search(r"\b([A-Z]{2,5}QF|NQF|NFQ) (\d+)(?:\s*[–-]\s*(\d+))?", text)
        if m:
            label = f"{m.group(1)} {m.group(2)}–{m.group(3)}" if m.group(3) else f"{m.group(1)} {m.group(2)}"
            return label, _nqf_to_eqf().get(s.get("country"), {}).get(m.group(3) or m.group(2))
    return plain(s.get("education_level")), None


def short(text: str | None, n: int = 120) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def step(kicker: str, big: str, lines: list[str], cls: str = "") -> str:
    body = "".join(f"<p>{l}</p>" for l in lines if l)
    return (f'<li class="lp-step {cls}"><span class="lp-k">{e(kicker)}</span>'
            f'<span class="lp-big">{e(big)}</span>{body}</li>')


def scheme_path(s: dict, code: str, the_name: str) -> str:
    # 1. Start
    ages = s.get("q_typical_age") or []
    age = ", ".join(ages) if ages else ""
    start = step("Start", f"Age {age[:1].lower() + age[1:]}" if age else "Entry", [e(short(plain(s.get("target_group")), 110))])

    # 2. Apprenticeship
    work = WORK_SHARE.get(s.get("workplace_time"))
    split = ""
    if work:
        split = (f'<span class="lp-split" role="img" aria-label="About {work}% of the time at the company">'
                 f'<span class="lp-work" style="width:{work}%"></span></span>'
                 f'<span class="lp-split-k"><span>Company</span><span>School</span></span>')
    pay = {"Wage": "Paid a wage", "Allowance": "Paid an allowance", "Mostly unpaid": "Mostly unpaid"}.get(s.get("compensation"), "")
    appr = step("Apprenticeship", s.get("duration") or "", [split, e(pay)])

    # 3. Qualification
    lv, top = level_text(s)
    route = s.get("q_qualification_route")
    route_txt = {"Only through apprenticeship": "Only through apprenticeship",
                 "Also through school-based VET": "Also possible in a school-based programme"}.get(route, "")
    qual = step("Qualification", lv, [e(short(plain(s.get("qualification")), 110)),
                                       f'<span class="lp-chip">{e(route_txt)}</span>' if route_txt else ""])

    # 4. Then: work, further study
    emp, branches = _employment(), []
    c, eu = emp.get(code), emp.get("EU27")
    if c:
        eu_txt = f" (EU: {eu['value']:.0f}%)" if eu else ""
        branches.append(f'<div class="lp-branch"><span class="lp-k">Work</span><span class="lp-big">{c["value"]:.0f}%</span>'
                        f'<p>of young people in {e(the_name)} who recently finished vocational training had a job, {e(c["time"])}{e(eu_txt)}</p></div>')
    he = s.get("q_access_to_he")
    study = {"Yes": "The qualification gives access to higher education",
             "No": "The qualification does not by itself give access to higher education"}.get(he, "")
    nxt = ""
    if top:
        # Only master-craftsperson qualifications count as a next step: they build on the apprenticeship.
        higher = sorted({(lv_, t) for lv_, t in _craft_next().get(s.get("country"), [])
                         if lv_ > top and MASTER.search(t) and not re.search(r"agricultur", t, re.I)})
        if higher:
            lv_, t = higher[-1]
            nxt = f'<p>Next step up: {e(short(t, 70))}, EQF {lv_}</p>'
    if study or nxt:
        mark = "✓" if he == "Yes" else ("–" if he == "No" else "")
        branches.append(f'<div class="lp-branch"><span class="lp-k">Further study</span><span class="lp-big" aria-hidden="true">{mark}</span>'
                        f'<p>{e(study)}</p>{nxt}</div>')
    then = (f'<li class="lp-step lp-then"><span class="lp-k lp-k-then">Then</span><div class="lp-branches">{"".join(branches)}</div></li>'
            if branches else "")

    return (f'<li class="lp-row"><h3><a href="#scheme-{e(s["id"])}">{e(s.get("name_en"))}</a></h3>'
            f'<ol class="lp-steps">{start}{appr}{qual}{then}</ol></li>')


def section_html(code: str, the_name: str, schemes: list[dict]) -> str:
    if not schemes:
        return ""
    rows = "".join(scheme_path(s, code, the_name) for s in schemes)
    emp = _employment()
    year = emp.get(code, {}).get("time")
    srcs = ["Cedefop’s European database on apprenticeship schemes (coded answers)",
            "Cedefop’s NQF online tool (next step up)"]
    if year:
        srcs.append(f'Eurostat edat_lfse_24 (<a href="../indicators/{EMPLOYMENT}.html">employment of recent graduates of vocational education and training</a>, all vocational programmes, not only apprenticeships)')
    title = the_name[0].upper() + the_name[1:]
    return f"""<section class="cp-sec" id="path" aria-labelledby="h-path">
  <h2 id="h-path">From school to work</h2>
  <p class="sub">The path through {"each apprenticeship scheme" if len(schemes) > 1 else "the apprenticeship scheme"} in {e(the_name)}: who starts, how long it takes, what it leads to, and what comes next.</p>
  <ol class="lp">{rows}</ol>
  <p class="provenance">{e(title)}: from {"; ".join(srcs)}. Ages are the typical ages Cedefop records, not limits.</p>
</section>"""
