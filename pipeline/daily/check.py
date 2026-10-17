"""Check a Cedefop Daily edition against the pool it was written from.

  python -m pipeline.daily.check 2026-10-19        exit 1 if any check fails

Failures (the edition must not go out):
  * a referenced item is not in the pool;
  * a URL in the edition or in the rendered page does not come from the pool
    (Apprentix's own pages and the paper's anchors excepted);
  * a number in a story is not found in that story's sources;
  * a quotation is not found verbatim in that story's sources;
  * a story has no connection line;
  * a banned word, a sensitive topic (held for the editor), or a person in more
    than one headline;
  * an event in the diary before the edition date.
Warnings (an editor may want to look): long headlines, items past their use-by date,
the Director in a headline.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unicodedata

from ..common import ROOT
from .render import DAILY, SITE, connection

USE_BY = {"cedefop": 7, "policy": 3, "agencies": 10, "countries": 30, "field": 8, "debate": 8, "research": 30,
          "data": 365, "people": 30}
BANNED = ["landmark", "ambitious", "controversial", "groundbreaking", "game-changer", "game changer",
          "unprecedented", "historic", "revolutionary", "world-class", "cutting-edge", "we ", "our "]
SENSITIVE = ["olaf", "audit", "ombudsman", "litigation", "lawsuit", "court of justice ruling", "died", "death of",
             "disciplinary", "harassment", "fraud investigation", "security incident"]
DIRECTOR = "Siebel"
ORG_WORDS = {"Social", "Insurance", "Policy", "Markets", "Employers", "Summit", "Alliance", "Institute", "Centre",
             "Center", "Union", "Council", "Commission", "European", "German", "French", "Spanish", "Greek", "Italian",
             "Irish", "British", "Ministry", "Education", "Agency", "Authority", "Foundation", "Association",
             "Parliament", "Office", "School", "Schools", "University", "College", "Survey", "Forum", "Network",
             "Board", "Fund", "Bank", "Organisation", "Organization", "Federation", "Chamber", "Trade", "Labour"}
ALLOWED_EXTERNAL = ("https://fonts.googleapis.com/", "https://github.com/costirezlescu/apprentix.eu/issues")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).lower()


def numbers(text: str) -> list[str]:
    out = []
    for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:st|nd|rd|th)?(?!\w)", text):
        out.append(m.group(1).replace(",", ""))
    return out


def main(argv: list[str]) -> int:
    date = argv[0] if argv else max(p.stem for p in (DAILY / "editions").glob("*.json"))
    ed = json.loads((DAILY / "editions" / f"{date}.json").read_text("utf-8"))
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
        m = re.fullmatch(re.escape(SITE) + r"/pages/duel\.html\?a=([A-Z]{2})&b=([A-Z]{2})", u)
        if m and duel and {m.group(1), m.group(2)} <= set(duel["meta"]["countries"]):
            return True
        return False

    def sources_text(ids: list[str], urls: list[str]) -> str:
        parts = [json.dumps(P[i], ensure_ascii=False) for i in ids if i in P]
        parts += [json.dumps(i, ensure_ascii=False) for i in pool["items"] if i["url"] in urls]
        text = norm(" ".join(parts))
        decimal = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", text)     # "5,6 Prozent" → 5.6
        return text + " " + " ".join(numbers(text)) + " " + " ".join(numbers(decimal))

    stories = []      # (where, pillar, headline, texts, item ids, urls, areas)

    def add(where, pillar, c, texts):
        ids = [x for x in [c.get("item"), c.get("connection_item"), *c.get("also", [])] if x]
        urls = [l["url"] for l in c.get("links", []) if l.get("url")] + ([c["url"]] if c.get("url") else [])
        ids_l = [l["item"] for l in c.get("links", []) if l.get("item")]
        for i in ids_l:
            if i not in P:
                fails.append(f"{where}: linked item {i} is not in the pool")
        stories.append((where, pillar, c.get("headline", ""), texts, ids, urls, c))

    lead = ed["lead"]
    add("lead", lead["pillar"], lead, [lead["headline"], lead["standfirst"], *lead["body"]])
    for s in ed["sections"]:
        for k, b in enumerate(s["blocks"]):
            where = f"{s['id']}[{k}]"
            if b["type"] == "card":
                add(where, s["id"], b, [b["headline"], b["standfirst"], *b.get("body", [])])
            elif b["type"] == "briefs":
                for r in b["items"]:
                    rr = dict(r)
                    if b.get("item") and not r.get("item"):
                        rr["item"] = b["item"]
                    add(where, s["id"], rr, [r["headline"], r["text"]])
            elif b["type"] in ("portraits", "pulse", "cited", "number", "insight", "dyk", "myth"):
                for i in [b.get("item"), *b.get("items", []), *b.get("facts", []), b.get("also_fact")]:
                    if i and i not in P:
                        fails.append(f"{where}: item {i} is not in the pool")
                for l in b.get("links", []):
                    if l.get("item"):
                        if l["item"] not in P:
                            fails.append(f"{where}: linked item {l['item']} is not in the pool")
                    elif not url_ok(l["url"]):
                        fails.append(f"{where}: URL not from the pool: {l['url']}")
                for i, note in b.get("notes", {}).items():
                    src = sources_text([i], [])
                    for n in numbers(note):
                        if n not in src and n not in date:
                            fails.append(f"{where}: number {n} not found in its source ({note[:60]}…)")
                if b["type"] == "number":
                    src = sources_text([b["item"]], [])
                    for n in numbers(b["answer"] + " " + b["question"]):
                        if n not in src and not any(n == str(o["max"]) for o in b["options"]):
                            fails.append(f"{where}: number {n} not found in its source")

    headlines = []
    for where, pillar, hl, texts, ids, urls, c in stories:
        for i in ids:
            if i not in P:
                fails.append(f"{where}: item {i} is not in the pool")
        ids = [i for i in ids if i in P]
        for u in urls:
            if not url_ok(u):
                fails.append(f"{where}: URL not from the pool: {u}")
        src = sources_text(ids, urls)
        body = " ".join(texts)
        for n in numbers(body):
            if n not in src and n not in date:
                fails.append(f"{where}: number {n} not found in its sources (“{hl or body[:50]}”)")
        press = [P[i] for i in ids if P[i]["circle"] in ("press", "4")]
        for q in re.findall(r"“([^”]+)”", body):
            if norm(q).strip(" .,") not in src:
                fails.append(f"{where}: quotation not found verbatim in its sources: “{q}”")
            if press and len(q.split()) > 12:
                fails.append(f"{where}: quotation from the press is longer than 12 words (copyright): “{q[:40]}…”")
        if press:
            # Private individuals in press stories are not named: flag capitalised name pairs for a look.
            allowed = {w for i in press for w in re.findall(r"[A-ZÀ-Ž][\wÀ-ž’'-]+", i["meta"].get("outlet", ""))}
            for m in re.finditer(r"(?<![.!?] )(?<!^)\b([A-ZÀ-Ž][a-zà-ž]+) ([A-ZÀ-Ž][a-zà-ž]+)\b", " ".join(texts[1:])):
                if not ({m.group(1), m.group(2)} & (allowed | ORG_WORDS)):
                    warns.append(f"{where}: possible personal name in a press story: “{m.group(0)}” (public role only)")
        low = " " + norm(body) + " "
        for w in BANNED:
            if f" {w}" in low and not any(f" {w}" in " " + norm(q) for q in re.findall(r"“([^”]+)”", body)):
                fails.append(f"{where}: banned word “{w.strip()}”")
        for w in SENSITIVE:
            if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low):
                fails.append(f"{where}: sensitive topic “{w}”: HOLD for the editor")
        if hl:
            headlines.append(hl)
            if len(hl) > 75:
                warns.append(f"{where}: headline is {len(hl)} characters: {hl}")
            if DIRECTOR in hl:
                warns.append(f"{where}: the Director is in a headline")
        if c.get("item") in P and (c.get("headline") and where != "lead" and "type" not in c or c.get("type") == "card"):
            try:
                if not connection(P[c["item"]], c.get("areas")):
                    fails.append(f"{where}: no connection line can be generated (no work area): out")
            except ValueError as e:
                fails.append(f"{where}: {e}")
        if c.get("item") in P and P[c["item"]]["date"] and pillar in USE_BY and c.get("type") == "card":
            age = (dt.date.fromisoformat(date) - dt.date.fromisoformat(P[c["item"]]["date"][:10])).days
            if age > USE_BY[pillar]:
                warns.append(f"{where}: item is {age} days old (use-by for {pillar}: {USE_BY[pillar]} days)")
    try:
        connection(P[lead.get("connection_item", lead["item"])], lead.get("areas")) or fails.append("lead: no connection line")
    except ValueError as e:
        fails.append(f"lead: {e}")

    names = {}
    for hl in headlines:
        for m in re.finditer(r"\b([A-ZÀ-Ž][a-zà-ž]+(?:\s[A-ZÀ-Ž][a-zà-ž]+)+)\b", hl):
            names.setdefault(m.group(1), []).append(hl)
    for n, hls in names.items():
        if len(hls) > 1:
            fails.append(f"“{n}” appears in {len(hls)} headlines")

    for x in ed["week_ahead"]["coming"] + [e for d in ed["week_ahead"]["days"] for e in d["events"]]:
        if x.get("date") and x["date"] < date:
            fails.append(f"diary: past event {x['text']} ({x['date']})")
        if x.get("url") and not url_ok(x["url"]):
            fails.append(f"diary: URL not from the pool: {x['url']}")
        if x.get("item") and x["item"] not in P:
            fails.append(f"diary: item {x['item']} is not in the pool")

    page = DAILY / date / "index.html"
    if page.exists():
        html_text = page.read_text("utf-8")
        ids = set(re.findall(r'\bid="([^"]+)"', html_text))
        for u in re.findall(r'<a\b[^>]*href="([^"]+)"', html_text):
            u = u.replace("&amp;", "&")
            if u.startswith("#") and u[1:] not in ids:
                fails.append(f"page: link to a missing anchor: {u}")
            if u.startswith(("#", "/")) and not u.startswith("//"):
                if u.startswith("/") and not (ROOT / u.split("?")[0].split("#")[0].lstrip("/")).exists() \
                        and not u.endswith("/"):
                    fails.append(f"page: internal link to a missing file: {u}")
                continue
            if u.startswith(ALLOWED_EXTERNAL) or url_ok(u) or url_ok(SITE + u):
                continue
            fails.append(f"page: link not from the pool: {u}")
    else:
        warns.append("page not rendered yet: run pipeline.daily.render first to check its links")

    for w in warns:
        print(f"  warning  {w}")
    for f in fails:
        print(f"  FAIL     {f}")
    print(f"{date}: {len(stories)} stories checked · {len(fails)} failures · {len(warns)} warnings")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
