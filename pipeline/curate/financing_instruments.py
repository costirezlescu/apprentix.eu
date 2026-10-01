"""Build the 'financing-instruments' dataset from Cedefop's financing apprenticeships database.

  python -m pipeline.curate.financing_instruments

Cedefop's pages refuse scripted requests, so the instrument pages were read in a
browser (one request every 1.5 s) and saved to
data/raw/cedefop-financing/<date>-instruments.jsonl: one JSON object per
instrument {slug, title, f: {Cedefop field label: text}, schemes: [slugs]} and
one {scheme_slug, scheme_title} line per apprenticeship scheme. Field keys are
shortened (see FIELDS); "na"/"nap" values were dropped. Long texts were
cut at about 320 characters (marked with "…"); each record links to its full
Cedefop page. The database's reference period is 2016–17 and it is not updated.
"""

from __future__ import annotations

import json
import re

from ..common import PUBLISHED, RAW, geo_code, write_json

DATASET = "financing-instruments"
BASE = "https://www.cedefop.europa.eu/en/tools/financing-apprenticeships/financing-instruments/"
SCHEME_BASE = "https://www.cedefop.europa.eu/en/tools/financing-apprenticeships/apprenticeship-schemes/"

# Short keys used in the raw extract → record fields.
FIELDS = {
    "n": "name_en", "c": "country", "ty": "type", "lv": "level", "rg": "region", "pa": "area",
    "se": "sectors", "lb": "legal_basis", "ob": "objectives", "yi": "year_introduced",
    "yt": "year_terminated", "el": "eligible_groups", "ed": "eligible_training",
    "src": "financing_source", "fo": "financing_formula", "co": "eligible_costs",
    "vo": "volume", "bu": "take_up",
}

NAMES = {"Czech Republic": "Czechia", "Slovak Republic": "Slovakia"}


def flag(code: str) -> str:
    iso = {"EL": "GR", "UK": "GB"}.get(code, code)
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in iso) if code and len(iso) == 2 else ""


def decade(y: str | None) -> str | None:
    m = re.search(r"(19|20)\d\d", y or "")
    if not m:
        return None
    yr = int(m.group(0))
    return "Before 1990" if yr < 1990 else f"{yr // 10 * 10}s"


def main() -> None:
    files = sorted((RAW / "cedefop-financing").glob("*-instruments.jsonl"))
    if not files:
        raise SystemExit("No data/raw/cedefop-financing/*-instruments.jsonl")
    path = files[-1]
    instruments, schemes = [], {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if "scheme_slug" in o:
            schemes[o["scheme_slug"]] = o["scheme_title"]
        else:
            instruments.append(o)

    from ..common import countries
    by_name = {c["name"]: c["code"] for c in countries()["by_code"].values()}
    records = []
    unknown_labels = set()
    for o in instruments:
        r = {"id": "fi-" + o["s"], "title": o.get("t") or o.get("n") or o["s"]}
        for short, value in o.items():
            if short in ("s", "t", "sc"):
                continue
            key = FIELDS.get(short)
            if key is None:
                unknown_labels.add(short)
                continue
            if value:
                r[key] = value
        raw_country = r.get("country", "")
        community = {"Belgium-FL": "Belgium — Flanders", "Belgium-FR": "Belgium — French community"}.get(raw_country)
        name = community or NAMES.get(raw_country, raw_country)
        r["country"] = name
        code = "BE" if community else (by_name.get(name) or geo_code(name))
        if code:
            r["country_code"] = code
            r["flag"] = flag(code)
        if r.get("type"):
            r["type"] = [t.strip() for t in re.split(r";|,(?![^()]*\))", r["type"]) if t.strip()]
        r["introduced"] = decade(r.get("year_introduced"))
        r["status"] = ("Ended or due to end" if re.search(r"\d{4}", r.get("year_terminated", ""))
                       else "Ongoing at the time of research (2016–17)")
        if r.get("eligible_training"):
            t = r["eligible_training"].lower()
            r["scope"] = ("Apprenticeship only" if re.search(r"only (supports|funds) apprentice|funds only apprentice|supports only apprentice|only apprentice", t)
                          else "Apprenticeship and other training")
        r["related_schemes"] = [schemes.get(s, s) for s in o.get("sc", [])]
        r["related_scheme_urls"] = [SCHEME_BASE + s for s in o.get("sc", [])]
        r["source_url"] = BASE + o["s"]
        r["retrieved"] = path.name[:10]
        records.append({k: v for k, v in r.items() if v not in (None, "", [])})
    records.sort(key=lambda r: (r.get("country", ""), r["title"]))
    if unknown_labels:
        print("Unmapped Cedefop field labels (add to FIELDS):", sorted(unknown_labels))
    write_json(PUBLISHED / DATASET / "records.json", records)
    print(f"{len(records)} instruments from {path.name}")


if __name__ == "__main__":
    main()
