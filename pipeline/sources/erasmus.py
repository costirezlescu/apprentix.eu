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

No personal data is published: contact persons, addresses and organisation
names are never read into the output. Reuse: both sites point to the
Commission legal notice (CC BY 4.0, Decision 2011/833/EU).
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import html
import io
import re
import sys
import urllib.parse
from collections import defaultdict

from ..common import (FetchError, countries, fetch, geo_code, provenance, read_json,
                      rel, save_raw, write_indicator, INDICATORS, head, today, write_json, RAW)

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
    "description": "Erasmus+ Key Action 1 VET mobility projects and EU grants by coordinating country and call year (2014–2025), new Erasmus accreditations in VET, and organisations taking part in Centres of Vocational Excellence projects.",
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


def parse_ka1(body: bytes, file_year: int, agg: dict, accr: dict) -> dict:
    """Stream one KA1 CSV, adding to agg[(geo, year, action)] = [projects, grant] and accr[(geo, year)]."""
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
            continue
        cell = agg[(geo, year, action)]
        cell[0] += 1
        cell[1] += _amount(row[i_grant]) or 0.0
        stats["vet_projects"] += 1
    text.detach()
    return stats


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


def cove_indicator() -> list[str]:
    page = fetch(COVE_PAGE, timeout=120).decode("utf-8", "replace")
    m = COVE_LINK.search(page)
    if not m:
        print("erasmus: CoVE participants XLSX link not found; skipped", file=sys.stderr)
        return []
    url = urllib.parse.urljoin(COVE_PAGE, html.unescape(m.group(1)))
    body = fetch(url, timeout=120)
    raw, digest = save_raw("erasmus", "cove-participants.xlsx", body)

    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    counts = defaultdict(int)
    extracted = None
    for ws in wb.worksheets:
        if not re.fullmatch(r"\d{4}", ws.title.strip()):
            continue
        year = ws.title.strip()
        header = None
        for row in ws.iter_rows(values_only=True):
            cells = [("" if v is None else str(v).strip()) for v in row]
            if header is None:
                low = [c.lower() for c in cells]
                if "role" in low and "country code" in low:
                    header = (low.index("role"), low.index("country code"))
                elif cells and cells[0].lower().startswith("data extracted"):
                    extracted = cells[0]
                continue
            role = ROLE_MAP.get(cells[header[0]].lower()) if len(cells) > header[0] else None
            geo = geo_code(cells[header[1]].upper()) if len(cells) > header[1] else None
            if role is None or geo is None:
                continue
            counts[(geo, year, role)] += 1
            counts[(geo, year, "TOTAL")] += 1
    wb.close()
    if not counts:
        print("erasmus: CoVE workbook had no usable rows; skipped", file=sys.stderr)
        return []
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


CACHE = RAW / "erasmus" / "ka1-cache.json"
MAX_AGE_DAYS = 28       # open call years: full re-download at least this often
LAST_CLOSED_YEAR = 2020  # 2014–2020 programme is closed


def _load_cache() -> dict:
    return read_json(CACHE) if CACHE.exists() else {}


def _is_fresh(year: int, c: dict | None, size: int | None) -> bool:
    if os.environ.get("APPRENTIX_FORCE") or not c or size is None or size != c["bytes"]:
        return False
    if year <= LAST_CLOSED_YEAR:
        return True
    age = (dt.date.fromisoformat(today()) - dt.date.fromisoformat(c["downloaded"])).days
    return age < MAX_AGE_DAYS


def run() -> list[str]:
    files = discover_ka1()
    cache = _load_cache()
    agg = defaultdict(lambda: [0, 0.0])
    accr = defaultdict(int)
    downloaded = 0
    for year, f in files.items():
        c = cache.get(str(year))
        size = head(f["url"]).get("content-length")
        size = int(size) if size and size.isdigit() else None
        if _is_fresh(year, c, size):
            for geo, y, a, p, g in c["agg"]:
                agg[(geo, y, a)][0] += p
                agg[(geo, y, a)][1] += g
            for geo, y, n in c["accr"]:
                accr[(geo, y)] += n
            f["bytes"], f["sha256"] = c["bytes"], c["sha256"]
            print(f"erasmus: KA1 {year}: unchanged ({size:,} bytes), not downloaded", file=sys.stderr)
            continue
        body = fetch(f["url"], timeout=300, polite_delay=2)
        downloaded += 1
        _, f["sha256"] = save_raw("erasmus", f"ka1-{year}.csv", body, keep=False)
        f["bytes"] = len(body)
        y_agg, y_accr = defaultdict(lambda: [0, 0.0]), defaultdict(int)
        stats = parse_ka1(body, year, y_agg, y_accr)
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
        print(f"erasmus: KA1 {year}: {stats}", file=sys.stderr)
    write_json(CACHE, dict(sorted(cache.items())))
    print(f"erasmus: downloaded {downloaded} of {len(files)} KA1 files", file=sys.stderr)
    written = ka1_indicators(files, agg, accr)
    written += cove_indicator()
    return written
