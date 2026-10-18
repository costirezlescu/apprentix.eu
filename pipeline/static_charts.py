"""Static SVG charts drawn at build time, so they show without JavaScript, can be indexed and
refresh with the data. Colours come from CSS classes (site.css, "Static charts"), so both themes work.

  ranked_bars(...)      latest value per country, sorted, with the EU-27 marker (indicator pages)
  small_multiples(...)  one small trend per country on a shared scale, EU-27 behind (indicator pages)
  tile_maps(...)        tile maps of the latest value and of growth since the first year (Erasmus+ pages)
  strip_plot(...)       one dot per region, grouped by country (RESET page, country pages)
  glance_tiles(...)     "at a glance" tiles: value, EU value, direction, trend (country pages)

All functions return escaped HTML. Deterministic.
"""

from __future__ import annotations

import math
from html import escape

AGG = {"EU27", "EU28", "EA", "EA19", "EA20"}
# Which way is better, for the chips on country pages. Indicators not listed are shown without a judgement.
HIGHER_BETTER = {"eurostat-edat_lfse_24-vet", "cedefop-kivet-2080a", "cedefop-kivet-2090a", "cedefop-kivet-2066",
                 "cedefop-kivet-1026", "eurostat-trng_cvt_34s", "oecd-emp-rate-upper-secondary",
                 "cedefop-kivet-1050", "cedefop-reset"}
LOWER_BETTER = {"eurostat-tps00215", "cedefop-kivet-3010", "cedefop-kivet-3030"}


def e(v) -> str:
    return escape(str(v if v is not None else ""), quote=True)


def num(v: float, unit: str | None = None) -> str:
    a = abs(v)
    if unit and unit.upper().startswith("EUR") and a >= 1e6:
        return f"€{v / 1e6:.1f}m"
    if a >= 1e5:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:,.0f}"
    return f"{v:.1f}"


def nice_step(raw: float) -> float:
    if raw <= 0:
        return 1
    p = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * p >= raw:
            return m * p
    return 10 * p


def default_obs(ind: dict) -> list[dict]:
    dims = ind.get("dims") or []
    return [o for o in ind["series"] if o.get("value") is not None
            and all((o.get("dims") or {}).get(d["key"], d.get("default")) == d.get("default") for d in dims)]


def by_geo(ind: dict) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for o in default_obs(ind):
        out.setdefault(o["geo"], {})[o["time"]] = o["value"]
    return out


# ---------------------------------------------------------------- ranked bars --

def ranked_bars(ind: dict, names: dict[str, str], highlight: str | None = None) -> str:
    G = by_geo(ind)
    latest = {g: max(s) for g, s in G.items()}
    rows = [(g, s[latest[g]], latest[g]) for g, s in G.items() if g not in AGG]
    if len(rows) < 3:
        return ""
    rows.sort(key=lambda r: -r[1])
    years = [t for _, _, t in rows]
    common = max(set(years), key=years.count)
    eu = G.get("EU27", {}).get(common)
    if eu is not None and eu > max(v for _, v, _ in rows):
        eu = None  # an EU total (a sum, such as euros or projects), not an average: no marker
    unit = ind.get("unit")
    lo = min(0.0, min(v for _, v, _ in rows), eu if eu is not None else 0)
    hi = max(0.0, max(v for _, v, _ in rows), eu if eu is not None else 0)
    W, L, R, rh, bh = 760, 150, 74, 19, 13
    H = 14 + len(rows) * rh + 22
    X = lambda v: L + (W - L - R) * (v - lo) / ((hi - lo) or 1)
    out = [f'<svg class="sc" viewBox="0 0 {W} {H}" role="img" aria-label="{e(ind["title"])}: latest value by country, sorted">']
    step = nice_step((hi - lo) / 5)
    v = math.ceil(lo / step) * step
    while v <= hi + 1e-9:
        x = X(v)
        out.append(f'<line class="sc-grid" x1="{x:.1f}" x2="{x:.1f}" y1="8" y2="{H - 18}"/>'
                   f'<text class="sc-ax" x="{x:.1f}" y="{H - 4}" text-anchor="middle">{e(num(v, unit))}</text>')
        v += step
    for i, (g, val, t) in enumerate(rows):
        y = 10 + i * rh
        x0, x1 = sorted((X(0), X(val)))
        cls = "sc-bar on" if g == highlight else "sc-bar"
        note = "" if t == common else f" ({t})"
        out.append(f'<g><title>{e(names.get(g, g))}: {e(num(val, unit))} {e(unit or "")} in {e(t)}</title>'
                   f'<text class="sc-lab{" on" if g == highlight else ""}" x="{L - 8}" y="{y + 11}" text-anchor="end">{e(names.get(g, g))}</text>'
                   f'<rect class="{cls}" x="{x0:.1f}" y="{y}" width="{max(1.5, x1 - x0):.1f}" height="{bh}" rx="2.5"/>'
                   f'<text class="sc-val" x="{max(x0, x1) + 5:.1f}" y="{y + 11}">{e(num(val, unit))}{e(note)}</text></g>')
    if eu is not None:
        x = X(eu)
        out.append(f'<line class="sc-eu" x1="{x:.1f}" x2="{x:.1f}" y1="4" y2="{H - 18}"/>'
                   f'<text class="sc-eu-lab" x="{x + 4:.1f}" y="{H - 20}">EU-27 {e(num(eu, unit))}</text>')
    out.append("</svg>")
    cap = f"Latest value for each country, {e(common)} unless shown in brackets" + ("; line: EU-27" if eu is not None else "") + "."
    return f'<figure class="sc-fig"><div class="sc-scroll">{"".join(out)}</div><figcaption class="sc-cap">{cap}</figcaption></figure>'


# ---------------------------------------------------------------- small multiples --

def small_multiples(ind: dict, names: dict[str, str]) -> str:
    G = by_geo(ind)
    countries = {g: s for g, s in G.items() if g not in AGG and len(s) >= 3}
    if len(countries) < 4:
        return ""
    times = sorted({t for s in G.values() for t in s})
    if len(times) < 4:
        return ""
    idx = {t: i for i, t in enumerate(times)}
    vals = [v for g, s in G.items() if g in countries or g == "EU27" for v in s.values()]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * .08 or 1
    lo, hi = lo - pad, hi + pad
    unit = ind.get("unit")
    w, h = 150, 54
    X = lambda t: 3 + (w - 6) * idx[t] / (len(times) - 1)
    Y = lambda v: 3 + (h - 6) * (hi - v) / (hi - lo)
    path = lambda s: "".join(f'{"M" if i == 0 else "L"}{X(t):.1f},{Y(s[t]):.1f}' for i, t in enumerate(sorted(s)))
    eu = G.get("EU27")
    cells = []
    for g, s in sorted(countries.items(), key=lambda kv: -kv[1][max(kv[1])]):
        last = max(s)
        first = min(s)
        d = s[last] - s[first]
        svg = (f'<svg class="sc" viewBox="0 0 {w} {h}" aria-hidden="true">'
               + (f'<path class="sc-eu-line" d="{path(eu)}"/>' if eu and len(eu) > 1 else "")
               + f'<path class="sc-line" d="{path(s)}"/><circle class="sc-dot" cx="{X(last):.1f}" cy="{Y(s[last]):.1f}" r="2.6"/></svg>')
        cells.append(f'<li class="sc-sm" title="{e(names.get(g, g))}: {e(num(s[first], unit))} in {e(first)}, {e(num(s[last], unit))} in {e(last)}">'
                     f'<div class="sc-sm-h"><span>{e(names.get(g, g))}</span><b>{e(num(s[last], unit))}</b></div>{svg}'
                     f'<div class="sc-sm-f"><span>{e(first)}–{e(last)}</span><span class="{"up" if d >= 0 else "down"}">{"+" if d >= 0 else "−"}{e(num(abs(d), unit))}</span></div></li>')
    cap = (f"Same scale in every panel ({e(num(lo + pad, unit))} to {e(num(hi - pad, unit))}{' ' + e(unit) if unit and unit != '%' else ''}). "
           + ("Grey line: EU-27. " if eu else "") + "Sorted by the latest value; the change is from each country’s first to its latest year.")
    return f'<figure class="sc-fig"><ul class="sc-sms">{"".join(cells)}</ul><figcaption class="sc-cap">{cap}</figcaption></figure>'


# ---------------------------------------------------------------- tile maps --

def tile_maps(ind: dict, countries: list[dict], link_prefix: str = "../countries/") -> str:
    G = by_geo(ind)
    rows = [c for c in countries if c.get("tile")]
    times = sorted({t for g, s in G.items() if g not in AGG for t in s})
    if len(times) < 2:
        return ""
    last, first = times[-1], times[0]
    unit = ind.get("unit")

    def one(title: str, val, fmt, legend: str) -> str:
        vs = [v for c in rows if (v := val(c["code"])) is not None]
        if not vs:
            return ""
        mx = max(vs)
        S, P = 40, 4
        cols = max(c["tile"][0] for c in rows) + 1
        nrows = max(c["tile"][1] for c in rows) + 1
        out = [f'<svg class="sc sc-tiles" viewBox="0 0 {cols * (S + P)} {nrows * (S + P)}" role="img" aria-label="{e(title)}">']
        for c in sorted(rows, key=lambda c: (c["tile"][1], c["tile"][0])):
            x, y = c["tile"][0] * (S + P), c["tile"][1] * (S + P)
            v = val(c["code"])
            if v is None:
                out.append(f'<g><title>{e(c["name"])}: no data</title><rect class="sc-tile none" x="{x}" y="{y}" width="{S}" height="{S}" rx="4"/>'
                           f'<text class="sc-tile-t none" x="{x + S / 2}" y="{y + S / 2 + 4}" text-anchor="middle">{e(c["code"])}</text></g>')
                continue
            step = min(5, 1 + int(5 * math.sqrt(max(v, 0) / mx))) if mx > 0 else 1
            out.append(f'<a href="{link_prefix}{c["code"].lower()}.html"><title>{e(c["name"])}: {e(fmt(v))}</title>'
                       f'<rect class="sc-tile s{step}" x="{x}" y="{y}" width="{S}" height="{S}" rx="4"/>'
                       f'<text class="sc-tile-t s{step}" x="{x + S / 2}" y="{y + S / 2 + 4}" text-anchor="middle">{e(c["code"])}</text></a>')
        out.append("</svg>")
        return f'<div class="sc-tilebox"><p class="sc-tile-h">{e(title)}</p>{"".join(out)}<p class="sc-cap">{e(legend)} Largest: {e(fmt(mx))}. Grey: no data.</p></div>'

    latest = lambda g: G.get(g, {}).get(last)
    growth = lambda g: (G[g][last] / G[g][first]) if G.get(g, {}).get(first) and G[g].get(last) is not None else None
    a = one(f"{last}", latest, lambda v: f"{num(v, unit)}{'' if (unit or '').upper().startswith('EUR') else ' ' + (unit or '')}".strip(), "Darker: more.")
    b = one(f"Growth, {first} → {last}", growth, lambda v: f"×{v:.1f}", f"Darker: faster growth (ratio of {last} to {first}).")
    if not a:
        return ""
    return f'<div class="sc-tilemaps">{a}{b}</div>'


# ---------------------------------------------------------------- strip plot --

def strip_plot(groups: list[dict], highlight: str | None = None, only: str | None = None) -> str:
    """groups: [{code, name, points: [(label, value)]}], values 0–100."""
    rows = [g for g in groups if g["points"]]
    if only:
        rows = [g for g in rows if g["code"] == only]
    if not rows:
        return ""
    rows.sort(key=lambda g: -max(v for _, v in g["points"]))
    W, L, R, rh = 760, 130, 20, 22
    H = 26 + len(rows) * rh
    X = lambda v: L + (W - L - R) * v / 100
    out = [f'<svg class="sc" viewBox="0 0 {W} {H}" role="img" aria-label="Scores by region">']
    for v in (0, 25, 50, 75, 100):
        out.append(f'<line class="sc-grid" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="14" y2="{H - 4}"/><text class="sc-ax" x="{X(v):.1f}" y="10" text-anchor="middle">{v}</text>')
    for i, g in enumerate(rows):
        y = 26 + i * rh
        vs = [v for _, v in g["points"]]
        on = " on" if g["code"] == highlight else ""
        out.append(f'<text class="sc-lab{on}" x="{L - 10}" y="{y + 4}" text-anchor="end">{e(g["name"])}</text>')
        if len(vs) > 1:
            out.append(f'<line class="sc-range{on}" x1="{X(min(vs)):.1f}" x2="{X(max(vs)):.1f}" y1="{y}" y2="{y}"/>')
        for label, v in g["points"]:
            out.append(f'<circle class="sc-pt{on}" cx="{X(v):.1f}" cy="{y}" r="4.6"><title>{e(label)} ({e(g["name"])}): {v:.1f}</title></circle>')
    out.append("</svg>")
    return f'<div class="sc-scroll">{"".join(out)}</div>'


# ---------------------------------------------------------------- at a glance --

def comparable(unit: str | None) -> bool:
    """Whether a country value can sit beside the EU-27 value: rates, shares, scores, per-head figures."""
    u = (unit or "").lower()
    return u == "%" or u.startswith("%") or any(w in u for w in ("per ", "score", "index", "rate", "pps", "years"))


def glance_tiles(rows: list[dict], code: str, name: str, by_time: dict[str, dict], tile_url) -> str:
    """rows: key_figures rows {ind, obs, eu}; by_time: {indicator id: {(geo, time): obs}}."""
    tiles = []
    for r in rows:
        ind, o, eu = r["ind"], r["obs"], r["eu"]
        unit = ind.get("unit")
        if not comparable(unit):
            eu = None  # counts and money: the EU figure is a total, not comparable with one country
        bt = by_time.get(ind["id"], {})
        mine = sorted((t, x["value"]) for (g, t), x in bt.items() if g == code and x.get("value") is not None)[-8:]
        eus = sorted((t, x["value"]) for (g, t), x in bt.items() if g == "EU27" and x.get("value") is not None)
        eus = [p for p in eus if mine and p[0] >= mine[0][0]] if comparable(unit) else []
        chip = ""
        if eu and eu.get("value") is not None:
            d = o["value"] - eu["value"]
            if ind["id"] in HIGHER_BETTER:
                tone = "good" if d >= 0 else "bad"
            elif ind["id"] in LOWER_BETTER:
                tone = "good" if d <= 0 else "bad"
            else:
                tone = "neutral"
            word = "above" if d > 0 else "below" if d < 0 else "level with"
            pts = "" if d == 0 else (" points" if unit == "%" else "")
            chip = f'<span class="sc-chip {tone}">{e(num(abs(d), unit) + pts + " " if d else "")}{word} EU</span>'
        spark = ""
        if len(mine) >= 2:
            ts = sorted({t for t, _ in mine + eus})
            vs = [v for _, v in mine + eus]
            lo, hi = min(vs), max(vs)
            X = lambda t: 3 + 194 * ts.index(t) / (len(ts) - 1)
            Y = lambda v: 4 + 30 * (hi - v) / ((hi - lo) or 1)
            p = lambda s: "".join(f'{"M" if i == 0 else "L"}{X(t):.1f},{Y(v):.1f}' for i, (t, v) in enumerate(s))
            spark = (f'<svg class="sc sc-spark" viewBox="0 0 200 38" aria-hidden="true">'
                     + (f'<path class="sc-eu-line" d="{p(eus)}"/>' if len(eus) > 1 else "")
                     + f'<path class="sc-line" d="{p(mine)}"/></svg><span class="sc-spark-k">{e(mine[0][0])}–{e(mine[-1][0])}'
                     + (" · grey: EU-27" if len(eus) > 1 else "") + "</span>")
        tiles.append(f"""<li class="sc-glance">
  <a class="sc-glance-t" href="{e(tile_url(ind['id']))}">{e(ind['title'])}</a>
  <span class="sc-glance-v">{e(num(o['value'], unit))}{'<small>%</small>' if unit == '%' else ''}</span>
  <span class="sc-glance-eu">{f"EU-27 {e(num(eu['value'], unit))} · " if eu and eu.get('value') is not None else ""}{e(o['time'])}</span>
  {chip}
  {spark}
</li>""")
    return f'<ul class="sc-glances">{"".join(tiles)}</ul>'
