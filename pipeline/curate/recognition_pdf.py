"""Extract Cedefop's recognition/validation mapping table from its PDF dataset.

  python -m pipeline.curate.recognition_pdf

Source: Cedefop (2026), "Recognition and validation of foreign VET qualifications in
Europe. Comparative insights for skills portability [Dataset]", DOI 10.2906/774317077022848.
Cedefop publishes this dataset only as a PDF; the newest copy in data/raw/cedefop/
(*-recognition_*dataset.pdf) is read.

Table 1 (pages 3-18) has one block per system (EU-27 + Iceland + Norway, Belgium split into
the Flemish and French Communities). Each block has three rows (information centre,
competent authority, applicable legal basis) across three purposes (further learning,
regulated employment, non-regulated employment), plus a fourth column, "Validation in
the labour market", which is one merged cell spanning the whole block.

The extraction is positional: words are assigned to columns by the table's vertical rules
and to rows by the row labels in the second column, so cells that wrap across lines and
pages are rebuilt in reading order. Text is kept as printed; only line breaks are joined
(a line ending in a hyphen is joined without a space, keeping the hyphen), a visibly
larger vertical gap inside a cell becomes a paragraph break ("\n"), and the few
non-breaking hyphens (U+2011) become plain hyphens.

Requires pdfplumber (pip install pdfplumber).
"""

from __future__ import annotations

import re
from pathlib import Path

from pdfplumber.utils.text import WordExtractor  # pip install pdfplumber

from ..common import PUBLISHED, RAW, geo_code, geo_name, countries, rel, sha256, write_json

DATASET_ID = "recognition-vet-qualifications"
OUT = PUBLISHED / DATASET_ID

DOI = "10.2906/774317077022848"
# Verified via the DOI, which resolves to data.europa.eu/88u/dataset/
# recognition_symeonidis_villalba_cedefop_2026_dataset (download URL of its PDF distribution).
SOURCE_URL = "https://www.cedefop.europa.eu/en/datasets/recognition-validation-VET-arrangements"
CITATION = ("Cedefop. (2026). Recognition and validation of foreign VET qualifications in Europe. "
            "Comparative insights for skills portability [Dataset]. Publications Office of the "
            "European Union. https://doi.org/" + DOI)

# Column boundaries (x, points) taken from the table's vertical rules on every page.
COL_EDGES = [113, 177, 328, 525, 678]
COLUMNS = ["country", "label", "further_learning", "regulated", "non_regulated", "labour_market"]

PURPOSES = {
    "further_learning": "For further learning",
    "regulated": "For employment (regulated professions)",
    "non_regulated": "For employment (non-regulated professions)",
}
ASPECTS = {
    "information_centre": ("Information centre", "Information centre"),
    "competent_authority": ("Competent authority", "Competent authority"),
    "legal_basis": ("Applicable legal basis", "Legal basis"),
}
LABEL_TO_ASPECT = {v[0]: k for k, v in ASPECTS.items()}

# Names as printed in the first column -> (country code, community or None).
SYSTEMS = {
    "Belgium (Flemish Community)": ("BE", "Flemish Community"),
    "Belgium (French community)": ("BE", "French Community"),
}

TABLE_PAGES = range(2, 18)  # 0-based: pages 3..18
LINE_TOL = 2.0
# A line ending in "-" followed by one of these is a suspended compound
# ("Berufsbildungsvalidierungs- und -digitalisierungsgesetz"): keep the space.
SUSPENDED_HYPHEN_NEXT = {"und", "oder", "and", "or", "et", "ou", "og", "eller", "och"}


def find_pdf() -> Path:
    files = sorted((RAW / "cedefop").glob("*-recognition_*dataset.pdf"))
    if not files:
        raise SystemExit("No data/raw/cedefop/*-recognition_*dataset.pdf found")
    return files[-1]


def column_of(x0: float) -> str:
    for i, edge in enumerate(COL_EDGES):
        if x0 < edge:
            return COLUMNS[i]
    return COLUMNS[-1]


def fixed_chars(chars):
    """A few hyphens are non-breaking hyphens (U+2011) set in a fallback font whose box sits
    about one line lower than the surrounding text, which would move them into the next line.
    Put each on the baseline of the preceding character and make it a plain hyphen."""
    out = []
    for c in chars:
        if c["text"] == "‑" and out:
            prev = out[-1]
            c = {**c, "text": "-", **{k: prev[k] for k in ("top", "bottom", "y0", "y1", "doctop")}}
        out.append(c)
    return out


def page_words(pdf):
    """Yield (page_no, word) for body words of Table 1, in page/top order."""
    for pno in TABLE_PAGES:
        page = pdf.pages[pno]
        header = [r for r in page.rects if round(r["x0"]) == 36 and 40 < r["height"] < 50]
        if not header:
            raise SystemExit(f"Page {pno + 1}: table header not found; layout changed?")
        body_top = header[0]["bottom"]
        for w in WordExtractor(x_tolerance=1.5).extract_words(fixed_chars(page.chars)):
            if w["top"] <= body_top:
                continue
            if w["text"] == "Source:" or w["top"] > 540:  # footnote / page number
                if w["text"] == "Source:":
                    break
                continue
            yield pno, w


def build_lines(words):
    """Group words (already in one cell) into lines; returns list of (key, top, height, text)."""
    words = sorted(words, key=lambda w: (w["_page"], w["top"], w["x0"]))
    lines = []
    for w in words:
        if lines and lines[-1]["page"] == w["_page"] and abs(lines[-1]["top"] - w["top"]) <= LINE_TOL:
            lines[-1]["words"].append(w)
        else:
            lines.append({"page": w["_page"], "top": w["top"], "bottom": w["bottom"], "words": [w]})
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        ln["text"] = " ".join(w["text"] for w in ln["words"])
        ln["bottom"] = max(w["bottom"] for w in ln["words"])
    return lines


def join_lines(lines) -> str | None:
    if not lines:
        return None
    heights = sorted(l["bottom"] - l["top"] for l in lines)
    h = heights[len(heights) // 2]
    out = lines[0]["text"]
    for prev, cur in zip(lines, lines[1:]):
        gap = cur["top"] - prev["bottom"] if cur["page"] == prev["page"] else 0
        if gap > 0.8 * h:  # a blank line inside the cell: new paragraph
            out += "\n" + cur["text"]
        elif (out.endswith("-") and not out.endswith(" -")
              and cur["text"].split(" ", 1)[0] not in SUSPENDED_HYPHEN_NEXT):
            out += cur["text"]
        else:
            out += " " + cur["text"]
    out = re.sub(r"[ \t]+", " ", out).strip()
    return out or None


def extract(path: Path) -> list[dict]:
    import pdfplumber

    blocks = []  # each: {"name_words": [...], "rows": {aspect: {col: [words]}}, "lm": [words]}
    current_row = None
    with pdfplumber.open(path) as pdf:
        stream = list(page_words(pdf))
        # Row starts: label words in the second column ("Information", "Competent", "Applicable").
        for pno, w in stream:
            w["_page"] = pno
        starts = sorted(
            [w for _, w in stream if column_of(w["x0"]) == "label"
             and w["text"] in ("Information", "Competent", "Applicable")],
            key=lambda w: (w["_page"], w["top"]))
        start_keys = [(w["_page"], w["top"] - LINE_TOL) for w in starts]
        start_aspect = {"Information": "information_centre", "Competent": "competent_authority",
                        "Applicable": "legal_basis"}

        def row_index(w):
            key = (w["_page"], w["top"])
            idx = -1
            for i, sk in enumerate(start_keys):
                if sk <= key:
                    idx = i
                else:
                    break
            return idx

        rows = []
        for s in starts:
            aspect = start_aspect[s["text"]]
            if aspect == "information_centre":
                blocks.append({"name": [], "rows": {}, "lm": []})
            if not blocks:
                raise SystemExit("Table does not start with an information-centre row")
            rows.append((blocks[-1], aspect))
            blocks[-1]["rows"][aspect] = {c: [] for c in PURPOSES}
        for _, w in stream:
            i = row_index(w)
            if i < 0:
                raise SystemExit(f"Text before the first row on page {w['_page'] + 1}: {w['text']!r}")
            block, aspect = rows[i]
            col = column_of(w["x0"])
            if col == "country":
                block["name"].append(w)
            elif col == "label":
                continue
            elif col == "labour_market":
                block["lm"].append(w)
            else:
                block["rows"][aspect][col].append(w)

    # Sanity: each block has the three aspects.
    for b in blocks:
        if set(b["rows"]) != set(ASPECTS):
            raise SystemExit(f"Block {join_lines(build_lines(b['name']))!r} lacks rows: {sorted(b['rows'])}")

    name_to_code = {c["name"]: c["code"] for c in countries()["by_code"].values()}
    records = []
    for b in blocks:
        name = join_lines(build_lines(b["name"])).replace("\n", " ")
        if name in SYSTEMS:
            code, community = SYSTEMS[name]
        else:
            code, community = name_to_code.get(name), None
        code = geo_code(code or "")
        if code is None:
            raise SystemExit(f"Unknown country in table: {name!r}")
        rid = code.lower() + ("-" + community.split()[0].lower() if community else "")
        country = geo_name(code)
        rec = {
            "id": rid,
            "country": country,
            "country_code": code,
            "flag": countries()["by_code"][code].get("flag"),
        }
        if community:
            rec["community"] = community
        rec["system"] = f"{country} ({community})" if community else country
        for purpose in PURPOSES:
            for aspect in ASPECTS:
                rec[f"{purpose}_{aspect}"] = join_lines(build_lines(b["rows"][aspect][purpose]))
        rec["labour_market_validation"] = join_lines(build_lines(b["lm"]))
        records.append(rec)
    return records


def main() -> None:
    path = find_pdf()
    records = extract(path)
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate ids")
    write_json(OUT / "records.json", records)
    write_json(OUT / "meta.json", build_meta(path, records))
    empty = [(r["id"], k) for r in records for k, v in r.items() if v is None and k != "flag"]
    print(f"{len(records)} records -> {rel(OUT / 'records.json')}")
    for rid, k in empty:
        print(f"  empty cell: {rid} {k}")


def build_meta(path: Path, records: list[dict]) -> dict:
    fields = [
        {"key": "system", "label": "Education and training system", "type": "title"},
        {"key": "country", "label": "Country", "type": "category", "facet": True, "collapse": 12},
        {"key": "community", "label": "Community (Belgium)", "type": "text"},
    ]
    sections = [{"title": "At a glance", "fields": ["country", "community"]}]
    for purpose, plabel in PURPOSES.items():
        keys = []
        for aspect, (_, alabel) in ASPECTS.items():
            key = f"{purpose}_{aspect}"
            fields.append({"key": key, "label": alabel, "type": "longtext"})
            keys.append(key)
        sections.append({"title": f"Recognition {plabel[0].lower()}{plabel[1:]}", "fields": keys})
    fields.append({"key": "labour_market_validation", "label": "Validation in the labour market",
                   "type": "longtext"})
    sections.append({"title": "Validation in the labour market", "fields": ["labour_market_validation"]})
    fields += [
        {"key": "country_code", "label": "Country code", "type": "hidden"},
        {"key": "flag", "label": "Flag", "type": "hidden"},
        {"key": "id", "label": "Identifier", "type": "hidden"},
    ]
    return {
        "id": DATASET_ID,
        "title": "Recognising foreign VET qualifications",
        "tagline": "Who informs, who decides and under which law foreign VET qualifications are recognised, in 30 European systems.",
        "description": (
            "Cedefop's comparative mapping of national arrangements for recognising and validating "
            "foreign vocational qualifications and skills in the EU Member States, Iceland and Norway "
            "(Belgium's Flemish and French Communities separately). For each purpose — further "
            "learning, employment in regulated professions, employment in non-regulated professions — "
            "it names the information centre, the competent authority and the legal basis, and it "
            "summarises validation arrangements in the labour market. Situation at 1 June 2026."
        ),
        "recordLabel": {"one": "system", "many": "systems"},
        "source": {
            "name": "Cedefop — Comparative mapping of national recognition and validation arrangements for foreign VET qualifications and skills. Dataset (2026)",
            "url": SOURCE_URL,
            "licence": "CC BY 4.0",
            "licence_id": "CC-BY-4.0",
            "citation": CITATION,
            "doi": DOI,
            "caveat": (
                "Extracted automatically from Table 1 of Cedefop's PDF dataset (by V. Symeonidis and "
                "E. Villalba-Garcia), which maps arrangements as at 1 June 2026. Recognition data come "
                "from a 2024 ReferNet survey and 2026 consultations with ENIC-NARIC centres and "
                "recognition authorities; validation data mainly from the European Inventory on "
                "Validation of Non-formal and Informal Learning, 2023. Cell text is reproduced as "
                "printed: only line breaks were joined (words split by a hyphen at a line end are "
                "rejoined with the hyphen kept; non-breaking hyphens are plain hyphens; blank lines within a cell are kept as paragraph breaks), so wording, spelling and abbreviations are Cedefop's. "
                "'Validation in the labour market' is a single cell per system in the source, not split "
                "by purpose. No categories have been derived. Belgium's two Communities are separate "
                "records with country code BE. The PDF is the authoritative version."
            ),
            "retrieved": path.name[:10],
            "raw_file": rel(path),
            "raw_sha256": sha256(path.read_bytes()),
            "publication_url": "https://www.cedefop.europa.eu/en/publications/7104",
        },
        "display": {
            "title": "system",
            "group": "country",
            "badge": "flag",
            "subtitle": "community",
        },
        "fields": fields,
        "sections": sections,
    }


if __name__ == "__main__":
    main()
