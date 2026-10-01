"""Erasmus+: VET mobility projects (Key Action 1) and Centres of Vocational Excellence.

KA1 project lists: https://erasmus-plus.ec.europa.eu/projects/projects-lists
  One CSV per call year (2014–2025), regenerated daily under dated UUID URLs,
  so the links are discovered from the listing page on every run. Each file is
  ~90 MB with 621 columns (coordinator + up to 38 partners). We stream rows,
  read only six columns, and keep nothing but country × call-year aggregates.
  The CSVs are never stored in the repository (save_raw keep=False); their
  URL, size and sha256 are recorded in the indicator provenance.

  Download only what changed: the portal regenerates every file nightly (new
  URL, new Last-Modified) even when the content is identical, so neither is a
  change signal. Instead each run sends a HEAD request (no download) and
  compares the file size with the last run. Per-year aggregates are cached in
  data/raw/erasmus/ka1-cache.json, so an unchanged file is never downloaded.
  Open call years (2021+) are still re-downloaded at least every 4 weeks to
  catch edits that keep the size; closed years (2014–2020) only on a size
  change. APPRENTIX_FORCE=1 forces a full refresh.

CoVE participants: DG EMPL XLSX "Project Participants data 2021-…-2025"
  linked from the Centres of Vocational Excellence page; one sheet per call
  year listing participating organisations, their role and country.

Record datasets (explorer):
  erasmus-vet-organisations: one record per organisation holding a KA120-VET
    accreditation (call years 2021+), with KA121/KA122-VET projects it
    coordinated since 2021. Organisation-level fields only (name, town taken
    from the address, region, type, website); per-year rows are cached in
    data/raw/erasmus/ka1-directory-cache.json alongside ka1-cache.json.
  cove-projects: one record per CoVE project from the DG EMPL workbook.

No personal data is published: contact persons, e-mails, phone numbers and
street addresses are never read into the output, and organisation rows whose
type denotes a private individual are skipped. Reuse: both sites point to the
Commission legal notice (CC BY 4.0, Decision 2011/833/EU).
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import html
import io
import json
import re
import sys
import urllib.parse
from collections import defaultdict

from ..common import (FetchError, countries, fetch, geo_code, provenance, read_json,
                      rel, save_raw, slug, write_indicator, write_records, INDICATORS, head,
                      today, write_json, PUBLISHED, RAW)

LISTING = "https://erasmus-plus.ec.europa.eu/projects/projects-lists"
COVE_PAGE = ("https://employment-social-affairs.ec.europa.eu/policies-and-activities/"
             "skills-and-qualifications/skills-jobs/centres-vocational-excellence_en")
LEGAL = "https://commission.europa.eu/legal-notice_en"
LICENCE = "CC-BY-4.0"

SOURCE = {
    "id": "erasmus",
    "name": "Erasmus+ project lists",
    "publisher": "European Commission (DG EAC / EACEA; DG EMPL for CoVEs)",
    "homepage": LISTING,
    "description": "Erasmus+ Key Action 1 VET mobility projects and EU grants by coordinating country and call year (2014–2025), new Erasmus accreditations in VET and a directory of accredited VET organisations, and Centres of Vocational Excellence projects with their participating organisations.",
    "access": "file",
    "browser_cors": False,
    "licence": LICENCE,
    "cadence": "files regenerated daily; new call-year results mainly summer–autumn",
    "secret": None,
    "outputs": [
        "indicators/erasmus-ka1-vet-projects",
        "indicators/erasmus-ka1-vet-grant",
        "indicators/erasmus-vet-accreditations",
        "indicators/erasmus-cove-participations",
        "erasmus-vet-organisations/records.json",
        "erasmus-vet-organisations/meta.json",
        "cove-projects/records.json",
        "cove-projects/meta.json",
    ],
}

# Links sit in url="..." attributes of <eac-document-teaser> elements (not href), so match any attribute.
KA1_LINK = re.compile(
    r"""=["']([^"'\s]*project-result-content/[0-9a-fA-F-]+/"""
    r"""ErasmusPlus_KA1_(\d{4})_LearningMobilityOfIndividuals_Projects_Overview_(\d{4}-\d{2}-\d{2})\.csv)["']""")
COVE_LINK = re.compile(r"""href=["']([^"']*/document/download/[^"']*Participants[^"']*\.xlsx)["']""", re.I)

# Project identifiers: 2021–: "2025-1-AT01-KA121-VET-000306220"; 2014–2020: "2019-1-AT01-KA102-050670".
PID = re.compile(r"-KA(\d{3})(?:-([A-Z]{3}))?-")

ACTIONS = {
    "TOTAL": "All VET mobility projects",
    "KA121": "Accredited VET mobility projects (KA121-VET, 2021–)",
    "KA122": "Short-term VET mobility projects (KA122-VET, 2021–)",
    "KA102": "VET learner and staff mobility (KA102, 2014–2020)",
    "KA116": "VET mobility with VET Mobility Charter (KA116, 2014–2020)",
}
PERIOD_ACTIONS = {"old": ["KA102", "KA116"], "new": ["KA121", "KA122"]}

ROLES = {
    "TOTAL": "All participations",
    "COORD": "Coordinator",
    "PARTNER": "Partner",
    "ASSOC": "Associated partner",
    "AFFIL": "Affiliated entity",
}
ROLE_MAP = {"coordinator": "COORD", "partner": "PARTNER",
            "associated partner": "ASSOC", "affiliated entity": "AFFIL"}

GRANT_NOTE = ("EU grant awarded after the selection stage, as published in the project lists; "
              "the Commission notes it is indicative and does not reflect changes made during or after the project.")


# ------------------------------------------------------------ discovery --

def discover_ka1() -> dict[int, dict]:
    """{call_year: {"url", "date"}} for every KA1 CSV linked from the listing page."""
    page = fetch(LISTING, timeout=120).decode("utf-8", "replace")
    found = {}
    for href, year, date in KA1_LINK.findall(page):
        url = urllib.parse.urljoin(LISTING, html.unescape(href))
        y = int(year)
        if y not in found or date > found[y]["date"]:
            found[y] = {"url": url, "date": date}
    if not found:
        raise FetchError(f"no KA1 CSV links found on {LISTING}; page layout may have changed")
    return dict(sorted(found.items()))


# -------------------------------------------------------------- parsing --

def _col(header: list[str], *prefixes: str) -> int:
    norm = [h.strip().lower().replace("’", "'") for h in header]
    for p in prefixes:
        for i, h in enumerate(norm):
            if h.startswith(p):
                return i
    raise KeyError(f"column starting with {prefixes!r} not found")


def _amount(s: str) -> float | None:
    s = (s or "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:          # 1,234.56
        s = s.replace(",", "")
    elif "," in s:                     # 1234,56
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _classify(pid: str, action_type: str) -> tuple[str | None, bool]:
    """Return (action code for VET mobility or None, is_vet_accreditation)."""
    m = PID.search(pid or "")
    if m:
        ka, field = "KA" + m.group(1), m.group(2)
        if field == "VET" and ka in ("KA121", "KA122"):
            return ka, False
        if field == "VET" and ka == "KA120":
            return None, True
        if ka in ("KA102", "KA116"):
            return ka, False
        return None, False
    # Fallback on the free-text Action Type when the identifier is unusual.
    a = re.sub(r"\s+", " ", (action_type or "").lower()).strip()
    if "vocational education and training" in a:
        if a.startswith("erasmus accreditation"):
            return None, True
        if a.startswith("accredited projects"):
            return "KA121", False
        if a.startswith("short-term projects"):
            return "KA122", False
    if a == "vet learner and staff mobility":
        return "KA102", False
    if a.startswith("vet learner and staff mobility with vet mobility charter"):
        return "KA116", False
    return None, False


def parse_ka1(body: bytes, file_year: int, agg: dict, accr: dict, directory: dict | None = None) -> dict:
    """Stream one KA1 CSV, adding to agg[(geo, year, action)] = [projects, grant] and accr[(geo, year)].

    With `directory` ({"accredited": [], "coord": defaultdict}), also collects
    organisation-level rows for the accredited-organisations directory (see
    _dir_row): one row per KA120-VET accreditation, and per coordinating
    organisation the number of KA121/KA122-VET projects and their grant.
    """
    head = body[:4096].decode("utf-8", "replace").splitlines()[0]
    delim = max([",", ";", "\t"], key=head.count)
    text = io.TextIOWrapper(io.BytesIO(body), encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.reader(text, delimiter=delim)
    header = next(reader)
    i_type = _col(header, "action type")
    i_year = _col(header, "call year")
    i_pid = _col(header, "project identifier")
    i_grant = _col(header, "eu grant")
    i_ctry = _col(header, "coordinator's country", "coordinating organisation country")
    width = max(i_type, i_year, i_pid, i_grant, i_ctry)
    dcols = _dir_cols(header) if directory is not None else None
    if dcols:
        width = max(width, *(i for i in dcols.values() if i is not None))
    stats = {"rows": 0, "vet_projects": 0, "vet_accreditations": 0, "unmapped_country": 0, "short_rows": 0}
    seen = set()
    for row in reader:
        stats["rows"] += 1
        if len(row) <= width:
            stats["short_rows"] += 1
            continue
        action, is_accr = _classify(row[i_pid], row[i_type])
        if not action and not is_accr:
            continue
        pid = row[i_pid].strip()
        if pid in seen:
            continue
        seen.add(pid)
        year = row[i_year].strip() or str(file_year)
        geo = geo_code(row[i_ctry].strip().upper())
        if geo is None:
            stats["unmapped_country"] += 1
            continue
        if is_accr:
            accr[(geo, year)] += 1
            stats["vet_accreditations"] += 1
            if dcols:
                d = _dir_row(row, dcols, pid, year, geo)
                if d:
                    directory["accredited"].append(d)
                else:
                    stats["dir_skipped"] = stats.get("dir_skipped", 0) + 1
            continue
        cell = agg[(geo, year, action)]
        cell[0] += 1
        amount = _amount(row[i_grant]) or 0.0
        cell[1] += amount
        stats["vet_projects"] += 1
        if dcols and action in ("KA121", "KA122") and dcols["name"] is not None:
            key = _org_key(row[dcols["name"]])
            if key:
                c = directory["coord"][(key, geo)]
                c[0 if action == "KA121" else 1] += 1
                c[2] += amount
    text.detach()
    return stats


# ---------------------------------------------- directory (organisations) --

# Organisation types that would denote a private individual; such rows are never published.
PERSON_TYPE = re.compile(r"natural person|individual|informal group|private person", re.I)
CARD_URL = "https://erasmus-plus.ec.europa.eu/projects/search/details/{pid}"
DIR_FIRST_YEAR = 2021   # KA120/KA121/KA122 exist from the 2021 call


def _dir_cols(header: list[str]) -> dict:
    def opt(*prefixes):
        try:
            return _col(header, *prefixes)
        except KeyError:
            return None
    return {
        "name": opt("coordinating organisation name"),
        "type": opt("coordinating organisation type"),
        "address": opt("coordinator's address"),   # read only to take the town; never stored
        "region": opt("coordinator's region"),
        "website": opt("coordinator's website"),
        "card": opt("results platform project card"),
        "status": opt("project or accreditation status"),
    }


def _org_key(name: str) -> str:
    return re.sub(r"\W+", " ", (name or "").casefold()).strip()


def _cell(row: list[str], i: int | None) -> str:
    return re.sub(r"\s+", " ", row[i]).strip() if i is not None and i < len(row) else ""


def _city(address: str) -> str:
    """Addresses read 'street, postcode, town'; keep only the town."""
    town = address.rsplit(",", 1)[-1].strip() if address else ""
    if not town or town.lower() in ("unknown", "null", "n/a", "-") or not re.search(r"[^\W\d_]", town):
        return ""
    return town.title() if town.isupper() and len(town) > 3 else town


def _website(w: str) -> str:
    w = w.replace(" ", "")
    if not w or "@" in w or "." not in w:
        return ""
    return w


def _card(pid: str) -> str:
    return CARD_URL.format(pid=urllib.parse.quote(pid))


def _dir_row(row, cols, pid, year, geo) -> list | None:
    """Organisation-level fields of one accreditation; None for individuals or unnamed rows."""
    name, otype = _cell(row, cols["name"]), _cell(row, cols["type"])
    if not name or PERSON_TYPE.search(otype):
        return None
    card = _cell(row, cols["card"])
    if not card.startswith("http") or card == _card(pid):
        card = ""   # the standard URL is rebuilt from the identifier; keeps the cache small
    return [pid, year, name, otype, _city(_cell(row, cols["address"])), _cell(row, cols["region"]),
            geo, _website(_cell(row, cols["website"])), card, _cell(row, cols["status"])]


# -------------------------------------------------------------- output ---

def _eu27() -> set[str]:
    return {c for c, v in countries()["by_code"].items() if v.get("group") == "eu"}


def _with_eu27(series: list[dict]) -> list[dict]:
    eu = _eu27()
    tot = defaultdict(float)
    for o in series:
        if o["geo"] in eu:
            tot[(o["time"], tuple(sorted(o.get("dims", {}).items())))] += o["value"]
    extra = [{"geo": "EU27", "time": t, "value": v, **({"dims": dict(d)} if d else {})}
             for (t, d), v in tot.items()]
    return series + extra


def _write(ind: dict) -> str:
    """write_indicator, but keep the previous provenance when the numbers are unchanged.

    The source files get new URLs and hashes every day; without this every run
    would rewrite the indicator even though nothing published has changed.
    """
    path = INDICATORS / f"{ind['id']}.json"
    if path.exists():
        old = read_json(path)
        keys = ("title", "description", "unit", "dims", "comparability")
        if all(old.get(k) == ind.get(k) for k in keys) and _norm(old["series"]) == _norm(ind["series"]):
            ind = {**ind, "provenance": old["provenance"]}
    return rel(write_indicator(ind))


def _norm(series: list[dict]) -> list:
    out = []
    for o in series:
        g = geo_code(o["geo"])
        if g is None or o.get("value") is None:
            continue
        out.append((g, str(o["time"]), round(float(o["value"]), 4),
                    tuple(sorted((o.get("dims") or {}).items()))))
    return sorted(out)


def ka1_indicators(files: dict, agg: dict, accr: dict) -> list[str]:
    years_by_geo = defaultdict(set)
    for geo, year, _ in agg:
        years_by_geo[year].add(geo)
    proj, grant = [], []
    for year, geos in years_by_geo.items():
        actions = PERIOD_ACTIONS["old" if int(year) <= 2020 else "new"]
        for geo in geos:
            tp, tg = 0, 0.0
            for a in actions:
                p, g = agg.get((geo, year, a), (0, 0.0))
                tp, tg = tp + p, tg + g
                proj.append({"geo": geo, "time": year, "value": p, "dims": {"action": a}})
                grant.append({"geo": geo, "time": year, "value": round(g, 2), "dims": {"action": a}})
            proj.append({"geo": geo, "time": year, "value": tp, "dims": {"action": "TOTAL"}})
            grant.append({"geo": geo, "time": year, "value": round(tg, 2), "dims": {"action": "TOTAL"}})

    file_list = [{"call_year": str(y), "url": f["url"], "bytes": f["bytes"], "sha256": f["sha256"]}
                 for y, f in files.items()]
    latest = max(f["date"] for f in files.values())

    def prov(code):
        p = provenance(
            publisher="European Commission (DG EAC / EACEA), Erasmus+ project results",
            dataset_code=code, source_url=LISTING, licence=LICENCE,
            citation="European Commission, Erasmus+ projects lists for download (KA1 Learning Mobility of Individuals), "
                     "aggregated by Apprentix.",
            source_updated=latest)
        p["licence_note"] = f"Commission legal notice ({LEGAL}): CC BY 4.0 under Decision 2011/833/EU."
        p["raw_note"] = "Source CSVs (~90 MB each) are not stored; URLs and SHA-256 hashes of the files used are listed below."
        p["files"] = file_list
        return p

    action_dim = [{"key": "action", "label": "Action type", "values": ACTIONS, "default": "TOTAL"}]
    common_cmp = ("Counts Erasmus+ Key Action 1 VET mobility projects by the country of the coordinating "
                  "(sending) organisation and call year, from the Commission's project lists. A project sends "
                  "learners and staff abroad from that country; destination countries are not counted. "
                  "The 2014–2020 actions (KA102, KA116) and 2021–2027 actions (KA121-VET, KA122-VET) are "
                  "different instruments, so the break in 2021 is structural. Accredited (KA121) projects are "
                  "multi-annual funding for accredited organisations, so a country with many accredited "
                  "providers has few but large projects. ErasmusPro (long-term mobility of apprentices) is not "
                  "a separate action and cannot be isolated. The participant count is not published in these files. "
                  "All selected projects are counted whatever their current status (including terminated). "
                  "Recent call years are incomplete until selection and contracting are finished. "
                  "EU27 is the sum of the 27 member states (also for years before 2020, when the UK took part).")
    out = []
    out.append(_write({
        "id": "erasmus-ka1-vet-projects",
        "title": "Erasmus+ VET mobility projects",
        "description": "Number of Erasmus+ Key Action 1 mobility projects for vocational education and training learners and staff, by country of the coordinating organisation and call year.",
        "unit": "projects",
        "topic": "Mobility",
        "source_label": "Erasmus+ projects lists, KA1 Learning Mobility of Individuals",
        "comparability": common_cmp,
        "dims": action_dim,
        "provenance": prov("ErasmusPlus_KA1"),
        "series": _with_eu27(proj),
    }))
    out.append(_write({
        "id": "erasmus-ka1-vet-grant",
        "title": "EU grant for Erasmus+ VET mobility projects",
        "description": "EU grant awarded to Erasmus+ Key Action 1 VET mobility projects, by country of the coordinating organisation and call year, in euros (current prices).",
        "unit": "EUR",
        "topic": "Mobility",
        "source_label": "Erasmus+ projects lists, KA1 Learning Mobility of Individuals",
        "comparability": GRANT_NOTE + " " + common_cmp,
        "dims": action_dim,
        "provenance": prov("ErasmusPlus_KA1"),
        "series": _with_eu27(grant),
    }))
    acc = [{"geo": g, "time": y, "value": n} for (g, y), n in accr.items()]
    if acc:
        out.append(_write({
            "id": "erasmus-vet-accreditations",
            "title": "New Erasmus accreditations in VET",
            "description": "Number of organisations or consortia awarded an Erasmus accreditation in vocational education and training (KA120-VET), by country and call year. Accredited organisations can then apply each year for KA121-VET mobility funding.",
            "unit": "accreditations",
            "topic": "Mobility",
            "source_label": "Erasmus+ projects lists, KA1 Learning Mobility of Individuals (KA120-VET)",
            "comparability": "Counts new accreditations granted in each call year; accreditations run until 2027, so this is a flow, not the stock of accredited providers. Includes consortium coordinators. No grant is attached to the accreditation itself. EU27 is the sum of member states.",
            "provenance": prov("ErasmusPlus_KA1 (KA120-VET)"),
            "series": _with_eu27(acc),
        }))
    return out


def cove_workbook() -> dict | None:
    """Download the DG EMPL participants workbook once; return its rows and provenance."""
    page = fetch(COVE_PAGE, timeout=120).decode("utf-8", "replace")
    m = COVE_LINK.search(page)
    if not m:
        print("erasmus: CoVE participants XLSX link not found; skipped", file=sys.stderr)
        return None
    url = urllib.parse.urljoin(COVE_PAGE, html.unescape(m.group(1)))
    body = fetch(url, timeout=120)
    raw, digest = save_raw("erasmus", "cove-participants.xlsx", body)

    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    rows = []   # (call year, acronym, project title, organisation, role cell, country code)
    extracted = None
    for ws in wb.worksheets:
        if not re.fullmatch(r"\d{4}", ws.title.strip()):
            continue
        year = ws.title.strip()
        header = None
        acronym = title = ""
        for row in ws.iter_rows(values_only=True):
            cells = [("" if v is None else re.sub(r"\s+", " ", str(v)).strip()) for v in row]
            if header is None:
                low = [c.lower() for c in cells]
                if "role" in low and "country code" in low:
                    def find(*pre):
                        return next((i for i, c in enumerate(low) if c.startswith(pre)), None)
                    header = {"acronym": find("acronym"), "title": find("project title"),
                              "name": find("legal name", "organisation"),
                              "role": low.index("role"), "cc": low.index("country code")}
                elif cells and cells[0].lower().startswith("data extracted"):
                    extracted = cells[0]
                continue
            get = lambda k: cells[header[k]] if header[k] is not None and header[k] < len(cells) else ""
            if get("acronym"):
                acronym, title = get("acronym"), get("title") or title
            rows.append((year, acronym, title, get("name"), get("role"), get("cc").upper()))
    wb.close()
    return {"url": url, "raw": raw, "sha256": digest, "extracted": extracted, "rows": rows}


def cove_indicator(cw: dict) -> list[str]:
    counts = defaultdict(int)
    for year, _, _, _, role_cell, cc in cw["rows"]:
        role = ROLE_MAP.get(role_cell.lower())
        geo = geo_code(cc)
        if role is None or geo is None:
            continue
        counts[(geo, year, role)] += 1
        counts[(geo, year, "TOTAL")] += 1
    if not counts:
        print("erasmus: CoVE workbook had no usable rows; skipped", file=sys.stderr)
        return []
    url, raw, digest, extracted = cw["url"], cw["raw"], cw["sha256"], cw["extracted"]
    geos_years = {(g, y) for g, y, _ in counts}
    series = [{"geo": g, "time": y, "value": counts.get((g, y, r), 0), "dims": {"role": r}}
              for g, y in geos_years for r in ROLES]
    prov = provenance(
        publisher="European Commission (DG EMPL), Centres of Vocational Excellence",
        dataset_code="CoVE project participants 2021–2025", source_url=COVE_PAGE, api_url=url,
        licence=LICENCE, citation="European Commission, DG EMPL: Project Participants data (Centres of Vocational Excellence), aggregated by Apprentix.",
        source_updated=extracted, raw=raw, raw_sha256=digest)
    prov["licence_note"] = f"Commission legal notice ({LEGAL}): CC BY 4.0 under Decision 2011/833/EU."
    return [_write({
        "id": "erasmus-cove-participations",
        "title": "Participations in Centres of Vocational Excellence projects",
        "description": "Number of organisations from each country taking part in Erasmus+ Centres of Vocational Excellence (CoVE) projects, by call year and role (coordinator, partner, associated partner, affiliated entity).",
        "unit": "participations",
        "topic": "Excellence",
        "source_label": "DG EMPL, CoVE Project Participants data 2021–2025",
        "comparability": "Counts organisation-participations, not distinct organisations or projects: an organisation in two CoVEs counts twice. Only 13–16 CoVE projects are selected per call, so national figures are small and volatile. Associated partners and affiliated entities do not receive EU funding in the same way as full partners. Countries outside Europe are dropped. EU27 is the sum of member states.",
        "dims": [{"key": "role", "label": "Role", "values": ROLES, "default": "TOTAL"}],
        "provenance": prov,
        "series": _with_eu27(series),
    })]


# ------------------------------------------------------- record datasets --

LICENCE_TEXT = ("CC BY 4.0, under the Commission's reuse policy (Decision 2011/833/EU; legal notice: "
                f"{LEGAL}). Cite as: European Commission, {{}}; compiled by Apprentix.")
# Countries that appear in CoVE partnerships but are not in data/reference/countries.json.
OTHER_COUNTRIES = {"AM": "Armenia", "CA": "Canada", "CN": "China", "EG": "Egypt", "GH": "Ghana",
                   "ZA": "South Africa", "US": "United States", "IL": "Israel", "TN": "Tunisia",
                   "MA": "Morocco", "JP": "Japan", "KR": "South Korea", "AU": "Australia", "IN": "India"}
PROJECT_BANDS = ["None", "1–2", "3–4", "5 or more"]


def _country(cc: str) -> tuple[str | None, str, str | None]:
    """(site code or None, display name, flag emoji or None) for a country code."""
    geo = geo_code(cc)
    if geo:
        c = countries()["by_code"][geo]
        return geo, c["name"], c.get("flag")
    return None, OTHER_COUNTRIES.get(cc, cc), None


def _publish(dataset_id: str, records: list[dict], meta: dict) -> list[str]:
    """Write records.json + meta.json; keep the previous 'retrieved' date when the records are unchanged."""
    folder = PUBLISHED / dataset_id
    old_rec, old_meta = folder / "records.json", folder / "meta.json"
    if old_rec.exists() and old_meta.exists() and read_json(old_rec) == records:
        prev = read_json(old_meta).get("source", {})
        for k in ("retrieved", "raw_file", "raw_sha256"):
            if k in prev:
                meta["source"][k] = prev[k]
    rec_path = write_records(dataset_id, records)
    write_json(old_meta, meta)
    return [rel(rec_path), rel(old_meta)]


def _band(n: int) -> str:
    return "None" if n == 0 else "1–2" if n <= 2 else "3–4" if n <= 4 else "5 or more"


def accredited_organisations(dir_by_year: dict) -> list[str]:
    """Directory of organisations holding an Erasmus accreditation in VET (KA120-VET, 2021–)."""
    acc = sorted((r for d in dir_by_year.values() for r in d["accredited"]), key=lambda r: (r[1], r[0]))
    coord = defaultdict(lambda: [0, 0, 0.0])
    for d in dir_by_year.values():
        for key, geo, n121, n122, grant in d["coord"]:
            c = coord[(key, geo)]
            c[0], c[1], c[2] = c[0] + n121, c[1] + n122, c[2] + grant
    orgs = {}
    for pid, year, name, otype, city, region, geo, website, card, status in acc:
        o = orgs.setdefault((_org_key(name), geo), {"pids": [], "years": set()})
        o["pids"].append(pid)
        o["years"].add(year)
        # The latest accreditation wins for descriptive fields; keep earlier values when blank.
        for k, v in (("name", name), ("type", otype), ("city", city), ("region", region),
                     ("website", website), ("card", card), ("status", status)):
            if v or k not in o:
                o[k] = v
    records = []
    for (key, geo), o in orgs.items():
        n121, n122, grant = coord.get((key, geo), (0, 0, 0.0))
        total = n121 + n122
        _, cname, flag = _country(geo)
        years = sorted(o["years"])
        loc = " · ".join(dict.fromkeys(x for x in (o["city"], o["region"]) if x))
        summary = (f"{total} mobility project{'s' if total != 1 else ''} since 2021"
                   + (f", €{round(grant):,}" if grant else "")) if total else "No mobility projects coordinated yet"
        records.append({
            "id": "erasmus-acc-" + o["pids"][0].rsplit("-", 1)[-1],
            "name": o["name"],
            "location": loc or None,
            "country": cname,
            "country_code": geo,
            "flag": flag,
            "org_type": o["type"] or None,
            "accreditation_years": years,
            "accredited_label": "Accredited " + ", ".join(years),
            "status": o["status"] or None,
            "accreditation_ids": o["pids"],
            "ka121_projects": n121,
            "ka122_projects": n122,
            "projects_band": _band(total),
            "grant_total": f"€{round(grant):,}" if grant else None,
            "projects_summary": summary,
            "website": o["website"] or None,
            "project_page": o["card"] or _card(o["pids"][-1]),
        })
    records = [{k: v for k, v in r.items() if v is not None} for r in records]
    records.sort(key=lambda r: (r["country"], r["name"].casefold(), r["id"]))
    status_order = ["Accredited", "Suspended", "Terminated"]
    meta = {
        "id": "erasmus-vet-organisations",
        "title": "Erasmus+ accredited VET organisations",
        "tagline": "Every organisation holding an Erasmus accreditation in vocational education and training since 2021.",
        "description": "Schools, training centres, companies, chambers and public bodies awarded an Erasmus accreditation in VET (KA120-VET) in the 2021–2027 programme. Accredited organisations can send apprentices, learners and staff abroad every year without competing project by project. Each record shows where the organisation is, when it was accredited, and how many Erasmus+ VET mobility projects it has coordinated since 2021.",
        "recordLabel": {"one": "organisation", "many": "organisations"},
        "source": {
            "name": "European Commission — Erasmus+ projects lists for download (KA1 Learning Mobility of Individuals)",
            "url": LISTING,
            "licence": LICENCE_TEXT.format("Erasmus+ projects lists (KA1)"),
            "licence_id": LICENCE,
            "caveat": ("Compiled automatically from the Commission's KA1 project lists, call years 2021 onwards: one record per "
                       "organisation named as holder of a KA120-VET accreditation. Organisations are matched by name and country "
                       "(the files carry no organisation ID), so a renamed organisation may appear twice and a name variant may miss "
                       "its project counts. Only organisation-level information is shown: name, town (taken from the published "
                       "address; street and postcode are dropped), region, type and website. No contact persons, e-mail addresses "
                       "or phone numbers are read or published, and rows describing private individuals are skipped. Members of "
                       "accredited consortia are not listed, only the consortium coordinator. 'Mobility projects since 2021' counts "
                       "KA121-VET and KA122-VET projects the organisation coordinated; the grant is the indicative amount awarded "
                       "at selection, not the amount finally paid. Status is the accreditation status shown in the lists "
                       "when they were last read."),
            "retrieved": today(),
        },
        "display": {
            "title": "name",
            "subtitle": "location",
            "group": "country",
            "badge": "flag",
            "link": "project_page",
            "facts": ["accredited_label", "org_type", "projects_summary"],
        },
        "fields": [
            {"key": "country", "label": "Country", "type": "category", "facet": True, "collapse": 12},
            {"key": "accreditation_years", "label": "Accreditation year", "type": "category", "facet": True},
            {"key": "org_type", "label": "Type of organisation", "type": "category", "facet": True, "collapse": 6},
            {"key": "projects_band", "label": "Mobility projects coordinated since 2021", "type": "category",
             "facet": True, "order": PROJECT_BANDS},
            {"key": "status", "label": "Accreditation status", "type": "category", "facet": True, "order": status_order},
            {"key": "name", "label": "Organisation", "type": "title"},
            {"key": "location", "label": "Town and region", "type": "subtitle"},
            {"key": "ka121_projects", "label": "Accredited mobility projects (KA121-VET)", "type": "text"},
            {"key": "ka122_projects", "label": "Short-term mobility projects (KA122-VET)", "type": "text"},
            {"key": "grant_total", "label": "EU grant for these projects (indicative)", "type": "text"},
            {"key": "accreditation_ids", "label": "Accreditation number", "type": "text"},
            {"key": "website", "label": "Website", "type": "text"},
            {"key": "project_page", "label": "Erasmus+ project page", "type": "link"},
            {"key": "accredited_label", "label": "Accredited", "type": "hidden"},
            {"key": "projects_summary", "label": "Mobility projects", "type": "hidden"},
            {"key": "country_code", "label": "Country code", "type": "hidden"},
            {"key": "flag", "label": "Flag", "type": "hidden"},
            {"key": "id", "label": "Identifier", "type": "hidden"},
        ],
        "sections": [
            {"title": "At a glance", "fields": ["country", "location", "org_type", "accreditation_years", "status"]},
            {"title": "Mobility projects coordinated since 2021",
             "fields": ["ka121_projects", "ka122_projects", "grant_total"]},
            {"title": "Links and identifiers", "fields": ["website", "accreditation_ids", "project_page"]},
        ],
    }
    return _publish("erasmus-vet-organisations", records, meta)


def cove_projects(cw: dict) -> list[str]:
    """One record per Centre of Vocational Excellence project, with its participating organisations."""
    projects = {}
    for year, acronym, title, name, role_cell, cc in cw["rows"]:
        role = ROLE_MAP.get(role_cell.lower())
        if not acronym or not name or role is None:
            continue
        p = projects.setdefault((year, acronym), {"title": title, "orgs": []})
        if (name, role, cc) not in p["orgs"]:
            p["orgs"].append((name, role, cc))
    role_word = {"COORD": ("coordinator", "coordinators"), "PARTNER": ("partner", "partners"),
                 "ASSOC": ("associated partner", "associated partners"),
                 "AFFIL": ("affiliated entity", "affiliated entities")}
    records, ids = [], set()
    for (year, acronym), p in projects.items():
        orgs = p["orgs"]
        coord = next((o for o in orgs if o[1] == "COORD"), None)
        ccode, cname, cflag = _country(coord[2]) if coord else (None, None, None)
        n = defaultdict(int)
        for _, role, _ in orgs:
            n[role] += 1
        names = sorted({_country(cc)[1] for _, _, cc in orgs if cc})
        order = list(ROLE_MAP.values())
        part = [f"{name} ({_country(cc)[1]}, {role_word[role][0]})"
                for name, role, cc in sorted(orgs, key=lambda o: (order.index(o[1]), o[0].casefold()))]
        rid = f"cove-{year}-{slug(acronym)}"
        while rid in ids:
            rid += "-x"
        ids.add(rid)
        rec = {
            "id": rid,
            "acronym": acronym,
            "project_title": p["title"] or None,
            "call_year": year,
            "coordinator": coord[0] if coord else None,
            "coordinator_country": cname,
            "coordinator_country_code": ccode,
            "flag": cflag,
            "countries": names,
            "country_count": len(names),
            "organisation_count": len(orgs),
            "partner_count": n["PARTNER"],
            "associated_partner_count": n["ASSOC"],
            "affiliated_entity_count": n["AFFIL"],
            "roles": ", ".join(f"{n[r]} {role_word[r][n[r] != 1]}" for r in order if n[r]),
            "size_label": f"{len(orgs)} organisations",
            "countries_label": f"{len(names)} countr{'ies' if len(names) != 1 else 'y'}",
            "participants": part,
        }
        records.append({k: v for k, v in rec.items() if v is not None})
    records.sort(key=lambda r: (r["call_year"], r["acronym"].casefold()))
    meta = {
        "id": "cove-projects",
        "title": "Centres of Vocational Excellence projects",
        "tagline": "Every Erasmus+ Centre of Vocational Excellence partnership since 2021, and who takes part.",
        "description": "Centres of Vocational Excellence (CoVEs) are Erasmus+ partnerships that bring together VET providers, employers, universities, chambers and public authorities from several countries around one sector or challenge. Each record is one CoVE project selected in the 2021–2025 calls, with its coordinator, partners and the countries involved.",
        "recordLabel": {"one": "CoVE project", "many": "CoVE projects"},
        "source": {
            "name": "European Commission (DG EMPL) — Centres of Vocational Excellence: Project Participants data",
            "url": COVE_PAGE,
            "licence": LICENCE_TEXT.format("DG EMPL, Centres of Vocational Excellence project participants data"),
            "licence_id": LICENCE,
            "caveat": ("Compiled automatically from the participants workbook published by DG EMPL "
                       f"({cw['extracted'] or 'extraction date not stated'}). Organisations are listed by the legal name "
                       "given in the workbook; no people are named. Associated partners and affiliated entities take part "
                       "without being full beneficiaries. Countries outside Europe are shown by name but do not have a "
                       "country page on this site."),
            "retrieved": today(),
            "file_url": cw["url"],
            "raw_file": rel(cw["raw"]),
            "raw_sha256": cw["sha256"],
        },
        "display": {
            "title": "acronym",
            "subtitle": "project_title",
            "group": "coordinator_country",
            "badge": "flag",
            "facts": ["call_year", "countries_label", "size_label"],
        },
        "fields": [
            {"key": "call_year", "label": "Call year", "type": "category", "facet": True},
            {"key": "coordinator_country", "label": "Coordinator country", "type": "category", "facet": True, "collapse": 12},
            {"key": "countries", "label": "Countries involved", "type": "category", "facet": True, "collapse": 12},
            {"key": "acronym", "label": "Acronym", "type": "title"},
            {"key": "project_title", "label": "Project", "type": "subtitle"},
            {"key": "coordinator", "label": "Coordinator", "type": "text"},
            {"key": "organisation_count", "label": "Organisations", "type": "text"},
            {"key": "partner_count", "label": "Full partners", "type": "text"},
            {"key": "associated_partner_count", "label": "Associated partners", "type": "text"},
            {"key": "affiliated_entity_count", "label": "Affiliated entities", "type": "text"},
            {"key": "country_count", "label": "Number of countries", "type": "text"},
            {"key": "roles", "label": "Make-up", "type": "text"},
            {"key": "participants", "label": "Participating organisations", "type": "longtext"},
            {"key": "size_label", "label": "Size", "type": "hidden"},
            {"key": "countries_label", "label": "Countries", "type": "hidden"},
            {"key": "coordinator_country_code", "label": "Coordinator country code", "type": "hidden"},
            {"key": "flag", "label": "Flag", "type": "hidden"},
            {"key": "id", "label": "Identifier", "type": "hidden"},
        ],
        "sections": [
            {"title": "At a glance", "fields": ["call_year", "coordinator", "coordinator_country", "roles", "country_count"]},
            {"title": "Countries", "fields": ["countries"]},
            {"title": "Who takes part", "fields": ["participants"]},
        ],
    }
    return _publish("cove-projects", records, meta)


CACHE = RAW / "erasmus" / "ka1-cache.json"
# Organisation rows for the accredited-organisations directory, per call year (2021+).
# A year is reused only when its sha256 matches the ka1-cache.json entry, so both caches
# always describe the same file; if either is missing or stale, the file is downloaded.
DIR_CACHE = RAW / "erasmus" / "ka1-directory-cache.json"
MAX_AGE_DAYS = 28       # open call years: full re-download at least this often
LAST_CLOSED_YEAR = 2020  # 2014–2020 programme is closed


def _load_cache(path=CACHE) -> dict:
    return read_json(path) if path.exists() else {}


def _is_fresh(year: int, c: dict | None, size: int | None) -> bool:
    if os.environ.get("APPRENTIX_FORCE") or not c or size is None or size != c["bytes"]:
        return False
    if year <= LAST_CLOSED_YEAR:
        return True
    age = (dt.date.fromisoformat(today()) - dt.date.fromisoformat(c["downloaded"])).days
    return age < MAX_AGE_DAYS


def _write_dir_cache(dcache: dict) -> None:
    """JSON with one row per line: compact, but still diffs line by line."""
    dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
    parts = []
    for year, d in dcache.items():
        rows = {k: "[\n" + ",\n".join(dump(r) for r in d[k]) + "\n]" for k in ("accredited", "coord")}
        parts.append(f'{dump(year)}:{{"sha256":{dump(d["sha256"])},\n"accredited":{rows["accredited"]},\n'
                     f'"coord":{rows["coord"]}}}')
    text = "{\n" + ",\n".join(parts) + "\n}\n"
    if not DIR_CACHE.exists() or DIR_CACHE.read_text(encoding="utf-8") != text:
        DIR_CACHE.write_text(text, encoding="utf-8")


def run() -> list[str]:
    files = discover_ka1()
    cache = _load_cache()
    dcache = _load_cache(DIR_CACHE)
    agg = defaultdict(lambda: [0, 0.0])
    accr = defaultdict(int)
    dir_by_year = {}
    downloaded = 0
    for year, f in files.items():
        c = cache.get(str(year))
        dc = dcache.get(str(year))
        wants_dir = year >= DIR_FIRST_YEAR
        size = head(f["url"]).get("content-length")
        size = int(size) if size and size.isdigit() else None
        dir_ok = not wants_dir or (dc is not None and c is not None and dc.get("sha256") == c.get("sha256"))
        if _is_fresh(year, c, size) and dir_ok:
            for geo, y, a, p, g in c["agg"]:
                agg[(geo, y, a)][0] += p
                agg[(geo, y, a)][1] += g
            for geo, y, n in c["accr"]:
                accr[(geo, y)] += n
            if wants_dir:
                dir_by_year[year] = dc
            f["bytes"], f["sha256"] = c["bytes"], c["sha256"]
            print(f"erasmus: KA1 {year}: unchanged ({size:,} bytes), not downloaded", file=sys.stderr)
            continue
        body = fetch(f["url"], timeout=300, polite_delay=2)
        downloaded += 1
        _, f["sha256"] = save_raw("erasmus", f"ka1-{year}.csv", body, keep=False)
        f["bytes"] = len(body)
        y_agg, y_accr = defaultdict(lambda: [0, 0.0]), defaultdict(int)
        y_dir = {"accredited": [], "coord": defaultdict(lambda: [0, 0, 0.0])} if wants_dir else None
        stats = parse_ka1(body, year, y_agg, y_accr, y_dir)
        del body
        for k, (p, g) in y_agg.items():
            agg[k][0] += p
            agg[k][1] += g
        for k, n in y_accr.items():
            accr[k] += n
        cache[str(year)] = {
            "bytes": f["bytes"], "sha256": f["sha256"], "downloaded": today(),
            "agg": sorted([g, y, a, p, round(gr, 2)] for (g, y, a), (p, gr) in y_agg.items()),
            "accr": sorted([g, y, n] for (g, y), n in y_accr.items()),
        }
        if wants_dir:
            dcache[str(year)] = dir_by_year[year] = {
                "sha256": f["sha256"],
                "accredited": sorted(y_dir["accredited"]),
                "coord": sorted([k, g, a, b, round(gr, 2)] for (k, g), (a, b, gr) in y_dir["coord"].items()),
            }
        print(f"erasmus: KA1 {year}: {stats}", file=sys.stderr)
    write_json(CACHE, dict(sorted(cache.items())))
    _write_dir_cache({k: dcache[k] for k in sorted(dcache) if int(k) in files})
    print(f"erasmus: downloaded {downloaded} of {len(files)} KA1 files", file=sys.stderr)
    written = ka1_indicators(files, agg, accr)
    written += accredited_organisations(dir_by_year)
    cw = cove_workbook()
    if cw:
        written += cove_indicator(cw)
        written += cove_projects(cw)
    return written
