"""Germany — BIBB (Federal Institute for Vocational Education and Training), DAZUBI additional tables.

File (stable name, replaced in place each year):
  https://www.bibb.de/dokumente/xls/dazubi_zusatztabellen_beteiligungsquoten_ab2012.xlsx
  listed on https://www.bibb.de/de/1868.php (DAZUBI Zusatztabellen)
  "Anfänger- und Absolventenquoten der dualen Berufsausbildung (BBiG/HwO) und des Hochschulsystems
  im Vergleich, Deutschland 2012 bis <latest>" — based on the vocational training statistics (31 Dec).

Why not new-contract counts from BIBB: the BIBB survey of new contracts at 30 September (naa309)
is published only through the naa309.bibb.de portal and PDFs, and the DAZUBI all-occupations workbook
covers a single year per file (8 MB, values rounded to multiples of 3, no national total row).
National counts of new contracts come from Destatis 21211 (de-destatis-new-contracts), which is the
same 31 December statistic that DAZUBI is built on.

Licence (stated in the workbook's 'Impressum' sheet): "Der Inhalt dieses Werkes steht unter einer
Creative-Commons-Lizenz (Lizenztyp: Namensnennung – Keine kommerzielle Nutzung – Keine Bearbeitung –
4.0 International)" — i.e. CC BY-NC-ND 4.0. Check that republishing extracted values is acceptable
under 'no derivatives' before publishing.

Produces (geo = DE, national):
  indicators/de-bibb-entry-graduation-rates   training-entrant and graduate rates, dual VET vs higher education
"""

from __future__ import annotations

import io
import re

from ..common import FetchError, fetch, latest_raw, provenance, rel, save_raw, sha256, write_indicator

URL = "https://www.bibb.de/dokumente/xls/dazubi_zusatztabellen_beteiligungsquoten_ab2012.xlsx"
LANDING = "https://www.bibb.de/de/1868.php"
RAW_NAME = "dazubi-beteiligungsquoten.xlsx"

LICENCE = ("CC BY-NC-ND 4.0 — workbook Impressum: 'Der Inhalt dieses Werkes steht unter einer "
           "Creative-Commons-Lizenz (Lizenztyp: Namensnennung – Keine kommerzielle Nutzung – Keine "
           "Bearbeitung – 4.0 International).' (© Bundesinstitut für Berufsbildung)")
LICENCE_URL = "https://creativecommons.org/licenses/by-nc-nd/4.0/"

SOURCE = {
    "id": "de-bibb",
    "name": "Germany — BIBB DAZUBI (training-entrant and graduate rates)",
    "publisher": "Bundesinstitut für Berufsbildung (BIBB)",
    "homepage": LANDING,
    "description": "BIBB's Datensystem Auszubildende (DAZUBI) additional tables: the training-entrant rate (Ausbildungsanfängerquote) and graduate rate of dual VET in Germany compared with higher education, since 2012.",
    "access": "file",
    "browser_cors": None,
    "licence": "CC BY-NC-ND 4.0 (as stated in the BIBB workbook)",
    "cadence": "annual (March)",
    "secret": None,
    # Not published until the publisher agrees; see pipeline/run.py.
    "permission_needed": "Licensed CC BY-NC-ND 4.0; 'no derivatives' may rule out republishing extracted values in charts. Ask BIBB for permission before enabling.",
    "reuse_note": "CC BY-NC-ND: non-commercial, no derivatives — confirm that republishing extracted values is acceptable.",
    "outputs": ["indicators/de-bibb-entry-graduation-rates"],
}

RATES = {
    "AAQ_DUAL": "Training-entrant rate, dual VET (Ausbildungsanfängerquote)",
    "SAQ_HE": "First-year student rate, higher education (excl. international students)",
    "SAQ_HE_INTL": "First-year student rate, higher education (incl. international students)",
    "ABSQ_DUAL": "Graduate rate, dual VET (Absolventenquote)",
    "ABSQ_HE": "Graduate rate, higher education (Absolventenquote)",
}


def download() -> tuple[bytes, object, str]:
    try:
        body = fetch(URL, timeout=120, polite_delay=1.0)
        if body[:2] != b"PK":
            raise FetchError("not an xlsx")
        raw, digest = save_raw("de-bibb", RAW_NAME, body)
        return body, raw, digest
    except FetchError:
        raw = latest_raw("de-bibb", "*-" + RAW_NAME)
        if raw is None:
            raise
        body = raw.read_bytes()
        return body, raw, sha256(body)


def parse(body: bytes) -> tuple[list[dict], dict, str]:
    """Return (observations, footnotes {n: text}, table title)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    ws = next(ws for ws in wb.worksheets if "quoten" in ws.title.lower())
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    title = next((str(r[0]) for r in rows if r and r[0] and str(r[0]).startswith("Tabelle")), "")
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] and str(r[0]).startswith("Berichts"))
    h1 = [re.sub(r"\s+", " ", str(v or "")) for v in rows[hdr_i]]
    h2 = [re.sub(r"\s+", " ", str(v or "")) for v in rows[hdr_i + 1]]
    # Header cells span merged columns: carry the last label to the right.
    span, last = [], ""
    for v in h1:
        last = v or last
        span.append(last)
    cols = {}
    for j, (top, sub) in enumerate(zip(span, h2)):
        if j == 0:
            continue
        if re.search(r"anfängerquote", top, re.I) and re.search(r"duale", top, re.I):
            cols.setdefault("AAQ_DUAL", j)
        elif re.search(r"studienanfänger", top, re.I):
            if re.search(r"\bmit\b", sub):
                cols.setdefault("SAQ_HE_INTL", j)
            elif re.search(r"\bohne\b", sub):
                cols.setdefault("SAQ_HE", j)
        elif re.search(r"absolventenquote", top, re.I) and re.search(r"duale", top, re.I):
            cols.setdefault("ABSQ_DUAL", j)
        elif re.search(r"absolventenquote", top, re.I) and re.search(r"hochschul", top, re.I):
            cols.setdefault("ABSQ_HE", j)
    if set(cols) != set(RATES):
        raise ValueError(f"BIBB rates table layout changed: found columns {cols}")

    obs, notes = [], {}
    for r in rows[hdr_i + 2:]:
        first = str(r[0]).strip() if r and r[0] is not None else ""
        m = re.match(r"^(\d{4})(?:\s+(\d+))?$", first)
        if m:
            year, fn = m.group(1), m.group(2)
            for key, j in cols.items():
                v = r[j] if j < len(r) else None
                if isinstance(v, (int, float)):
                    o = {"geo": "DE", "time": year, "value": float(v), "dims": {"rate": key}}
                    # Footnote 2 marks the dual-VET break (2022), footnote 3 the higher-education break (2023).
                    if fn == "2" and key in ("AAQ_DUAL", "ABSQ_DUAL") or fn == "3" and key.endswith(("_HE", "_HE_INTL")):
                        o["flag"] = "b"
                    obs.append(o)
            continue
        fm = re.match(r"^(\d)\s+(.+)", first, re.S)
        if fm and not obs == []:
            notes[fm.group(1)] = re.sub(r"\s+", " ", fm.group(2)).strip()
    return obs, notes, title


def run() -> list[str]:
    body, raw, digest = download()
    obs, notes, title = parse(body)
    years = sorted({o["time"] for o in obs})
    note_txt = " ".join(f"({k}) {v}" for k, v in sorted(notes.items()))
    ind = {
        "id": "de-bibb-entry-graduation-rates",
        "title": "Training-entrant and graduate rates: dual VET vs higher education (Germany)",
        "description": "Share of the resident population of the relevant ages that starts dual vocational training (BBiG/HwO) for the first time (Ausbildungsanfängerquote, calculated with the quota-sum method) or completes it (Absolventenquote), compared with the first-year student and graduate rates in higher education. Calculated by BIBB and Destatis.",
        "unit": "%",
        "topic": "Participation",
        "national": True,
        "source_label": re.sub(r"\s+", " ", title).strip() or "BIBB DAZUBI: Anfänger- und Absolventenquoten",
        "comparability": ("National German rates based on the vocational training statistics (31 December) and population "
                          "statistics; dual training under BBiG/HwO only (no school-based VET). Rates are not counts and "
                          "use German definitions — not comparable with other countries' series. Flag 'b' marks breaks "
                          "in series. " + note_txt).strip(),
        "dims": [{"key": "rate", "label": "Rate", "values": RATES, "default": "AAQ_DUAL"}],
        "flags": {"b": "break in time series"},
        "provenance": {
            **provenance(publisher="Bundesinstitut für Berufsbildung (BIBB)", dataset_code="DAZUBI Zusatztabellen: Beteiligungsquoten",
                         source_url=LANDING, api_url=URL, licence=LICENCE,
                         citation=f"BIBB, Datensystem Auszubildende (DAZUBI), Zusatztabellen: Anfänger- und Absolventenquoten der dualen Berufsausbildung und des Hochschulsystems im Vergleich, Deutschland {years[0]}–{years[-1]}. CC BY-NC-ND 4.0.",
                         raw=raw, raw_sha256=digest),
            "licence_url": LICENCE_URL,
        },
        "series": obs,
    }
    return [rel(write_indicator(ind))]
