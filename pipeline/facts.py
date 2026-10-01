"""Short "Did you know?" facts computed from the published data → data/published/facts/facts.json.

  python -m pipeline.facts      (prints every fact; build() is called from pipeline/build.py)

Every number is recomputed from the published data on each build; nothing is
hard-coded except wording. A fact is only emitted when the data supports it:

  * cross-country comparisons use the latest year with broad coverage, EEA
    countries, the indicator's default breakdown, and skip values flagged as
    low reliability (u), definition differs (d), not applicable or confidential;
  * changes over time skip any series with a break-in-series flag (b…) between
    the two compared years;
  * national statistics are only ever used as within-country trends (their
    definitions differ), and partial years are never used as an end point;
  * monthly stocks are compared on their December values.

Each fact: id (stable), text (≤ 180 characters), highlight (verbatim in text),
kind, countries, link (repo-relative), source (short publisher name), weight
(1–3, 3 = most surprising). Output is deterministic and sorted by id.
"""

from __future__ import annotations

import collections
import re

from .common import PUBLISHED, RAW, read_json, write_json
from .insights import EEA, EU27, ind, latest, n, obs, series

OUT = PUBLISHED / "facts" / "facts.json"
MAX_LEN = 180
KINDS = ("record", "contrast", "trend", "design", "qualification", "mobility", "policy", "outcome")
BAD_FLAGS = ("u", "d", "z", "c", "m")   # any of these letters → not used in a cross-country comparison
THE = {"NL": "the Netherlands", "UK": "the United Kingdom", "CZ": "Czechia"}
ALIASES = {"GR": "EL", "GB": "UK"}


# ------------------------------------------------------------------ helpers

def cn(code: str) -> str:
    """Country name as used mid-sentence ("the Netherlands")."""
    return THE.get(code, n(code))


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def pct(v: float) -> str:
    return f"{v:.0f}%" if abs(v) >= 9.95 else f"{v:.1f}%"


def num(v: float) -> str:
    return f"{v:,.0f}"


def times(r: float) -> str:
    return f"{r:.0f} times" if r >= 9.5 else f"{r:.1f} times"


def growth(a: float, b: float) -> str:
    """'+23%' / '−6%' style change."""
    p = 100 * (b / a - 1)
    return f"+{p:.0f}%" if p >= 0 else f"−{abs(p):.0f}%"


def flag(o: dict | None) -> str:
    return (o or {}).get("flag") or ""


def reliable(o: dict) -> bool:
    return not any(ch in flag(o) for ch in BAD_FLAGS)


def broken(s: dict, a: str, b: str) -> bool:
    """A break-in-series flag on any observation after a and up to b."""
    return any(flag(s[t]).startswith("b") for t in s if a < t <= b)


def code(c: str) -> str:
    return ALIASES.get(c, c)


def ind_link(iid: str, geos=()) -> str:
    return f"pages/indicators.html?id={iid}" + (f"&geo={','.join(geos)}" if geos else "")


def explore_link(dataset: str, **filters) -> str:
    from urllib.parse import quote
    q = [f"dataset={dataset}"]
    for k, v in filters.items():
        if k == "open":
            q.append(f"open={quote(v)}")
        else:
            for x in (v if isinstance(v, (list, tuple)) else [v]):
                q.append(f"f.{k}={quote(x)}")
    return "pages/explore.html?" + "&".join(q)


SOURCE_SHORT = [("eurostat-", "Eurostat"), ("cedefop-", "Cedefop"), ("erasmus-", "European Commission (Erasmus+)"),
                ("fr-dares", "DARES (France)"), ("no-ssb", "Statistics Norway"), ("ch-bfs", "Swiss Federal Statistical Office"),
                ("uk-dfe", "Department for Education (England)"), ("fi-statfin", "Statistics Finland"),
                ("nl-duo", "DUO (Netherlands)"), ("ie-cso", "CSO Ireland"), ("oecd-", "OECD"), ("uis-", "UNESCO UIS")]


def src(iid: str) -> str:
    return next((s for p, s in SOURCE_SHORT if iid.startswith(p)), ind(iid)["provenance"]["publisher"])


class Facts:
    def __init__(self):
        self.items: dict[str, dict] = {}
        self.rejected: list[str] = []

    def add(self, id, text, highlight, kind, countries, link, source, weight=1):
        text = " ".join(text.split())
        why = None
        if id in self.items:
            why = "duplicate id"
        elif highlight not in text:
            why = "highlight not in text"
        elif len(text) > MAX_LEN:
            why = f"{len(text)} characters"
        elif kind not in KINDS:
            why = f"unknown kind {kind}"
        if why:
            self.rejected.append(f"{id}: {why} — {text}")
            return
        self.items[id] = {"id": id, "text": text, "highlight": highlight, "kind": kind,
                          "countries": sorted({code(c) for c in countries}), "link": link,
                          "source": source, "weight": max(1, min(3, int(weight)))}


def cross_section(iid: str, dims=None, geos=EEA, min_n: int = 12, avoid=()):
    """Latest year with broad coverage → {geo: obs} (reliable values only), year."""
    by_year = collections.defaultdict(dict)
    for o in obs(ind(iid), dims):
        if o["geo"] in geos and o.get("value") is not None:
            by_year[o["time"]][o["geo"]] = o
    if not by_year:
        return {}, None
    top = max(len(v) for v in by_year.values())
    ok = [y for y, v in by_year.items() if len(v) >= max(min_n, 0.6 * top) and y not in avoid]
    if not ok:
        return {}, None
    y = max(ok)
    rows = {g: o for g, o in by_year[y].items() if reliable(o)}
    return (rows, y) if len(rows) >= min_n else ({}, None)


def extremes(rows: dict):
    """Highest and lowest countries (ties listed, at most two each)."""
    vals = sorted(rows.items(), key=lambda kv: (-kv[1]["value"], kv[0]))
    hv, lv = vals[0][1]["value"], vals[-1][1]["value"]
    hi = sorted(g for g, o in rows.items() if o["value"] == hv)
    lo = sorted(g for g, o in rows.items() if o["value"] == lv)
    if len(hi) > 2 or len(lo) > 2 or hv == lv:
        return None
    return hi, hv, lo, lv


# ------------------------------------------------------------------ 1. extremes per key indicator

# (indicator, template, highlight, kind, weight, value formatter).  Placeholders:
# {hi} {lo} country names, {Hi} capitalised, {vh} {vl} values, {r} "N times", {year}.
# Templates using {r} are only used when the ratio is at least 2.
SPREADS = [
    ("eurostat-tps00215", "In {hi}, {vh} of recent VET graduates had work-based learning during their programme; in {lo}, only {vl} ({year}).", "vh", "contrast", 3, pct),
    ("eurostat-edat_lfse_24-vet", "{vh} of recent VET graduates in {hi} are in work, against {vl} in {lo} ({year}).", "vh", "contrast", 2, pct),
    ("cedefop-kivet-1010", "{vh} of upper-secondary students in {hi} are in vocational programmes; in {lo}, just {vl} ({year}).", "vh", "contrast", 2, pct),
    ("cedefop-kivet-1070", "{vh} of girls in upper-secondary education in {hi} are in a vocational programme; in {lo}, only {vl} ({year}).", "vl", "contrast", 2, pct),
    ("cedefop-kivet-1050", "Adults in {hi} are {r} as likely as adults in {lo} to have taken part in learning in the last four weeks: {vh} against {vl} ({year}).", "r", "contrast", 2, pct),
    ("cedefop-kivet-1060", "{vh} of enterprises in {hi} provided training for their staff in {year}; in {lo}, {vl}.", "vh", "contrast", 1, pct),
    ("cedefop-kivet-1030", "{vh} of staff in enterprises in {hi} took part in employer-sponsored training courses in {year}; in {lo}, {vl}.", "vh", "contrast", 1, pct),
    ("cedefop-kivet-1080", "{vh} of 18–24-year-olds with a vocational qualification in {hi} are still in education or training; in {lo}, {vl} ({year}).", "vh", "contrast", 2, pct),
    ("cedefop-kivet-2010", "{Hi} spends {vh} of GDP on initial VET, {r} the share in {lo} ({vl}, {year}).", "r", "contrast", 2, lambda v: f"{v:.2f}%"),
    ("cedefop-kivet-2025", "Public spending per initial-VET student is {r} higher in {hi} than in {lo} ({year}, adjusted for price levels).", "r", "contrast", 3, lambda v: f"{v:.1f}"),
    ("cedefop-kivet-2040", "Initial-VET students in {hi} learn {vh} foreign languages on average; in {lo}, {vl} ({year}).", "vl", "contrast", 2, lambda v: f"{v:.1f}"),
    ("cedefop-kivet-2050", "{vh} of upper-secondary VET graduates in {hi} trained in a STEM field, against {vl} in {lo} ({year}).", "vh", "contrast", 1, pct),
    ("cedefop-kivet-3030", "{vh} of 15–29-year-olds in {hi} are neither in work nor in education or training, {r} the rate in {lo} ({vl}, {year}).", "r", "contrast", 1, pct),
    ("cedefop-kivet-3010", "{vh} of 18–24-year-olds in {hi} left education and training early, against {vl} in {lo} ({year}).", "vh", "contrast", 1, pct),
    ("eurostat-trng_cvt_34s", "{vh} of enterprises in {hi} train apprentices or other initial-VET learners; in {lo}, only {vl} ({year}).", "vh", "contrast", 3, pct),
]


def spreads(F: Facts):
    for iid, tpl, hl, kind, w, fmt in SPREADS:
        rows, year = cross_section(iid)
        if not rows:
            continue
        ex = extremes(rows)
        if not ex:
            continue
        hi, hv, lo, lv = ex
        if "{r}" in tpl and (lv <= 0 or hv / lv < 2):
            continue
        vals = {"hi": join([cn(g) for g in hi]), "lo": join([cn(g) for g in lo]), "vh": fmt(hv), "vl": fmt(lv),
                "year": year, "r": times(hv / lv) if lv > 0 else ""}
        vals["Hi"] = cap(vals["hi"])
        text = cap(tpl.format(**vals))
        F.add(f"spread-{iid}", text, vals[hl], kind, hi + lo, ind_link(iid, hi + lo), src(iid), w)

    # VET employment premium: one country far ahead, another where VET graduates do worse.
    iid = "cedefop-kivet-2090a"
    rows, year = cross_section(iid)
    ex = rows and extremes(rows)
    if ex and ex[1] > 0 and ex[3] < 0:
        hi, hv, lo, lv = ex
        hl = f"{hv:.1f} points"
        F.add("spread-vet-premium",
              f"Recent VET graduates in {join([cn(g) for g in hi])} are {hl} more likely to be employed than general-education "
              f"graduates; in {join([cn(g) for g in lo])}, {abs(lv):.1f} points less likely ({year}).",
              hl, "outcome", hi + lo, ind_link(iid, hi + lo), src(iid), 3)


# ------------------------------------------------------------------ 2. EU targets

# First year of monitoring after the 2020 Council Recommendation on VET (and of Eurostat's
# work-based learning series); changes are measured from here.
BASELINE = "2021"


def eu_targets(F: Facts):
    # topic, verb (past), qualifier for "the share of recent VET graduates …", key
    labels = {"eurostat-tps00215": ("work-based learning", "had work-based learning", "with work-based learning", "wbl"),
              "eurostat-edat_lfse_24-vet": ("employment", "were in work", "in work", "emp")}
    p1 = lambda v: f"{v:.1f}%"
    for iid, (topic, verb, qual, key) in labels.items():
        d = ind(iid)
        t = d.get("target")
        if not t:
            continue
        target = t["value"]
        eu = series(iid, "EU27")
        if not eu:
            continue
        year = max(eu)
        L = {g: o for g, o in latest(iid, min_year=year, geos=EU27).items()}
        if len(L) < 15:
            continue
        ev = eu[year]["value"]
        met = sorted(g for g in L if L[g]["value"] >= target)
        hl = f"{len(met)} of {len(L)}"
        F.add(f"target-{key}-met",
              f"In {year}, {hl} EU countries with data met the EU target of {target}% for recent VET graduates' {topic}; "
              f"the EU as a whole reached {p1(ev)}.",
              hl, "record", [], ind_link(iid), src(iid), 2)
        if ev >= target:
            F.add(f"target-{key}-eu",
                  f"The EU beat its {target}% target: {p1(ev)} of recent VET graduates {verb} in {year}.",
                  p1(ev), "record", ["EU27"], ind_link(iid), src(iid), 1)
        else:
            F.add(f"target-{key}-eu",
                  f"The EU missed its {target}% target: {p1(ev)} of recent VET graduates {verb} in {year}.",
                  p1(ev), "outcome", ["EU27"], ind_link(iid), src(iid), 2)
        R = {g: o for g, o in L.items() if reliable(o)}
        if len(R) < 10:
            continue
        lo = min(R, key=lambda g: (R[g]["value"], g))
        hi = max(R, key=lambda g: (R[g]["value"], g))
        if R[lo]["value"] < target:
            F.add(f"target-{key}-furthest",
                  f"{cap(cn(lo))} is furthest from the EU's {target}% {topic} target: {p1(R[lo]['value'])} of recent VET graduates {verb} in {year}.",
                  p1(R[lo]["value"]), "record", [lo], ind_link(iid, [lo]), src(iid), 2)
        if R[hi]["value"] >= target:
            F.add(f"target-{key}-top",
                  f"{cap(cn(hi))} leads the EU: {p1(R[hi]['value'])} of its recent VET graduates {verb} in {year}, against an EU target of {target}%.",
                  p1(R[hi]["value"]), "record", [hi], ind_link(iid, [hi]), src(iid), 1)
        # Largest change since the baseline year, without breaks or low reliability.
        first = BASELINE if BASELINE in eu else min(eu)
        ch = []
        for g in L:
            s = series(iid, g)
            if first in s and year in s and not broken(s, first, year) and reliable(s[first]) and reliable(s[year]):
                ch.append((s[year]["value"] - s[first]["value"], g, s[first]["value"], s[year]["value"]))
        if len(ch) >= 10:
            ch.sort()
            dv, g, a, b = ch[-1]
            if dv >= 5:
                hl = f"{dv:.1f} points"
                F.add(f"target-{key}-gain",
                      f"{cap(cn(g))} raised the share of recent VET graduates {qual} by {hl} between {first} and {year}, "
                      f"to {p1(b)} — the largest gain in the EU.",
                      hl, "trend", [g], ind_link(iid, [g]), src(iid), 2)
            dv, g, a, b = ch[0]
            if dv <= -3:
                hl = f"{abs(dv):.1f} points"
                F.add(f"target-{key}-fall",
                      f"The share of recent VET graduates {qual} in {cn(g)} fell by {hl} between {first} and {year}, to {p1(b)} — the largest fall in the EU.",
                      hl, "trend", [g], ind_link(iid, [g]), src(iid), 1)


# ------------------------------------------------------------------ 3. VET vs general, gender

def vet_vs_general(F: Facts):
    v, gen = "eurostat-edat_lfse_24-vet", "eurostat-edat_lfse_24-general"
    V, year = cross_section(v)
    if not V:
        return
    G = {g: o for g, o in latest(gen, min_year=year).items() if o["time"] == year and reliable(o)}
    both = sorted(g for g in V if g in G)
    if len(both) >= 15:
        ahead = [g for g in both if V[g]["value"] > G[g]["value"]]
        hl = f"{len(ahead)} of {len(both)}"
        F.add("vet-vs-general-count",
              f"In {hl} European countries, recent VET graduates are more likely to be in work than recent general-education graduates ({year}).",
              hl, "outcome", [], ind_link(v), src(v), 2)
        behind = sorted((V[g]["value"] - G[g]["value"], g) for g in both if V[g]["value"] < G[g]["value"])
        if behind:
            dv, g = behind[0]
            F.add("vet-vs-general-behind",
                  f"{cap(cn(g))} is an exception: recent general-education graduates are {abs(dv):.1f} points more likely to be in work than VET graduates ({year}).",
                  f"{abs(dv):.1f} points", "outcome", [g], ind_link(gen, [g]), src(v), 2)
    # EU-level gender gap: VET vs general
    try:
        last = max(y for y in series(v, "EU27") if y in series(gen, "EU27"))
        f_v, m_v = series(v, "EU27", {"sex": "F"})[last]["value"], series(v, "EU27", {"sex": "M"})[last]["value"]
        f_g, m_g = series(gen, "EU27", {"sex": "F"})[last]["value"], series(gen, "EU27", {"sex": "M"})[last]["value"]
        if m_v > f_v and m_g > f_g:
            hl = f"{m_v - f_v:.1f} points"
            F.add("gender-eu-vet-employment",
                  f"Across the EU, young men with a recent VET qualification are {hl} more likely to be in work than young women "
                  f"({last}), against {abs(m_g - f_g):.1f} points after general education.",
                  hl, "contrast", ["EU27"], ind_link(v), src(v), 1)
    except (KeyError, ValueError):
        pass
    # Country gender gaps in VET graduate employment
    Fm, yf = cross_section(v, {"sex": "F"})
    Mm, ym = cross_section(v, {"sex": "M"})
    if Fm and yf == ym:
        gaps = sorted((Mm[g]["value"] - Fm[g]["value"], g) for g in Fm if g in Mm)
        if len(gaps) >= 12:
            dv, g = gaps[-1]
            if dv >= 10:
                hl = f"{dv:.1f} points"
                F.add("gender-vet-employment-max",
                      f"In {cn(g)}, young men with a recent VET qualification are {hl} more likely to be in work than young women — the widest gap in Europe ({yf}).",
                      hl, "contrast", [g], ind_link(v, [g]) + "&dim_sex=F", src(v), 3)
            dv, g = gaps[0]
            if dv <= -2:
                hl = f"{abs(dv):.1f} points"
                F.add("gender-vet-employment-women",
                      f"In {cn(g)}, young women with a recent VET qualification are {hl} more likely to be in work than young men ({yf}).",
                      hl, "contrast", [g], ind_link(v, [g]) + "&dim_sex=F", src(v), 2)
    # Work-based learning by sex, EU
    w = "eurostat-tps00215"
    try:
        e = series(w, "EU27")
        y = max(e)
        fw, mw = series(w, "EU27", {"sex": "F"})[y]["value"], series(w, "EU27", {"sex": "M"})[y]["value"]
        if abs(fw - mw) >= 2:
            more, less = ("women", "men") if fw > mw else ("men", "women")
            hl = f"{max(fw, mw):.1f}%"
            F.add("gender-eu-wbl",
                  f"Work-based learning is more common for {more}: {hl} of recent EU VET graduates who are {more} had it in {y}, against {min(fw, mw):.1f}% of {less}.",
                  hl, "contrast", ["EU27"], ind_link(w), src(w), 1)
    except (KeyError, ValueError):
        pass


# ------------------------------------------------------------------ 4. national trends (within-country only)

def annual(iid: str, dims=None, month: str | None = None) -> dict:
    """{year: obs}; monthly series → the given month; partial years dropped."""
    d = ind(iid)
    partial = {k for k, v in (d.get("flags") or {}).items() if "partial" in v.lower()}
    out = {}
    for o in obs(d, dims):
        t = o["time"]
        if month:
            if not t.endswith(f"-{month}"):
                continue
            t = t[:4]
        elif "-" in t:
            continue
        if flag(o) in partial:
            continue
        out[t] = o
    return out


# (indicator, dims, month, base year, what (plural noun phrase), country, how to describe the year)
NATIONAL = [
    ("fr-dares-apprentices-stock", None, "12", "2017", "apprentices under contract", "FR", "December {y}"),
    ("no-ssb-apprentices", None, None, "2017", "apprentices", "NO", "{y}"),
    ("no-ssb-new-apprentices", None, None, "2017", "new apprentices", "NO", "{y}"),
    ("no-ssb-trade-certificates", None, None, "2017", "trade and journeyman examinations taken", "NO", "{y}"),
    ("ch-bfs-entrants-vet", {"form": "DUAL"}, None, "2017", "entrants to dual VET", "CH", "{y}"),
    ("uk-dfe-apprenticeship-starts", None, None, "2017", "apprenticeship starts", "UK", "{y}/{y1}"),
    ("uk-dfe-apprenticeship-achievements", None, None, "2017", "apprenticeship achievements", "UK", "{y}/{y1}"),
    ("fi-statfin-apprenticeship-students", None, None, "2019", "vocational students with apprenticeship periods", "FI", "{y}"),
    ("nl-duo-bbl-students", None, None, "2021", "students in work-based MBO (BBL)", "NL", "{y}"),
    ("ie-cso-qualified-apprentices", None, None, "2010", "apprentices qualifying", "IE", "{y}"),
]


def where(c: str) -> str:
    return "England" if c == "UK" else cn(c)


def national(F: Facts):
    for iid, dims, month, base, what, c, ylab in NATIONAL:
        try:
            s = annual(iid, dims, month)
        except FileNotFoundError:
            continue
        ys = sorted(s)
        if base not in s or len(ys) < 3:
            continue
        last = ys[-1]
        if last <= base or broken(s, base, last):
            continue
        a, b = s[base]["value"], s[last]["value"]
        lab = lambda y: ylab.format(y=y, y1=str(int(y) + 1)[2:])
        place = where(c)
        r = b / a
        link = ind_link(iid) + ("".join(f"&dim_{k}={v}" for k, v in (dims or {}).items()))
        if r >= 1.8:
            hl = f"{r:.1f}-fold"
            text = f"{cap(what)} in {place} grew {hl} between {lab(base)} and {lab(last)}, to {num(b)}."
            F.add(f"trend-{iid}", text, hl, "trend", [c], link, src(iid), 3)
        elif abs(r - 1) >= 0.05:
            hl = growth(a, b)
            text = f"{cap(what)} in {place}: {hl} between {lab(base)} and {lab(last)}, from {num(a)} to {num(b)}."
            F.add(f"trend-{iid}", text, hl, "trend", [c], link, src(iid), 2 if abs(r - 1) >= 0.15 else 1)
        vals = [s[y]["value"] for y in ys]
        # Rebound from a low point inside the series
        lo_y = min(ys, key=lambda y: (s[y]["value"], y))
        if r < 1.8 and ys[0] < lo_y < last and b / s[lo_y]["value"] >= 1.8 and not broken(s, lo_y, last):
            hl = f"{b / s[lo_y]['value']:.1f}-fold"
            F.add(f"rebound-{iid}",
                  f"{cap(what)} in {place} rose {hl} from a low of {num(s[lo_y]['value'])} in {lab(lo_y)} to {num(b)} in {lab(last)}.",
                  hl, "trend", [c], link, src(iid), 2)
        # Record high
        if b == max(vals) and len(ys) >= 8 and b > s[ys[-2]]["value"]:
            hl = num(b)
            F.add(f"record-{iid}",
                  f"{cap(what)} in {place} reached {hl} in {lab(last)}, the highest since the series began in {lab(ys[0])}.",
                  hl, "record", [c], link, src(iid), 2)
        # First fall after a run of growth
        prev = s[ys[-2]]["value"]
        if b < prev:
            falls = [ys[i] for i in range(1, len(ys) - 1) if s[ys[i]]["value"] < s[ys[i - 1]]["value"]]
            if not falls or falls[-1] <= str(int(last) - 4):
                since = f"the first annual fall since {lab(falls[-1])}" if falls else "the first annual fall in the series"
                hl = growth(prev, b).lstrip("−")
                F.add(f"turn-{iid}",
                      f"{cap(what)} in {place} fell {hl} in the year to {lab(last)}, to {num(b)} — {since}.",
                      hl, "trend", [c], link, src(iid), 2)

    # France: share of apprentices preparing a higher-education diploma
    try:
        tot = annual("fr-dares-apprentices-stock", None, "12")
        he = annual("fr-dares-apprentices-stock", {"scope": "HIGHER"}, "12")
        y = max(set(tot) & set(he))
        b0 = "2017"
        if b0 in tot and b0 in he:
            s1, s0 = 100 * he[y]["value"] / tot[y]["value"], 100 * he[b0]["value"] / tot[b0]["value"]
            hl = f"{s1:.0f}%"
            F.add("fr-higher-education-share",
                  f"{hl} of France's apprentices now prepare a higher-education diploma (end of {y}), up from {s0:.0f}% at the end of {b0}.",
                  hl, "trend", ["FR"], ind_link("fr-dares-apprentices-stock") + "&dim_scope=HIGHER", src("fr-dares-apprentices-stock"), 3)
    except (KeyError, ValueError, FileNotFoundError):
        pass

    # Switzerland: share of initial-VET learners in dual (company-based) training
    try:
        tot = annual("ch-bfs-learners-vet-form")
        dual = annual("ch-bfs-learners-vet-form", {"form": "DUAL"})
        y = max(set(tot) & set(dual))
        sh = 100 * dual[y]["value"] / tot[y]["value"]
        if sh >= 50:
            hl = f"{sh:.0f}%"
            F.add("ch-dual-share",
                  f"In Switzerland, {hl} of learners in initial VET train in a company as well as at school — only a minority are in full-time VET schools ({y}).",
                  hl, "design", ["CH"], ind_link("ch-bfs-learners-vet-form"), src("ch-bfs-learners-vet-form"), 2)
    except (KeyError, ValueError, FileNotFoundError):
        pass

    # Gender shares within national series
    for iid, fdims, tdims, what, c in (
            ("ie-cso-qualified-apprentices", {"sex": "2"}, None, "apprentices who qualified", "IE"),
            ("no-ssb-apprentices", {"sex": "2"}, None, "apprentices", "NO"),
            ("ch-bfs-entrants-vet", {"form": "DUAL", "sex": "F"}, {"form": "DUAL"}, "entrants to dual VET", "CH")):
        try:
            fs, ts = annual(iid, fdims), annual(iid, tdims)
            y = max(set(fs) & set(ts))
            fv, tv = fs[y]["value"], ts[y]["value"]
        except (KeyError, ValueError, FileNotFoundError):
            continue
        sh = 100 * fv / tv
        if sh < 20:
            hl = f"{num(fv)} of the {num(tv)}"
            F.add(f"gender-{iid}", f"Only {hl} {what} in {where(c)} in {y} were women.",
                  hl, "contrast", [c], ind_link(iid), src(iid), 3)
        elif sh < 45:
            hl = f"{sh:.0f}%"
            F.add(f"gender-{iid}", f"Women make up only {hl} of {what} in {where(c)} ({y}).",
                  hl, "contrast", [c], ind_link(iid), src(iid), 2)

    # Ireland: employment of qualified apprentices two years on (cohorts)
    iid = "ie-cso-apprentice-employment-rate"
    try:
        s = annual(iid)
        ys = sorted(s)
        a, b = s[ys[0]]["value"], s[ys[-1]]["value"]
        if b - a >= 10:
            hl = f"{b:.0f}%"
            F.add("ie-apprentice-employment",
                  f"Two years after qualifying, {hl} of Irish apprentices who finished in {ys[-1]} were in work — against {a:.0f}% of those who finished in {ys[0]}.",
                  hl, "outcome", ["IE"], ind_link(iid), src(iid), 2)
    except (KeyError, ValueError, FileNotFoundError, IndexError):
        pass


# ------------------------------------------------------------------ 5. scheme design (Cedefop coded answers)

def has(r, k, v):
    x = r.get(k)
    return v in (x if isinstance(x, list) else [x])


def only(r, k, v):
    """The record's answer to k is v alone (ignoring 'Other')."""
    x = r.get(k)
    xs = [y for y in (x if isinstance(x, list) else [x]) if y and y != "Other"]
    return xs == [v]


def place(r) -> str:
    return r["country"].split(" — ")[-1]


# (field, value, template, weight, mode)
#   mode "count":     {k} schemes with that answer (among other answers), of {n} schemes answering the question;
#   mode "exclusive": {k} schemes giving that answer alone (ignoring "Other");
#   mode "rare":      at most three schemes, each giving that answer alone, named in {who};
#                     {is}/{are}-style choices are written {sg|pl}.
#   {m:<field>=<value>} counts the schemes with another answer ("all" when every scheme has it).
SCHEME = [
    ("q_typical_age", "Over 24", "In {k} of {n} European apprenticeship schemes many apprentices are over 24 — apprenticeship is not only for school-leavers.", 3, "count"),
    ("q_learner_status", "Employee", "Cedefop codes apprentices as employees in only {k} of {n} schemes; in {m:q_learner_status=Specific apprentice status} they have a specific apprentice status.", 2, "count"),
    ("q_learner_status", "Student", "In {k} of {n} apprenticeship schemes the apprentice is legally only a student, not an employee.", 2, "exclusive"),
    ("q_qualification_route", "Only through apprenticeship", "In only {k} of {n} schemes is apprenticeship the sole route to the qualification; elsewhere a school route leads to the same certificate.", 2, "count"),
    ("q_access_to_he", "No", "In {k} of {n} schemes the apprenticeship qualification does not give direct access to higher education.", 1, "count"),
    ("q_introduced", "After 2012", "{k} of {n} apprenticeship schemes in Europe were introduced after 2012; {m:q_introduced=Before 2000} date from before 2000.", 2, "count"),
    ("q_min_workplace_share", "50% or more", "In {k} of {n} schemes apprentices must spend at least half of their training time at the workplace.", 1, "count"),
    ("q_training_vs_work_time", "Yes", "Only {k} of {n} schemes legally distinguish an apprentice's training time from productive work time.", 2, "count"),
    ("q_sanctions", "Yes", "In {k} of {n} schemes companies can be sanctioned if they do not train apprentices properly.", 1, "count"),
    ("q_pay_covers_school", "Yes", "In {k} of {n} schemes apprentices are also paid for their time at school; in {m:q_pay_covers_school=No, company time only} only company time is paid.", 2, "count"),
    ("q_wage_setting", "By law", "Apprentice pay is set by law in {k} of {n} schemes, and by sectoral collective agreements in {m:q_wage_setting=Sectoral agreements}.", 1, "count"),
    ("q_quality_assurance", "Impact or cost–benefit evaluation", "Only {k} of {n} apprenticeship schemes are checked with impact or cost–benefit evaluations, though {m:q_quality_assurance=Monitoring during training} monitor training as it happens.", 2, "count"),
    ("q_contract_type", "Formal agreement, not a contract", "In {k} of {n} schemes apprentices sign only a training agreement, not an employment or apprenticeship contract.", 2, "exclusive"),
    ("q_age_limits", "Minimum and maximum", "{k} of {n} apprenticeship schemes set a maximum age in law as well as a minimum.", 1, "count"),
    ("q_pay_funded_by", "State", "The state helps pay apprentices in {k} of {n} schemes; employers pay them in {m:q_pay_funded_by=Employers}.", 1, "count"),
    ("q_share_of_vet", "Over 60%", "Only {k} of {n} apprenticeship schemes enrol more than 60% of their country's VET learners at that level.", 2, "count"),
    ("q_min_workplace_share", "No minimum", "Only {who} {sets|set} no minimum share of time at the workplace.", 2, "rare"),
    ("q_alternation_form", "School years, then workplace", "Only in {who} do apprentices spend one or two years at school first, then move to the workplace.", 2, "rare"),
    ("q_financial_incentives", "None", "Only {who} {offers|offer} companies no financial incentive to take apprentices.", 3, "rare"),
    ("q_written_arrangement", "No", "Only {who} {requires|require} no written contract or agreement for apprentices.", 3, "rare"),
    ("q_origin", "Created from scratch", "Only {k} schemes were built from scratch: {who}.", 2, "rare"),
    ("q_alternation_compulsory", "No", "Alternating between school and company is not compulsory in {who}.", 2, "rare"),
    ("q_wage_setting", "Cross-sector agreements", "Only {who} {sets|set} apprentice pay through cross-sector collective agreements.", 2, "rare"),
]


def who(recs, R, bare=False) -> str:
    """'the schemes in Cyprus and Portugal', naming the scheme where a country has several."""
    per = collections.Counter(place(r) for r in R)
    parts = [place(r) if per[place(r)] == 1 else f"{place(r)}'s {r['name_en']}" for r in recs]
    if bare:
        return join(parts)
    if all(per[place(r)] == 1 for r in recs):
        return ("the scheme in " if len(recs) == 1 else "the schemes in ") + join(parts)
    return join(parts)


def schemes(F: Facts):
    R = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")
    if len(R) < 10:
        return
    for fld, val, tpl, w, mode in SCHEME:
        answered = [r for r in R if r.get(fld)]
        N = len(answered)
        test = only if mode in ("exclusive", "rare") else has
        recs = sorted([r for r in answered if test(r, fld, val)], key=lambda r: (place(r), r["id"]))
        k = len(recs)
        if not k:
            continue
        link = f"pages/compare.html?q={fld}"
        cs = [r["country_code"] for r in recs]
        sid = re.sub(r"[^a-z0-9]+", "-", f"{fld[2:]}-{val}".lower()).strip("-")
        if mode == "rare":
            # every scheme with this answer must give it alone, otherwise "only" would mislead
            if k > 3 or len([r for r in R if has(r, fld, val)]) != k:
                continue
            text = re.sub(r"\{(\w+)\|(\w+)\}", lambda m: m.group(1) if k == 1 else m.group(2), tpl)
            text = text.replace("{who}", who(recs, R, bare="{k}" in tpl)).replace("{k}", str(k))
            if k == 1:
                link = explore_link("apprenticeship-schemes", open=recs[0]["id"])
            hl = f"{k} schemes" if "{k}" in tpl else who(recs, R, bare=True)
            F.add(f"scheme-{sid}", cap(text), hl, "design", cs, link, "Cedefop", w)
        else:
            if k < 2 or k > N - 2:
                continue

            def m(match):
                f2, v2 = match.group(1).split("=", 1)
                c2 = sum(1 for r in answered if has(r, f2, v2))
                return "all" if c2 == N else str(c2)
            text = re.sub(r"\{m:([^}]+)\}", m, tpl).format(k=k, n=N)
            hl = f"{k} of {N}"
            F.add(f"scheme-{sid}", text, hl, "design", cs if k <= 8 else [], link, "Cedefop", w)


# ------------------------------------------------------------------ 6. qualification levels

def eqf(r):
    lv = [l for l in r.get("eqf_level", []) if l.startswith("EQF")]
    return int(lv[0].split()[1]) if len(lv) == 1 else None


def qualifications(F: Facts):
    N = read_json(PUBLISHED / "nqf-qualification-levels" / "records.json")
    A = [r for r in N if r.get("apprenticeship_or_craft") == "Yes" and eqf(r)]
    if len(A) < 10:
        return
    # Master craftsperson levels (same words as insights.master_craft_levels)
    words = ("master craft", "meister", "mastership", "maîtrise", "master craftsman", "master craftsperson")
    best = {}
    for r in A:
        t = r["qualification_type"].lower()
        if any(w in t for w in words) and "agricult" not in t:
            c = r["country_code"]
            best[c] = max(best.get(c, 0), eqf(r))
    if len(best) >= 4:
        top, bot = max(best.values()), min(best.values())
        if top - bot >= 2:
            hi = sorted(c for c, v in best.items() if v == top)
            lo = sorted(c for c, v in best.items() if v == bot)
            hl = f"EQF {top}"
            F.add("eqf-master-craft",
                  f"The same master craftsperson certificate sits at {hl} in {join([cn(c) for c in hi])}, but at EQF {bot} in {join([cn(c) for c in lo])}.",
                  hl, "qualification", hi + lo, "pages/insights.html#master-craft-levels", "Cedefop", 3)
    # One qualification type spanning several EQF levels within a country
    # Identical names (up to dash style and spacing): the same qualification type placed at several levels.
    norm = lambda s: re.sub(r"\s+", " ", re.sub(r"[–—-]", "-", s.lower())).strip()
    groups = collections.defaultdict(set)
    names = {}
    for r in A:
        k = (r["country_code"], norm(r["qualification_type"]))
        groups[k].add(eqf(r))
        names.setdefault(k, r)
    spans = sorted(((len(v), max(v) - min(v), k) for k, v in groups.items() if len(v) >= 2), key=lambda x: (-x[0], -x[1], x[2]))
    emitted = set()
    for cnt, span, key in spans:
        c = key[0]
        if c in emitted or len(emitted) >= 3:
            continue
        lv = sorted(groups[key])
        r = names[key]
        label = r["qualification_type"].split(" (")[0]
        if len(label) > 60:
            label = re.split(r" [–—-] ", label)[0]
        unit = re.sub(r"^(.*) — (.*)$", r"\1's \2", r["country"])
        hl = f"{cnt} different EQF levels" if cnt > 2 else f"both EQF {lv[0]} and EQF {lv[1]}"
        rng = f", from EQF {lv[0]} to EQF {lv[-1]}" if cnt > 2 else ""
        before = len(F.items)
        F.add(f"eqf-span-{c.lower()}",
              f"In {unit}, one apprenticeship qualification — “{label}” — sits at {hl}{rng}.",
              hl, "qualification", [c],
              explore_link("nqf-qualification-levels", country=r["country"], apprenticeship_or_craft="Yes"), "Cedefop", 2 if cnt > 2 else 1)
        if len(F.items) > before:
            emitted.add(c)
    # Share of apprenticeship/craft qualifications at EQF 5 or above
    high = [r for r in A if eqf(r) >= 5]
    hl = f"{len(high)} of {len(A)}"
    F.add("eqf-high-share",
          f"{hl} apprenticeship and craft qualifications in Europe's national frameworks sit at EQF 5 or above — beyond upper-secondary level.",
          hl, "qualification", [], explore_link("nqf-qualification-levels", apprenticeship_or_craft="Yes"), "Cedefop", 2)


# ------------------------------------------------------------------ 7. Erasmus+ and CoVEs

def vet_pupils() -> dict:
    raw = read_json(sorted((RAW / "eurostat").glob("*educ_uoe_enrs04-ed35.json"))[-1])
    gidx, tidx = raw["dimension"]["geo"]["category"]["index"], raw["dimension"]["time"]["category"]["index"]
    ginv, tinv, nt = {v: k for k, v in gidx.items()}, {v: k for k, v in tidx.items()}, len(tidx)
    out = {}
    for k, v in raw["value"].items():
        k = int(k)
        if tinv[k % nt] == max(tidx):
            out[{"EU27_2020": "EU27"}.get(ginv[k // nt], ginv[k // nt])] = v
    return out


def erasmus(F: Facts):
    g_iid, p_iid = "erasmus-ka1-vet-grant", "erasmus-ka1-vet-projects"
    eu = series(g_iid, "EU27")
    if eu:
        ys = sorted(eu)
        a, b = eu[ys[0]]["value"], eu[ys[-1]]["value"]
        if b / a >= 1.5:
            hl = f"€{b / 1e6:,.0f} million"
            F.add("erasmus-grant-growth",
                  f"Erasmus+ grants for VET mobility reached {hl} in {ys[-1]} — {times(b / a)} the €{a / 1e6:,.0f} million of {ys[0]}.",
                  hl, "mobility", ["EU27"], ind_link(g_iid), src(g_iid), 3)
        pe = series(p_iid, "EU27")
        if pe and ys[0] in pe and ys[-1] in pe:
            hl = num(pe[ys[-1]]["value"])
            F.add("erasmus-projects",
                  f"{hl} Erasmus+ projects sending VET learners and staff abroad were funded in {ys[-1]}, up from {num(pe[ys[0]]['value'])} in {ys[0]}.",
                  hl, "mobility", ["EU27"], ind_link(p_iid), src(p_iid), 1)
        # per pupil
        try:
            pupils = vet_pupils()
            y = ys[-1]
            grant = {o["geo"]: o["value"] for o in obs(ind(g_iid)) if o["time"] == y}
            per = sorted([(grant[g] / pupils[g], g) for g in EU27 if g in grant and pupils.get(g)], reverse=True)
            if len(per) >= 15:
                (hv, hi), (lv, lo) = per[0], per[-1]
                hl = f"€{hv:,.0f}"
                F.add("erasmus-per-pupil",
                      f"Erasmus+ VET mobility grants in {y} came to {hl} per upper-secondary VET pupil in {cn(hi)}, but €{lv:,.0f} in {cn(lo)}.",
                      hl, "mobility", [hi, lo], ind_link(g_iid, [hi, lo]), src(g_iid), 3)
        except (IndexError, KeyError, FileNotFoundError):
            pass
    # Accredited organisations
    O = read_json(PUBLISHED / "erasmus-vet-organisations" / "records.json")
    acc = [r for r in O if r.get("status") == "Accredited"]
    c = collections.Counter(r["country_code"] for r in acc)
    if len(c) >= 2:
        (g1, n1), (g2, n2) = c.most_common(2)
        hl = num(n1)
        F.add("erasmus-accredited-top",
              f"{cap(cn(g1))} has the most Erasmus-accredited VET organisations — {hl}, ahead of {cn(g2)} with {num(n2)}.",
              hl, "mobility", [g1, g2],
              explore_link("erasmus-vet-organisations", country=next(r["country"] for r in acc if r["country_code"] == g1), status="Accredited"),
              "European Commission (Erasmus+)", 1)
        hl = num(len(acc))
        F.add("erasmus-accredited-total",
              f"{hl} schools, companies and other organisations hold an Erasmus accreditation to send VET learners and staff abroad every year.",
              hl, "mobility", [], explore_link("erasmus-vet-organisations", status="Accredited"), "European Commission (Erasmus+)", 1)
    # CoVEs
    C = read_json(PUBLISHED / "cove-projects" / "records.json")
    if len(C) >= 10:
        cc = collections.Counter(code(r["coordinator_country_code"]) for r in C)
        (g1, n1), (g2, n2) = cc.most_common(2)
        if n1 >= 1.5 * n2:
            hl = f"{n1} of the {len(C)}"
            F.add("cove-coordinators",
                  f"{cap(cn(g1))} coordinates {hl} Erasmus+ Centres of Vocational Excellence selected since {min(r['call_year'] for r in C)} — more than any other country.",
                  hl, "mobility", [g1],
                  explore_link("cove-projects", coordinator_country=next(r["coordinator_country"] for r in C if code(r["coordinator_country_code"]) == g1)),
                  "European Commission (Erasmus+)", 3)
        big = max(C, key=lambda r: (r["organisation_count"], r["id"]))
        hl = f"{big['organisation_count']} organisations"
        F.add("cove-largest",
              f"The largest Centre of Vocational Excellence, {big['acronym']}, brings together {hl} from {big['country_count']} countries.",
              hl, "mobility", [code(big["coordinator_country_code"])], explore_link("cove-projects", open=big["id"]),
              "European Commission (Erasmus+)", 1)


# ------------------------------------------------------------------ 8. policies

APP_TITLE = re.compile(r"apprentic|dual|work-based", re.I)


def policies(F: Facts):
    T = read_json(PUBLISHED / "vet-policy-timeline" / "records.json")
    app = [r for r in T if r.get("concerns_apprenticeship") == "Yes"]
    if len(app) < 20:
        return
    # Counted per reporting unit (Belgium's communities report separately).
    c = collections.Counter(r["country"] for r in app)
    (u1, n1), (u2, n2) = c.most_common(2)
    if n1 > n2:
        g1 = next(r["country_code"] for r in app if r["country"] == u1)
        g2 = next(r["country_code"] for r in app if r["country"] == u2)
        hl = str(n1)
        F.add("policy-most",
              f"Cedefop lists {hl} apprenticeship-related VET policies for {u1} since 2015, more than for any other country ({u2}: {n2}).",
              hl, "policy", [g1, g2], explore_link("vet-policy-timeline", country=u1, concerns_apprenticeship="Yes"), "Cedefop & ReferNet", 2)
    disc = [r for r in app if r.get("latest_stage") == "Discontinued"]
    hl = f"{len(disc)} of {len(app)}"
    F.add("policy-discontinued",
          f"Only {hl} apprenticeship-related policies reported to Cedefop since 2015 have been discontinued; most are being implemented or completed.",
          hl, "policy", [], explore_link("vet-policy-timeline", concerns_apprenticeship="Yes", latest_stage="Discontinued"), "Cedefop & ReferNet", 1)
    hl = f"{len(app):,} of {len(T):,}"
    F.add("policy-share",
          f"{hl} national VET policies tracked by Cedefop and ReferNet since 2015 concern apprenticeship or work-based learning.",
          hl, "policy", [], explore_link("vet-policy-timeline", concerns_apprenticeship="Yes"), "Cedefop & ReferNet", 1)
    # Most recent apprenticeship reform per country (title names apprenticeship / dual / work-based learning)
    newest = max(int(r["first_year"]) for r in app if r.get("first_year"))
    by = collections.defaultdict(list)
    for r in app:
        if APP_TITLE.search(r["title"]) and r.get("first_year"):
            by[r["country_code"]].append(r)
    for g, rs in sorted(by.items()):
        r = max(rs, key=lambda r: (r["first_year"], int(r.get("policy_id") or 0)))
        if int(r["first_year"]) < newest - 5:
            continue
        title = r["title"].strip().rstrip(".")
        text = f"Most recent apprenticeship policy Cedefop lists for {cn(g)} (first reported {r['first_year']}): “{title}”."
        F.add(f"policy-latest-{g.lower()}", text, title, "policy", [g],
              explore_link("vet-policy-timeline", open=r["id"]), "Cedefop & ReferNet", 1)


# ------------------------------------------------------------------ 9. financing

def financing(F: Facts):
    R = read_json(PUBLISHED / "financing-instruments" / "records.json")
    dated = [r for r in R if (r.get("year_introduced") or "").isdigit()]
    if len(dated) < 10:
        return
    old = min(dated, key=lambda r: (int(r["year_introduced"]), r["id"]))
    hl = old["year_introduced"]
    F.add("finance-oldest",
          f"The oldest instrument in Cedefop's apprenticeship financing database is {n(old['country_code'])}'s “{old['title']}”, in place since {hl}.",
          hl, "policy", [old["country_code"]], explore_link("financing-instruments", open=old["id"]), "Cedefop", 3)
    funds = [r for r in dated if "Training funds" in r.get("type", [])]
    if funds:
        lev = min(funds, key=lambda r: (int(r["year_introduced"]), r["id"]))
        if lev["id"] != old["id"]:
            hl = lev["year_introduced"]
            F.add("finance-oldest-levy",
                  f"{n(lev['country_code'])}'s “{lev['title']}”, a levy on companies that funds apprenticeship, dates back to {hl}.",
                  hl, "policy", [lev["country_code"]], explore_link("financing-instruments", open=lev["id"]), "Cedefop", 3)
    by = collections.defaultdict(set)
    for r in R:
        for t in r.get("type", []):
            by[r["country_code"]].add(t)
    levy = sorted(c for c, s in by.items() if "Training funds" in s)
    if 2 <= len(levy) <= 8:
        hl = f"{len(levy)} of {len(by)}"
        F.add("finance-levy-countries",
              f"Only {hl} countries studied by Cedefop use levy-financed training funds for apprenticeship: "
              f"{join([{'UK': 'the UK'}.get(c, cn(c)) for c in levy])} (2016–17).",
              hl, "policy", levy, explore_link("financing-instruments", type="Training funds"), "Cedefop", 2)
    cc = collections.Counter(r["country_code"] for r in R)
    (g1, n1), (g2, n2) = cc.most_common(2)
    if n1 > n2:
        hl = f"{n1} instruments"
        F.add("finance-most",
              f"{cap(cn(g1))} has the most apprenticeship financing instruments in Cedefop's database — {hl} of {len(R)} (2016–17).",
              hl, "policy", [g1], explore_link("financing-instruments", country=next(r["country"] for r in R if r["country_code"] == g1)), "Cedefop", 1)


# ------------------------------------------------------------------ build

BUILDERS = [spreads, eu_targets, vet_vs_general, national, schemes, qualifications, erasmus, policies, financing]


def build() -> list[dict]:
    F = Facts()
    failed = []
    for b in BUILDERS:
        try:
            b(F)
        except Exception as e:  # one broken family must not stop the build
            failed.append(f"{b.__name__}: {type(e).__name__}: {e}")
    items = [F.items[k] for k in sorted(F.items)]
    write_json(OUT, {
        "description": "Short facts computed by Apprentix from its published data (pipeline/facts.py). Recomputed on every build.",
        "count": len(items),
        "items": items,
        "rejected": F.rejected,
        "failed": failed,
    })
    return items


if __name__ == "__main__":
    out = build()
    for f in out:
        print(f"[{f['kind']:<13}] w{f['weight']} {f['id']}\n    {f['text']}\n    ★ {f['highlight']}  → {f['link']}  ({f['source']})")
    d = read_json(OUT)
    print(f"\n{len(out)} facts;", dict(collections.Counter(f["kind"] for f in out)))
    for r in d["rejected"]:
        print("REJECTED", r)
    for r in d["failed"]:
        print("FAILED", r)
