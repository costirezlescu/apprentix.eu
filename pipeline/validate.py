"""Validate everything the site publishes.

  python -m pipeline.validate

Checks:
  - every indicator file against data/schemas/indicator.schema.json
  - every dataset meta.json against data/schemas/meta.schema.json
  - records: unique ids; every field used by meta exists; country codes resolve
  - datasets.json entries point at real files
Uses the `jsonschema` package when installed (CI installs it); otherwise only
the structural checks run, with a warning.
Exits non-zero on any error.
"""

from __future__ import annotations

import sys

from .common import DATA, INDICATORS, ROOT, geo_code, read_json

errors: list[str] = []
warnings: list[str] = []


def err(where: str, msg: str) -> None:
    errors.append(f"{where}: {msg}")


def schema_validator(name: str):
    try:
        import jsonschema
    except ImportError:
        warnings.append("jsonschema not installed — schema checks skipped (pip install -r pipeline/requirements.txt)")
        return None
    schema = read_json(DATA / "schemas" / name)
    return jsonschema.Draft202012Validator(schema)


def check_indicators() -> int:
    v = schema_validator("indicator.schema.json")
    n = 0
    for p in sorted(INDICATORS.glob("*.json")):
        if p.name == "index.json":
            continue
        n += 1
        where = p.relative_to(ROOT).as_posix()
        ind = read_json(p)
        if v:
            for e in v.iter_errors(ind):
                err(where, f"{'/'.join(map(str, e.path))}: {e.message[:200]}")
        if ind.get("id") != p.stem:
            err(where, f"id '{ind.get('id')}' does not match file name")
        for o in ind.get("series", []):
            if geo_code(o["geo"]) != o["geo"]:
                err(where, f"unknown or non-normalised geo '{o['geo']}'")
                break
        dims = {d["key"]: d for d in ind.get("dims", [])}
        for o in ind.get("series", []):
            for k, val in o.get("dims", {}).items():
                if k not in dims:
                    err(where, f"observation uses undeclared dim '{k}'")
                    break
                if val not in dims[k]["values"]:
                    err(where, f"dim {k} value '{val}' not declared")
                    break
        if not p.with_suffix(".csv").exists():
            err(where, "missing CSV twin")
    return n


def check_datasets() -> int:
    v = schema_validator("meta.schema.json")
    manifest = read_json(DATA / "datasets.json")
    seen = set()
    for d in manifest["datasets"]:
        where = f"datasets.json:{d['id']}"
        if d["id"] in seen:
            err(where, "duplicate dataset id")
        seen.add(d["id"])
        meta_p = ROOT / d["path"] / "meta.json"
        rec_p = ROOT / d["path"] / "records.json"
        if not meta_p.exists() or not rec_p.exists():
            err(where, "meta.json or records.json missing")
            continue
        meta, records = read_json(meta_p), read_json(rec_p)
        mw = meta_p.relative_to(ROOT).as_posix()
        if v:
            for e in v.iter_errors(meta):
                err(mw, f"{'/'.join(map(str, e.path))}: {e.message[:200]}")
        keys = {f["key"] for f in meta["fields"]}
        for k in [*meta["display"].values()]:
            for kk in (k if isinstance(k, list) else [k]):
                if kk not in keys:
                    err(mw, f"display refers to unknown field '{kk}'")
        for sec in meta.get("sections", []):
            for kk in sec["fields"]:
                if kk not in keys:
                    err(mw, f"section '{sec['title']}' refers to unknown field '{kk}'")
        ids = [r.get("id") for r in records]
        if None in ids:
            err(rec_p.relative_to(ROOT).as_posix(), "record without id")
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            err(rec_p.relative_to(ROOT).as_posix(), f"duplicate ids: {sorted(dupes)[:5]}")
        bad_cc = sorted({r["country_code"] for r in records
                         if r.get("country_code") and not geo_code(r["country_code"])})
        if bad_cc:
            err(rec_p.relative_to(ROOT).as_posix(), f"unknown country codes: {bad_cc}")
        unknown = sorted({k for r in records for k in r} - keys)
        if unknown:
            warnings.append(f"{rec_p.relative_to(ROOT).as_posix()}: fields not described in meta.json: {unknown}")
        if d.get("records") != len(records):
            err(where, f"records count {d.get('records')} != {len(records)} (run python -m pipeline.run --build-only)")
    return len(seen)


def main() -> int:
    n_ind = check_indicators()
    n_ds = check_datasets()
    for w in dict.fromkeys(warnings):
        print("warning:", w)
    for e in errors:
        print("ERROR:", e)
    print(f"Checked {n_ind} indicators and {n_ds} datasets: {len(errors)} error(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
