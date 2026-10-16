"""Scheme portraits: a visual summary and a "What to expect on this scheme" story for each
of the 34 apprenticeship schemes, written only from Cedefop's coded answers (the q_* fields)
and the scheme record's own short texts.

  python -m pipeline.portraits

  data/published/portraits/portraits.json   {scheme id: {country, name, split, facts, story, html}}

The "html" snippet is escaped here and reused as is by the country pages (render_pages.py),
the Scheme of the week card and the quiz results, so every place tells the same story.
Deterministic: no clock.
"""

from __future__ import annotations

import html
import re

from .common import PUBLISHED, read_json, write_json

OUT = PUBLISHED / "portraits" / "portraits.json"
DATASET = PUBLISHED / "apprenticeship-schemes" / "records.json"


def e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def as_list(v) -> list[str]:
    return [x for x in (v if isinstance(v, list) else [v]) if x]


def join_or(items: list[str]) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1] if items else ""


# Share of time at the company, as drawn on the split bar (fraction) and said in words.
SPLIT = {
    "Mostly at work (≥2/3)": (0.7, "most of your time (two-thirds or more) at the company"),
    "Around half": (0.5, "about half your time at the company"),
    "Under half": (0.3, "less than half your time at the company, the rest at school or a training centre"),
}
RHYTHM = {
    "Every week, both venues": "switching between school and work every week",
    "Blocks of weeks": "in blocks of a few weeks at school and at work",
    "Blocks of months": "in blocks of several months at school and at work",
    "School years, then workplace": "first at school, then at the workplace",
}
AGE = {"15–18": "between 15 and 18", "18–24": "between 18 and 24", "Over 24": "over 24"}
WAGE_SET = {"By law": "by law", "Sectoral agreements": "by collective agreements for your sector",
            "Cross-sector agreements": "by national collective agreements",
            "Firm or individual agreements": "by agreement with your employer"}
FUNDER = {"Employers": "your employer", "State": "the state"}
STATUS = {
    ("Specific apprentice status", "Specific apprenticeship contract"):
        "You would sign an apprenticeship contract and have the legal status of an apprentice.",
    ("Employee", "Ordinary employment contract"):
        "You would be an employee, on an ordinary employment contract.",
    ("Student", "Formal agreement, not a contract"):
        "You would stay a student, with a formal training agreement between you, your school and the company.",
}


def duration_words(d: str) -> str:
    d = re.sub(r"-yrs?\b", "-year", d or "")
    d = re.sub(r"\byrs\b", "years", d)
    return re.sub(r"\byr\b", "year", d)


def portrait(s: dict) -> dict:
    country = (s.get("country") or "").split(" — ")[0]
    share = s.get("workplace_time")
    split, split_words = SPLIT.get(share, (None, None))
    pay = as_list(s.get("q_compensation"))
    status = as_list(s.get("q_learner_status"))
    contract = as_list(s.get("q_contract_type"))
    he = s.get("q_access_to_he")

    facts = []
    if pay:
        pay_label = "Wage" if "Wage" in pay else "Allowance" if "Allowance" in pay else "Not required by law"
        who = join_or([FUNDER.get(f, "") for f in as_list(s.get("q_pay_funded_by")) if f in FUNDER])
        facts.append({"icon": "pay", "label": "Pay", "value": pay_label + (f", paid by {who}" if who and pay_label != "Not required by law" else "")})
    if contract:
        facts.append({"icon": "contract", "label": "Arrangement", "value": join_or(contract)})
    if s.get("duration"):
        facts.append({"icon": "time", "label": "Duration", "value": s["duration"]})
    if s.get("q_typical_age"):
        facts.append({"icon": "age", "label": "Typical age", "value": join_or(as_list(s["q_typical_age"]))})
    level = s.get("education_level")
    detail = s.get("education_level_detail") or ""
    if level == "Multiple levels" and detail and len(detail) <= 40:
        level = detail
    elif level == "Multiple levels":
        level = "Several levels"
    if level:
        facts.append({"icon": "level", "label": "Leads to", "value": level + (" · access to higher education" if he == "Yes" else "")})

    # The story, sentence by sentence; each sentence only when the coded answers support it.
    story = []
    ages = [AGE[a] for a in as_list(s.get("q_typical_age")) if a in AGE]
    if ages:
        line = f"You would most likely be {join_or(ages)}"
        if "Over 24" in as_list(s.get("q_typical_age")) and len(ages) == 1:
            line += " — many apprentices here are adults"
        story.append(line + ".")
    key = (status[0] if len(status) == 1 else None, contract[0] if len(contract) == 1 else None)
    if key in STATUS:
        story.append(STATUS[key])
    elif contract:
        story.append(f"Your training would be set out in a written arrangement ({join_or([c.lower() for c in contract])}).")
    if split_words:
        rhythm = [RHYTHM[r] for r in as_list(s.get("q_alternation_form")) if r in RHYTHM]
        story.append(f"You would spend {split_words}" + (f", {rhythm[0]}" if len(rhythm) == 1 else "") + ".")
    if "Wage" in pay:
        sets = [WAGE_SET[w] for w in as_list(s.get("q_wage_setting")) if w in WAGE_SET]
        who = join_or([FUNDER[f] for f in as_list(s.get("q_pay_funded_by")) if f in FUNDER])
        line = "You would earn a wage" + (f", set {join_or(sets)}" if sets else "") + (f", paid by {who}" if who else "")
        if s.get("q_pay_covers_school") == "Yes":
            line += "; it also covers your days at school"
        story.append(line + ".")
    elif "Allowance" in pay:
        who = join_or([FUNDER[f] for f in as_list(s.get("q_pay_funded_by")) if f in FUNDER])
        story.append("You would receive an allowance rather than a wage" + (f", paid by {who}" if who else "") + ".")
    elif "None required by law" in pay:
        story.append("The law does not require you to be paid.")
    if s.get("duration"):
        d = duration_words(s["duration"])
        if re.match(r"\d[\d\s–.,/]*(school )?(months?|years?|weeks?|hours?|h)\b", d):
            story.append(f"It would take {d}.")
        else:
            story.append(f"Duration: {d[0].lower() + d[1:] if d[1:2].islower() else d}.")
    if s.get("qualification"):
        line = f"You would finish with: {s['qualification']}"
        if he == "Yes":
            line += ", which gives direct access to higher education"
        elif he == "No":
            line += ", which does not by itself give access to higher education"
        story.append(line + ".")

    # The story always sits under the scheme's own name (country pages, Scheme of the week,
    # quiz results), so a neutral title avoids two schemes in one country sharing a heading.
    title = "What to expect on this scheme"
    return {"country": country, "country_code": s.get("country_code"), "name": s.get("name_en"),
            "split": split, "split_label": share, "facts": facts, "story_title": title, "story": story,
            "html": render(s, title, split, share, facts, story)}


ICONS = {   # 20×20 stroke icons (currentColor)
    "pay": '<path d="M3 6h14v9H3z"/><circle cx="10" cy="10.5" r="2.2"/><path d="M6 6V4.5h8V6"/>',
    "contract": '<path d="M5 2.5h7l3 3v12H5z"/><path d="M12 2.5v3h3M7.5 9h5M7.5 12h5M7.5 15h3"/>',
    "time": '<circle cx="10" cy="10" r="7"/><path d="M10 6v4l3 2"/>',
    "age": '<circle cx="10" cy="7" r="3"/><path d="M4 17c.8-3.2 3.2-5 6-5s5.2 1.8 6 5"/>',
    "level": '<path d="M2 8l8-4 8 4-8 4z"/><path d="M5.5 9.8V13c1.2 1.3 2.8 2 4.5 2s3.3-.7 4.5-2V9.8"/>',
}


def icon(name: str) -> str:
    # width/height attributes keep the icon small even if a stale stylesheet is served.
    return (f'<svg class="pt-icon" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" focusable="false" fill="none" '
            f'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def render(s: dict, title: str, split, share, facts, story) -> str:
    bar = ""
    if split is not None:
        pct = round(split * 100)
        bar = (f'<div class="pt-split" role="img" aria-label="Time at the company: {e(share)}">'
               f'<span class="pt-work" style="width:{pct}%"><span>Company</span></span>'
               f'<span class="pt-school" style="width:{100 - pct}%"><span>School</span></span></div>'
               f'<p class="pt-split-note">{e(share)}</p>')
    chips = "".join(f'<li>{icon(f["icon"])}<span class="pt-k">{e(f["label"])}</span> <span class="pt-v">{e(f["value"])}</span></li>'
                    for f in facts)
    text = " ".join(e(x) for x in story)
    return (f'<div class="portrait">{bar}<ul class="pt-facts">{chips}</ul>'
            f'<div class="pt-story"><h4>{e(title)}</h4><p>{text}</p>'
            f'<p class="pt-src">From Cedefop\'s coded answers for this scheme (2026 fiche).</p></div></div>')


def build() -> dict:
    schemes = read_json(DATASET)
    out = {s["id"]: portrait(s) for s in sorted(schemes, key=lambda s: s["id"])}
    write_json(OUT, {"description": "Scheme portraits and 'What to expect on this scheme' stories, generated from "
                                    "Cedefop's coded answers by pipeline/portraits.py.",
                     "portraits": out})
    print(f"Portraits: {len(out)} schemes")
    return out


if __name__ == "__main__":
    build()
