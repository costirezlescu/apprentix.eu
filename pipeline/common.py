"""Shared helpers for the Apprentix data pipeline.

Every connector in pipeline/sources/ uses these so that all output has the
same shape, the same provenance block, and the same file conventions:

  data/raw/<source>/<YYYY-MM-DD>-<name>.<ext>   originals (kept only when they change)
  data/published/indicators/<id>.json|.csv      statistical series
  data/published/<dataset>/records.json         record datasets (explorer)

Standard library only, except openpyxl (Excel) which is imported where needed.
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PUBLISHED = DATA / "published"
INDICATORS = PUBLISHED / "indicators"
REFERENCE = DATA / "reference"

USER_AGENT = (
    "apprentix.eu-data-pipeline/1.0 "
    "(+https://apprentix.eu; https://github.com/costirezlescu/apprentix.eu)"
)

LICENCES = {
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "EC-reuse": "https://eur-lex.europa.eu/eli/dec/2011/833/oj",
    "dl-de/by-2-0": "https://www.govdata.de/dl-de/by-2-0",
    "etalab-2.0": "https://www.etalab.gouv.fr/licence-ouverte-open-licence/",
    "NLOD-2.0": "https://data.norge.no/nlod/en/2.0",
    "OGL-UK-3.0": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC-BY-NC-ND-4.0": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
}


# ---------------------------------------------------------------- time ----

def now_iso() -> str:
    """UTC timestamp, overridable with APPRENTIX_NOW for reproducible runs."""
    fixed = os.environ.get("APPRENTIX_NOW")
    if fixed:
        return fixed
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return now_iso()[:10]


# ---------------------------------------------------------------- warnings

WARNINGS: list[str] = []


def warn(msg: str) -> None:
    """Record something a person should know (e.g. a stale fallback). The runner
    attaches these to the connector's status, and pipeline/watch.py reports them."""
    print(f"  warning: {msg}")
    WARNINGS.append(msg)


# ---------------------------------------------------------------- http ----

class FetchError(RuntimeError):
    pass


def _ssl_context():
    # python.org builds on macOS ship without CA certificates; certifi fixes that if present.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL = _ssl_context()


def fetch(url: str, *, params: dict | None = None, headers: dict | None = None,
          data: bytes | None = None, method: str | None = None,
          retries: int = 3, timeout: int = 60, polite_delay: float = 0.5) -> bytes:
    """GET (or POST) a URL politely and return the body as bytes.

    `params` values may be lists, which become repeated query keys
    (Eurostat and SDMX filters use this).
    """
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    hdrs = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    hdrs.update(headers or {})
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            time.sleep(polite_delay)
            return body
        except urllib.error.HTTPError as e:
            last = e
            # Client errors other than rate limiting will not get better.
            if 400 <= e.code < 500 and e.code != 429:
                raise FetchError(f"HTTP {e.code} for {url}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:  # incl. connection resets
            last = e
        time.sleep(2 ** attempt * 2)
    raise FetchError(f"Failed after {retries} attempts: {url} ({last})")


def head(url: str, *, timeout: int = 60) -> dict:
    """HEAD request; returns lower-cased response headers, or {} if the server refuses."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            return {k.lower(): v for k, v in r.headers.items()}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {}


def fetch_json(url: str, **kw):
    kw.setdefault("headers", {}).setdefault("Accept", "application/json")
    return json.loads(fetch(url, **kw))


# ---------------------------------------------------------------- files ---

def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_raw(source_id: str, name: str, body: bytes, *, keep: bool = True) -> tuple[Path | None, str]:
    """Store an original download under data/raw/<source>/, dated.

    A new dated file is written only when the content differs from the most
    recent stored copy, so unchanged sources do not grow the repository.
    With keep=False (very large files) only the hash is returned.
    Returns (path or None, sha256).
    """
    digest = sha256(body)
    if not keep:
        return None, digest
    folder = RAW / source_id
    folder.mkdir(parents=True, exist_ok=True)
    stem, _, ext = name.rpartition(".")
    existing = sorted(folder.glob(f"*-{stem}.{ext}"))
    if existing and sha256(existing[-1].read_bytes()) == digest:
        return existing[-1], digest
    path = folder / f"{today()}-{name}"
    path.write_bytes(body)
    return path, digest


def latest_raw(source_id: str, pattern: str) -> Path | None:
    """Most recent file in data/raw/<source>/ matching a glob (dated names sort)."""
    files = sorted((RAW / source_id).glob(pattern))
    return files[-1] if files else None


def rel(path: Path | None) -> str | None:
    return None if path is None else path.relative_to(ROOT).as_posix()


# ---------------------------------------------------------------- geo -----

_COUNTRIES = None


def countries() -> dict:
    global _COUNTRIES
    if _COUNTRIES is None:
        ref = read_json(REFERENCE / "countries.json")
        _COUNTRIES = {"by_code": {c["code"]: c for c in ref["countries"]},
                      "aliases": ref["aliases"]}
        for c in ref["countries"]:
            _COUNTRIES["aliases"].setdefault(c["iso3"], c["code"])
            if c["iso2"] != c["code"]:
                _COUNTRIES["aliases"].setdefault(c["iso2"], c["code"])
    return _COUNTRIES


def geo_code(code: str) -> str | None:
    """Normalise a country code to the site convention, or None if not a known geography."""
    c = countries()
    code = (code or "").strip()
    code = c["aliases"].get(code, code)
    return code if code in c["by_code"] else None


def geo_name(code: str) -> str:
    return countries()["by_code"][code]["name"]


# ---------------------------------------------------------------- text ----

_TAG = re.compile(r"<[^>]+>")


def html_to_text(s) -> str | None:
    """Turn the light HTML found in source spreadsheets into plain paragraphs."""
    if s is None:
        return None
    s = str(s)
    s = re.sub(r"</p>\s*<p[^>]*>|<br\s*/?>|</li>\s*<li[^>]*>", "\n", s, flags=re.I)
    s = _TAG.sub("", s)
    import html
    s = html.unescape(html.unescape(s))
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip() or None


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def num(v):
    """Parse a spreadsheet cell into a float, treating ':' and blanks as missing."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace(" ", "")
    if s in ("", ":", "-", "..", "n/a", "NA"):
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


# ---------------------------------------------------------------- output --

def provenance(*, publisher: str, source_url: str, licence: str, citation: str | None = None,
               dataset_code: str | None = None, api_url: str | None = None,
               source_updated: str | None = None, raw: Path | None = None,
               raw_sha256: str | None = None, retrieved_at: str | None = None) -> dict:
    p = {
        "publisher": publisher,
        "dataset_code": dataset_code,
        "source_url": source_url,
        "api_url": api_url,
        "licence": licence,
        "licence_url": LICENCES.get(licence),
        "citation": citation,
        "source_updated": source_updated,
        "retrieved_at": retrieved_at or now_iso(),
        "raw_file": rel(raw),
        "raw_sha256": raw_sha256,
    }
    return {k: v for k, v in p.items() if v is not None}


def write_indicator(ind: dict) -> Path:
    """Write one indicator as JSON + CSV. See data/schemas/indicator.schema.json.

    Observations are sorted, values rounded to 4 significant decimals, and
    unknown geographies dropped, so reruns produce byte-identical files.
    """
    series = []
    for o in ind["series"]:
        g = geo_code(o["geo"])
        if g is None or o.get("value") is None:
            continue
        ob = {"geo": g, "time": str(o["time"]), "value": round(float(o["value"]), 4)}
        if o.get("flag"):
            ob["flag"] = str(o["flag"])
        if o.get("dims"):
            ob["dims"] = o["dims"]
        series.append(ob)
    series.sort(key=lambda o: (json.dumps(o.get("dims", {}), sort_keys=True), o["geo"], o["time"]))
    ind = {**ind, "series": series}
    if ind.get("missing"):
        missing = [{**m, "geo": geo_code(m["geo"]), "time": str(m["time"])}
                   for m in ind["missing"] if geo_code(m["geo"])]
        missing.sort(key=lambda m: (json.dumps(m.get("dims", {}), sort_keys=True), m["geo"], m["time"]))
        ind["missing"] = missing
    ind["coverage"] = {
        "geos": sorted({o["geo"] for o in series}),
        "time": [min((o["time"] for o in series), default=None),
                 max((o["time"] for o in series), default=None)],
        "observations": len(series),
    }
    path = INDICATORS / f"{ind['id']}.json"
    # Keep retrieved_at stable when nothing else changed, so unchanged data makes no diff.
    if path.exists():
        old = read_json(path)
        same = {**old, "provenance": {**old.get("provenance", {}), "retrieved_at": None}}
        new = {**ind, "provenance": {**ind.get("provenance", {}), "retrieved_at": None}}
        if json.dumps(same, sort_keys=True) == json.dumps(new, sort_keys=True):
            return path
    write_json(path, ind)

    dim_keys = sorted({k for o in series for k in o.get("dims", {})})
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["indicator", "geo", "geo_name", "time", *dim_keys, "value", "flag", "unit"])
    for o in series:
        w.writerow([ind["id"], o["geo"], geo_name(o["geo"]), o["time"],
                    *[o.get("dims", {}).get(k, "") for k in dim_keys],
                    o["value"], o.get("flag", ""), ind.get("unit", "")])
    path.with_suffix(".csv").write_text(buf.getvalue(), encoding="utf-8")
    return path


def write_records(dataset_id: str, records: list[dict]) -> Path:
    path = PUBLISHED / dataset_id / "records.json"
    write_json(path, records)
    return path
