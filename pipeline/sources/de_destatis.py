"""Germany — Destatis GENESIS-Online, statistic 21211 'Berufsbildungsstatistik'.

API: GENESIS web services, RESTful/JSON, guide v5.1
  https://genesis.destatis.de/datenbank/online/docs/GENESIS-Webservices_Introduction.pdf
  POST https://genesis.destatis.de/genesisWS/rest/2020/data/tablefile
  account data in HTTP headers ('username' = personal 32-character API token, empty 'password'),
  further parameters form-encoded in the body (Content-Type application/x-www-form-urlencoded).
  format=ffcsv returns a zip with one flat CSV (';'-separated; revised 2025 layout with English
  column names: time, N_variable_code/_label, N_variable_attribute_code/_label,
  value_variable_code/_label, value, value_unit [, value_q]).

The token is free: register at GENESIS-Online and copy it from the 'Webservice (API)' dialog.
Set it as the DESTATIS_TOKEN environment variable (GitHub Actions secret). The 'find' method
works anonymously, data downloads do not.

Licence: Datenlizenz Deutschland – Namensnennung – Version 2.0 (Destatis Open Data page:
"GENESIS-Online can be used free of charge and without registering under the 'Data Licence
Germany - Namensnennung - Version 2.0'").

Produces (geo = DE, national figures; written only when DESTATIS_TOKEN is set):
  indicators/de-destatis-apprentices        apprentices at 31 Dec by sex and training area (21211-0001)
  indicators/de-destatis-new-contracts      newly concluded training contracts by sex and training area (21211-0004)
  indicators/de-destatis-exams-passed       final examinations passed by sex and training area (21211-0007)
  indicators/de-destatis-apprentices-land   apprentices at 31 Dec by Land and sex (21211-0101)
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.parse
import zipfile

from ..common import FetchError, fetch, provenance, rel, save_raw, write_indicator

API = "https://genesis.destatis.de/genesisWS/rest/2020/"
TABLE_PAGE = "https://www-genesis.destatis.de/datenbank/online/table/{name}"
STAT_PAGE = "https://www-genesis.destatis.de/datenbank/online/statistic/21211/details"
TOKEN_ENV = "DESTATIS_TOKEN"
LICENCE = "dl-de/by-2-0"

SOURCE = {
    "id": "de-destatis",
    "name": "Germany — Destatis GENESIS 21211 (vocational training statistics)",
    "publisher": "Statistisches Bundesamt (Destatis)",
    "homepage": STAT_PAGE,
    "description": "Germany's official vocational training statistics (Berufsbildungsstatistik, 31 December survey): apprentices in dual training under BBiG/HwO, newly concluded training contracts and passed final examinations, by sex, training area and Land.",
    "access": "api",
    "browser_cors": False,
    "licence": LICENCE,
    "cadence": "annual (results for 31 December published in summer of the following year)",
    "secret": TOKEN_ENV,
    "outputs": ["indicators/de-destatis-apprentices", "indicators/de-destatis-new-contracts",
                "indicators/de-destatis-exams-passed", "indicators/de-destatis-apprentices-land"],
}

BASE_NOTE = ("National series from the Berufsbildungsstatistik (statistic 21211; reported by the competent bodies "
             "— chambers etc. — to the statistical offices). Covers dual vocational training under the Vocational "
             "Training Act (BBiG) and the Crafts Code (HwO) only; school-based VET (e.g. health and care schools, "
             "Berufsfachschulen) is not included. ")

# Variable recognition: by GENESIS code where known, else by label (language=en / de).
VARS = {
    "sex": (("GES",), r"\bsex\b|geschlecht"),
    "nationality": (("NAT",), r"nationalit|staatsangeh"),
    "training_area": ((), r"training area|ausbildungsbereich"),
    "land": (("DLAND",), r"l(ä|ae)nder|\bland\b|federal state"),
    "germany": (("DINSG",), r"^germany$|^deutschland"),  # national-total regional variable, always dropped
}
SEX_MAP = {"GESM": "M", "GESW": "F", "male": "M", "female": "F", "männlich": "M", "weiblich": "F"}
SEX_LABELS = {"T": "Total", "M": "Males", "F": "Females"}
LAND_LABELS = {"08": "Baden-Württemberg", "09": "Bavaria", "11": "Berlin", "12": "Brandenburg", "04": "Bremen",
               "02": "Hamburg", "06": "Hesse", "13": "Mecklenburg-Vorpommern", "03": "Lower Saxony",
               "05": "North Rhine-Westphalia", "07": "Rhineland-Palatinate", "10": "Saarland", "14": "Saxony",
               "15": "Saxony-Anhalt", "01": "Schleswig-Holstein", "16": "Thuringia"}

SPECS = [
    {
        "id": "de-destatis-apprentices", "table": "21211-0001",
        "keep": ["sex", "training_area"], "drop": ["nationality"], "value_match": r"apprentice|auszubild",
        "title": "Apprentices in dual vocational training (Germany)",
        "unit": "apprentices", "topic": "Participation",
        "description": "Number of apprentices (Auszubildende) in dual vocational training in Germany on 31 December, by sex and training area (Ausbildungsbereich: industry and trade, crafts, public service, agriculture, liberal professions, housekeeping, shipping).",
        "comparability": BASE_NOTE + "Stock on 31 December; counts training relationships (contracts), not persons. Do not add to other countries' figures.",
    },
    {
        "id": "de-destatis-new-contracts", "table": "21211-0004",
        "keep": ["sex", "training_area"], "drop": ["nationality"], "value_match": r"new|neu",
        "title": "Newly concluded apprenticeship contracts (Germany)",
        "unit": "contracts", "topic": "Participation",
        "description": "Number of newly concluded training contracts (neu abgeschlossene Ausbildungsverträge) in dual vocational training in Germany during the calendar year, by sex and training area.",
        "comparability": BASE_NOTE + "Flow: contracts concluded between 1 January and 31 December and still recorded by the competent body (Destatis count). BIBB's figure for new contracts (survey at 30 September, see de-bibb) uses a different reference period and is not identical. Do not add to other countries' figures.",
    },
    {
        "id": "de-destatis-exams-passed", "table": "21211-0007",
        "keep": ["sex", "training_area"], "drop": ["nationality"], "value_match": r"pass|bestand",
        "title": "Final apprenticeship examinations passed (Germany)",
        "unit": "examinations", "topic": "Outcomes",
        "description": "Number of final examinations (Abschlussprüfungen) passed in dual vocational training in Germany during the calendar year, by sex and training area.",
        "comparability": BASE_NOTE + "Flow: passed examinations in the calendar year (including external candidates admitted without a training contract, as reported by Destatis). Do not add to other countries' figures.",
    },
    {
        "id": "de-destatis-apprentices-land", "table": "21211-0101",
        "keep": ["land", "sex"], "drop": ["nationality", "training_area"], "value_match": r"apprentice|auszubild",
        "title": "Apprentices in dual vocational training by Land (Germany)",
        "unit": "apprentices", "topic": "Participation",
        "description": "Number of apprentices in dual vocational training on 31 December, by federal state (Land) of the training place and sex. 'DE' is the national total.",
        "comparability": BASE_NOTE + "Stock on 31 December, by Land. Do not add to other countries' figures.",
    },
]


class GenesisError(RuntimeError):
    pass


def tablefile(name: str, token: str, startyear: str = "1990") -> bytes:
    params = {"name": name, "area": "all", "format": "ffcsv", "compress": "false",
              "startyear": startyear, "language": "en"}
    body = fetch(API + "data/tablefile", data=urllib.parse.urlencode(params).encode(), method="POST",
                 headers={"Content-Type": "application/x-www-form-urlencoded",
                          "username": token, "password": ""},
                 timeout=180, polite_delay=1.0)
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv")] or z.namelist()
            return z.read(names[0])
    if body.lstrip()[:1] == b"{":
        try:
            st = json.loads(body)
            st = st.get("Status", st)
        except ValueError:
            st = {}
        raise GenesisError(f"GENESIS {name}: status {st.get('Code')} — {st.get('Content')}")
    return body  # plain CSV


def parse_ffcsv(text: str) -> tuple[list[dict], dict, dict]:
    """Parse the flat-file CSV into rows.

    Returns (rows, variables, value_vars): each row is
    {"time", "vars": {var_code: attr_code}, "vv": value_var_code, "value", "flag"};
    variables = {var_code: {"label", "attrs": {attr_code: attr_label}}}.
    """
    lines = text.splitlines()
    header = lines[0]
    body = [l for l in lines[1:] if l[:4].isdigit()]  # data rows start with the statistic code
    reader = csv.DictReader(io.StringIO("\n".join([header, *body])), delimiter=";")
    cols = reader.fieldnames or []
    nvars = sorted({int(m.group(1)) for c in cols if (m := re.match(r"^(\d+)_variable_code$", c))})
    if "value" not in cols or not nvars:
        raise GenesisError(f"unexpected ffcsv layout: {cols[:12]}")
    rows, variables, value_vars = [], {}, {}
    for r in reader:
        rv = {}
        for n in nvars:
            vc = (r.get(f"{n}_variable_code") or "").strip()
            if not vc:
                continue
            ac = (r.get(f"{n}_variable_attribute_code") or "").strip() or "TOTAL"
            al = (r.get(f"{n}_variable_attribute_label") or "").strip()
            if al.lower() in ("total", "insgesamt"):
                ac = "TOTAL"
            v = variables.setdefault(vc, {"label": (r.get(f"{n}_variable_label") or vc).strip(), "attrs": {}})
            v["attrs"].setdefault(ac, al or ac)
            rv[vc] = ac
        vv = (r.get("value_variable_code") or r.get("value_variable_label") or "").strip()
        value_vars.setdefault(vv, (r.get("value_variable_label") or vv).strip())
        raw = (r.get("value") or "").strip()
        flag = (r.get("value_q") or "").strip() or None
        if raw == "-":
            val = 0.0  # Destatis convention: '-' = nothing (exactly zero)
        else:
            try:
                val = float(raw.replace(",", "")) if raw not in ("", ".", "...", "/", "x") else None
            except ValueError:
                val = None
        ym = re.search(r"(19|20)\d{2}", r.get("time") or r.get("time_label") or "")
        time = ym.group(0) if ym else ""
        rows.append({"time": time, "vars": rv, "vv": vv, "value": val, "flag": flag, "raw": raw})
    return rows, variables, value_vars


def role_of(code: str, label: str) -> str | None:
    for role, (codes, pattern) in VARS.items():
        if code in codes or re.search(pattern, label, re.I):
            return role
    return None


def aggregate(rows: list[dict], var_roles: dict, keep: list[str], drop: list[str]) -> dict:
    """Reduce rows to {(time, *keep attrs): value}, using source totals where present and summing otherwise."""
    role_code = {role: code for code, role in var_roles.items()}
    cube = {}
    for r in rows:
        if r["value"] is None:
            continue
        key = (r["time"], *[r["vars"].get(role_code.get(k), "TOTAL") for k in keep],
               *[r["vars"].get(role_code.get(d), "TOTAL") for d in drop])
        cube[key] = r["value"]
    nk = len(keep)
    # Collapse dropped variables: prefer TOTAL rows, else sum.
    for i in range(len(drop)):
        pos = 1 + nk + i
        has_total = {k[:pos] + k[pos + 1:] for k in cube if k[pos] == "TOTAL"}
        new = {}
        for k, v in cube.items():
            rest = k[:pos] + k[pos + 1:]
            if rest in has_total:
                if k[pos] == "TOTAL":
                    new[rest[:pos] + ("TOTAL",) + rest[pos:]] = v
            else:
                kk = rest[:pos] + ("TOTAL",) + rest[pos:]
                new[kk] = new.get(kk, 0.0) + v
        cube = new
    cube = {k[:1 + nk]: v for k, v in cube.items()}
    # Add totals over kept variables when the source has none.
    for i in range(nk):
        pos = 1 + i
        have = {k for k in cube if k[pos] == "TOTAL"}
        sums = {}
        for k, v in cube.items():
            if k[pos] != "TOTAL":
                kk = k[:pos] + ("TOTAL",) + k[pos + 1:]
                if kk not in have:
                    sums[kk] = sums.get(kk, 0.0) + v
        cube.update(sums)
    return cube


def build(spec: dict, token: str) -> dict:
    raw_bytes = tablefile(spec["table"], token)
    raw, digest = save_raw("de-destatis", f"{spec['table']}.csv", raw_bytes)
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    rows, variables, value_vars = parse_ffcsv(text)

    # Pick the value variable.
    if len(value_vars) > 1:
        match = [c for c, l in value_vars.items() if re.search(spec["value_match"], f"{c} {l}", re.I)]
        if len(match) != 1:
            raise GenesisError(f"{spec['table']}: cannot choose value variable among {value_vars}")
        rows = [r for r in rows if r["vv"] == match[0]]
    vv_label = next(iter(value_vars.values())) if len(value_vars) == 1 else value_vars[match[0]]

    var_roles = {}
    for code, v in variables.items():
        role = role_of(code, v["label"])
        if role is None:
            raise GenesisError(f"{spec['table']}: unknown variable {code} ({v['label']})")
        var_roles[code] = role
    drop = [*spec["drop"], *sorted({r for r in var_roles.values() if r not in spec["keep"] and r not in spec["drop"]})]
    cube = aggregate(rows, var_roles, spec["keep"], drop)

    role_code = {role: code for code, role in var_roles.items()}
    dims, recode = [], {}
    for role in spec["keep"]:
        attrs = variables.get(role_code.get(role), {"attrs": {}})["attrs"]
        if role == "sex":
            rec = {a: SEX_MAP.get(a, SEX_MAP.get(l.lower(), a)) for a, l in attrs.items()}
            rec["TOTAL"] = "T"
            values = {c: SEX_LABELS.get(c, c) for c in ["T", *sorted(set(rec.values()) - {"T"})]}
            dims.append({"key": "sex", "label": "Sex", "values": values, "default": "T"})
        elif role == "land":
            rec = {a: a for a in attrs}
            rec["TOTAL"] = "DE"
            values = {"DE": "Germany", **{a: LAND_LABELS.get(a, attrs[a]) for a in sorted(attrs) if a != "TOTAL"}}
            dims.append({"key": "land", "label": "Land", "values": values, "default": "DE"})
        else:
            rec = {a: a for a in attrs}
            values = {"TOTAL": "Total", **{a: attrs[a] for a in sorted(attrs) if a != "TOTAL"}}
            dims.append({"key": role, "label": "Training area", "values": values, "default": "TOTAL"})
        recode[role] = rec

    series = []
    for k, v in cube.items():
        d = {role: recode[role].get(k[1 + i], k[1 + i]) for i, role in enumerate(spec["keep"])}
        series.append({"geo": "DE", "time": k[0], "value": v, "dims": d})

    api_url = f"{API}data/tablefile (POST name={spec['table']}&format=ffcsv&language=en)"
    return {
        "id": spec["id"],
        "title": spec["title"],
        "description": spec["description"],
        "unit": spec["unit"],
        "topic": spec["topic"],
        "national": True,
        "source_label": f"Destatis GENESIS {spec['table']}: {vv_label}",
        "comparability": spec["comparability"],
        "dims": dims,
        "provenance": provenance(
            publisher="Statistisches Bundesamt (Destatis)", dataset_code=spec["table"],
            source_url=TABLE_PAGE.format(name=spec["table"]), api_url=api_url, licence=LICENCE,
            citation=f"Statistisches Bundesamt (Destatis), GENESIS-Online, table {spec['table']} (Berufsbildungsstatistik). Datenlizenz Deutschland – Namensnennung – Version 2.0.",
            raw=raw, raw_sha256=digest),
        "series": series,
    }


def run() -> list[str]:
    token = os.environ.get(TOKEN_ENV)
    if not token:
        raise FetchError(f"{TOKEN_ENV} is not set; GENESIS data downloads require a personal API token")
    return [rel(write_indicator(build(spec, token))) for spec in SPECS]
