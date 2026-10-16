"""Germany — Statistik der Bundesagentur für Arbeit (BA): the apprenticeship-market statistics
(Ausbildungsmarktstatistik).

File (stable "Aktuell" address, replaced when the BA publishes a new edition; product ID 181,
"Bewerberinnen und Bewerber sowie Berufsausbildungsstellen — Zeitreihe"):
  https://statistik.arbeitsagentur.de/Statistikdaten/Detail/Aktuell/ausbildungsmarkt/zr-monat-ausbm/zr-monat-ausbm-d-0-xlsx.xlsx
Sheets Zeitreihe_Stellen / _Stellen_unbes / _Bewerber / _Bewerber_unvers: one row per region
(Germany, West/East, Länder, districts), one column per month March–September of each reporting
year (Berichtsjahr, 1 October – 30 September), values cumulative since the start of the reporting
year. The September column is the reporting-year total at 30 September, which is what we publish.

What is counted: training places for occupations recognised under the Vocational Training Act
(BBiG, including the Crafts Code) that employers registered with the employment agencies and job
centres for placement, and the young people who used their placement service. Registration is
voluntary, so these are not all apprenticeship places or all applicants.

Reuse: "Daten und Tabellen ... dürfen uneingeschränkt verwendet werden"; information may be stored
and passed on with a source credit; own calculations must be marked; values must not be altered.
Credit: "© Statistik der Bundesagentur für Arbeit", online with a link to its homepage
(https://statistik.arbeitsagentur.de/DE/Home/Service/Impressum/impressum_node.html).

Replaces the earlier job-board connector (advertised places from the BA Jobbörse API), whose
reuse needed the BA's permission.

Produces (geo = DE, by Land; time = the year the reporting year ends, e.g. 2025 = 2024/25):
  indicators/de-ba-training-places          registered training places
  indicators/de-ba-unfilled-places          of which unfilled at 30 September
  indicators/de-ba-applicants               registered applicants
  indicators/de-ba-unplaced-applicants      of which unplaced at 30 September
"""

from __future__ import annotations

import hashlib
import io
import re
import warnings

from ..common import FetchError, fetch, latest_raw, provenance, rel, save_raw, write_indicator

URL = ("https://statistik.arbeitsagentur.de/Statistikdaten/Detail/Aktuell/ausbildungsmarkt/zr-monat-ausbm/"
       "zr-monat-ausbm-d-0-xlsx.xlsx?__blob=publicationFile&v=1")
LANDING = "https://statistik.arbeitsagentur.de/DE/Navigation/Statistiken/Fachstatistiken/Ausbildungsmarkt/Ausbildungsmarkt-Nav.html"
HOME = "https://statistik.arbeitsagentur.de/"
TERMS = "https://statistik.arbeitsagentur.de/DE/Home/Service/Impressum/impressum_node.html"
PUBLISHER = "Statistik der Bundesagentur für Arbeit"
LICENCE = ("Free reuse with source credit: '© Statistik der Bundesagentur für Arbeit' (BA statistics imprint: data and "
           "tables 'dürfen uneingeschränkt verwendet werden'; own calculations must be marked; values must not be altered)")

SOURCE = {
    "id": "de-ba-statistik",
    "name": "Statistik der Bundesagentur für Arbeit — Ausbildungsmarkt (Germany)",
    "publisher": PUBLISHER,
    "homepage": LANDING,
    "description": "Training places and applicants registered with Germany's employment agencies and job centres, "
                   "per reporting year (October–September) and Land, since 2008/09: registered and unfilled training "
                   "places, registered and unplaced applicants.",
    "access": "file",
    "browser_cors": False,
    "licence": LICENCE,
    "cadence": "annual (revised figures in July; reporting-year results end of October), file checked weekly",
    "secret": None,
    "outputs": ["indicators/de-ba-training-places", "indicators/de-ba-unfilled-places",
                "indicators/de-ba-applicants", "indicators/de-ba-unplaced-applicants"],
}

warnings.filterwarnings("ignore", message="Unknown extension is not supported", module="openpyxl")

LAENDER = {"01": "Schleswig-Holstein", "02": "Hamburg", "03": "Lower Saxony", "04": "Bremen",
           "05": "North Rhine-Westphalia", "06": "Hesse", "07": "Rhineland-Palatinate", "08": "Baden-Württemberg",
           "09": "Bavaria", "10": "Saarland", "11": "Berlin", "12": "Brandenburg", "13": "Mecklenburg-Vorpommern",
           "14": "Saxony", "15": "Saxony-Anhalt", "16": "Thuringia"}

COMMON = ("National statistic (Germany), not comparable with other countries. Counts only what was registered with "
          "the employment agencies (Agenturen für Arbeit) and job centres for placement: registration is voluntary for "
          "employers and young people, so these are not all apprenticeship places or all applicants. Occupations "
          "recognised under the Vocational Training Act (BBiG, incl. the Crafts Code), i.e. mostly dual training. "
          "Time is the year in which the reporting year (1 October – 30 September) ends: 2025 = 2024/25; values are "
          "the reporting-year totals at 30 September. The most recent year may carry revised data. Source: "
          "© Statistik der Bundesagentur für Arbeit.")

MEASURES = [
    {"sheet": "Zeitreihe_Stellen", "id": "de-ba-training-places", "unit": "training places",
     "title": "Training places registered with the employment agencies (Germany)",
     "description": "Company training places (Berufsausbildungsstellen) that employers registered with the employment "
                    "agencies and job centres for placement during the reporting year (October–September), by Land.",
     "extra": ""},
    {"sheet": "Zeitreihe_Stellen_unbes", "id": "de-ba-unfilled-places", "unit": "training places",
     "title": "Registered training places still unfilled at 30 September (Germany)",
     "description": "Registered training places that were still vacant at the end of the reporting year (30 September), "
                    "by Land: a measure of employers' difficulty in finding apprentices.",
     "extra": " Unfilled = registered places with no apprentice at 30 September."},
    {"sheet": "Zeitreihe_Bewerber", "id": "de-ba-applicants", "unit": "applicants",
     "title": "Applicants for training places registered with the employment agencies (Germany)",
     "description": "Young people who used the employment agencies' and job centres' placement service to look for a "
                    "training place during the reporting year (October–September), by Land of residence.",
     "extra": ""},
    {"sheet": "Zeitreihe_Bewerber_unvers", "id": "de-ba-unplaced-applicants", "unit": "applicants",
     "title": "Registered applicants still without a training place at 30 September (Germany)",
     "description": "Registered applicants who at the end of the reporting year (30 September) had neither a training "
                    "place nor an alternative (such as school, a course or a job) and were still looking, by Land.",
     "extra": " Unplaced (unversorgt) excludes applicants with an alternative who still want a training place."},
]


def download() -> tuple[bytes, object, str]:
    try:
        body = fetch(URL, timeout=180)
        if body[:2] == b"PK":
            raw, digest = save_raw("de-ba-statistik", "zr-monat-ausbm.xlsx", body)
            return body, raw, digest
    except FetchError:
        pass
    raw = latest_raw("de-ba-statistik", "*-zr-monat-ausbm.xlsx")
    if not raw:
        raise RuntimeError(f"BA statistics download failed and no stored copy exists ({URL})")
    body = raw.read_bytes()
    return body, raw, hashlib.sha256(body).hexdigest()


def parse_sheet(ws) -> dict[str, dict[str, float]]:
    """{land key ('DE' or '01'…'16'): {end year: value at 30 September}}."""
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows) if r and str(r[0] or "").startswith("Regionen"))
    years, dates = rows[hdr_i], rows[hdr_i + 1]
    cols = {}                      # column -> end year, September columns only
    current = None
    for j in range(1, len(years)):
        m = re.search(r"(\d{4})/(\d{2})", str(years[j] or ""))
        if m:
            current = m.group(1)
        d = dates[j]
        if current and hasattr(d, "month") and d.month == 9:
            cols[j] = str(d.year)
    if len(cols) < 5:
        raise RuntimeError(f"BA workbook layout changed in {ws.title}: found only {len(cols)} September columns")
    out: dict[str, dict[str, float]] = {}
    for r in rows[hdr_i + 3:]:
        name = str(r[0] or "").strip()
        key = "DE" if name == "Gesamt" else (name[:2] if re.fullmatch(r"\d\d [^\d].*", name) else None)
        if key is None or (key != "DE" and key not in LAENDER):
            continue                               # West/East and districts
        vals = {y: float(r[j]) for j, y in cols.items() if isinstance(r[j], (int, float))}
        if vals:
            out[key] = vals
    if "DE" not in out or len(out) < 17:
        raise RuntimeError(f"BA workbook {ws.title}: expected Germany and 16 Länder, found {sorted(out)}")
    return out


def run() -> list[str]:
    import openpyxl
    body, raw, digest = download()
    wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    written = []
    for m in MEASURES:
        data = parse_sheet(wb[m["sheet"]])
        series = [{"geo": "DE", "time": y, "value": v, "dims": {"land": k}}
                  for k, by_year in sorted(data.items()) for y, v in sorted(by_year.items())]
        ind = {
            "id": m["id"],
            "title": m["title"],
            "description": m["description"],
            "unit": m["unit"],
            "topic": "Participation",
            "national": True,
            "source_label": f"{PUBLISHER}, Ausbildungsmarkt time series (product 181), sheet {m['sheet']}",
            "comparability": COMMON + m["extra"],
            "dims": [{"key": "land", "label": "Land", "values": {"DE": "Germany", **LAENDER}, "default": "DE"}],
            "provenance": provenance(
                publisher=PUBLISHER, dataset_code="Ausbildungsmarkt, Zeitreihe (Produkt-ID 181)", source_url=LANDING,
                api_url=URL.split("?")[0], licence=LICENCE,
                citation=f"© Statistik der Bundesagentur für Arbeit, Bewerberinnen und Bewerber sowie "
                         f"Berufsausbildungsstellen — Zeitreihe ({m['sheet']}). {HOME}",
                raw=raw, raw_sha256=digest),
            "licence_url": TERMS,
            "series": series,
        }
        written.append(rel(write_indicator(ind)))
    return written
