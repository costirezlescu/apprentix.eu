"""Source watch: what changed upstream that a person should look at.

  python -m pipeline.watch              check, write data/watch/report.json, print a summary
  python -m pipeline.watch --markdown   same, but print the GitHub issue body (empty if nothing to do)
  python -m pipeline.watch --ack        accept everything currently reported as reviewed
                                        (and snooze "probably out" reminders for 3 months)

The weekly refresh keeps known datasets current by itself. This catches what
it cannot: new datasets, renamed release files, refused downloads and overdue
releases. Run after `python -m pipeline.run` (it reads data/sources.json and
the files connectors write).

Checks
  1. Cedefop catalogue on data.europa.eu: new datasets, or a changed issued/modified date.
  2. Eurostat table of contents: new datasets whose title concerns VET or apprenticeship.
  3. Connector warnings and failures (e.g. a refused download where a stored copy was used).
  4. Release cadence: a source past its usual publication date, i.e. probably a new
     release exists under a new file name, or a hand-curated source is due a check.
  5. data.europa.eu catalogue: apprenticeship datasets newly found on European portals
     (candidates for new connectors). Informational.

data/watch/known.json holds what has been reviewed. On the first run it is
seeded from the current state, so only later changes are reported.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import sys

from .common import DATA, PUBLISHED, RAW, fetch, now_iso, read_json, today, write_json

WATCH = DATA / "watch"
KNOWN = WATCH / "known.json"
REPORT = WATCH / "report.json"

EUROSTAT_TOC = "https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt?lang=en"
EUROSTAT_TERMS = re.compile(
    r"vocational|apprentic|work[- ]based|\bIVET\b|\bCVET\b|initial vocational|continuing vocational|"
    r"work experience|orientation of (the )?programme|programme orientation", re.I)

CEDEFOP_DATASETS = "https://www.cedefop.europa.eu/en/datasets"


def _cadence_rules() -> list[dict]:
    """Publication cycles. 'version' is the year-month of the release we hold."""
    from .sources import cedefop_files, cedefop_skills

    def ym(text: str, default_month: int) -> tuple[int, int]:
        m = re.search(r"(20\d\d)(?:[-_ ](0[1-9]|1[0-2]))?", text)
        return int(m.group(1)), int(m.group(2) or default_month)

    rules = [
        {"id": "cedefop-kivet", "name": "Cedefop Key indicators on VET",
         "version": ym(cedefop_files.FILES["kivet"]["url"], 7), "cycle": 12, "grace": 2,
         "check": cedefop_files.FILES["kivet"]["landing"],
         "action": "If Cedefop has published a new Key indicators file, put its download link in FILES['kivet'] in pipeline/sources/cedefop_files.py."},
        {"id": "cedefop-timeline", "name": "Cedefop Timeline of VET policies",
         "version": (cedefop_files.FILES["timeline"]["year"], 7), "cycle": 12, "grace": 3,
         "check": cedefop_files.FILES["timeline"]["landing"],
         "action": "The connector tries next year's file name automatically. If the name changed, update FILES['timeline'] in pipeline/sources/cedefop_files.py."},
        {"id": "cedefop-esi", "name": "Cedefop European Skills Index",
         "version": ym(cedefop_skills.FILES["esi-2024"]["file"], 6), "cycle": 24, "grace": 4,
         "check": cedefop_skills.FILES["esi-2024"]["landing"],
         "action": "If a new ESI edition exists, add it to FILES in pipeline/sources/cedefop_skills.py."},
        {"id": "cedefop-clssi", "name": "Cedefop labour and skills shortage index",
         "version": ym(cedefop_skills.FILES["clssi"]["file"], 6), "cycle": 12, "grace": 3,
         "check": cedefop_skills.FILES["clssi"]["landing"],
         "action": "Update FILES['clssi'] in pipeline/sources/cedefop_skills.py with the new file name."},
        {"id": "cedefop-stas", "name": "Cedefop STAS skills forecasts",
         "version": ym(cedefop_skills.FILES["stas"]["file"], 2), "cycle": 6, "grace": 2,
         "check": cedefop_skills.FILES["stas"]["landing"],
         "action": "Update FILES['stas'] in pipeline/sources/cedefop_skills.py with the new release file name."},
    ]
    fiches = sorted((RAW / "cedefop-schemes").glob("*-fiche-answers.txt"))
    if fiches:
        d = fiches[-1].name[:10]
        rules.append({
            "id": "cedefop-scheme-fiches", "name": "Cedefop apprenticeship scheme fiches (hand-curated)",
            "version": (int(d[:4]), int(d[5:7])), "cycle": 12, "grace": 0,
            "check": "https://www.cedefop.europa.eu/en/tools/apprenticeship-schemes/scheme-fiches",
            "action": "Re-read the fiches in a browser with pipeline/curate/fiche_extract.js, then run python -m pipeline.curate.merge_fiches (see README). Cedefop updates fiches between major rounds."})
    return rules


# ------------------------------------------------------------------ checks --

def check_cedefop_catalogue(known: dict) -> tuple[list[dict], dict]:
    path = WATCH / "cedefop-catalogue.json"
    if not path.exists():
        return [], {}
    current = {d["id"]: {"title": d.get("title"), "issued": d.get("issued"), "modified": d.get("modified"),
                         "portal_url": d.get("portal_url")} for d in read_json(path)["datasets"]}
    items = []
    seen = known.get("cedefop_catalogue", {})
    for i, d in current.items():
        old = seen.get(i)
        if old is None:
            items.append({"kind": "new-dataset", "source": "Cedefop", "title": d["title"] or i,
                          "detail": f"New dataset in Cedefop's data.europa.eu catalogue (issued {d['issued'] or 'n/a'}).",
                          "url": d["portal_url"], "action": "Decide whether to add it: a new connector, or an entry in pipeline/sources/_catalogue.py."})
        elif (old.get("issued"), old.get("modified")) != (d["issued"], d["modified"]):
            items.append({"kind": "updated-dataset", "source": "Cedefop", "title": d["title"] or i,
                          "detail": f"Issued/modified changed: {old.get('issued')}/{old.get('modified')} → {d['issued']}/{d['modified']}.",
                          "url": d["portal_url"], "action": "If Apprentix uses this dataset and the file name changed, update the connector's URL."})
    return items, current


def check_eurostat(known: dict) -> tuple[list[dict], dict]:
    body = fetch(EUROSTAT_TOC, timeout=180).decode("utf-8", "replace")
    rows = csv.reader(io.StringIO(body), delimiter="\t")
    next(rows, None)
    current = {}
    for r in rows:
        if len(r) < 3 or r[2].strip() not in ("dataset", "table"):
            continue
        title, code = r[0].strip(), r[1].strip()
        if EUROSTAT_TERMS.search(title):
            current[code] = title
    items = []
    seen = known.get("eurostat", {})
    for code, title in sorted(current.items()):
        if seen and code not in seen:
            items.append({"kind": "new-dataset", "source": "Eurostat", "title": f"{code}: {title}",
                          "detail": "New Eurostat dataset whose title concerns VET or apprenticeship.",
                          "url": f"https://ec.europa.eu/eurostat/databrowser/view/{code}/default/table?lang=en",
                          "action": "If relevant, add a spec to SPECS in pipeline/sources/eurostat.py."})
    return items, current


def check_connectors() -> list[dict]:
    path = DATA / "sources.json"
    if not path.exists():
        return []
    items = []
    for s in read_json(path)["sources"]:
        st = s.get("status") or {}
        for w in st.get("warnings", []):
            items.append({"kind": "warning", "source": s["name"], "title": f"{s['id']}: {w[:120]}",
                          "detail": w, "url": s.get("homepage"),
                          "action": "Check the source by hand; if a file moved, update the connector's URL."})
        if st.get("result") == "error":
            items.append({"kind": "failure", "source": s["name"], "title": f"{s['id']} failed",
                          "detail": st.get("detail", ""), "url": s.get("homepage"),
                          "action": "See the workflow log. The previous data stays published until fixed."})
    return items


SNOOZE_MONTHS = 3


def check_cadence(known: dict) -> list[dict]:
    now = dt.date.fromisoformat(today())
    snoozed = known.get("snoozed", {})
    items = []
    for r in _cadence_rules():
        if snoozed.get(r["id"], "") > today():
            continue
        y, m = r["version"]
        months = y * 12 + (m - 1) + r["cycle"] + r["grace"]
        due = dt.date(months // 12, months % 12 + 1, 1)
        if now >= due:
            items.append({"kind": "overdue", "rule": r["id"], "source": r["name"], "title": f"{r['name']}: a newer release is probably out",
                          "detail": f"We hold the {y}-{m:02d} release; this source usually updates every {r['cycle']} months.",
                          "url": r["check"], "action": r["action"]})
    return items


def check_catalogue(known: dict) -> tuple[list[dict], list[str]]:
    path = PUBLISHED / "data-catalogue" / "records.json"
    if not path.exists():
        return [], []
    recs = read_json(path)
    ids = sorted(r["id"] for r in recs)
    seen = set(known.get("catalogue_ids", []))
    if not seen:
        return [], ids
    new = [r for r in recs if r["id"] not in seen and r.get("concerns_apprenticeship") == "Yes"]
    items = [{"kind": "candidate", "source": r.get("publisher") or "data.europa.eu",
              "title": f"{r.get('country', '')}: {r.get('title', r['id'])}"[:160],
              "detail": "Newly listed open dataset about apprenticeship.", "url": r.get("portal_url") or r.get("landing_page"),
              "action": "Consider a national connector if it is machine-readable and openly licensed."}
             for r in sorted(new, key=lambda r: (r.get("country", ""), r.get("title", "")))[:40]]
    return items, ids


# ------------------------------------------------------------------ output --

ORDER = {"failure": 0, "warning": 1, "new-dataset": 2, "updated-dataset": 3, "overdue": 4, "candidate": 5}
HEADINGS = {
    "failure": "Connectors that failed",
    "warning": "Warnings (possibly stale data)",
    "new-dataset": "New datasets at the sources",
    "updated-dataset": "Revised datasets",
    "overdue": "Releases that are probably out (or due a check)",
    "candidate": "New apprenticeship datasets on European portals (candidates)",
}


def markdown(items: list[dict]) -> str:
    if not items:
        return ""
    out = ["The weekly refresh found things that need a person. Data already handled automatically is not listed here.", ""]
    for kind in sorted({i["kind"] for i in items}, key=ORDER.get):
        out.append(f"### {HEADINGS[kind]}")
        for i in [x for x in items if x["kind"] == kind]:
            link = f" — [open]({i['url']})" if i.get("url") else ""
            out.append(f"- **{i['title']}**{link}  \n  {i['detail']}  \n  _Action:_ {i['action']}")
        out.append("")
    out.append("When an item is dealt with (or deliberately ignored), run `python -m pipeline.watch --ack` and commit "
               "`data/watch/known.json`. That also snoozes \"probably out\" reminders for 3 months; they clear for good once the connector holds the newer release.")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    known = read_json(KNOWN) if KNOWN.exists() else {}
    first_run = not known

    items, cat_now = check_cedefop_catalogue(known)
    try:
        eu_items, eu_now = check_eurostat(known)
    except Exception as e:  # the watch must never break the refresh
        eu_items, eu_now = [{"kind": "warning", "source": "Eurostat", "title": "Eurostat catalogue check failed",
                             "detail": str(e)[:200], "url": EUROSTAT_TOC, "action": "Usually transient; check next week."}], known.get("eurostat", {})
    cand_items, cat_ids = check_catalogue(known)
    items += eu_items + check_connectors() + check_cadence(known) + cand_items
    items.sort(key=lambda i: (ORDER[i["kind"]], i["source"], i["title"]))

    if first_run or "--ack" in argv:
        snoozed = {k: v for k, v in known.get("snoozed", {}).items() if v > today()}
        if "--ack" in argv:
            now = dt.date.fromisoformat(today())
            m = now.year * 12 + now.month - 1 + SNOOZE_MONTHS
            until = dt.date(m // 12, m % 12 + 1, now.day if now.day <= 28 else 28).isoformat()
            snoozed.update({i["rule"]: until for i in items if i["kind"] == "overdue"})
        write_json(KNOWN, {
            "description": "What has been reviewed. pipeline/watch.py reports only changes against this. Update with: python -m pipeline.watch --ack",
            "acknowledged_at": today(),
            "cedefop_catalogue": cat_now,
            "eurostat": eu_now,
            "catalogue_ids": cat_ids,
            "snoozed": dict(sorted(snoozed.items())),
        })
        if first_run:
            items = [i for i in items if i["kind"] not in ("new-dataset", "updated-dataset", "candidate")]
        else:
            items = [i for i in items if i["kind"] in ("failure", "warning")]

    report = {"description": "Items from the source watch that need a person. See pipeline/watch.py.",
              "checked_at": now_iso(), "count": len(items), "items": items}
    if REPORT.exists() and read_json(REPORT).get("items") == items:
        report["checked_at"] = read_json(REPORT).get("checked_at", report["checked_at"])
    write_json(REPORT, report)

    if "--markdown" in argv:
        sys.stdout.write(markdown(items))
    else:
        print(f"Source watch: {len(items)} item(s) need attention" + (" (first run: state seeded)" if first_run else ""))
        for i in items:
            print(f"  [{i['kind']}] {i['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
