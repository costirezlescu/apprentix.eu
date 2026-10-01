"""ESCO: the European classification of occupations, as reference data for linking schemes to occupations.

API: https://ec.europa.eu/esco/api (no key, CORS open). We page through
/search?type=occupation with full=false (preferred labels in all languages,
ESCO code, broader ISCO group) and pin selectedVersion so labels never change
unnoticed. Alternative labels are not collected: the API returns them only in
the full record (~40 KB per occupation, all languages), i.e. >100 MB per run.

Licence (ESCO FAQ, https://esco.ec.europa.eu/en/about-esco/faq): "In accordance
with the Commission Decision of 12 December 2011 on the reuse of Commission
documents (2011/833/EU), the ESCO classification can be downloaded, used,
reproduced and reused for any purpose and by any interested party free of
charge." Conditions: acknowledge with "This service uses the ESCO classification
of the European Commission." and mark modified versions as such.
"""

from __future__ import annotations

import hashlib
import json

from ..common import REFERENCE, fetch_json, now_iso, read_json, rel, write_json

API = "https://ec.europa.eu/esco/api/search"
VERSION = "v1.2.1"  # latest on https://esco.ec.europa.eu/en/use-esco/download (22 Dec 2025)
PAGE = 500
# Preferred labels in other languages come free with each page (28 languages),
# but all of them make the file ~6 MB. List ISO 639-1 codes here to include some.
EXTRA_LANGS: list[str] = []
OUT = REFERENCE / "esco-occupations.json"
ACK = "This service uses the ESCO classification of the European Commission."

SOURCE = {
    "id": "esco",
    "name": "ESCO — European Skills, Competences, Qualifications and Occupations",
    "publisher": "European Commission (DG EMPL)",
    "homepage": "https://esco.ec.europa.eu/",
    "description": f"Reference list of every ESCO occupation (URI, English label, ESCO code, ISCO-08 unit group), pinned to ESCO {VERSION}. Used to link apprenticeship schemes to occupations.",
    "access": "api",
    "browser_cors": True,
    "licence": "EC-reuse",
    "cadence": "irregular (new ESCO versions roughly yearly)",
    "secret": None,
    "outputs": ["reference/esco-occupations.json"],
}


def isco_code(uri: str | None) -> str | None:
    # http://data.europa.eu/esco/isco/C2166 -> 2166
    if uri and "/isco/C" in uri:
        return uri.rsplit("/C", 1)[1]
    return None


def run() -> list[str]:
    results, total, page = [], None, 0
    while total is None or page * PAGE < total:
        js = fetch_json(API, params={"type": "occupation", "language": "en", "full": "false",
                                     "limit": PAGE, "offset": page, "selectedVersion": VERSION},
                        timeout=120, polite_delay=1.0)
        total = js["total"]
        batch = js.get("_embedded", {}).get("results", [])
        if not batch:
            break
        results.extend(batch)
        page += 1

    occ = {}
    for r in results:
        code = r.get("code") or ""
        isco_groups = sorted(filter(None, (isco_code(u) for u in r.get("broaderIscoGroup", []))))
        labels = r.get("preferredLabel", {})
        occ[r["uri"]] = {
            "uri": r["uri"],
            "label": labels.get("en") or r.get("title"),
            "code": code or None,
            "isco08": isco_groups[0] if isco_groups else (code.split(".")[0] or None),
            "broader_occupation": sorted(r.get("broaderOccupation", [])) or None,
            "labels": {l: labels[l] for l in sorted(EXTRA_LANGS) if l in labels} or None,
        }
    if len(occ) != total:
        raise RuntimeError(f"ESCO: expected {total} occupations, got {len(occ)}")
    occupations = [{k: v for k, v in o.items() if v is not None} for _, o in sorted(occ.items())]
    digest = hashlib.sha256(json.dumps(occupations, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    retrieved = now_iso()
    if OUT.exists():
        old = read_json(OUT)
        if old.get("content_sha256") == digest:
            retrieved = old.get("retrieved_at", retrieved)
    doc = {
        "description": "Every ESCO occupation with its preferred English label, ESCO code and ISCO-08 unit group. Reference data for linking apprenticeship schemes to occupations.",
        "source": "ESCO — European Skills, Competences, Qualifications and Occupations, European Commission",
        "source_url": "https://esco.ec.europa.eu/",
        "api_url": f"{API}?type=occupation&language=en&full=false&limit={PAGE}&offset=<page>&selectedVersion={VERSION}",
        "esco_version": VERSION,
        "licence": "European Commission reuse notice (Decision 2011/833/EU): free reuse for any purpose; modified versions must be marked as such.",
        "licence_id": "EC-reuse",
        "acknowledgement": ACK,
        "fields": {
            "uri": "ESCO concept URI",
            "label": "Preferred label in English",
            "code": "ESCO occupation code (ISCO-08 unit group followed by ESCO extension)",
            "isco08": "ISCO-08 unit group (4 digits)",
            "broader_occupation": "Broader ESCO occupation(s), when the occupation is not directly under an ISCO group",
            "labels": "Preferred label in further languages (ISO 639-1), when configured",
        },
        "retrieved_at": retrieved,
        "content_sha256": digest,
        "count": len(occupations),
        "occupations": occupations,
    }
    write_json(OUT, doc)
    return [rel(OUT)]
