"""Build the 'nqf-qualification-levels' dataset from Cedefop's NQF online tool.

  python -m pipeline.curate.nqf_levels

The NQF tool's country pages (state of play 2024) were read in a browser,
because Cedefop's pages refuse scripted requests, and their level tables saved
to data/raw/cedefop-nqf/<date>-level-tables.txt, one line per qualification type:

  C|<page slug>|<country name as shown>
  Q|<page slug>|<NQF level>|<EQF level>|<qualification type>

Blank EQF cells were merged (rowspan) on the page, so the EQF level of the row
above applies; such values are marked eqf_from_merged_cell. A blank on a
country's lowest level is left blank (the merge cannot be confirmed).

Each record is one qualification type placed at a national (NQF) and European
(EQF) level. 'Apprenticeship or craft' is an Apprentix flag: Yes when the type
name mentions apprenticeship, journeyman/craftsperson, crafts, dual training or
the German/Dutch/Nordic terms for them (rule in APPRENTICESHIP below).
"""

from __future__ import annotations

import re

from ..common import PUBLISHED, RAW, geo_code, write_json

DATASET = "nqf-qualification-levels"
PAGE = "https://www.cedefop.europa.eu/en/tools/nqfs-online-tool/countries/{}"

COMMUNITIES = {
    "Belgium-DE": ("BE", "Belgium — German-speaking community"),
    "Belgium-FL": ("BE", "Belgium — Flanders"),
    "Belgium-FR": ("BE", "Belgium — French community"),
}
NAMES = {"Bosnia & Herzegovina": "Bosnia and Herzegovina", "Czech Republic": "Czechia",
         "North Macedonia": "North Macedonia", "Turkey": "Türkiye", "Kosovo": "Kosovo*"}

APPRENTICESHIP = re.compile(
    r"apprentic|journeym|craftsperson|craftsman|craft|\bdual\b|lehr|gesell|meister|"
    r"vakbekwaam|gezel|svenne|fagbrev|svennebrev|oppisopim|tirocin", re.I)


# Law names that mention crafts without the qualification being a craft/apprenticeship one.
NOT_A_QUALIFICATION = re.compile(r"Crafts and Trades Regulation Code|Handwerksordnung|HwO", re.I)


def flag(code: str) -> str:
    iso = {"EL": "GR", "UK": "GB"}.get(code, code)
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in iso) if code and len(iso) == 2 else ""


def main() -> None:
    files = sorted((RAW / "cedefop-nqf").glob("*-level-tables.txt"))
    if not files:
        raise SystemExit("No data/raw/cedefop-nqf/*-level-tables.txt")
    path = files[-1]
    from ..common import countries
    by_name = {c["name"]: c["code"] for c in countries()["by_code"].values()}
    names, rows = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("C|"):
            _, slug, cname = line.split("|", 2)
            names[slug] = cname
        elif line.startswith("Q|"):
            _, slug, nqf, eqf, qtype = line.split("|", 4)
            rows.append((slug, nqf.strip(), eqf.strip(), qtype.strip()))

    placeholders = {"(not available)", "currently no qualifications", "not part of the nkr"}
    lowest = {}
    for slug, nqf, _, _ in rows:
        lowest[slug] = nqf  # rows run from the highest level down
    records, seen, carry = [], {}, {}
    for slug, nqf, eqf, qtype in rows:
        if not eqf and nqf != lowest[slug]:
            eqf, inferred = carry.get(slug, ""), True
        else:
            inferred = False
            if eqf:
                carry[slug] = eqf
        if not qtype or qtype.lower() in placeholders:
            continue
        cname = names.get(slug, slug)
        if cname in COMMUNITIES:
            code, country = COMMUNITIES[cname]
        else:
            country = NAMES.get(cname, cname)
            code = by_name.get(country) or geo_code(country)
        base = f"nqf-{slug}-{re.sub(r'[^a-z0-9]+', '-', nqf.lower()).strip('-') or 'x'}"
        seen[base] = seen.get(base, 0) + 1
        eqf_levels = sorted({int(x) for x in re.findall(r"\b[1-8]\b", eqf)}) if "No EQF" not in eqf else []
        rec = {
            "id": f"{base}-{seen[base]}",
            "country": country,
            "country_code": code,
            "flag": flag(code) if code else None,
            "nqf_level": nqf or None,
            "eqf_level": [f"EQF {x}" for x in eqf_levels] or (["Not referenced to the EQF"] if "No EQF" in eqf else None),
            "eqf_from_merged_cell": "Yes" if inferred and eqf_levels else None,
            "qualification_type": qtype,
            "apprenticeship_or_craft": "Yes" if APPRENTICESHIP.search(NOT_A_QUALIFICATION.sub("", qtype)) else "No",
            "source_url": PAGE.format(slug + "-2024"),
            "reference_year": "2024",
            "retrieved": path.name[:10],
        }
        records.append({k: v for k, v in rec.items() if v not in (None, "", [])})
    write_json(PUBLISHED / DATASET / "records.json", records)
    print(f"{len(records)} qualification types from {path.name}")


if __name__ == "__main__":
    main()
