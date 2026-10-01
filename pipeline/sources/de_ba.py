"""Germany — Bundesagentur für Arbeit (BA) Jobbörse: advertised apprenticeship places (aggregate snapshot).

Endpoint (undocumented public API of the BA job board, documented by the community at
https://github.com/bundesAPI/jobsuche-api):
  GET https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs?angebotsart=4&size=1&page=1
  header X-API-Key: jobboerse-jobsuche   (public client id used by the BA web app)
  angebotsart=4 = 'AUSBILDUNG / Duales Studium'. The response carries 'maxErgebnisse' (total
  number of matching advertisements) and 'facetten' (counts by facet, e.g. ausbildungsart).

No Land breakdown: the API has no Bundesland filter, and the free-text location parameter
('wo=Hessen', 'wo=Sachsen', 'wo=Brandenburg') matches towns of the same name, so Land counts
would be wrong.

Only aggregate counts are kept: one request with size=1 per breakdown; the single returned ad,
employer facets and all ad texts are discarded and never written to disk.

(The related Ausbildungssuche API, /infosysbub/absuche/pc/v1/ausbildungsangebot with
X-API-Key infosysbub-absuche, lists courses of education and training *providers* — school-based
training, preparation measures, retraining — not company apprenticeship vacancies, so it is not used.)

Reuse terms: none published for the API. The bundesAPI repository states no licence. The BA
website imprint (https://www.arbeitsagentur.de/impressum, 'Copyright und Markenschutz') says
content is the BA's intellectual property and use beyond information — copying, distributing,
'Einspeicherung und Verarbeitung in elektronischen Systemen' — needs prior permission, and that
content may be published or passed on only with source attribution. Treat as unverified.

The series grows by one observation per calendar month: the first successful run in a month
records that month's snapshot; later runs in the same month keep it (no refetch), so reruns are
deterministic. Earlier months are read back from the published indicator file.

Produces (geo = DE):
  indicators/de-ba-advertised-training-places   advertised apprenticeship / dual-study places, by type (national only)
"""

from __future__ import annotations

import json
import time

from ..common import (FetchError, INDICATORS, now_iso, provenance, read_json, rel, save_raw,
                      write_indicator)
from .. import common

API = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
HEADERS = {"X-API-Key": "jobboerse-jobsuche", "Accept": "application/json"}
INDICATOR_ID = "de-ba-advertised-training-places"

LICENCE = ("unverified — no licence or terms published for the Jobsuche API (bundesAPI/jobsuche-api states none). "
           "BA imprint: 'Die Nutzung der Inhalte zu anderen Zwecken, insbesondere die Verwendung der Inhalte in "
           "eigenen Werken, das Vervielfältigen/Kopieren oder das Verbreiten, bedarf der ausdrücklichen vorherigen "
           "Genehmigung durch die BA. Alle Inhalte von diesem Internetauftritt dürfen nur unter Angabe der Quelle "
           "(BUNDESAGENTUR FÜR ARBEIT (BA), [Jahresangabe]: [Dokumenttitel], [URL], Stand: [Datum]) veröffentlicht "
           "oder an Dritte weitergegeben werden.' Only aggregate counts are republished.")
LICENCE_URL = "https://www.arbeitsagentur.de/impressum"

SOURCE = {
    "id": "de-ba",
    "name": "Germany — BA Jobbörse: advertised apprenticeship places (monthly snapshot)",
    "publisher": "Bundesagentur für Arbeit (BA)",
    "homepage": "https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=4",
    "description": "Number of apprenticeship and dual-study places currently advertised in the Federal Employment Agency's job board (Jobbörse), recorded once a month, by type (apprenticeship vs dual study). Aggregate counts only — no ad texts or employer details are stored.",
    "access": "api",
    "browser_cors": None,
    "licence": "unverified — no API terms published; BA imprint requires permission for reuse beyond information and source attribution",
    "cadence": "monthly snapshot (first run of each month)",
    "secret": None,
    # Not published until the publisher agrees; see pipeline/run.py.
    "permission_needed": 'The BA imprint requires prior permission to reuse its content, and the API has no published terms. Ask the Bundesagentur für Arbeit before enabling.',
    "reuse_note": "Undocumented public API (client id from the BA web app); reuse terms unclear — aggregate counts only.",
    "outputs": [f"indicators/{INDICATOR_ID}"],
}

TYPES = {"TOTAL": "All (apprenticeship and dual study)", "AUSBILDUNG": "Apprenticeship (Ausbildung)",
         "DUALES_STUDIUM": "Dual study programme (Duales Studium)"}
# ausbildungsart facet codes as returned by the API: 0 = Ausbildung; 1 and 2 = Duales Studium variants.
TYPE_CODES = {"0": "AUSBILDUNG", "1": "DUALES_STUDIUM", "2": "DUALES_STUDIUM"}


def query(params: dict, tries: int = 5) -> dict:
    """GET with retries; the service resets connections under load. Only counts are returned."""
    last = None
    for attempt in range(tries):
        try:
            body = common.fetch(API, params={**params, "size": 1, "page": 1}, headers=HEADERS,
                                timeout=60, polite_delay=2.0, retries=1)
            d = json.loads(body)
            if "maxErgebnisse" not in d:
                raise FetchError(f"unexpected response keys {sorted(d)[:8]}")
            return {"maxErgebnisse": d["maxErgebnisse"],
                    "ausbildungsart": (d.get("facetten", {}).get("ausbildungsart", {}) or {}).get("counts", {})}
        except (FetchError, OSError, ValueError) as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise FetchError(f"BA Jobsuche failed after {tries} attempts: {last}")


def previous() -> tuple[list[dict], dict | None]:
    path = INDICATORS / f"{INDICATOR_ID}.json"
    if not path.exists():
        return [], None
    old = read_json(path)
    return old.get("series", []), old


def run() -> list[str]:
    month = now_iso()[:7]
    series, old = previous()
    if any(o["time"] == month for o in series):
        return []  # this month's snapshot already recorded

    snap = query({"angebotsart": 4})
    counts = {"TOTAL": snap["maxErgebnisse"]}
    for code, n in snap["ausbildungsart"].items():
        t = TYPE_CODES.get(str(code))
        if t:
            counts[t] = counts.get(t, 0) + n
    new = [{"geo": "DE", "time": month, "value": v, "dims": {"type": t}} for t, v in counts.items()]

    raw_doc = {"retrieved_at": now_iso(), "query": {"angebotsart": 4}, "counts": counts,
               "ausbildungsart_facet": snap["ausbildungsart"]}
    raw, digest = save_raw("de-ba", f"snapshot-{month}.json",
                           (json.dumps(raw_doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode())

    ind = {
        "id": INDICATOR_ID,
        "title": "Advertised apprenticeship places in the BA job board (Germany)",
        "description": "Number of advertisements for in-company apprenticeships (Ausbildung) and dual study places open in the Federal Employment Agency's online job board (Jobbörse) at the time of the monthly snapshot. Time is the month of the snapshot.",
        "unit": "advertisements",
        "topic": "Vacancies",
        "national": True,
        "source_label": "BA Jobbörse, Jobsuche API, angebotsart=4 (Ausbildung/Duales Studium)",
        "comparability": ("Snapshot count of advertisements (not places, not contracts) live in the BA Jobbörse when the "
                          "pipeline ran in that month; an advertisement can cover several places, and it includes ads "
                          "imported from partner job boards (externe Stellenbörsen) and dual study programmes. Not the "
                          "BA's official training-market statistics (registered training places, reporting year Oct–Sep). "
                          "Counts vary with the season (peak before the August/September training start). "
                          "National series: do not add to other countries' figures."),
        "dims": [{"key": "type", "label": "Type", "values": TYPES, "default": "TOTAL"}],
        "provenance": {
            **provenance(publisher="Bundesagentur für Arbeit (BA)", dataset_code="jobsuche-service pc/v6/jobs angebotsart=4",
                         source_url=SOURCE["homepage"], api_url=f"{API}?angebotsart=4&size=1&page=1 (X-API-Key: jobboerse-jobsuche)",
                         licence=LICENCE,
                         citation=f"Bundesagentur für Arbeit (BA), Jobbörse — Ausbildungsangebote (Stand: {month}), https://www.arbeitsagentur.de/jobsuche/. Aggregation by Apprentix.",
                         raw=raw, raw_sha256=digest),
            "licence_url": LICENCE_URL,
        },
        "series": [o for o in series if o["time"] != month] + new,
    }
    return [rel(write_indicator(ind))]
