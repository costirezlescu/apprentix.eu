"""Build the 'vet-systems' dataset: a link-and-credit record per country for Cedefop's VET in Europe database.

  python -m pipeline.curate.vet_systems

The VET in Europe country descriptions are long texts written by ReferNet
partners; Apprentix links to them rather than copying them. Read in a browser
(Cedefop's pages refuse scripted requests) and saved to
data/raw/cedefop-vet-in-europe/<date>-systems.txt.
"""

from __future__ import annotations

import re

from ..common import PUBLISHED, RAW, countries, write_json

BASE = "https://www.cedefop.europa.eu"
SYSTEM = BASE + "/en/tools/vet-in-europe/systems/{}"
PDF = BASE + "/en/print/pdf/node/{}"


def flag(code: str) -> str:
    iso = {"EL": "GR", "UK": "GB"}.get(code, code)
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in iso)


def main() -> None:
    path = sorted((RAW / "cedefop-vet-in-europe").glob("*-systems.txt"))[-1]
    by_name = {c["name"]: c["code"] for c in countries()["by_code"].values()}
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("V|"):
            continue
        _, slug, country, chart, node, spotlight, cite = line.split("|", 6)
        year = re.search(r"\((20\d\d)\)", cite)
        partner = re.search(r"Cedefop[,;]\s*&?\s*(.+?)\s*\(20\d\d\)", cite)
        code = by_name[country]
        rec = {
            "id": "vet-" + slug,
            "country": country,
            "country_code": code,
            "flag": flag(code),
            "title": f"VET in {country}: system description",
            "version": year.group(1) if year else None,
            "refernet_partner": partner.group(1).strip().rstrip(".") if partner else None,
            "has_spotlight": "Yes" if spotlight == "yes" else "No",
            "source_url": SYSTEM.format(slug),
            "full_description_pdf": PDF.format(node),
            "spotlight_pdf": PDF.format(node) + "?t=spotlight" if spotlight == "yes" else None,
            "system_chart": BASE + chart if chart else None,
            "citation": cite.strip() + " " + SYSTEM.format(slug),
            "retrieved": path.name[:10],
        }
        records.append({k: v for k, v in rec.items() if v})
    records.sort(key=lambda r: r["country"])
    write_json(PUBLISHED / "vet-systems" / "records.json", records)
    print(f"{len(records)} VET system descriptions from {path.name}")


if __name__ == "__main__":
    main()
