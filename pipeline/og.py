"""Social link-preview images (Open Graph / Twitter cards) and duel share pages.

  assets/og/site.png                    default card (home, about, anything without its own)
  assets/og/<section>.png               one per section page (indicators, insights, find, duel,
                                        compare, data, ask, explore, play, countries)
  assets/og/country/<code>.png          one per country profile (pages/countries/<code>.html)
  assets/og/indicator/<id>.png          one per indicator page (pages/indicators/<id>.html)
  assets/og/duel/<a>-<b>.png            one per duel share page
  pages/duel/<a>-<b>.html               static share pages for a budgeted set of country pairs:
                                        proper og/twitter meta (crawlers do not run JS), a short
                                        summary and a redirect to the live duel (../duel.html?a=&b=).
                                        Not listed in sitemap.xml (canonical is the live duel).
  data/published/og/duel-pairs.json     which pairs have a share page (used by duel.js "Copy link")

Cards are 1200×630 PNGs drawn with Pillow in the site's light palette and fonts
(Newsreader, Public Sans, IBM Plex Mono — OFL, bundled in pipeline/assets/fonts/).

Deterministic: same data → byte-identical PNGs (no metadata, fixed fonts, no clock),
and files are only rewritten when their bytes change, so weekly PRs do not churn.
Byte-identity across machines also needs the same Pillow build, hence the exact pin in
pipeline/requirements.txt.

Needs data/published/{indicators,duel,insights} — run after duel.build() and
insights.build(). Page renderers reference the image paths below (deterministic), so
they may run before or after this; run this first so a fresh checkout has no broken images.

Run on its own with:  python -m pipeline.og
"""

from __future__ import annotations

import io
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from .common import DATA, INDICATORS, PUBLISHED, REFERENCE, ROOT, read_json

W, H = 1200, 630
S = 2                      # supersampling factor: draw at 2×, downsample (smooth edges)
M = 64                     # outer margin
OG_DIR = ROOT / "assets" / "og"
DUEL_PAGES = ROOT / "pages" / "duel"
PAIRS_JSON = PUBLISHED / "og" / "duel-pairs.json"
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
SOURCE_LINE = "Source: Eurostat, Cedefop · apprentix.eu"

# site.css light theme
C = {
    "ground": "#f6f6f3", "surface": "#ffffff", "sunken": "#ecece7", "ink": "#14181b",
    "muted": "#5c6569", "faint": "#8b9398", "line": "#e1e1db", "line_strong": "#c8c9c1",
    "accent": "#0f6b63", "accent_ink": "#0a4a44", "accent_soft": "#e2f0ee",
    "amber": "#a15c11", "side_a": "#2a78d6", "side_b": "#eb6834",
}

# Image paths (relative to the site root). Pages use these; keep in sync with build().
SECTIONS = ("indicators", "insights", "find", "duel", "compare", "data", "ask", "explore", "play", "countries")


def site_path() -> str:
    return "assets/og/site.png"


def section_path(key: str) -> str:
    return f"assets/og/{key}.png"


def country_path(code: str) -> str:
    return f"assets/og/country/{code.lower()}.png"


def indicator_path(iid: str) -> str:
    return f"assets/og/indicator/{quote(iid)}.png"


def duel_slug(a: str, b: str) -> str:
    return f"{a.lower()}-{b.lower()}"


def duel_path(a: str, b: str) -> str:
    return f"assets/og/duel/{duel_slug(a, b)}.png"


# ---------------------------------------------------------------- duel pairs --

# Every country vs EU-27, plus these peers (neighbours and most-compared systems).
# Written order is the share page's side A / side B. Keep the total ≤ 150.
PEERS = """
AT-FR AT-CH AT-DE AT-CZ AT-SK AT-HU AT-SI AT-IT AT-LI
BE-FR BE-LU BE-NL BE-DE
BG-RO BG-RS BG-MK BG-EL BG-TR
CH-DE CH-FR CH-IT CH-LI
CY-EL CY-MT
CZ-DE CZ-PL CZ-SK
DE-DK DE-NL DE-LU DE-PL DE-FR DE-IT DE-ES DE-UK
DK-SE DK-NO
EE-LV EE-FI
EL-AL EL-MK EL-TR EL-IT
ES-PT ES-FR ES-IT
FI-SE FI-NO
FR-IT FR-LU FR-UK FR-NL
GE-TR GE-UA GE-MD
HR-SI HR-HU HR-RS HR-BA HR-ME
HU-SK HU-RO HU-RS HU-UA HU-SI
IE-UK IE-MT
IS-NO IS-DK
IT-SI IT-MT
LT-LV LT-PL LT-EE
MD-RO MD-UA
ME-RS ME-BA ME-AL ME-XK
MK-RS MK-AL MK-XK
NO-SE
PL-SK PL-UA
PT-FR
RO-RS RO-UA
RS-BA RS-XK
SK-UA
AL-XK
NL-DK UK-NL
""".split()
MAX_PAIRS = 150


def duel_pairs(codes: list[str], eu: str = "EU27") -> list[tuple[str, str]]:
    have = set(codes)
    out: list[tuple[str, str]] = [(c, eu) for c in sorted(codes) if c != eu and eu in have]
    seen = {frozenset(p) for p in out}
    for p in PEERS:
        a, b = p.split("-")
        if a in have and b in have and frozenset((a, b)) not in seen:
            seen.add(frozenset((a, b)))
            out.append((a, b))
    return out[:MAX_PAIRS]


# ---------------------------------------------------------------- fonts --

@lru_cache(maxsize=None)
def font(family: str, size: float, weight: int = 400):
    """family: 'display' (Newsreader), 'body' (Public Sans), 'mono' (IBM Plex Mono). size in 1× px."""
    from PIL import ImageFont
    px = max(1, round(size * S))
    if family == "mono":
        return ImageFont.truetype(str(FONT_DIR / "IBMPlexMono-Medium.ttf"), px)
    if family == "display":
        f = ImageFont.truetype(str(FONT_DIR / "Newsreader-VF.ttf"), px)
        f.set_variation_by_axes([weight, max(6, min(72, size))])   # axes: wght, opsz
        return f
    f = ImageFont.truetype(str(FONT_DIR / "PublicSans-VF.ttf"), px)
    f.set_variation_by_axes([weight])
    return f


def text_w(text: str, f) -> float:
    return f.getlength(text) / S


def wrap(text: str, f, max_w: float) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}" if cur else w
        if text_w(t, f) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    # Hard-break single words that are still too wide.
    out = []
    for ln in lines:
        while text_w(ln, f) > max_w and len(ln) > 1:
            k = len(ln)
            while k > 1 and text_w(ln[:k], f) > max_w:
                k -= 1
            out.append(ln[:k])
            ln = ln[k:]
        out.append(ln)
    return out


def ellipsize(line: str, f, max_w: float) -> str:
    if text_w(line, f) <= max_w:
        return line
    while line and text_w(line.rstrip(" ,;:·—-") + "…", f) > max_w:
        line = line[:-1]
    return line.rstrip(" ,;:·—-") + "…"


def fit(text: str, family: str, weight: int, max_w: float, max_lines: int, sizes, lh: float = 1.12):
    """Largest size whose wrapped text fits in max_lines; else smallest size, truncated."""
    for size in sizes:
        f = font(family, size, weight)
        lines = wrap(text, f, max_w)
        if len(lines) <= max_lines:
            return f, size, lines, size * lh
    size = sizes[-1]
    f = font(family, size, weight)
    lines = wrap(text, f, max_w)
    lines = lines[:max_lines]
    lines[-1] = ellipsize(lines[-1] + " …", f, max_w) if len(lines[-1]) else lines[-1]
    return f, size, lines, size * lh


# ---------------------------------------------------------------- canvas --

class Canvas:
    def __init__(self):
        from PIL import Image, ImageDraw
        self.img = Image.new("RGB", (W * S, H * S), C["ground"])
        self.d = ImageDraw.Draw(self.img)

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=1, r=0):
        box = [round(x0 * S), round(y0 * S), round(x1 * S) - 1, round(y1 * S) - 1]
        if r:
            self.d.rounded_rectangle(box, radius=r * S, fill=fill, outline=outline, width=width * S if outline else 0)
        else:
            self.d.rectangle(box, fill=fill, outline=outline, width=width * S if outline else 0)

    def poly(self, pts, fill):
        self.d.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def line(self, pts, fill, width=2):
        self.d.line([(x * S, y * S) for x, y in pts], fill=fill, width=round(width * S), joint="curve")

    def dot(self, x, y, r, fill):
        self.d.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=fill)

    def text(self, x, y, s, f, fill, anchor="ls"):
        """(x, y) is the baseline-left point by default (anchor 'ls')."""
        self.d.text((x * S, y * S), s, font=f, fill=fill, anchor=anchor)

    def lines(self, x, y_top, lines, f, size, lh, fill, anchor="ls"):
        """Draw wrapped lines; y_top is the top of the block. Returns the block bottom."""
        y = y_top
        for ln in lines:
            self.text(x, y + size * 0.86, ln, f, fill, anchor)
            y += lh
        return y_top + lh * len(lines)

    def png(self) -> bytes:
        from PIL import Image
        img = self.img.resize((W, H), Image.Resampling.LANCZOS)
        img = img.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        return buf.getvalue()


# ---------------------------------------------------------------- flags --

def _stripes(cv, x, y, w, h, colours, vertical=False, weights=None):
    weights = weights or [1] * len(colours)
    tot, pos = sum(weights), 0
    for col, wt in zip(colours, weights):
        if vertical:
            cv.rect(x + w * pos / tot, y, x + w * (pos + wt) / tot, y + h, fill=col)
        else:
            cv.rect(x, y + h * pos / tot, x + w, y + h * (pos + wt) / tot, fill=col)
        pos += wt


def _nordic(cv, x, y, w, h, bg, outer, inner=None, unit=(28, 37, 12, 4)):
    """Nordic cross. unit = (height units, width units, units before the vertical bar, bar units)."""
    hu, wu, before, bar = unit
    cv.rect(x, y, x + w, y + h, fill=bg)
    ux, uy = w / wu, h / hu
    cx0, cy0 = x + before * ux, y + (hu - bar) / 2 * uy
    cv.rect(cx0, y, cx0 + bar * ux, y + h, fill=outer)
    cv.rect(x, cy0, x + w, cy0 + bar * uy, fill=outer)
    if inner:
        cv.rect(cx0 + ux, y, cx0 + (bar - 1) * ux, y + h, fill=inner)
        cv.rect(x, cy0 + uy, x + w, cy0 + (bar - 1) * uy, fill=inner)


def _star(cx, cy, r):
    import math
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.382
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


H_STRIPES = {
    "AT": ["#C8102E", "#FFFFFF", "#C8102E"], "BG": ["#FFFFFF", "#00966E", "#D62612"],
    "DE": ["#000000", "#DD0000", "#FFCE00"], "EE": ["#0072CE", "#000000", "#FFFFFF"],
    "HU": ["#CE2939", "#FFFFFF", "#477050"], "LT": ["#FDB913", "#006A44", "#C1272D"],
    "LU": ["#EA141D", "#FFFFFF", "#51ADDA"], "NL": ["#AE1C28", "#FFFFFF", "#21468B"],
    "PL": ["#FFFFFF", "#DC143C"], "UA": ["#0057B7", "#FFD700"],
}
V_STRIPES = {
    "BE": ["#000000", "#FDDA24", "#EF3340"], "FR": ["#002395", "#FFFFFF", "#ED2939"],
    "IE": ["#169B62", "#FFFFFF", "#FF883E"], "IT": ["#009246", "#FFFFFF", "#CE2B37"],
    "RO": ["#002B7F", "#FCD116", "#CE1126"],
}
SIMPLE_FLAGS = set(H_STRIPES) | set(V_STRIPES) | {"LV", "DK", "SE", "FI", "NO", "IS", "CH", "CZ", "EL", "EU27"}


def flag(cv: Canvas, code: str, x: float, y: float, h: float) -> float:
    """Draw a simple, correct flag (only flags without emblems); otherwise a code badge.
    Returns the width used."""
    if code not in SIMPLE_FLAGS:
        f = font("mono", h * 0.42)
        w = max(h * 1.5, text_w(code, f) + h * 0.5)
        cv.rect(x, y, x + w, y + h, fill=C["accent"], r=h * 0.14)
        cv.text(x + w / 2, y + h / 2, code, f, C["surface"], anchor="mm")
        return w
    w = h if code == "CH" else (h * 1.4 if code in ("DK", "SE", "FI", "NO", "IS") else h * 1.5)
    if code in H_STRIPES:
        _stripes(cv, x, y, w, h, H_STRIPES[code])
    elif code in V_STRIPES:
        _stripes(cv, x, y, w, h, V_STRIPES[code], vertical=True)
    elif code == "LV":
        _stripes(cv, x, y, w, h, ["#9E3039", "#FFFFFF", "#9E3039"], weights=[2, 1, 2])
    elif code == "DK":
        _nordic(cv, x, y, w, h, "#C8102E", "#FFFFFF")
    elif code == "SE":
        _nordic(cv, x, y, w, h, "#006AA7", "#FECC02", unit=(10, 16, 5, 2))
    elif code == "FI":
        _nordic(cv, x, y, w, h, "#FFFFFF", "#003580", unit=(11, 18, 5, 3))
    elif code == "NO":
        _nordic(cv, x, y, w, h, "#BA0C2F", "#FFFFFF", "#00205B", unit=(16, 22, 6, 4))
    elif code == "IS":
        _nordic(cv, x, y, w, h, "#02529C", "#FFFFFF", "#DC1E35", unit=(18, 25, 7, 4))
    elif code == "CH":
        cv.rect(x, y, x + w, y + h, fill="#DA291C")
        u = w / 32
        cv.rect(x + 13 * u, y + 6 * u, x + 19 * u, y + 26 * u, fill="#FFFFFF")
        cv.rect(x + 6 * u, y + 13 * u, x + 26 * u, y + 19 * u, fill="#FFFFFF")
    elif code == "CZ":
        cv.rect(x, y, x + w, y + h / 2, fill="#FFFFFF")
        cv.rect(x, y + h / 2, x + w, y + h, fill="#D7141A")
        cv.poly([(x, y), (x + w / 2, y + h / 2), (x, y + h)], fill="#11457E")
    elif code == "EL":
        _stripes(cv, x, y, w, h, ["#0D5EAF", "#FFFFFF"] * 4 + ["#0D5EAF"])
        s = h * 5 / 9
        cv.rect(x, y, x + s, y + s, fill="#0D5EAF")
        cv.rect(x + s * 2 / 5, y, x + s * 3 / 5, y + s, fill="#FFFFFF")
        cv.rect(x, y + s * 2 / 5, x + s, y + s * 3 / 5, fill="#FFFFFF")
    elif code == "EU27":
        import math
        cv.rect(x, y, x + w, y + h, fill="#003399")
        cx, cy, rr = x + w / 2, y + h / 2, h / 3
        for k in range(12):
            a = k * math.pi / 6
            cv.poly(_star(cx + rr * math.sin(a), cy - rr * math.cos(a), h / 18), fill="#FFCC00")
    cv.rect(x, y, x + w, y + h, outline=C["line_strong"], width=1)
    return w


# ---------------------------------------------------------------- formatting --

def fmt_num(v: float) -> str:
    if v == int(v) and abs(v) >= 10:
        return f"{v:,.0f}"
    if abs(v) >= 100:
        return f"{v:,.0f}"
    if abs(v) >= 10:
        return f"{v:,.1f}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def big_value(v: float, unit: str | None) -> tuple[str, str]:
    """(big number, small unit text) for a stat tile."""
    u = (unit or "").strip()
    if "%" in u:
        return f"{v:,.1f}%", u.replace("%", "", 1).strip()
    if u == "EUR":
        if abs(v) >= 1e9:
            return f"€{v / 1e9:,.1f}bn", ""
        if abs(v) >= 1e6:
            return f"€{v / 1e6:,.{0 if abs(v) >= 1e8 else 1}f}m", ""
        return f"€{fmt_num(v)}", ""
    if u in ("1000s", "thousand persons"):
        return fmt_num(v), "thousand" + ("" if u == "1000s" else " persons")
    if u == "1000 PPS":
        return fmt_num(v), "thousand PPS"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.1f}m", u
    return fmt_num(v), u


# ---------------------------------------------------------------- layout --

def chrome(cv: Canvas, kicker: str, source: str = SOURCE_LINE) -> None:
    """Accent strip, wordmark, kicker pill and the source footer."""
    cv.rect(0, 0, W, 10, fill=C["accent"])
    fw = font("display", 38, 600)
    x, base = M, 78
    cv.text(x, base, "Apprenti", fw, C["ink"])
    x += text_w("Apprenti", fw)
    cv.text(x, base, "x", fw, C["accent"])
    x += text_w("x", fw) + 6
    cv.text(x, base - 4, ".eu", font("mono", 16), C["faint"])
    if kicker:
        fk = font("mono", 16)
        k = kicker.upper()
        kw = text_w(k, fk)
        cv.rect(W - M - kw - 32, 48, W - M, 84, fill=C["accent_soft"], r=18)
        cv.text(W - M - kw / 2 - 16, 66, k, fk, C["accent_ink"], anchor="mm")
    cv.rect(M, H - 70, W - M, H - 69, fill=C["line"])
    fs = font("mono", 17)
    cv.text(M, H - 34, ellipsize(source, fs, W - 2 * M - 160), fs, C["muted"])
    cv.text(W - M, H - 34, "apprentix.eu", fs, C["accent"], anchor="rs")


TILE_TOP, TILE_BOTTOM = 382, 536


def tiles(cv: Canvas, stats: list[dict], top: float = TILE_TOP, bottom: float = TILE_BOTTOM) -> None:
    """Stat tiles in a row. A stat: {big, unit, label, note} or {spark: [...], label, note, span: 2}."""
    if not stats:
        return
    gap = 20
    spans = [s.get("span", 1) for s in stats]
    slots = max(3, sum(spans))        # never stretch one or two tiles across the whole card
    unit_w = (W - 2 * M - gap * (slots - 1)) / slots
    x = M
    for s, sp in zip(stats, spans):
        w = unit_w * sp + gap * (sp - 1)
        cv.rect(x, top, x + w, bottom, fill=C["surface"], outline=C["line"], width=1, r=12)
        if "spark" in s:
            sparkline(cv, s, x + 24, top + 20, w - 48, bottom - top - 40)
        elif "pair" in s:
            pair_tile(cv, s, x + 24, top + 20, w - 48, bottom - top - 40)
        else:
            stat_tile(cv, s, x + 24, top + 20, w - 48, bottom - top - 40)
        x += w + gap


def stat_tile(cv: Canvas, s: dict, x, y, w, h) -> None:
    big = s["big"]
    unit = s.get("unit") or ""
    fu = font("body", 20, 500)
    uw = text_w(" " + unit, fu) if unit else 0
    for size in (56, 50, 44):
        fb = font("display", size, 600)
        bw = text_w(big, fb)
        if bw + uw <= w:
            break
    else:                # unit does not fit beside the number: move it into the label
        s = {**s, "label": (unit[0].upper() + unit[1:] + " · " if unit else "") + s.get("label", "")}
        unit = ""
        for size in (56, 50, 44, 38, 32, 28):
            fb = font("display", size, 600)
            bw = text_w(big, fb)
            if bw <= w:
                break
    base = y + 48
    cv.text(x, base, big, fb, C["accent_ink"])
    if unit:
        cv.text(x + bw + 6, base, ellipsize(unit, fu, w - bw - 6), fu, C["muted"])
    note = s.get("note")
    fl = font("body", 19, 500)
    max_lines = 2 if note else 3
    lines = wrap(s.get("label", ""), fl, w)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = ellipsize(lines[-1] + " …", fl, w)
    yy = cv.lines(x, base + 12, lines, fl, 19, 23, C["ink"])
    if note:
        fn = font("mono", 15)
        cv.text(x, max(yy + 18, y + h - 2), ellipsize(note, fn, w), fn, C["muted"])


def pair_tile(cv: Canvas, s: dict, x, y, w, h) -> None:
    """Two values side by side (duel): A in side-A colour, B in side-B colour."""
    a, b = s["pair"]
    for size in (40, 36, 32, 28, 24):
        fb = font("display", size, 600)
        fv = font("body", 18, 500)
        tw = text_w(a, fb) + text_w("  vs  ", fv) + text_w(b, fb)
        if tw <= w:
            break
    base = y + 38
    cv.text(x, base, a, fb, C["side_a"])
    xx = x + text_w(a, fb)
    cv.text(xx, base, "  vs  ", fv, C["muted"])
    xx += text_w("  vs  ", fv)
    cv.text(xx, base, b, fb, C["side_b"])
    fl = font("body", 18, 500)
    lines = wrap(s.get("label", ""), fl, w)
    if len(lines) > 2:
        lines = lines[:2]
        lines[-1] = ellipsize(lines[-1] + " …", fl, w)
    cv.lines(x, base + 12, lines, fl, 18, 22, C["ink"])
    if s.get("note"):
        fn = font("mono", 15)
        cv.text(x, y + h - 2, ellipsize(s["note"], fn, w), fn, C["muted"])


def sparkline(cv: Canvas, s: dict, x, y, w, h) -> None:
    pts = s["spark"]                  # [(time, value)]
    fl = font("body", 19, 500)
    cv.text(x, y + 18, ellipsize(s.get("label", ""), fl, w), fl, C["ink"])
    fn = font("mono", 15)
    gx0, gy0, gx1, gy1 = x + 4, y + 36, x + w - 4, y + h - 26
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.12
    lo, hi = lo - pad, hi + pad
    n = len(pts)
    xy = [(gx0 + (gx1 - gx0) * (i / (n - 1) if n > 1 else 0.5), gy1 - (gy1 - gy0) * (v - lo) / (hi - lo))
          for i, (_, v) in enumerate(pts)]
    cv.rect(gx0, gy1 + 1, gx1, gy1 + 2, fill=C["line"])
    if n > 1:
        cv.line(xy, C["accent"], 4)
    cv.dot(*xy[-1], 7, C["accent"])
    cv.dot(*xy[0], 4, C["accent"])
    cv.text(gx0, y + h - 2, str(pts[0][0]), fn, C["muted"])
    cv.text(gx1, y + h - 2, str(pts[-1][0]), fn, C["muted"], anchor="rs")
    if s.get("note"):
        cv.text((gx0 + gx1) / 2, y + h - 2, ellipsize(s["note"], fn, w - 160), fn, C["muted"], anchor="ms")


def title_block(cv: Canvas, title: str, subtitle: str | None, top: float = 128, bottom: float = TILE_TOP - 26,
                left: float = M, max_lines: int = 3, sizes=(76, 68, 62, 56, 50, 46, 42, 38)) -> None:
    max_w = W - M - left
    sub_lines, fsub = [], font("body", 26, 400)
    if subtitle:
        sub_lines = wrap(subtitle, fsub, max_w)[:2]
        if len(wrap(subtitle, fsub, max_w)) > 2:
            sub_lines[-1] = ellipsize(sub_lines[-1] + " …", fsub, max_w)
    sub_h = (len(sub_lines) * 34 + 14) if sub_lines else 0
    avail = bottom - top - sub_h
    for size in sizes:
        f = font("display", size, 600)
        lines = wrap(title, f, max_w)
        if len(lines) <= max_lines and len(lines) * size * 1.08 <= avail:
            break
    else:
        size = sizes[-1]
        f = font("display", size, 600)
        lines = wrap(title, f, max_w)
        k = max(1, min(max_lines, int(avail // (size * 1.08))))
        if len(lines) > k:
            lines = lines[:k]
            lines[-1] = ellipsize(lines[-1] + " …", f, max_w)
    yy = cv.lines(left, top, lines, f, size, size * 1.08, C["ink"])
    if sub_lines:
        cv.lines(left, yy + 14, sub_lines, fsub, 26, 34, C["muted"])


def card(kicker: str, title: str, subtitle: str | None, stats: list[dict], source: str = SOURCE_LINE) -> bytes:
    cv = Canvas()
    chrome(cv, kicker, source)
    title_block(cv, title, subtitle)
    tiles(cv, stats[:3])
    return cv.png()


# ---------------------------------------------------------------- data --

def default_series(ind: dict) -> list[dict]:
    dims = ind.get("dims") or []
    return [o for o in ind["series"]
            if o.get("value") is not None
            and all((o.get("dims") or {}).get(d["key"], d.get("default")) == d.get("default") for d in dims)]


def latest_by_geo(obs: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for o in obs:
        g = o["geo"]
        if g not in out or str(o["time"]) > str(out[g]["time"]):
            out[g] = o
    return out


def compare_measure(m: dict, A: dict, B: dict) -> dict:
    """Python twin of compareMeasure() in assets/js/duel-core.js."""
    a = (A.get("figures") or {}).get(m["key"])
    b = (B.get("figures") or {}).get(m["key"])
    out = {"a": a, "b": b, "comparable": False, "edge": None,
           "directional": m.get("better") in ("higher", "lower")}
    if not a or not b or a["id"] != b["id"]:
        return out
    ya, yb = int(str(a["y"])[:4]), int(str(b["y"])[:4])
    if abs(ya - yb) > 1:
        return out
    out["comparable"] = True
    if out["directional"] and a["v"] != b["v"]:
        out["edge"] = "a" if (m["better"] == "higher") == (a["v"] > b["v"]) else "b"
    return out


def scorecard(measures: list[dict], A: dict, B: dict) -> dict:
    n = a = b = tie = 0
    for m in measures:
        c = compare_measure(m, A, B)
        if not c["comparable"] or not c["directional"]:
            continue
        n += 1
        if c["edge"] == "a":
            a += 1
        elif c["edge"] == "b":
            b += 1
        else:
            tie += 1
    return {"n": n, "a": a, "b": b, "tie": tie}


def scorecard_text(sc: dict, na: str, nb: str) -> str:
    """Python twin of scorecardText() in assets/js/duel-core.js."""
    if not sc["n"]:
        return f"No measure with a defined direction has comparable data for both {na} and {nb}."
    of = f"of {sc['n']} comparable measure{'' if sc['n'] == 1 else 's'}"
    tie = f", level on {sc['tie']}" if sc["tie"] else ""
    if sc["a"] == sc["b"]:
        return f"{na} and {nb} are each ahead on {sc['a']} {of}{tie}."
    hi, hn, lo, ln = (na, sc["a"], nb, sc["b"]) if sc["a"] > sc["b"] else (nb, sc["b"], na, sc["a"])
    return f"{hi} is ahead on {hn} {of}; {lo} on {ln}{tie}."


# Short labels for card tiles (the full labels are in duel/countries.json "measures").
SHORT = {
    "wbl": "Recent VET graduates with work-based learning",
    "vet_emp": "Recent VET graduates in employment",
    "ivet_share": "Upper-secondary students in vocational programmes",
    "he_access": "VET students with direct access to higher education",
    "early_leavers": "Early leavers from education and training",
    "neet": "Young people not in employment, education or training",
    "youth_unemp": "Unemployment rate, ages 20–34",
    "adult_emp": "Employment rate of adults with a VET qualification",
    "wb_share": "VET pupils in work-based programmes",
    "firms_ivet": "Enterprises employing initial-VET participants",
    "mobility": "IVET learners with a learning mobility abroad",
    "vet_premium": "Employment premium of VET over general graduates",
}
def shaky(f: dict | None) -> bool:
    """Low reliability (u) or definition differs (d): a card has no room for the caveat, so skip it."""
    return bool(f) and str(f.get("f") or "")[:1] in ("u", "d")


HEADLINE_ORDER = ["wbl", "vet_emp", "ivet_share", "he_access", "early_leavers", "neet", "youth_unemp",
                  "adult_emp", "wb_share", "firms_ivet", "mobility", "vet_premium"]


# ---------------------------------------------------------------- cards --

def country_card(code: str, P: dict, duel: dict) -> tuple[bytes, str]:
    eu_ref, units = duel.get("eu_ref") or {}, {k: v.get("unit") for k, v in (duel.get("indicators") or {}).items()}
    name = P["name"]
    stats = []
    for key in HEADLINE_ORDER:
        f = (P.get("figures") or {}).get(key)
        if not f or shaky(f):
            continue
        big, unit = big_value(f["v"], units.get(f["id"]))
        eu = (eu_ref.get(f["id"]) or {}).get(str(f["y"]))
        note = (f"EU-27 {big_value(eu['v'], units.get(f['id']))[0]} · {f['y']}" if eu else str(f["y"]))
        stats.append({"big": big, "unit": unit, "label": SHORT[key], "note": note})
        if len(stats) == 3:
            break
    ns = ((P.get("schemes") or {}).get("count")) or 0
    pol = P.get("policy") or {}
    extras = []
    if pol.get("vet"):
        extras.append({"big": f"{pol['vet']:,}", "label": "VET policy developments tracked since 2015",
                       "note": f"{pol.get('apprenticeship', 0):,} on apprenticeship"})
    orgs = (P.get("erasmus") or {}).get("orgs")
    if orgs:
        extras.append({"big": f"{orgs:,}", "label": "Organisations with an Erasmus+ VET accreditation", "note": "2021–2025 calls"})
    nqf = (P.get("nqf") or {}).get("types")
    if nqf:
        extras.append({"big": f"{nqf:,}", "label": "Qualification types in the national framework", "note": "Cedefop NQF tool"})
    stats += extras[: 3 - len(stats)]
    sub_bits = ["Apprenticeships and vocational education"]
    sub_bits.append(f"{ns} apprenticeship scheme{'' if ns == 1 else 's'}" if ns else "not covered by Cedefop's scheme database")
    subtitle = " · ".join(sub_bits)

    cv = Canvas()
    chrome(cv, "Country profile")
    fh = 64
    fw = flag(cv, code, M, 128, fh)
    title_block(cv, name, None, top=124, bottom=228, left=M + fw + 28, max_lines=2,
                sizes=(84, 76, 68, 60, 54, 48, 42, 38))
    fsub = font("body", 26, 400)
    cv.text(M, 290, ellipsize(subtitle, fsub, W - 2 * M), fsub, C["muted"])
    if any("EU-27" in (s.get("note") or "") for s in stats):
        fn = font("mono", 16)
        cv.text(M, 336, "LATEST VALUE, WITH THE EU-27 FIGURE FOR THE SAME YEAR", fn, C["faint"])
    tiles(cv, stats)
    alt = f"{name}: apprenticeship and VET profile on Apprentix — " + "; ".join(
        f"{s['label']} {s['big']}" + (f" ({s['note']})" if s.get("note") else "") for s in stats) + "."
    return cv.png(), alt


def indicator_card(ind: dict, names: dict[str, str]) -> tuple[bytes, str]:
    p = ind.get("provenance") or {}
    obs = default_series(ind)
    unit = ind.get("unit")
    cov = ind.get("coverage") or {}
    geos = cov.get("geos") or []
    t = cov.get("time") or ["", ""]
    single = len(geos) == 1
    focus = geos[0] if single else ("EU27" if any(o["geo"] == "EU27" for o in obs) else None)
    stats, alt_bits = [], []
    latest = latest_by_geo(obs)
    if focus and focus in latest:
        o = latest[focus]
        big, u = big_value(o["value"], unit)
        label = names.get(focus, focus)
        stats.append({"big": big, "unit": u, "label": f"{label}, latest", "note": str(o["time"])})
        alt_bits.append(f"{label} {big} {u} ({o['time']})".replace("  ", " "))
        series = sorted(((str(x["time"]), x["value"]) for x in obs if x["geo"] == focus))
        if len(series) >= 3:
            stats.append({"spark": series[-200:], "label": f"{label} over time", "span": 2})
    countries = {g: o for g, o in latest.items() if g in names and g != "EU27" and not g.startswith("EU")}
    if countries and len(stats) < 3 and not single:
        newest = max(str(o["time"]) for o in countries.values())
        same = {g: o for g, o in countries.items() if str(o["time"]) == newest}
        if len(same) >= 2:
            hi = max(same.items(), key=lambda kv: (kv[1]["value"], kv[0]))
            lo = min(same.items(), key=lambda kv: (kv[1]["value"], kv[0]))
            for tag, (g, o) in (("Highest", hi), ("Lowest", lo)):
                if len(stats) >= 3 or (len(stats) == 2 and stats[-1].get("span") == 2):
                    break
                big, u = big_value(o["value"], unit)
                stats.append({"big": big, "unit": u, "label": f"{tag}: {names[g]}", "note": f"{newest} · {len(same)} countries"})
                alt_bits.append(f"{tag.lower()} {names[g]} {big}")
    pub = p.get("publisher", "")
    sub = " · ".join(x for x in (pub, (names.get(geos[0], geos[0]) if single else f"{len(geos)} countries"),
                                  f"{t[0]}–{t[1]}" if t[0] != t[1] else str(t[0])) if x)
    cv = Canvas()
    chrome(cv, "Indicator", source=f"Source: {pub} · apprentix.eu" if pub else SOURCE_LINE)
    title_block(cv, ind["title"], sub, sizes=(64, 58, 52, 48, 44, 40, 36, 32))
    tiles(cv, stats)
    alt = f"{ind['title']} — {sub}" + (f". {'; '.join(alt_bits)}." if alt_bits else ".")
    return cv.png(), alt


def duel_card(a: str, b: str, A: dict, B: dict, duel: dict) -> tuple[bytes, str, str]:
    measures = duel.get("measures") or []
    units = {k: v.get("unit") for k, v in (duel.get("indicators") or {}).items()}
    sc = scorecard(measures, A, B)
    summary = scorecard_text(sc, A["name"], B["name"])
    by_key = {m["key"]: m for m in measures}
    stats = []
    for key in HEADLINE_ORDER:
        m = by_key.get(key)
        if not m:
            continue
        c = compare_measure(m, A, B)
        if not c["comparable"] or shaky(c["a"]) or shaky(c["b"]):
            continue
        u = units.get(c["a"]["id"])
        va, vb = big_value(c["a"]["v"], u)[0], big_value(c["b"]["v"], u)[0]
        ya, yb = str(c["a"]["y"]), str(c["b"]["y"])
        stats.append({"pair": (va, vb), "label": SHORT.get(key, m["label"]), "note": ya if ya == yb else f"{ya} / {yb}"})
        if len(stats) == 3:
            break
    if len(stats) < 3:
        na = ((A.get("schemes") or {}).get("count")) or 0
        nb = ((B.get("schemes") or {}).get("count")) or 0
        if na or nb:
            stats.append({"pair": (str(na), str(nb)), "label": "Apprenticeship schemes", "note": "Cedefop"})
    if len(stats) < 3:
        pa, pb = (A.get("policy") or {}).get("vet"), (B.get("policy") or {}).get("vet")
        if pa or pb:
            stats.append({"pair": (f"{pa or 0:,}", f"{pb or 0:,}"), "label": "VET policy developments since 2015", "note": "Cedefop / ReferNet"})

    cv = Canvas()
    chrome(cv, "Country vs country")
    colw = (W - 2 * M - 100) / 2
    for i, (code, P, col) in enumerate(((a, A, C["side_a"]), (b, B, C["side_b"]))):
        x0 = M + i * (colw + 100)
        fw = flag(cv, code, x0, 120, 48)
        f, size, lines, lh = fit(P["name"], "display", 600, colw, 1, (60, 54, 48, 44), 1.04)
        if len(wrap(P["name"], f, colw)) == 1:
            cv.lines(x0, 186, lines, f, size, lh, C["ink"])
        else:
            f, size, lines, lh = fit(P["name"], "display", 600, colw, 2, (48, 44, 40, 36, 32), 1.04)
            cv.lines(x0, 178, lines, f, size, lh, C["ink"])
        cv.rect(x0, 300, x0 + colw, 306, fill=col)
    cv.text(W / 2, 214, "vs", font("display", 44, 400), C["muted"], anchor="ms")
    fs = font("body", 23, 500)
    sl = wrap(summary, fs, W - 2 * M)
    if len(sl) > 2:
        sl = sl[:2]
        sl[-1] = ellipsize(sl[-1] + " …", fs, W - 2 * M)
    cv.lines(M, 318 if len(sl) > 1 else 326, sl, fs, 23, 28, C["ink"])
    tiles(cv, stats, top=380, bottom=540)
    alt = f"{A['name']} vs {B['name']} on Apprentix. {summary}"
    return cv.png(), alt, summary


# ---------------------------------------------------------------- section cards --

def counts() -> dict:
    manifest = read_json(DATA / "datasets.json")
    index = read_json(INDICATORS / "index.json")["indicators"]
    duel = read_json(PUBLISHED / "duel" / "countries.json")
    countries = [c for c in duel["countries"] if c != duel.get("eu", "EU27")]
    recs = {d["id"]: d.get("records") or 0 for d in manifest["datasets"]}
    ins_path = PUBLISHED / "insights" / "insights.json"
    insights = read_json(ins_path)["items"] if ins_path.exists() else []
    src_path = DATA / "sources.json"
    sources = read_json(src_path)["sources"] if src_path.exists() else []
    smeta = read_json(PUBLISHED / "apprenticeship-schemes" / "meta.json")
    schemes = read_json(PUBLISHED / "apprenticeship-schemes" / "records.json")
    return {
        "datasets": len(manifest["datasets"]), "records": sum(recs.values()), "recs": recs,
        "indicators": len(index), "countries": len(countries), "sources": len(sources),
        "insights": len(insights), "schemes": len(schemes),
        "scheme_countries": len({s.get("country_code") for s in schemes if s.get("country_code")}),
        "questions": len((smeta.get("matrix") or {}).get("questions") or []),
        "measures": len(duel.get("measures") or []),
        "eu": duel["countries"].get(duel.get("eu", "EU27"), {}),
        "units": {k: v.get("unit") for k, v in (duel.get("indicators") or {}).items()},
        "publishers": len({(m.get("provenance") or {}).get("publisher") for m in index}),
    }


def section_specs(N: dict) -> dict[str, dict]:
    def stat(n, label, note=None):
        return {"big": f"{n:,}" if isinstance(n, int) else n, "label": label, **({"note": note} if note else {})}
    eu = N["eu"].get("figures") or {}

    def eu_stat(key, label):
        f = eu.get(key)
        if not f:
            return None
        return {"big": big_value(f["v"], N["units"].get(f["id"]))[0], "label": label, "note": f"EU-27 · {f['y']}"}

    ins_stats = [s for s in (stat(N["insights"], "Findings, each with its data, method and caveats"),
                             eu_stat("wbl", "of recent VET graduates learned at work"),
                             eu_stat("vet_emp", "of recent VET graduates are employed")) if s]
    return {
        "site": dict(kicker="Open data", title="European apprenticeship and VET data, made searchable",
                     subtitle="Schemes, statistics and policies from public sources — search, filter and compare.",
                     stats=[stat(N["schemes"], "Apprenticeship schemes"), stat(N["indicators"], "Statistical indicators"),
                            stat(N["countries"], "Countries")]),
        "indicators": dict(kicker="Indicators", title="Statistics on apprenticeship and VET in Europe",
                           subtitle="Maps, rankings and trends, with sources and downloads.",
                           stats=[stat(N["indicators"], "Statistical indicators"), stat(N["countries"], "Countries"),
                                  stat(N["publishers"], "Publishers", "Eurostat, Cedefop, OECD, UIS and national offices")]),
        "insights": dict(kicker="Insights", title="Insights on apprenticeships in Europe",
                         subtitle="What the data says when you put the sources side by side.", stats=ins_stats),
        "find": dict(kicker="Find", title="Find my apprenticeship",
                     subtitle="Answer up to seven short questions and see which schemes fit you best.",
                     stats=[stat(N["schemes"], "Apprenticeship schemes"), stat(N["scheme_countries"], "Countries"),
                            stat(7, "Short questions")]),
        "duel": dict(kicker="Country vs country", title="Put two European countries side by side",
                     subtitle="Schemes, key VET figures against the EU-27, policies and funding.",
                     stats=[stat(N["countries"], "Countries and the EU-27"), stat(N["measures"], "Key figures compared"),
                            stat(N["schemes"], "Apprenticeship schemes")]),
        "compare": dict(kicker="Compare", title="Compare Europe's apprenticeship schemes side by side",
                        subtitle="Pay, contract, workplace share, governance, financing and incentives.",
                        stats=[stat(N["schemes"], "Apprenticeship schemes"), stat(N["questions"], "Questions coded by Cedefop"),
                               stat(N["scheme_countries"], "Countries")]),
        "data": dict(kicker="Data & sources", title="Where the data comes from",
                     subtitle="Every source, licence and caveat — with downloads.",
                     stats=[stat(N["datasets"], "Record datasets"), stat(N["indicators"], "Statistical indicators"),
                            stat(N["sources"], "Upstream sources tracked")]),
        "ask": dict(kicker="Ask", title="Ask Apprentix",
                    subtitle="Questions about European apprenticeship data, answered from the sources — with links.",
                    stats=[stat(N["datasets"], "Record datasets"), stat(N["records"], "Records"),
                           stat(N["indicators"], "Statistical indicators")]),
        "explore": dict(kicker="Explore", title="Search, filter and compare apprenticeship and VET records",
                        subtitle="Schemes, policies, qualifications, Erasmus+ organisations and open datasets.",
                        stats=[stat(N["datasets"], "Record datasets"), stat(N["records"], "Records"),
                               stat(N["recs"].get("vet-policy-timeline", 0), "VET policies since 2015")]),
        "play": dict(kicker="Game", title="Higher or lower?",
                     subtitle="Which European country scores higher? Test your feel for apprenticeship and VET numbers.",
                     stats=[stat(N["countries"], "Countries"), stat(N["indicators"], "Statistical indicators"),
                            stat(N["schemes"], "Apprenticeship schemes")]),
        "countries": dict(kicker="Countries", title="Apprenticeships by country",
                          subtitle="Schemes, key figures against the EU-27, policies and open datasets.",
                          stats=[stat(N["countries"], "Country profiles"), stat(N["schemes"], "Apprenticeship schemes"),
                                 stat(N["recs"].get("vet-policy-timeline", 0), "VET policies since 2015")]),
    }


def section_alt(spec: dict) -> str:
    def low(t: str) -> str:
        return t[0].lower() + t[1:] if t[1:2].islower() else t
    return f"{spec['title']} — Apprentix. " + "; ".join(f"{s['big']} {low(s['label'])}" for s in spec["stats"]) + "."


# ---------------------------------------------------------------- share pages --

def duel_share_page(a: str, b: str, A: dict, B: dict, summary: str, alt: str, updated: str) -> str:
    from .render_pages import SITE, breadcrumb, e, page, website
    slug = duel_slug(a, b)
    page_url = f"{SITE}pages/duel/{slug}.html"
    target = f"../duel.html?a={a}&b={b}"
    title = f"{A['name']} vs {B['name']} — apprenticeships and VET compared | Apprentix"
    description = (f"{A['name']} and {B['name']} side by side: apprenticeship schemes, key VET figures against the EU-27, "
                   f"policies and funding. {summary}")
    body = f"""<nav class="cp-crumbs" aria-label="Breadcrumb"><a href="../../">Apprentix</a> <span aria-hidden="true">›</span> <a href="../duel.html">Country vs country</a> <span aria-hidden="true">›</span> <span aria-current="page">{e(A['name'])} vs {e(B['name'])}</span></nav>

<header class="cp-head">
  <div>
    <div class="mono cp-group">Country vs country</div>
    <h1>{e(A['name'])} vs {e(B['name'])}</h1>
    <p class="lede">{e(summary)}</p>
    <p class="cp-links cp-actions"><a class="btn primary" href="{e(target)}">Open the full comparison</a></p>
  </div>
</header>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": page_url, "url": page_url, "name": title, "description": description,
         "inLanguage": "en", "dateModified": updated, "isPartOf": {"@id": SITE + "#website"},
         "breadcrumb": {"@id": page_url + "#breadcrumb"}},
        website(),
        breadcrumb([("Apprentix", SITE), ("Country vs country", SITE + "pages/duel.html"),
                    (f"{A['name']} vs {B['name']}", page_url)], page_url)]}
    redirect = (f'<script>location.replace({json.dumps(target)} + location.hash);</script>')
    return page(title=title, description=description, canonical=page_url, root="../../", body=body,
                json_ld_obj=ld, current=None, updated=updated,
                og_image=duel_path(a, b), og_image_alt=alt, head_extra=redirect)


# ---------------------------------------------------------------- io --

def write_bytes(path: Path, data: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def prune(folder: Path, pattern: str, keep: set[str], changed: list[Path]) -> None:
    if not folder.exists():
        return
    for p in folder.glob(pattern):
        if p.name not in keep:
            p.unlink()
            changed.append(p)


def build() -> list[Path]:
    from .render_pages import write_text
    changed: list[Path] = []
    manifest = read_json(DATA / "datasets.json")
    updated = manifest["site"].get("updated", "")
    duel = read_json(PUBLISHED / "duel" / "countries.json")
    profiles = duel["countries"]
    eu = duel.get("eu", "EU27")
    ref = read_json(REFERENCE / "countries.json")
    names = {c["code"]: c["name"] for c in ref["countries"]}
    names["EU27"] = "EU-27"

    def put(rel: str, data: bytes):
        if write_bytes(ROOT / rel, data):
            changed.append(ROOT / rel)

    # Site + sections
    specs = section_specs(counts())
    alts = {}
    for key, spec in specs.items():
        rel = site_path() if key == "site" else section_path(key)
        put(rel, card(spec["kicker"], spec["title"], spec["subtitle"], spec["stats"]))
        alts[key] = section_alt(spec)

    # Countries
    keep = set()
    for code in sorted(profiles):
        if code == eu:
            continue
        png, alt = country_card(code, profiles[code], duel)
        put(country_path(code), png)
        keep.add(Path(country_path(code)).name)
        alts[f"country:{code}"] = alt
    prune(OG_DIR / "country", "*.png", keep, changed)

    # Indicators
    keep = set()
    for p in sorted(INDICATORS.glob("*.json")):
        if p.name == "index.json":
            continue
        ind = read_json(p)
        png, alt = indicator_card(ind, names)
        put(indicator_path(ind["id"]), png)
        keep.add(f"{ind['id']}.png")
        alts[f"indicator:{ind['id']}"] = alt
    prune(OG_DIR / "indicator", "*.png", keep, changed)

    # Duels: cards + share pages + the pair list for duel.js
    keep_png, keep_html, pairs = set(), set(), {}
    for a, b in duel_pairs(list(profiles), eu):
        png, alt, summary = duel_card(a, b, profiles[a], profiles[b], duel)
        put(duel_path(a, b), png)
        slug = duel_slug(a, b)
        keep_png.add(f"{slug}.png")
        keep_html.add(f"{slug}.html")
        html_path = DUEL_PAGES / f"{slug}.html"
        if write_text(html_path, duel_share_page(a, b, profiles[a], profiles[b], summary, alt, updated)):
            changed.append(html_path)
        pairs[f"{a}-{b}"] = f"pages/duel/{slug}.html"
    prune(OG_DIR / "duel", "*.png", keep_png, changed)
    prune(DUEL_PAGES, "*.html", keep_html, changed)

    alt_text = {"description": "Alt text for the social preview images in assets/og/ (generated by pipeline/og.py).",
                "alt": alts}
    pairs_doc = {
        "description": ("Country pairs with a static share page (pages/duel/<a>-<b>.html) carrying a preview image. "
                        "Key 'A-B' = side A vs side B, as in duel.html?a=A&b=B. Generated by pipeline/og.py."),
        "pairs": pairs,
    }
    for path, doc in ((PAIRS_JSON, pairs_doc), (PUBLISHED / "og" / "alt.json", alt_text)):
        if write_text(path, json.dumps(doc, ensure_ascii=False, indent=1) + "\n"):
            changed.append(path)

    total = sum(p.stat().st_size for p in OG_DIR.rglob("*.png"))
    print(f"OG: {len(specs)} site/section cards, {len([k for k in alts if k.startswith('country:')])} country, "
          f"{len([k for k in alts if k.startswith('indicator:')])} indicator, {len(pairs)} duel cards + share pages; "
          f"{total / 1e6:.1f} MB total, {len(changed)} file(s) changed")
    return changed


def alt_for(key: str, fallback: str = "") -> str:
    """Alt text written by the last build (pages read it so they need not recompute cards)."""
    p = PUBLISHED / "og" / "alt.json"
    if not p.exists():
        return fallback
    return read_json(p).get("alt", {}).get(key, fallback)


if __name__ == "__main__":
    build()
