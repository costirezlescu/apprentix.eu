"""Merge Cedefop's structured fiche answers into the apprenticeship-schemes records.

  python -m pipeline.curate.merge_fiches

Reads the newest data/raw/cedefop-schemes/*-fiche-answers.txt (produced in a
browser with pipeline/curate/fiche_extract.js, because Cedefop's pages refuse
scripted requests), maps option indices to labels via scheme_questions.py, and
writes the q_* fields, fiche credits and links into records.json. Hand-written
fields (overview, duration, learners, ...) are left alone; meta.json is
regenerated for the q_* fields so filters and the comparison matrix pick them up.
"""

from __future__ import annotations

from ..common import PUBLISHED, RAW, read_json, write_json
from .scheme_questions import QUESTIONS, SECTIONS

DATASET = PUBLISHED / "apprenticeship-schemes"
PDF = "https://www.cedefop.europa.eu/en/print/pdf/node/{}"
COUNTRY_FICHE = "https://www.cedefop.europa.eu/en/tools/apprenticeship-schemes/country-fiches/{}"


def load_answers():
    files = sorted((RAW / "cedefop-schemes").glob("*-fiche-answers.txt"))
    if not files:
        raise SystemExit("No data/raw/cedefop-schemes/*-fiche-answers.txt found")
    path = files[-1]
    answers, meta = {}, {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("A|"):
            _, slug, codes = line.split("|", 2)
            per_q = {}
            for part in codes.split():
                n, _, idx = part.partition("=")
                per_q[int(n)] = [int(i) for i in idx.split(",") if i != ""]
            answers[slug] = per_q
        elif line.startswith("META|"):
            _, slug, country, node, author = line.split("|", 4)
            meta[slug] = {"country_fiche": country, "pdf_node": node, "author": author}
    return path, answers, meta


def labels_for(n: int, idx: list[int]) -> list[str]:
    key, label, multi, options = QUESTIONS[n]
    names = list(options.values())
    for i in idx:
        if i >= len(names):
            raise SystemExit(f"Q{n}: option index {i} out of range — questionnaire changed? Update scheme_questions.py")
    return [names[i] for i in idx]


def main() -> None:
    path, answers, meta = load_answers()
    date = path.name[:10]
    rec_path = DATASET / "records.json"
    records = read_json(rec_path)
    matched = 0
    for r in records:
        slug = r["source_url"].rstrip("/").rsplit("/", 1)[-1]
        if slug not in answers:
            print(f"! no fiche answers for {r['id']} ({slug})")
            continue
        matched += 1
        for n, (key, _label, multi, _opts) in QUESTIONS.items():
            vals = labels_for(n, answers[slug].get(n, []))
            if not vals:
                r.pop(key, None)
            else:
                r[key] = vals if multi else vals[0]
        m = meta.get(slug, {})
        if m:
            r["fiche_author"] = m["author"]
            r["fiche_pdf"] = PDF.format(m["pdf_node"])
            r["country_fiche_url"] = COUNTRY_FICHE.format(m["country_fiche"])
        r["fiche_answers_read"] = date
    write_json(rec_path, records)
    print(f"merged fiche answers into {matched}/{len(records)} records from {path.name}")

    # Regenerate the q_* part of meta.json, keeping everything hand-written.
    meta_path = DATASET / "meta.json"
    mj = read_json(meta_path)
    keep = [f for f in mj["fields"] if not f["key"].startswith("q_")
            and f["key"] not in ("fiche_author", "fiche_pdf", "country_fiche_url", "fiche_answers_read")]
    facet_keys = {"q_compensation", "q_min_workplace_share", "q_learner_status", "q_contract_type",
                  "q_share_of_vet", "q_introduced", "q_financial_incentives", "q_wage_setting",
                  "q_access_to_he", "q_alternation_form"}
    qfields = []
    for n, (key, label, multi, options) in QUESTIONS.items():
        f = {"key": key, "label": label, "type": "category", "order": list(dict.fromkeys(options.values())),
             "question": f"Q{n}", "multi": multi}
        if key in facet_keys:
            f["facet"] = True
            f["collapse"] = 6
        qfields.append(f)
    extra = [
        {"key": "fiche_author", "label": "Fiche drafted by", "type": "text"},
        {"key": "fiche_pdf", "label": "Fiche (PDF)", "type": "link"},
        {"key": "country_fiche_url", "label": "Country fiche", "type": "link"},
        {"key": "fiche_answers_read", "label": "Coded answers read from Cedefop", "type": "text"},
    ]
    # Insert coded fields after the hand-written facets, before free text.
    idx = next((i for i, f in enumerate(keep) if f["type"] in ("text", "longtext", "title", "subtitle")), len(keep))
    mj["fields"] = keep[:idx] + qfields + keep[idx:] + extra
    mj["sections"] = [s for s in mj.get("sections", []) if not s.get("coded")]
    for title, qs in SECTIONS:
        mj["sections"].append({"title": f"Cedefop coding — {title.lower()}", "coded": True,
                               "fields": [QUESTIONS[n][0] for n in qs]})
    for s in mj["sections"]:
        if s["title"] == "Provenance":
            s["fields"] = [k for k in s["fields"] if k not in ("fiche_author", "fiche_answers_read")] + ["fiche_author", "fiche_answers_read"]
    mj.setdefault("matrix", {})["questions"] = [QUESTIONS[n][0] for _, qs in SECTIONS for n in qs]
    write_json(meta_path, mj)


if __name__ == "__main__":
    main()
