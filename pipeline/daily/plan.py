"""Plan editions from a story bank: about 12 items a day, in one of four variants.

  python -m pipeline.daily.plan 2026-10-19            write the lab (all variants, Mon–Fri)
                                                      and the main edition for that day

Variants:
  layout  shape     The one thing · Lives · Five to know · Today's question · Diary · More today
          sections  the paper's sections, each capped, about the same number of stories
  rhythm  plain     every day ranks stories by priority alone
          rhythm    each weekday boosts one focus: Mon policy and Cedefop, Tue research,
                    Wed the field, Thu AI and the future of work, Fri long reads (and
                    the Lives story at length)

The planner walks the week in order and never runs a story twice, so later days use
what earlier days left, as the pacing banks in BLUEPRINT §7 intend. A story with
"only_on" runs only that day; one with "lead_on" leads that day; one with "no_lead"
(housekeeping: board changes, short notices) never leads. Deterministic.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

from ..common import ROOT

DAILY = ROOT / "daily"
BOOST = 2.0
DAY_FOCUS = {0: {"policy", "cedefop"}, 1: {"research"}, 2: {"field"}, 3: {"ai"}, 4: {"long"}}
DAY_NAME = {0: "Policy and the week ahead", 1: "Research day", 2: "From the field", 3: "AI and the future of work",
            4: "Long reads"}
FIVE, MORE = 5, 4                      # shape: lead + 5 cards + 4 links = 10 stories
MAX_STORIES = 10
CAPS = {"cedefop": 2, "field": 2, "debate": 2, "policy": 2, "agencies": 1, "research": 2}
SECTION_STORIES = 9                    # sections: lead + 9 cards = 10 stories
SECTION_ORDER = [("cedefop", "At Cedefop"), ("field", "From the field"), ("debate", "The wider debate"),
                 ("policy", "EU policy"), ("agencies", "Agencies and partners"), ("research", "Research")]
VARIANTS = [("shape", False), ("shape", True), ("sections", False), ("sections", True)]


def variant_id(layout: str, rhythm: bool) -> str:
    return f"{layout}-{'rhythm' if rhythm else 'plain'}"


def weight(s: dict, wd: int, rhythm: bool) -> float:
    w = s["priority"]
    if rhythm and set(s.get("focus", [])) & DAY_FOCUS[wd]:
        w *= BOOST
    return w


def plan_day(bank: dict, date: str, number: int, used: set, layout: str, rhythm: bool, main: bool,
             days_left: int = 1) -> dict:
    d = dt.date.fromisoformat(date)
    wd = d.weekday()
    avail = [s for s in bank["stories"] if s["key"] not in used and s.get("only_on", date) == date]
    # Pacing: share what is left across the days left, at most 10 stories a day.
    later = [s for s in bank["stories"] if s["key"] not in used and not s.get("only_on")]
    target = min(MAX_STORIES, max(1, math.ceil(len(later) / days_left)) + sum(1 for s in avail if s.get("only_on")))
    order = sorted(avail, key=lambda s: (-weight(s, wd, rhythm), -s["priority"], s["key"]))
    lead = (next((s for s in order if s.get("lead_on") == date), None)
            or next((s for s in order if s["priority"] >= 4 and not s.get("lead_on") and not s.get("no_lead")), None)
            or next((s for s in order if not s.get("lead_on") and not s.get("no_lead")), None)
            or next(s for s in order if not s.get("lead_on")))
    rest = [s for s in order if s is not lead]
    ed = {"schema": 2, "layout": layout, "rhythm": rhythm, "date": date, "number": number, "pool": bank["pool"],
          "built_from": "public sources retrieved on 17 October 2026", "built_on": bank["built_on"],
          "preview": not main, "day_focus": DAY_NAME[wd] if rhythm else None,
          "strip": STRIP, "lead": lead}
    picked = [lead]
    if layout == "shape":
        ed["five"] = rest[:min(FIVE, target - 1)]
        ed["more"] = rest[len(ed["five"]):max(len(ed["five"]), target - 1)][:MORE]
        picked += ed["five"] + ed["more"]
    else:
        count, sections = {k: 0 for k in CAPS}, {k: [] for k in CAPS}
        for s in rest:
            if sum(count.values()) >= min(SECTION_STORIES, target - 1):
                break
            p = s["pillar"]
            if p in CAPS and count[p] < CAPS[p]:
                count[p] += 1
                sections[p].append(s)
                picked.append(s)
        ed["sections"] = [{"id": k, "pillar": k, "title": t, "stories": sections[k]} for k, t in SECTION_ORDER if sections[k]]
    used |= {s["key"] for s in picked}
    lives = next((x for x in bank["lives"] if x["date"] == date), None)
    if lives:
        lives = dict(lives)
        if rhythm and wd == 4 and lives.get("long"):
            lives["body"], lives["is_long"] = lives["long"], True
            ed["lives_first"] = True          # Friday's long Lives story opens the paper
        ed["lives"] = lives
    ed["question"] = bank["questions"][str(wd)]
    diary = bank["diary"]
    if wd == 0:
        ed["diary"] = {"title": "Week ahead", "days": [{"date": date, "events": diary["week_ahead"]}],
                       "more": diary["more"], "coming": diary["coming"]}
    else:
        ed["diary"] = {"title": "Diary", "days": [], "more": [], "coming": diary["coming"][:4]}
    return ed


STRIP = {"kind": "numbers", "title": "This week in numbers", "items": [
    {"count": {"source": "openalex_fulltext", "from": "2026-10-11", "to": "2026-10-17"},
     "label": "research papers mentioning Cedefop", "note": "published 11–17 October · OpenAlex full text"},
    {"count": {"source": "cellar_recent", "kind": "publication", "from": "2026-09-28", "to": "2026-10-17", "exclude_title": "Grant Award Notice"},
     "label": "new Cedefop publications catalogued", "note": "28 September – 17 October · EU Publications Office"},
    {"count_press": {"from": "2026-10-10", "to": "2026-10-17"},
     "label": "press and field stories on VET and skills", "note": "10–17 October · from the paper’s press feeds"},
    {"value": {"item": "6516e27cb6", "field": "latest_value", "suffix": "%"},
     "label": "of 18–24-year-olds left education and training early", "note": "EU-27, 2025 · Eurostat"}]}


def week(start: str) -> list[str]:
    d = dt.date.fromisoformat(start)
    return [(d + dt.timedelta(days=i)).isoformat() for i in range(5)]


def main(argv: list[str]) -> int:
    start = argv[0] if argv else "2026-10-19"
    bank = json.loads((DAILY / "bank" / f"{start}.json").read_text("utf-8"))
    days = week(start)
    for layout, rhythm in VARIANTS:
        used: set = set()
        for n, date in enumerate(days, start=1):
            ed = plan_day(bank, date, n, used, layout, rhythm, main=False, days_left=len(days) - n + 1)
            out = DAILY / "lab" / variant_id(layout, rhythm) / date / "edition.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(ed, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"lab/{variant_id(layout, rhythm)}: {len(used)} of {len(bank['stories'])} bank stories used over 5 days")
    # The main paper: shape, no rhythm (the recommended default), for the bank's first day only.
    ed = plan_day(bank, start, 1, set(), "shape", False, main=True, days_left=len(days))
    (DAILY / "editions" / f"{start}.json").write_text(json.dumps(ed, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"editions/{start}.json: main edition (shape, no rhythm)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
