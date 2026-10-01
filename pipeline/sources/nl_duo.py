"""Netherlands — DUO Open Onderwijsdata: MBO students by learning pathway (BBL/BOL).

Portal: https://onderwijsdata.duo.nl (CKAN). Resources are discovered through the
CKAN action API (package_show) by resource name, so a new yearly file (the
download URLs embed the year range) is picked up automatically.

BBL (beroepsbegeleidende leerweg) is the work-based MBO pathway: at least 60% of
the programme is spent learning in a company, usually with an employment
contract. It is the Dutch apprenticeship-type route, but DUO counts *students
enrolled in the pathway*, not apprenticeship contracts.

DUO replaces cells with 1–4 students by -1 (statistical disclosure control);
those cells are left out of the sums here, so totals are lower bounds.
"""

from __future__ import annotations

import csv
import io
import re

from ..common import fetch, fetch_json, provenance, rel, save_raw, write_indicator

CKAN = "https://onderwijsdata.duo.nl/api/3/action/package_show"
DATASET_PAGE = "https://onderwijsdata.duo.nl/dataset/{name}"
DOCS = "https://duo.nl/open_onderwijsdata/middelbaar-beroepsonderwijs/aantal-studenten/aantal-mbo-studenten-sector-type-mbo.jsp"
PUBLISHER = "DUO (Dienst Uitvoering Onderwijs), Open Onderwijsdata"

SOURCE = {
    "id": "nl-duo",
    "name": "DUO Open Onderwijsdata — MBO students",
    "publisher": PUBLISHER,
    "homepage": "https://duo.nl/open_onderwijsdata/middelbaar-beroepsonderwijs/",
    "description": "Students in Dutch secondary vocational education (MBO) at 1 October, by learning pathway — BBL (work-based, apprenticeship-type) vs BOL (school-based) — and for BBL by level and sector chamber.",
    "access": "file",
    "browser_cors": None,
    "licence": "Creative Commons Attribution (as declared in the CKAN metadata, license_id 'cc-by'; version not stated)",
    "cadence": "annual (January–February, reference date 1 October)",
    "secret": None,
    "outputs": ["indicators/nl-duo-mbo-students", "indicators/nl-duo-bbl-students"],
}

SECTOR_EN = {
    "bovensectoraal": "Cross-sector",
    "entree": "Entry level",
    "handel": "Trade and retail",
    "ict-en-creatieve-industrie": "ICT and creative industries",
    "mobiliteit-transport-logistiek-en-maritiem": "Mobility, transport, logistics and maritime",
    "specialistisch-vakmanschap": "Specialist craftsmanship",
    "techniek-en-gebouwde-omgeving": "Engineering and built environment",
    "voedsel-groen-en-gastvrijheid": "Food, green sectors and hospitality",
    "zakelijke-dienstverlening-en-veiligheid": "Business services and security",
    "zorg-welzijn-en-sport": "Care, welfare and sport",
    "niet-gespecificeerd-naar-sector": "Not specified by sector",
}

PATHWAYS = {
    "TOTAL": "All MBO students (sum of pathways)",
    "BBL": "BBL — work-based pathway (beroepsbegeleidende leerweg)",
    "BOLVT": "BOL full-time — school-based pathway (beroepsopleidende leerweg, voltijd)",
    "BOLDT": "BOL part-time (deeltijd)",
    "EX": "Exam participants only (examendeelnemers)",
}

BASE_NOTE = (
    "Netherlands, national source (DUO, 1-cijferbestand mbo from the ROD register). Stock: "
    "main enrolments (one per student per institution) at the reference date 1 October of the "
    "school year; time is the calendar year of that 1 October (e.g. 2025 = school year "
    "2025/26). Includes funded and non-funded enrolments. The most recent year is provisional "
    "(flag 'p'). BBL is a learning pathway within MBO (levels 1–4, EQF 1–4), not a count of "
    "apprenticeship contracts; there is no higher-education apprenticeship in this count. "
    "DUO suppresses cells of 1–4 students (published as -1); these are excluded, so sums are "
    "lower bounds (by at most 4 × the number of suppressed cells). Do not sum with other countries."
)


_PKG: dict = {}


def _package(name: str) -> dict:
    if name not in _PKG:
        _PKG[name] = fetch_json(CKAN, params={"id": name})["result"]
    return _PKG[name]


def _resource(pkg: dict, pattern: str) -> dict:
    hits = [r for r in pkg["resources"] if re.search(pattern, r.get("name") or "", re.I)]
    if len(hits) != 1:
        raise ValueError(f"DUO {pkg['name']}: expected one resource matching {pattern!r}, got {len(hits)}")
    return hits[0]


def _csv(url: str, source_name: str) -> tuple[list[dict], object, str]:
    body = fetch(url, timeout=180)
    raw, digest = save_raw("nl-duo", source_name, body, keep=len(body) <= 5_000_000)
    text = body.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text))), raw, digest


def _int(s) -> int | None:
    v = int(str(s).strip())
    return None if v < 0 else v


def _prov(pkg: dict, res: dict, raw, digest) -> dict:
    return provenance(
        publisher=PUBLISHER, dataset_code=pkg["name"], source_url=DATASET_PAGE.format(name=pkg["name"]),
        api_url=res["url"], licence=SOURCE["licence"],
        citation=f"DUO Open Onderwijsdata, '{pkg['title']}' — {res['name']}.",
        source_updated=(res.get("last_modified") or res.get("created") or "")[:10] or None,
        raw=raw, raw_sha256=digest)


def mbo_students(provisional: str) -> dict:
    pkg = _package("mbo-studenten-per-instelling")
    res = _resource(pkg, r"^Studenten per instelling bevoegd gezag plaats gemeente provincie van de instelling en leerweg$")
    rows, raw, digest = _csv(res["url"], "mbo-studenten-per-instelling-leerweg.csv")
    sums, suppressed = {}, {}
    for r in rows:
        y = r["JAAR"].strip()
        for lw in ("BBL", "BOLVT", "BOLDT", "EX"):
            v = _int(r[lw])
            if v is None:
                suppressed[(y, lw)] = suppressed.get((y, lw), 0) + 1
                v = 0
            sums[(y, lw)] = sums.get((y, lw), 0) + v
            sums[(y, "TOTAL")] = sums.get((y, "TOTAL"), 0) + v
    series = [{"geo": "NL", "time": y, "value": v, "dims": {"pathway": lw},
               **({"flag": "p"} if y == provisional else {})}
              for (y, lw), v in sorted(sums.items())]
    return {
        "id": "nl-duo-mbo-students",
        "title": "MBO students in the Netherlands by learning pathway",
        "description": "Students in Dutch secondary vocational education (MBO) at 1 October, by learning pathway: BBL (work-based, apprenticeship-type), BOL full-time and part-time (school-based), and exam-only participants.",
        "unit": "students",
        "topic": "Participation",
        "national": True,
        "source_label": f"DUO — {pkg['title']}: {res['name']}",
        "comparability": BASE_NOTE + " Summed from per-institution counts; very few cells are suppressed in this file.",
        "dims": [{"key": "pathway", "label": "Learning pathway", "values": PATHWAYS, "default": "BBL"}],
        "flags": {"p": "provisional (DUO: the latest 1 October count is provisional)"},
        "provenance": _prov(pkg, res, raw, digest),
        "series": series,
    }


def bbl_students(provisional: str) -> dict:
    pkg = _package("mbo-studenten-per-sectorkamer-en-leerweg")
    res = _resource(pkg, r"^Studenten per sectorkamer leerweg niveau woonprovincie$")
    rows, raw, digest = _csv(res["url"], "mbo-studenten-sectorkamer-leerweg-niveau.csv")
    years = sorted(k[5:] for k in rows[0] if re.fullmatch(r"JAAR_\d{4}", k))
    sums, sectors = {}, {}
    for r in rows:
        if r["LEERWEG"].strip() != "BBL":
            continue
        sector = r["SECTORKAMER NAAM"].strip()
        skey = re.sub(r"[^a-z0-9]+", "-", sector.lower()).strip("-")
        sectors[skey] = f"{SECTOR_EN[skey]} ({sector})" if skey in SECTOR_EN else sector
        level = r["NIVEAU"].strip()
        for y in years:
            v = _int(r[f"JAAR_{y}"]) or 0
            for lv in (level, "ALL"):
                for sk in (skey, "ALL"):
                    sums[(y, lv, sk)] = sums.get((y, lv, sk), 0) + v
    series = [{"geo": "NL", "time": y, "value": v, "dims": {"level": lv, "sector": sk},
               **({"flag": "p"} if y == provisional else {})}
              for (y, lv, sk), v in sorted(sums.items())]
    levels = {"ALL": "All levels", "1": "Level 1 (Entree)", "2": "Level 2 (basic vocational)",
              "3": "Level 3 (professional)", "4": "Level 4 (middle management / specialist)"}
    return {
        "id": "nl-duo-bbl-students",
        "title": "BBL (work-based MBO) students in the Netherlands",
        "description": "Students in the Dutch work-based MBO pathway (BBL) at 1 October, by MBO level and sector chamber (sectorkamer).",
        "unit": "students",
        "topic": "Participation",
        "national": True,
        "source_label": f"DUO — {pkg['title']}: {res['name']}",
        "comparability": BASE_NOTE + " Summed from cells by sector chamber, level and province of "
                         "residence, where suppression is more frequent than in the per-institution "
                         "file: the all-levels/all-sectors total here is up to ~0.5% below the BBL "
                         "value in nl-duo-mbo-students.",
        "dims": [
            {"key": "level", "label": "MBO level", "values": levels, "default": "ALL"},
            {"key": "sector", "label": "Sector chamber", "values": {"ALL": "All sectors", **dict(sorted(sectors.items()))},
             "default": "ALL"},
        ],
        "flags": {"p": "provisional (DUO: the latest 1 October count is provisional)"},
        "provenance": _prov(pkg, res, raw, digest),
        "series": series,
    }


def _provisional_year(pkg_name: str) -> str | None:
    """DUO's notes say e.g. '(voorlopige cijfers 2025)'."""
    m = re.search(r"voorlopige cijfers (\d{4})", _package(pkg_name).get("notes") or "")
    return m.group(1) if m else None


def run() -> list[str]:
    _PKG.clear()
    prov = _provisional_year("mbo-studenten-per-instelling")
    return [rel(write_indicator(mbo_students(prov))), rel(write_indicator(bbl_students(prov)))]
