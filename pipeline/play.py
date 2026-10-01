"""Question pool for the "Higher or lower?" game → data/published/play/questions.json.

  python -m pipeline.play      (build() is meant to be called from pipeline/build.py)

Every question asks which of two countries has the higher value of one measure.
A question is only emitted when the comparison is fair:

  * cross-country comparable indicators only (Eurostat, Cedefop key indicators
    on VET, OECD — harmonised definitions); never national series, never counts
    that mostly reflect country size;
  * both countries on the SAME indicator, the SAME year and the indicator's
    default breakdown; the year is the latest one with broad coverage (same rule
    as pipeline/facts.py: ≥ 12 EEA countries and ≥ 60 % of the best year);
  * only values without a flag, or flagged provisional / estimated; anything
    flagged low reliability, definition differs, break in series, confidential
    or not applicable is dropped (stricter than facts.py, which only checks
    breaks for trends: a break year is skipped here too);
  * no ties or near-ties: the relative gap |a − b| / max(|a|, |b|) must be at
    least 5 % AND the absolute gap above a per-unit minimum (e.g. 2 percentage
    points), so the answer never hangs on measurement noise;
  * difficulty from the relative gap: 1 (≥ 35 %), 2 (≥ 15 %), 3 (≥ 5 %);
  * phrasing is neutral: always "which is higher / more", never "better";
  * scheme-design questions use Cedefop's coded fiche answers for countries
    with a single scheme and only when the coded bands are at least two
    categories apart. Scheme duration is free text (ranges, "by programme"),
    so "which lasts longer" is deliberately not asked.

Selection is deterministic: candidates are ordered by a SHA-1 of their id,
balanced by difficulty and by country within each indicator. Output sorted by id.
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
from urllib.parse import quote

from .common import PUBLISHED, read_json
from .insights import EEA, ind, obs
from .render_pages import fmt_value

OUT = PUBLISHED / "play" / "questions.json"

# Flags that are fine to compare across countries (none, provisional, estimated).
OK_FLAGS = {"", "p", "e", "ep", "pe"}
MIN_REL = 0.05
DIFFICULTY = [(0.35, 1), (0.15, 2), (MIN_REL, 3)]
MIN_ABS_BY_UNIT = {"%": 2.0, "% of enterprises": 2.0, "1000 PPS": 0.5, "languages": 0.2}
PER_DIFFICULTY = 7          # questions per indicator and difficulty (at most)
PER_COUNTRY = 3             # appearances of one country per indicator (at most)
EXPLAIN_MAX = 160
# Small percentages shown with two decimals so close values never print the same.
DIGITS = {"cedefop-kivet-2010": 2}

# (indicator, question, override of the absolute minimum gap or None)
MEASURES = [
    ("eurostat-edat_lfse_24-vet", "Which country has more recent VET graduates in work?", None),
    ("eurostat-tps00215", "In which country did more recent VET graduates learn at a workplace during their course?", None),
    ("eurostat-trng_cvt_34s", "In which country do more companies employ apprentices or other vocational trainees?", None),
    ("cedefop-kivet-1010", "In which country are more upper-secondary students on vocational programmes?", None),
    ("cedefop-kivet-1020", "In which country do more vocational students learn partly in a company (school plus workplace)?", None),
    ("cedefop-kivet-1025", "In which country can more vocational students go straight on to higher education?", None),
    ("cedefop-kivet-1030", "In which country do more employees take part in work-related training courses?", None),
    ("cedefop-kivet-1050", "In which country did more adults (25–64) take part in learning in the last four weeks?", None),
    ("cedefop-kivet-1060", "In which country do more companies provide training for their staff?", None),
    ("cedefop-kivet-1070", "In which country are more upper-secondary girls on vocational programmes?", None),
    ("cedefop-kivet-1080", "In which country do more young vocational graduates carry on in education or training?", None),
    ("cedefop-kivet-1140a", "In which country do more adults learn online?", None),
    ("cedefop-kivet-2010", "Which country spends a larger share of its GDP on vocational education for young people?", 0.1),
    ("cedefop-kivet-2025", "Which country spends more public money per vocational student (adjusted for price levels)?", None),
    ("cedefop-kivet-2040", "In which country do vocational students learn more foreign languages on average?", None),
    ("cedefop-kivet-2050", "In which country do more vocational graduates come from science, technology, engineering or maths?", None),
    ("cedefop-kivet-2130a", "In which country do more adults have at least basic digital skills?", None),
    ("cedefop-kivet-3010", "Which country has more early leavers from education and training (18–24)?", None),
    ("cedefop-kivet-3021", "In which country do more 25–34-year-olds have a university-level degree?", None),
    ("cedefop-kivet-3030", "Which country has more young people (15–29) neither in work nor in education or training?", None),
    ("cedefop-kivet-3040", "Which country has the higher unemployment rate among 20–34-year-olds?", None),
    ("cedefop-kivet-3060", "Which country has the higher employment rate among 20–64-year-olds?", None),
    ("oecd-emp-rate-upper-secondary", "In which country are more adults with a vocational upper-secondary qualification in work?", None),
]

# Scheme-design questions: (coded question, measure, ordered bands low → high, display phrase per band)
SCHEME_QUESTIONS = [
    ("q_share_of_vet", "Which country's apprenticeship scheme takes in a larger share of its vocational learners?",
     ["Under 10%", "10–30%", "30–60%", "Over 60%"],
     {"Under 10%": "under 10% of VET learners", "10–30%": "10–30% of VET learners",
      "30–60%": "30–60% of VET learners", "Over 60%": "over 60% of VET learners"}),
    ("q_introduced", "Which country's apprenticeship scheme has existed for longer?",
     ["After 2012", "2000–2012", "Before 2000"],
     {"After 2012": "introduced after 2012", "2000–2012": "introduced 2000–2012",
      "Before 2000": "dates from before 2000"}),
]
SCHEME_MIN_BANDS = 2
ALIASES = {"GR": "EL", "GB": "UK"}


def _h(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _flag(o: dict | None) -> str:
    return ((o or {}).get("flag") or "").strip()


def _ok(o: dict) -> bool:
    return _flag(o).lower() in OK_FLAGS


def _cross_section(iid: str):
    """Latest year with broad coverage (facts.py rule) → ({geo: obs} usable values, year, EU obs)."""
    d = ind(iid)
    by_year = collections.defaultdict(dict)
    eu = {}
    for o in obs(d):
        if o.get("value") is None:
            continue
        if o["geo"] in EEA:
            by_year[o["time"]][o["geo"]] = o
        elif o["geo"] == "EU27":
            eu[o["time"]] = o
    if not by_year:
        return d, {}, None, None
    top = max(len(v) for v in by_year.values())
    ok = [y for y, v in by_year.items() if len(v) >= max(12, 0.6 * top)]
    if not ok:
        return d, {}, None, None
    y = max(ok)
    rows = {g: o for g, o in by_year[y].items() if _ok(o)}
    e = eu.get(y)
    return d, rows, y, (e if e and _ok(e) else None)


def _difficulty(a: float, b: float, min_abs: float) -> int | None:
    gap = abs(a - b)
    top = max(abs(a), abs(b))
    if not top or gap < min_abs:
        return None
    rel = gap / top
    for cut, level in DIFFICULTY:
        if rel >= cut:
            return level
    return None


def _fmt(iid: str, v: float, unit: str) -> str:
    if iid in DIGITS and "%" in unit:
        return f"{v:,.{DIGITS[iid]}f}%"
    if unit == "languages":
        return f"{v:.1f} languages"
    return fmt_value(v, unit)


def _num(v: float):
    r = round(float(v), 4)
    return int(r) if r == int(r) else r


def _pick(cands: list[dict]) -> list[dict]:
    """Deterministic, balanced choice: per difficulty, hash order, country cap."""
    chosen, per_geo = [], collections.Counter()
    for level in (1, 2, 3):
        k = 0
        for q in sorted((c for c in cands if c["difficulty"] == level), key=lambda c: _h(c["id"])):
            ga, gb = q["a"]["geo"], q["b"]["geo"]
            if per_geo[ga] >= PER_COUNTRY or per_geo[gb] >= PER_COUNTRY:
                continue
            chosen.append(q)
            per_geo[ga] += 1
            per_geo[gb] += 1
            k += 1
            if k >= PER_DIFFICULTY:
                break
    return chosen


def _side(geo: str, C: dict, value, display: str, flag: str = "", flag_label: str = "") -> dict:
    c = C[geo]
    out = {"geo": geo, "name": c["name"], "emoji": c.get("flag", ""), "value": value, "display": display}
    if flag:
        out["flag"] = flag
        if flag_label:
            out["flag_label"] = flag_label
    return out


def _order(q_id: str, x, y):
    """Put the pair in a hash-determined order so the answer is not always 'a'."""
    return (x, y) if int(_h(q_id + "|order")[:8], 16) % 2 == 0 else (y, x)


def _indicator_questions(C: dict, rejected: collections.Counter) -> list[dict]:
    out = []
    for iid, measure, min_abs_override in MEASURES:
        d, rows, year, eu = _cross_section(iid)
        if not rows:
            rejected["no usable cross-section"] += 1
            continue
        unit = d.get("unit", "")
        min_abs = min_abs_override if min_abs_override is not None else MIN_ABS_BY_UNIT.get(unit)
        if min_abs is None:
            raise ValueError(f"{iid}: no minimum gap defined for unit {unit!r}")
        flags = d.get("flags") or {}
        publisher = (d.get("provenance") or {}).get("publisher", "")
        geos = sorted(g for g in rows if g in C)
        cands = []
        for i, g1 in enumerate(geos):
            for g2 in geos[i + 1:]:
                o1, o2 = rows[g1], rows[g2]
                lvl = _difficulty(o1["value"], o2["value"], min_abs)
                if lvl is None:
                    rejected["gap too small"] += 1
                    continue
                qid = f"{iid}-{year}-{g1}-{g2}"
                x, y = _order(qid, (g1, o1), (g2, o2))
                sides = [_side(g, C, _num(o["value"]), _fmt(iid, o["value"], unit), _flag(o),
                               flags.get(_flag(o), "")) for g, o in (x, y)]
                if sides[0]["display"] == sides[1]["display"]:
                    rejected["values print the same"] += 1
                    continue
                answer = "a" if x[1]["value"] > y[1]["value"] else "b"
                explain = f"{sides[0]['name']}: {sides[0]['display']}, {sides[1]['name']}: {sides[1]['display']} ({year})."
                if eu:
                    explain += f" EU-27: {_fmt(iid, eu['value'], unit)}."
                if len(explain) > EXPLAIN_MAX:
                    rejected["explain too long"] += 1
                    continue
                cands.append({
                    "id": qid, "kind": "indicator", "indicator": iid, "title": d.get("title", ""),
                    "measure": measure, "unit": unit, "year": year,
                    "a": sides[0], "b": sides[1], "answer": answer, "explain": explain,
                    "link": f"indicators.html?id={iid}&geo={g1},{g2}&year={year}",
                    "difficulty": lvl, "source": publisher,
                })
        out += _pick(cands)
    return out


def _scheme_questions(C: dict, rejected: collections.Counter) -> list[dict]:
    recs = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")
    by_country = collections.defaultdict(list)
    for r in recs:
        by_country[ALIASES.get(r["country_code"], r["country_code"])].append(r)
    # Only countries with exactly one scheme: no question of which scheme is "the" one.
    single = {g: rs[0] for g, rs in by_country.items() if len(rs) == 1 and g in C}
    years = sorted({y for r in recs for y in re.findall(r"\b(20\d\d)\b", r.get("source_version", ""))})
    year = years[-1] if years else ""
    out = []
    for key, measure, bands, phrase in SCHEME_QUESTIONS:
        rank = {b: i for i, b in enumerate(bands)}
        coded = {g: r[key] for g, r in single.items() if isinstance(r.get(key), str) and r[key] in rank}
        geos = sorted(coded)
        cands = []
        for i, g1 in enumerate(geos):
            for g2 in geos[i + 1:]:
                d = abs(rank[coded[g1]] - rank[coded[g2]])
                if d < SCHEME_MIN_BANDS:
                    rejected["scheme bands too close"] += 1
                    continue
                qid = f"scheme-{key[2:].replace('_', '-')}-{g1}-{g2}"
                x, y = _order(qid, g1, g2)
                sides = [_side(g, C, coded[g], phrase[coded[g]]) for g in (x, y)]
                for s, g in zip(sides, (x, y)):
                    s["scheme"] = single[g].get("name_en", "")
                answer = "a" if rank[coded[x]] > rank[coded[y]] else "b"
                explain = (f"{sides[0]['name']}: {sides[0]['display']}; "
                           f"{sides[1]['name']}: {sides[1]['display']} (Cedefop scheme fiches, {year}).")
                if len(explain) > EXPLAIN_MAX:
                    rejected["explain too long"] += 1
                    continue
                link = ("explore.html?dataset=apprenticeship-schemes"
                        f"&f.country={quote(single[g1]['country'])}&f.country={quote(single[g2]['country'])}")
                cands.append({
                    "id": qid, "kind": "scheme", "indicator": key, "title": "Cedefop apprenticeship scheme fiches",
                    "measure": measure, "unit": "band", "year": year,
                    "a": sides[0], "b": sides[1], "answer": answer, "explain": explain,
                    "link": link, "difficulty": 1 if d >= 3 else 2, "source": "Cedefop",
                })
        out += _pick(cands)
    return out


def build() -> dict:
    ref = read_json(PUBLISHED.parent / "reference" / "countries.json")
    C = {c["code"]: c for c in ref["countries"] if c["code"] in EEA}
    rejected: collections.Counter = collections.Counter()
    qs = _indicator_questions(C, rejected) + _scheme_questions(C, rejected)
    qs.sort(key=lambda q: q["id"])
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids)), "duplicate question id"
    out = {
        "description": ("Question pool for the Apprentix 'Higher or lower?' game (pages/play.html). "
                        "Generated by pipeline/play.py: same indicator and year for both countries, "
                        "cross-country comparable sources only, no flagged or near-equal values."),
        "rules": {
            "min_relative_gap": MIN_REL,
            "min_absolute_gap": MIN_ABS_BY_UNIT,
            "difficulty": {"1": "relative gap ≥ 35%", "2": "relative gap ≥ 15%", "3": "relative gap ≥ 5%"},
            "flags_allowed": sorted(f for f in OK_FLAGS if f),
            "countries": "EU-27, Iceland, Liechtenstein, Norway, Switzerland",
        },
        "count": len(qs),
        "questions": qs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n"
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
        OUT.write_text(text, encoding="utf-8")
    build.rejected = rejected
    return out


if __name__ == "__main__":
    o = build()
    qs = o["questions"]
    by_d = collections.Counter(q["difficulty"] for q in qs)
    by_i = collections.Counter(q["indicator"] for q in qs)
    print(f"{OUT.relative_to(PUBLISHED.parent.parent)}: {len(qs)} questions; "
          f"difficulty {dict(sorted(by_d.items()))}; {OUT.stat().st_size / 1024:.0f} KB")
    for k, v in sorted(by_i.items()):
        print(f"  {v:3d}  {k}")
    print("  rejected:", dict(build.rejected))
