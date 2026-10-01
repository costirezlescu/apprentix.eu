"""Switzerland — Federal Statistical Office (BFS/OFS): initial VET (berufliche Grundbildung).

Datasets are catalogued on opendata.swiss (CKAN) and served by the BFS PxWeb API:
  catalogue: https://ckan.opendata.swiss/api/3/action/package_show?id=<dataset>
             (opendata.swiss/api/... redirects; the ckan. host answers directly)
  data:      POST https://www.pxweb.bfs.admin.ch/api/v1/de/<table>/<table>.px  (JSON-stat 2.0)

The PxWeb table id is read from the CKAN record each run (falling back to the
known id), so a renamed table is picked up without editing this file.

Terms: opendata.swiss "Open use. Must provide the source." (terms_by); the BFS
table pages say "Freie Nutzung - Quellenangabe ist Pflicht".

Produces (all geo = CH, national figures):
  indicators/ch-bfs-learners-vet          learners in initial VET by programme type, since 1999/2000 (SDL)
  indicators/ch-bfs-learners-vet-form     learners by training form (dual / school-based), type, sex, since 2005 (SBG-SFPI)
  indicators/ch-bfs-learners-vet-canton   learners by canton of the training company and training form
  indicators/ch-bfs-entrants-vet          entrants by training form, type, sex
  indicators/ch-bfs-qualifications-vet    VET qualifications (EFZ/EBA) by training form, type, sex
"""

from __future__ import annotations

import itertools
import json

from ..common import FetchError, fetch, fetch_json, provenance, rel, save_raw, write_indicator

CKAN = "https://ckan.opendata.swiss/api/3/action/package_show"
PXAPI = "https://www.pxweb.bfs.admin.ch/api/v1/de/{t}/{t}.px"
DATASET_PAGE = "https://opendata.swiss/de/dataset/{name}"

LICENCE = ("opendata.swiss terms of use 'Open use. Must provide the source.' (terms_by): "
           "non-commercial and commercial use allowed; you must provide the source (author, title "
           "and link to the dataset). BFS: 'Freie Nutzung - Quellenangabe ist Pflicht'.")
LICENCE_URL = "https://opendata.swiss/en/terms-of-use#terms_by"

SOURCE = {
    "id": "ch-bfs",
    "name": "Switzerland — BFS initial VET statistics (opendata.swiss)",
    "publisher": "Swiss Federal Statistical Office (BFS/OFS)",
    "homepage": "https://www.bfs.admin.ch/bfs/de/home/statistiken/bildung-wissenschaft/personen-ausbildung/sekundarstufe-II.html",
    "description": "Learners, entrants and qualifications in Swiss initial VET (EFZ/EBA), split into dual (company-based) and full-time school-based training, by sex and canton. National series.",
    "access": "api",
    "browser_cors": None,
    "licence": "opendata.swiss terms_by (open use, source must be cited)",
    "cadence": "annual (SDL learners in February; SBG-SFPI entrants/stock/qualifications in June)",
    "secret": None,
    "outputs": ["indicators/ch-bfs-learners-vet", "indicators/ch-bfs-learners-vet-form",
                "indicators/ch-bfs-learners-vet-canton", "indicators/ch-bfs-entrants-vet",
                "indicators/ch-bfs-qualifications-vet"],
}

# BFS codes -> site codes and English labels.
SEX = {"0": ("T", "Total"), "1": ("M", "Males"), "2": ("F", "Females")}
FORM = {"0": ("TOTAL", "Total"), "20": ("DUAL", "Dual (company-based)"),
        "10": ("SCHOOL", "Full-time school-based"), "99": ("UNK", "Not recorded")}
TYPE_SBG = {"0": ("TOTAL", "Total"), "1": ("EFZ", "Federal VET Diploma (EFZ/CFC, 3–4 years)"),
            "2": ("EBA", "Federal VET Certificate (EBA/AFP, 2 years)"),
            "3": ("NONREG", "Not regulated by the VET Act")}
TYPE_SDL = {"0": ("TOTAL", "Total"), "221": ("EFZ", "Federal VET Diploma (EFZ/CFC)"),
            "222": ("EBA", "Federal VET Certificate (EBA/AFP)"),
            "223": ("NONREG", "Not regulated by the VET Act"),
            "224": ("HMS_IMS", "Commercial and IT schools (HMS/IMS, until 2013)"),
            "225": ("ANLEHRE", "Anlehre (former short training, phased out)")}
CANTONS = ["CH", "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL",
           "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU"]

SBG_NOTE = ("Source: BFS survey 'Berufliche Grundbildung (inkl. Qualifikationsverfahren)' (SBG-SFPI), "
            "calendar-year reference period, based on apprenticeship-contract and qualification-procedure records. ")

SPECS = [
    {
        "id": "ch-bfs-learners-vet",
        "dataset": "sekundarstufe-ii-berufliche-grundbildung-lernende-nach-bildungstyp-ausbildungsfeld-geschlecht-u3",
        "table": "px-x-1502020100_104",
        "query": {"Bildungstyp": "*", "Ausbildungsfeld": ["0"], "Geschlecht": "*",
                  "Staatsangehörigkeit (Kategorie)": ["0"], "Jahr": "*"},
        "dims": {"Bildungstyp": ("type", "Programme type", TYPE_SDL),
                 "Geschlecht": ("sex", "Sex", SEX)},
        "title": "Learners in initial VET (Switzerland)",
        "unit": "learners",
        "topic": "Participation",
        "description": "Number of learners enrolled in upper-secondary initial vocational education and training in Switzerland, by programme type (EFZ, EBA, non-regulated, commercial/IT schools, Anlehre) and sex. Time is the first calendar year of the school year (1999 = 1999/2000).",
        "comparability": "National series (BFS learners statistics, SDL; reference period = school year). Counts all learners in initial VET — both dual apprenticeships and full-time school-based programmes — so it is broader than an apprenticeship-contract count. The training-form split is in ch-bfs-learners-vet-form. Do not add to other countries' figures.",
    },
    {
        "id": "ch-bfs-learners-vet-form",
        "dataset": "gesamtbestand-der-lernenden-nach-ausbildungsfeld-lehrbetriebskanton-ausbildungstyp-ausbildungsf1",
        "table": "px-x-1502020100_203",
        "query": {"Ausbildungsfeld": ["0"], "Lehrbetriebskanton": ["0"], "Ausbildungstyp": "*",
                  "Ausbildungsform": "*", "Geschlecht": "*", "Jahr": "*"},
        "dims": {"Ausbildungsform": ("form", "Training form", FORM),
                 "Ausbildungstyp": ("type", "Qualification type", TYPE_SBG),
                 "Geschlecht": ("sex", "Sex", SEX)},
        "title": "Learners in initial VET by training form — dual vs school-based (Switzerland)",
        "unit": "learners",
        "topic": "Participation",
        "description": "Total stock of learners in Swiss initial VET (EFZ, EBA and non-regulated programmes), split into dual (training company + vocational school) and full-time school-based training, by qualification type and sex.",
        "comparability": SBG_NOTE + "Stock of learners during the calendar year, including full-time school-based programmes unless the 'Dual' training form is selected. The training form was not recorded in 2005–2006 (all learners appear as 'Not recorded'). Differs slightly from ch-bfs-learners-vet (different survey and reference period). National series: do not add to other countries' figures.",
    },
    {
        "id": "ch-bfs-learners-vet-canton",
        "dataset": "gesamtbestand-der-lernenden-nach-ausbildungsfeld-lehrbetriebskanton-ausbildungstyp-ausbildungsf1",
        "table": "px-x-1502020100_203",
        "query": {"Ausbildungsfeld": ["0"], "Lehrbetriebskanton": "*", "Ausbildungstyp": ["0"],
                  "Ausbildungsform": "*", "Geschlecht": ["0"], "Jahr": "*"},
        "dims": {"Lehrbetriebskanton": ("canton", "Canton of the training company", None),
                 "Ausbildungsform": ("form", "Training form", FORM)},
        "title": "Learners in initial VET by canton and training form (Switzerland)",
        "unit": "learners",
        "topic": "Participation",
        "description": "Total stock of learners in Swiss initial VET by canton of the training company (Lehrbetriebskanton) and training form (dual vs full-time school-based). 'CH' is the national total.",
        "comparability": SBG_NOTE + "Cantons are those of the training company (cantonal boundaries as at 1.1.2022). National series: do not add to other countries' figures.",
    },
    {
        "id": "ch-bfs-entrants-vet",
        "dataset": "eintritte-nach-ausbildungsfeld-lehrbetriebskanton-ausbildungstyp-ausbildungsform-geschlecht-und1",
        "table": "px-x-1502020100_103",
        "query": {"Ausbildungsfeld": ["0"], "Lehrbetriebskanton": ["0"], "Ausbildungstyp": "*",
                  "Ausbildungsform": "*", "Geschlecht": "*", "Jahr": "*"},
        "dims": {"Ausbildungsform": ("form", "Training form", FORM),
                 "Ausbildungstyp": ("type", "Qualification type", TYPE_SBG),
                 "Geschlecht": ("sex", "Sex", SEX)},
        "title": "Entrants to initial VET by training form (Switzerland)",
        "unit": "entrants",
        "topic": "Participation",
        "description": "Number of people entering Swiss initial VET (new learners) in the calendar year, by training form (dual vs full-time school-based), qualification type and sex.",
        "comparability": SBG_NOTE + "A flow (entries in the year), not a stock; closest Swiss equivalent of 'new apprenticeship contracts' when the 'Dual' form is selected. National series: do not add to other countries' figures.",
    },
    {
        "id": "ch-bfs-qualifications-vet",
        "dataset": "abschlusse-nach-ausbildungsfeld-lehrbetriebskanton-ausbildungstyp-ausbildungsform-geschlecht-un1",
        "table": "px-x-1502020100_303",
        "query": {"Ausbildungsfeld": ["0"], "Lehrbetriebskanton": ["0"], "Ausbildungstyp": "*",
                  "Ausbildungsform": "*", "Geschlecht": "*", "Jahr": "*"},
        "dims": {"Ausbildungsform": ("form", "Training form", FORM),
                 "Ausbildungstyp": ("type", "Qualification type", TYPE_SBG),
                 "Geschlecht": ("sex", "Sex", SEX)},
        "title": "Initial VET qualifications awarded by training form (Switzerland)",
        "unit": "qualifications",
        "topic": "Outcomes",
        "description": "Number of initial VET qualifications awarded in Switzerland (Federal VET Diploma EFZ, Federal VET Certificate EBA, non-regulated), by training form (dual vs full-time school-based) and sex.",
        "comparability": SBG_NOTE + "Counts qualifications (successful qualification procedures) in the calendar year, not learners. National series: do not add to other countries' figures.",
    },
]


def find_dataset(spec: dict) -> tuple[str, str | None, str]:
    """Return (pxweb table id, issued date, dataset page) from opendata.swiss, or the defaults."""
    name, table, issued = spec["dataset"], spec["table"], None
    try:
        res = fetch_json(CKAN, params={"id": name})["result"]
        name = res.get("name", name)
        issued = (res.get("issued") or "")[:10] or None
        for r in res.get("resources", []):
            url = r.get("url") or ""
            if "pxweb.bfs.admin.ch" in url and "/px-x-" in url:
                table = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".px")
                break
    except (FetchError, KeyError, ValueError):
        pass
    return table, issued, DATASET_PAGE.format(name=name)


def query(table: str, q: dict) -> tuple[dict, bytes]:
    body = {"query": [{"code": k, "selection": ({"filter": "all", "values": ["*"]} if v == "*"
                                                 else {"filter": "item", "values": v})}
                      for k, v in q.items()],
            "response": {"format": "json-stat2"}}
    raw = fetch(PXAPI.format(t=table), data=json.dumps(body).encode(), method="POST",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=120, polite_delay=1.0)
    return json.loads(raw), raw


def decode(js: dict) -> list[dict]:
    ids = js["id"]
    cats = []
    for d in ids:
        idx = js["dimension"][d]["category"]["index"]
        cats.append(sorted(idx, key=idx.get) if isinstance(idx, dict) else idx)
    vals = js["value"]
    if isinstance(vals, dict):
        vals = [vals.get(str(i)) for i in range(len(list(itertools.product(*cats))))]
    return [{**dict(zip(ids, combo)), "_v": vals[i]} for i, combo in enumerate(itertools.product(*cats))]


def build(spec: dict) -> dict:
    table, issued, page = find_dataset(spec)
    js, body = query(table, spec["query"])
    raw, digest = save_raw("ch-bfs", f"{spec['id']}.json", body)
    rows = decode(js)

    # Training form not recorded: when 'Not recorded' equals the total, the dual/school split
    # for that year is unknown (shown as 0 by BFS) and must not be published as zero.
    unrecorded = set()
    if "Ausbildungsform" in spec["dims"]:
        tot, unk = {}, {}
        for r in rows:
            key = tuple((k, r[k]) for k in sorted(r) if k not in ("Ausbildungsform", "_v"))
            if r["Ausbildungsform"] == "0":
                tot[key] = r["_v"]
            elif r["Ausbildungsform"] == "99":
                unk[key] = r["_v"]
        unrecorded = {k for k, v in tot.items() if v and unk.get(k) == v}

    dims_out, series = [], []
    labels = {}
    for src, (key, label, mapping) in spec["dims"].items():
        cat = js["dimension"][src]["category"]
        order = sorted(cat["index"], key=cat["index"].get)
        if mapping is None:  # cantons
            if len(order) != len(CANTONS):
                raise ValueError(f"{table}: unexpected canton list ({len(order)} values)")
            mapping = {c: (CANTONS[i], "Switzerland" if i == 0 else cat["label"][c])
                       for i, c in enumerate(order)}
        labels[src] = mapping
        values = {mapping[c][0]: mapping[c][1] for c in order if c in mapping}
        default = "CH" if key == "canton" else "TOTAL" if "TOTAL" in values else "T" if "T" in values else next(iter(values))
        dims_out.append({"key": key, "label": label, "values": values, "default": default})

    for r in rows:
        if r["_v"] is None:
            continue
        if r.get("Ausbildungsform") in ("10", "20"):
            key = tuple((k, r[k]) for k in sorted(r) if k not in ("Ausbildungsform", "_v"))
            if key in unrecorded:
                continue
        dims = {spec["dims"][src][0]: labels[src][r[src]][0] for src in spec["dims"]}
        series.append({"geo": "CH", "time": r["Jahr"], "value": r["_v"], "dims": dims})

    api_url = PXAPI.format(t=table)
    return {
        "id": spec["id"],
        "title": spec["title"],
        "description": spec["description"],
        "unit": spec["unit"],
        "topic": spec["topic"],
        "national": True,
        "source_label": js.get("label"),
        "comparability": spec["comparability"],
        "dims": dims_out,
        "provenance": {
            **provenance(
                publisher="Swiss Federal Statistical Office (BFS)", dataset_code=table,
                source_url=page, api_url=api_url, licence=LICENCE,
                citation=f"BFS, {js.get('label')} ({table}). opendata.swiss / BFS PxWeb. Source: {js.get('source', 'BFS')}.",
                source_updated=issued, raw=raw, raw_sha256=digest),
            "licence_url": LICENCE_URL,
        },
        "series": series,
    }


def run() -> list[str]:
    return [rel(write_indicator(build(spec))) for spec in SPECS]
