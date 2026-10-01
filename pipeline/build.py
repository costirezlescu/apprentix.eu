"""Build steps that run after the connectors.

  data/published/indicators/index.json   list of indicators (metadata, no series) for the site
  data/sources.json                      catalogue of every upstream source + last run status
  data/datasets.json                     record counts refreshed
  datapackage.json                       Frictionless Data Package v2 describing everything published

None of this is a site build step: it only writes JSON the static site reads.
"""

from __future__ import annotations

from .common import (DATA, INDICATORS, LICENCES, PUBLISHED, RAW, ROOT,
                     read_json, write_json)
from .sources import _catalogue

SITE = "https://apprentix.eu/"


def indicator_index() -> list[dict]:
    items = []
    for p in sorted(INDICATORS.glob("*.json")):
        if p.name == "index.json":
            continue
        ind = read_json(p)
        meta = {k: v for k, v in ind.items() if k not in ("series", "missing", "flags")}
        meta["path"] = p.relative_to(ROOT).as_posix()
        meta["csv"] = p.with_suffix(".csv").relative_to(ROOT).as_posix()
        items.append(meta)
    write_json(INDICATORS / "index.json", {
        "description": "All statistical indicators published by Apprentix. Each entry links to a JSON file (with provenance and series) and a CSV.",
        "indicators": items,
    })
    return items


def sources_catalogue(connectors: dict, status: dict) -> list[dict]:
    path = DATA / "sources.json"
    previous = {}
    if path.exists():
        previous = {s["id"]: s.get("status") for s in read_json(path)["sources"]}
    out = []
    for sid, m in connectors.items():
        s = dict(m.SOURCE)
        s["automated"] = True
        s["connector"] = f"pipeline/sources/{m.__name__.rsplit('.', 1)[-1]}.py"
        s["licence_url"] = LICENCES.get(s.get("licence"))
        st = status.get(sid) or previous.get(sid)
        if st:
            s["status"] = st
        out.append(s)
    for s in _catalogue.MANUAL:
        out.append({**s, "automated": False, "licence_url": LICENCES.get(s.get("licence"))})
    out = [{k: v for k, v in s.items() if v is not None} for s in out]
    write_json(path, {
        "description": "Every upstream source Apprentix tracks: what it provides, how it is accessed, its licence and refresh cadence. 'automated' sources are fetched by pipeline/ connectors; the others are curated by hand or not yet integrated.",
        "sources": out,
    })
    return out


def refresh_manifest(indicators: list[dict]) -> None:
    path = DATA / "datasets.json"
    m = read_json(path)
    for d in m["datasets"]:
        rec = ROOT / d["path"] / "records.json"
        if rec.exists():
            d["records"] = len(read_json(rec))
    m["indicators"] = {"count": len(indicators), "path": "data/published/indicators/index.json"}
    # "Last updated" = newest dated original in data/raw, so it only moves when data does.
    dated = sorted(p.name[:10] for p in RAW.rglob("*") if p.is_file() and p.name[:4].isdigit())
    if dated and dated[-1] > m["site"].get("updated", ""):
        m["site"]["updated"] = dated[-1]
    write_json(path, m)


def datapackage(indicators: list[dict]) -> None:
    manifest = read_json(DATA / "datasets.json")
    resources = []
    for d in manifest["datasets"]:
        meta = read_json(ROOT / d["path"] / "meta.json")
        src = meta.get("source", {})
        resources.append({
            "name": d["id"],
            "path": f"{d['path']}/records.json",
            "format": "json",
            "mediatype": "application/json",
            "title": d["title"],
            "description": meta.get("description") or d.get("tagline"),
            "sources": [{"title": src.get("name"), "path": src.get("url")}],
            "licenses": [{"name": src.get("licence_id", "see-source"), "title": src.get("licence")}],
        })
    for ind in indicators:
        p = ind.get("provenance", {})
        lic = p.get("licence")
        for fmt, key in (("json", "path"), ("csv", "csv")):
            resources.append({
                "name": f"{ind['id']}-{fmt}".lower().replace("_", "-"),
                "path": ind[key],
                "format": fmt,
                "mediatype": "application/json" if fmt == "json" else "text/csv",
                "title": ind["title"],
                "description": ind.get("description"),
                "sources": [{"title": p.get("publisher"), "path": p.get("source_url")}],
                "licenses": [{"name": lic, **({"path": LICENCES[lic]} if lic in LICENCES else {})}],
            })
    write_json(ROOT / "datapackage.json", {
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
        "name": "apprentix",
        "title": "Apprentix — European apprenticeship and VET data",
        "description": "Republished public European data on apprenticeship and vocational education and training. Each resource keeps its original publisher's licence; see 'licenses' per resource.",
        "homepage": SITE,
        "version": manifest["site"].get("updated"),
        "contributors": [{"title": "Apprentix", "roles": ["publisher"], "path": SITE}],
        "resources": resources,
    })


def all(connectors: dict, status: dict) -> None:
    inds = indicator_index()
    sources_catalogue(connectors, status)
    refresh_manifest(inds)
    datapackage(inds)
    print(f"Built: {len(inds)} indicators, catalogue, manifest, datapackage.json")
    from . import insights, render_insights
    insights.build()          # analyses across all data → data/published/insights/
    render_insights.render_insights()
    from . import render_pages
    render_pages.render_all()
    from . import build_ai_index
    build_ai_index.build()
