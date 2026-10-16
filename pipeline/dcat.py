"""DCAT-AP catalogue of everything Apprentix publishes → data/catalog.rdf (RDF/XML).

  python -m pipeline.dcat

DCAT-AP is the metadata format data.europa.eu (and national portals) harvest. One
dcat:Dataset per record dataset and per indicator, each with its licence, the original
publisher (dct:creator / dct:source), coverage in space and time, and CSV/JSON
distributions. Apprentix is the dct:publisher (it republishes); the original publisher
stays authoritative and is named on every dataset. Deterministic: no clock.

Controlled vocabularies (EU Publications Office authority tables): data theme EDUC,
language ENG, file types CSV/JSON, countries by ISO 3166 alpha-3, and the licence table
for the Creative Commons licences; other licences are given by their own URL.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from .common import DATA, INDICATORS, LICENCES, PUBLISHED, REFERENCE, ROOT, read_json

SITE = "https://apprentix.eu/"
OUT = DATA / "catalog.rdf"
AUTH = "http://publications.europa.eu/resource/authority/"
EU_LICENCE = {"CC-BY-4.0": "CC_BY_4_0", "CC-BY-SA-4.0": "CC_BYSA_4_0",
              "CC-BY-NC-ND-4.0": "CC_BYNCND_4_0", "CC0-1.0": "CC0"}
MEDIA = {"CSV": "text/csv", "JSON": "application/json"}
KEYWORDS = ["apprenticeship", "vocational education and training", "VET", "work-based learning", "Europe"]


def x(s) -> str:
    return escape(str(s or ""))


def a(s) -> str:
    return quoteattr(str(s or ""))


def licence_ref(lic_id: str | None, url: str | None, label: str | None) -> str:
    """dct:license as a resource: EU vocabulary when known, else the licence's own URL."""
    if lic_id in EU_LICENCE:
        return f'<dct:license rdf:resource={a(AUTH + "licence/" + EU_LICENCE[lic_id])}/>'
    target = LICENCES.get(lic_id or "") or url
    if not target:
        return ""
    lab = f"<rdfs:label>{x((label or lic_id or '')[:300])}</rdfs:label>" if (label or lic_id) else ""
    return f'<dct:license><dct:LicenseDocument rdf:about={a(target)}>{lab}</dct:LicenseDocument></dct:license>'


def agent(name: str, homepage: str | None = None) -> str:
    hp = f"<foaf:homepage rdf:resource={a(homepage)}/>" if homepage else ""
    return f"<foaf:Agent><foaf:name>{x(name)}</foaf:name>{hp}</foaf:Agent>"


def distribution(about: str, title: str, fmt: str, download: str, access: str, lic: str) -> str:
    return (f'<dcat:distribution><dcat:Distribution rdf:about={a(about)}>'
            f"<dct:title>{x(title)}</dct:title>"
            f'<dcat:accessURL rdf:resource={a(access)}/><dcat:downloadURL rdf:resource={a(download)}/>'
            f'<dct:format rdf:resource={a(AUTH + "file-type/" + fmt)}/>'
            f'<dcat:mediaType rdf:resource={a("https://www.iana.org/assignments/media-types/" + MEDIA[fmt])}/>'
            f"{lic}</dcat:Distribution></dcat:distribution>")


def dataset(*, about, title, description, landing, creator, source_url, keywords, iso3, years, modified,
            distributions, lic) -> str:
    kw = "".join(f"<dcat:keyword>{x(k)}</dcat:keyword>" for k in dict.fromkeys(k for k in keywords if k))
    spatial = "".join(f'<dct:spatial rdf:resource={a(AUTH + "country/" + c)}/>' for c in iso3)
    temporal = ""
    if years and years[0] and years[1]:
        temporal = (f'<dct:temporal><dct:PeriodOfTime>'
                    f'<dcat:startDate rdf:datatype="http://www.w3.org/2001/XMLSchema#gYear">{x(years[0][:4])}</dcat:startDate>'
                    f'<dcat:endDate rdf:datatype="http://www.w3.org/2001/XMLSchema#gYear">{x(years[1][:4])}</dcat:endDate>'
                    f'</dct:PeriodOfTime></dct:temporal>')
    mod = (f'<dct:modified rdf:datatype="http://www.w3.org/2001/XMLSchema#date">{x(modified)}</dct:modified>'
           if modified else "")
    src = f"<dct:source rdf:resource={a(source_url)}/>" if source_url else ""
    return (f'<dcat:Dataset rdf:about={a(about)}>'
            f'<dct:identifier>{x(about)}</dct:identifier>'
            f'<dct:title xml:lang="en">{x(title)}</dct:title>'
            f'<dct:description xml:lang="en">{x(description)}</dct:description>'
            f'<dcat:landingPage rdf:resource={a(landing)}/>'
            f'<dct:publisher rdf:resource="{SITE}#apprentix"/>'
            f"<dct:creator>{agent(creator)}</dct:creator>{src}"
            f'<dcat:theme rdf:resource="{AUTH}data-theme/EDUC"/>'
            f'<dct:language rdf:resource="{AUTH}language/ENG"/>'
            f'<dcat:contactPoint rdf:resource="{SITE}#contact"/>'
            f"{kw}{spatial}{temporal}{mod}{lic}{distributions}</dcat:Dataset>")


def build() -> int:
    ref = read_json(REFERENCE / "countries.json")
    iso3 = {c["code"]: c.get("iso3") for c in ref["countries"] if c.get("group") != "aggregate"}
    manifest = read_json(DATA / "datasets.json")
    updated = manifest["site"].get("updated", "")
    items = []

    for d in manifest["datasets"]:
        meta = read_json(ROOT / d["path"] / "meta.json")
        recs = read_json(ROOT / d["path"] / "records.json")
        src = meta.get("source") or {}
        page = f"{SITE}pages/datasets/{d['id']}.html"
        codes = sorted({r.get("country_code") for r in recs if isinstance(r, dict) and r.get("country_code")})
        lic = licence_ref(src.get("licence_id"), src.get("url"), src.get("licence"))
        dist = distribution(f"{page}#json", f"{d['title']} (JSON records)", "JSON",
                            f"{SITE}{d['path']}/records.json", page, lic)
        items.append(dataset(
            about=f"{page}#dataset", title=d["title"], description=meta.get("description") or d.get("tagline", ""),
            landing=page, creator=src.get("name") or "see landing page", source_url=src.get("url"),
            keywords=KEYWORDS,
            iso3=sorted(filter(None, (iso3.get(c) for c in codes))), years=None,
            modified=src.get("retrieved"), distributions=dist, lic=lic))

    index = read_json(INDICATORS / "index.json")["indicators"]
    for m in sorted(index, key=lambda i: i["id"]):
        ind = read_json(INDICATORS / f"{m['id']}.json")
        p = ind.get("provenance") or {}
        page = f"{SITE}pages/indicators/{m['id']}.html"
        lic_id = p.get("licence") if p.get("licence") in LICENCES or p.get("licence") in EU_LICENCE else None
        lic = licence_ref(lic_id, ind.get("licence_url") or p.get("licence_url") or page, p.get("licence"))
        dists = (distribution(f"{page}#csv", f"{ind['title']} (CSV)", "CSV", f"{SITE}data/published/indicators/{m['id']}.csv", page, lic)
                 + distribution(f"{page}#json", f"{ind['title']} (JSON with provenance)", "JSON",
                                f"{SITE}data/published/indicators/{m['id']}.json", page, lic))
        cov = ind.get("coverage") or m.get("coverage") or {}
        geos = cov.get("geos") or sorted({o["geo"] for o in ind.get("series", [])})
        times = cov.get("time") or []
        desc = ind.get("description", "")
        if ind.get("comparability"):
            desc += " What is counted: " + ind["comparability"]
        items.append(dataset(
            about=f"{page}#dataset", title=ind["title"], description=desc, landing=page,
            creator=p.get("publisher") or "see landing page", source_url=p.get("source_url"),
            keywords=KEYWORDS + [ind.get("topic", ""), p.get("dataset_code", "")],
            iso3=sorted(filter(None, (iso3.get(g) for g in geos))), years=(times[0], times[-1]) if times else None,
            modified=(p.get("retrieved_at") or "")[:10], distributions=dists, lic=lic))

    body = "\n".join(f"  <dcat:dataset>{it}</dcat:dataset>" for it in items)
    rdf = f"""<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF
  xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
  xmlns:dcat="http://www.w3.org/ns/dcat#"
  xmlns:dct="http://purl.org/dc/terms/"
  xmlns:foaf="http://xmlns.com/foaf/0.1/"
  xmlns:vcard="http://www.w3.org/2006/vcard/ns#">
<dcat:Catalog rdf:about="{SITE}data/catalog.rdf#catalog">
  <dct:title xml:lang="en">Apprentix — European apprenticeship and VET data</dct:title>
  <dct:description xml:lang="en">Public European data on apprenticeship and vocational education and training, republished by Apprentix (apprentix.eu), an independent, non-commercial project not affiliated with any EU institution. Each dataset names its original publisher, which remains authoritative, and keeps that publisher's licence. Archived on Zenodo: https://doi.org/10.5281/zenodo.23426138</dct:description>
  <foaf:homepage rdf:resource="{SITE}"/>
  <dct:publisher rdf:resource="{SITE}#apprentix"/>
  <dct:language rdf:resource="{AUTH}language/ENG"/>
  <dcat:themeTaxonomy rdf:resource="{AUTH}data-theme"/>
  <dct:modified rdf:datatype="http://www.w3.org/2001/XMLSchema#date">{x(updated)}</dct:modified>
  <dct:spatial rdf:resource="{AUTH}continent/EUROPE"/>
{body}
</dcat:Catalog>
<foaf:Agent rdf:about="{SITE}#apprentix">
  <foaf:name>Apprentix</foaf:name>
  <foaf:homepage rdf:resource="{SITE}"/>
</foaf:Agent>
<vcard:Organization rdf:about="{SITE}#contact">
  <vcard:fn>Apprentix</vcard:fn>
  <vcard:hasURL rdf:resource="{SITE}pages/about.html"/>
</vcard:Organization>
</rdf:RDF>
"""
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != rdf:
        OUT.write_text(rdf, encoding="utf-8")
    print(f"DCAT-AP: {len(items)} datasets → data/catalog.rdf")
    return len(items)


if __name__ == "__main__":
    build()
