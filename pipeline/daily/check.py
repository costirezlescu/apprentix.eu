"""Check Cedefop Daily editions against the pool they were written from.

  python -m pipeline.daily.check 2026-10-19        the main edition (exit 1 on any failure)
  python -m pipeline.daily.check --lab             every edition in daily/lab/

Failures (the edition must not go out):
  * a referenced item is not in the pool;
  * a URL in the edition or in the rendered page does not come from the pool
    (Apprentix's own pages and the paper's anchors excepted), or an anchor is missing;
  * a number in a story is not found in that story's sources;
  * a quotation is not verbatim, or a press quotation is longer than 12 words;
  * a story has no connection line, or a "why it matters" link is not in the pool;
  * a banned word, a sensitive topic (held for the editor), a person in more than one
    headline, the same story twice, or a past event in the diary;
  * Lives: a name the story lists as named does not appear in its source.
Warnings: long headlines, items past their use-by date, the Director in a headline,
possible personal names in press stories, an edition over its item budget.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

from ..common import ROOT
from .render import DAILY, HOOKS, SITE, connection

USE_BY = {"cedefop": 7, "policy": 3, "agencies": 10, "field": 8, "debate": 8, "research": 30, "people": 30, "lives": 60}
BUDGET = 14            # items on the page, all tiers together
BANNED = ["landmark", "ambitious", "controversial", "groundbreaking", "game-changer", "game changer",
          "unprecedented", "historic", "revolutionary", "world-class", "cutting-edge", "we ", "our "]
SENSITIVE = ["olaf", "audit", "ombudsman", "litigation", "lawsuit", "court of justice ruling", "died", "death of",
             "disciplinary", "harassment", "fraud investigation", "security incident"]
DIRECTOR = "Siebel"
ORG_WORDS = {"Social", "Competition", "Vocational", "President", "Insurance", "Policy", "Markets", "Employers", "Summit", "Alliance", "Institute", "Centre",
             "Center", "Union", "Council", "Commission", "European", "German", "French", "Spanish", "Greek", "Italian",
             "Irish", "British", "Ministry", "Education", "Agency", "Authority", "Foundation", "Association",
             "Parliament", "Office", "School", "Schools", "University", "College", "Survey", "Forum", "Network",
             "Board", "Fund", "Bank", "Organisation", "Organization", "Federation", "Chamber", "Trade", "Labour",
             "Sports", "Great", "Britain", "London", "Bus", "Station", "Bavarian", "Shanghai", "Madrid", "Berlin",
             "Korea", "Netherlands", "Ireland", "Japan", "Switzerland", "Preston", "Burnley", "Flein", "Seine", "Saint",
             "Denis", "Wood", "Bad", "Wildungen", "Nördlingen", "King", "Kings", "WorldSkills", "Wiener", "Jugend"}
FUNCTION_WORDS = {"In", "While", "Their", "The", "A", "An", "At", "On", "For", "With", "Its", "His", "Her", "They",
                  "He", "She", "When", "After", "Before", "Now", "Some", "One", "This", "That", "These", "Those"}
ALLOWED_EXTERNAL = ("https://fonts.googleapis.com/", "https://open-meteo.com/", "https://github.com/costirezlescu/apprentix.eu/issues")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).lower()


def numbers(text: str) -> list[str]:
    return [m.group(1).replace(",", "") for m in
            re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:st|nd|rd|th)?(?!\w)", text)]


def stories_of(ed: dict) -> list[tuple[str, dict, str]]:
    """(where, story, pillar) for every story in an edition, whatever its layout."""
    out = [("lead", ed["lead"], ed["lead"]["pillar"])]
    out += [(f"know[{k}]", s, s["pillar"]) for k, s in enumerate(ed.get("know", []))]
    out += [(f"more[{k}]", s, s["pillar"]) for k, s in enumerate(ed.get("more", []))]
    for x in ed.get("sections", []):
        out += [(f"{x['id']}[{k}]", s, x["pillar"]) for k, s in enumerate(x["stories"])]
    if ed.get("lives"):
        out.append(("lives", ed["lives"], "lives"))
    if ed.get("feature"):
        f = ed["feature"]       # parts and deadline notes are checked like body text
        out.append(("feature", dict(f, body=f.get("body", []) + [x["text"] for x in f.get("parts", []) + f.get("rows", [])],
                                    also=f.get("also", []) + [r["item"] for r in f.get("rows", [])] + f.get("facts", [])),
                    f["pillar"]))
    if ed.get("chart"):
        c = ed["chart"]
        out.append(("chart", dict(c, key="chart:" + c["item"], body=c["reading"]), "data"))
    return out


def check(ed: dict, page: Path | None) -> tuple[list[str], list[str], int]:
    date = ed["date"]
    pool = json.loads((DAILY / "pool" / f"{ed['pool']}.json").read_text("utf-8"))
    P = {i["id"]: i for i in pool["items"]}
    fails, warns = [], []
    pool_urls = {i["url"] for i in pool["items"]}
    for i in pool["items"]:
        pool_urls |= {l["url"] for l in i["meta"].get("links", [])}
    duel = next((i for i in pool["items"] if i["source"] == "apprentix" and i["title"] == "Country vs country"), None)

    def url_ok(u: str) -> bool:
        if u.startswith("#") or u in pool_urls:
            return True
        m = re.fullmatch(re.escape(SITE) + r"/pages/duel\.html\?a=([A-Z]{2}|EU27)&b=([A-Z]{2}|EU27)", u)
        return bool(m and duel and {m.group(1), m.group(2)} <= set(duel["meta"]["countries"]))

    def sources_text(ids: list[str], urls: list[str]) -> str:
        parts = [json.dumps(P[i], ensure_ascii=False) for i in ids if i in P]
        parts += [json.dumps(i, ensure_ascii=False) for i in pool["items"] if i["url"] in urls]
        text = norm(" ".join(parts))
        decimal = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", text)     # "5,6 Prozent" → 5.6
        return text + " " + " ".join(numbers(text)) + " " + " ".join(numbers(decimal))

    for a, h in HOOKS.items():
        if not url_ok(h["url"]):
            fails.append(f"hooks.json: the link for {a} is not in the pool: {h['url']}")

    seen, headlines = set(), []
    built = min(date, ed.get("built_on", date))
    for where, s, pillar in stories_of(ed):
        key = s.get("key") or s.get("item")
        if key in seen:
            fails.append(f"{where}: the same story twice ({key})")
        seen.add(key)
        ids = [x for x in [s.get("item"), s.get("connection_item"), *s.get("also", [])] if x]
        ids += [l["item"] for l in s.get("links", []) if l.get("item")]
        urls = [l["url"] for l in s.get("links", []) if l.get("url")]
        for i in ids:
            if i not in P:
                fails.append(f"{where}: item {i} is not in the pool")
        for u in urls:
            if not url_ok(u):
                fails.append(f"{where}: URL not from the pool: {u}")
        ids = [i for i in ids if i in P]
        src = sources_text(ids, urls)
        texts = [s.get("headline", ""), s.get("standfirst", ""), *s.get("body", []), s.get("more", "")]
        body = " ".join(t for t in texts if t)
        for n in numbers(body):
            if n not in src and n not in date:
                fails.append(f"{where}: number {n} not found in its sources (“{s.get('headline', '')[:50]}”)")
        press = [P[i] for i in ids if P[i]["circle"] in ("press", "4")]
        for q in re.findall(r"“([^”]+)”", body):
            if norm(q).strip(" .,") not in src:
                fails.append(f"{where}: quotation not found verbatim in its sources: “{q}”")
            if press and len(q.split()) > 12:
                fails.append(f"{where}: press quotation longer than 12 words (copyright): “{q[:40]}…”")
        low = " " + norm(body) + " "
        quoted = " ".join(" " + norm(q) for q in re.findall(r"“([^”]+)”", body))
        for w in BANNED:
            if f" {w}" in low and f" {w}" not in quoted:
                fails.append(f"{where}: banned word “{w.strip()}”")
        for w in SENSITIVE:
            if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low):
                fails.append(f"{where}: sensitive topic “{w}”: HOLD for the editor")
        named = set(s.get("named", []))
        for n in named:
            if norm(n) not in src:
                fails.append(f"{where}: named person “{n}” does not appear in the source")
        if press:
            allowed = {w for i in press for w in re.findall(r"[A-ZÀ-Ž][\wÀ-ž’'-]+", i["meta"].get("outlet", ""))}
            allowed |= {w for n in named | set(s.get("public_roles", [])) for w in n.split()}
            joined = " ".join(texts[1:])
            for m in re.finditer(r"\b([A-ZÀ-Ž][a-zà-ž]+) ([A-ZÀ-Ž][a-zà-ž]+)\b", joined):
                start = m.start()
                if start == 0 or joined[max(0, start - 2):start] in (". ", "? ", "! ", ": ", "; ") \
                        or m.group(1) in FUNCTION_WORDS:
                    continue                    # a capital at the start of a sentence is not a name
                if not ({m.group(1), m.group(2)} & (allowed | ORG_WORDS)):
                    warns.append(f"{where}: possible personal name in a press story: “{m.group(0)}” (public role only)")
        hl = s.get("headline", "")
        if where != "lives" and not where.startswith("more"):
            headlines.append(hl)
            if len(hl) > 75:
                warns.append(f"{where}: headline is {len(hl)} characters: {hl}")
            if DIRECTOR in hl:
                warns.append(f"{where}: the Director is in a headline")
        if where not in ("lives", "chart") and s.get("item") in P:
            try:
                if not connection(P[s.get("connection_item", s["item"])], s.get("areas")):
                    fails.append(f"{where}: no connection line can be generated (no work area): out")
            except ValueError as e:
                fails.append(f"{where}: {e}")
        it = P.get(s.get("item"))
        if it and it["date"] and pillar in USE_BY and where != "chart" and s.get("type") not in ("archive", "paper"):
            age = (dt.date.fromisoformat(built) - dt.date.fromisoformat(it["date"][:10])).days
            if age > USE_BY[pillar]:
                warns.append(f"{where}: item is {age} days old (use-by for {pillar}: {USE_BY[pillar]} days)")

    names: dict = {}
    for hl in headlines:
        for m in re.finditer(r"\b([A-ZÀ-Ž][a-zà-ž]+(?:\s[A-ZÀ-Ž][a-zà-ž]+)+)\b", hl):
            names.setdefault(m.group(1), []).append(hl)
    for n, hls in names.items():
        if len(hls) > 1:
            fails.append(f"“{n}” appears in {len(hls)} headlines")

    q = ed.get("question", {})
    for i in [q.get("item"), q.get("also_fact")]:
        if i and i not in P:
            fails.append(f"question: item {i} is not in the pool")
    if q.get("type") == "number":
        src = sources_text([q["item"]], [])
        for n in numbers(q["answer"] + " " + q["question"]):
            if n not in src and not any(n == str(o["max"]) for o in q["options"]):
                fails.append(f"question: number {n} not found in its source")

    f = ed.get("feature") or {}
    for r in f.get("rows", []):
        until = P.get(r["item"], {}).get("meta", {}).get("until")
        if not until:
            fails.append(f"feature: deadline row {r['item']} has no closing date in the pool")
        elif until < date:
            fails.append(f"feature: deadline already passed: {P[r['item']]['title']} ({until})")
    c = ed.get("chart") or {}
    if c:
        vals = P.get(c["item"], {}).get("meta", {}).get("values") or {}
        if not vals:
            fails.append(f"chart: item {c['item']} has no data")
        elif c["type"] == "rank":
            got = [g for g in vals if c["year"] in vals[g]]
            if len(got) < 10:
                fails.append(f"chart: only {len(got)} countries have {c['year']} data")
            for g in c.get("highlight", []):
                if c["year"] not in vals.get(g, {}):
                    fails.append(f"chart: highlighted {g} has no {c['year']} value")
            if any(vals[g][c["year"]] < 0 for g in got):
                fails.append("chart: negative values; a ranked bar chart cannot show them")
        elif c["geo"] not in vals:
            fails.append(f"chart: no series for {c['geo']}")

    o = ed.get("out") or {}
    last = (dt.date.fromisoformat(date) + dt.timedelta(days=6)).isoformat()
    for k, x in enumerate(o.get("items", []) + o.get("also", [])):
        it = next((i for i in pool["items"] if i["url"] == x["url"]), None)
        if not it:
            fails.append(f"out[{k}]: event page not in the pool (fetch --only events): {x['url']}")
            continue
        if x.get("date") and not date <= x["date"] <= last:
            fails.append(f"out[{k}]: {x['date']} is outside {date}–{last}: {x.get('title', x.get('text', ''))[:50]}")
        src = sources_text([it["id"]], [])
        when = f"{int(x['date'][8:])} {x.get('start', '')}" if x.get("date") else ""
        text = " ".join([when, x.get("title", ""), x.get("trail", ""), x.get("meta", ""), x.get("listen", ""), x.get("text", "")])
        for n in numbers(text):
            if n not in src:
                fails.append(f"out[{k}]: number {n} not on the event page ({x.get('title', x.get('text', ''))[:40]})")
        for q in re.findall(r"“([^”]+)”", text):
            if norm(q).strip(" .,") not in src:
                fails.append(f"out[{k}]: quotation not found verbatim on the event page: “{q}”")

    d = ed.get("diary", {})
    for x in d.get("coming", []) + [ev for day in d.get("days", []) for ev in day["events"]] + d.get("more", []):
        if x.get("date") and x["date"] < date:
            fails.append(f"diary: past event {x['text']} ({x['date']})")
        if x.get("url") and not url_ok(x["url"]):
            fails.append(f"diary: URL not from the pool: {x['url']}")
        if x.get("item") and x["item"] not in P:
            fails.append(f"diary: item {x['item']} is not in the pool")

    count = len(stories_of(ed)) + (1 if q else 0) + (1 if d else 0)
    if count > BUDGET:
        warns.append(f"{count} items on the page (budget about 12, at most {BUDGET})")

    if page and page.exists():
        text = page.read_text("utf-8")
        anchors = set(re.findall(r'\bid="([^"]+)"', text))
        for u in re.findall(r'<a\b[^>]*href="([^"]+)"', text):
            u = u.replace("&amp;", "&")
            if u.startswith("#"):
                if u[1:] not in anchors:
                    fails.append(f"page: link to a missing anchor: {u}")
                continue
            if u.startswith("/") and not u.startswith("//"):
                path = ROOT / u.split("?")[0].split("#")[0].lstrip("/")
                if not path.exists() and not u.endswith("/"):
                    fails.append(f"page: internal link to a missing file: {u}")
                continue
            if u.startswith(ALLOWED_EXTERNAL) or url_ok(u) or url_ok(SITE + u):
                continue
            fails.append(f"page: link not from the pool: {u}")
    elif page:
        warns.append("page not rendered yet: run pipeline.daily.render first to check its links")
    return fails, warns, count


def report(label: str, fails: list[str], warns: list[str], count: int) -> None:
    for w in warns:
        print(f"  warning  {w}")
    for f in fails:
        print(f"  FAIL     {f}")
    print(f"{label}: {count} items · {len(fails)} failures · {len(warns)} warnings")


def main(argv: list[str]) -> int:
    failed = False
    if "--lab" in argv:
        for f in sorted((DAILY / "lab").glob("*/*/edition.json")):
            ed = json.loads(f.read_text("utf-8"))
            fails, warns, n = check(ed, f.parent / "index.html")
            report(str(f.parent.relative_to(DAILY)), fails, warns, n)
            failed |= bool(fails)
        return 1 if failed else 0
    date = argv[0] if argv else max(p.stem for p in (DAILY / "editions").glob("*.json"))
    ed = json.loads((DAILY / "editions" / f"{date}.json").read_text("utf-8"))
    fails, warns, n = check(ed, DAILY / date / "index.html")
    report(date, fails, warns, n)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
