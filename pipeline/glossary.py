"""Render pages/glossary.html from data/reference/glossary.json.

A–Z list of every term used on the site, each with an anchor (#<id>), the short and
long plain-language definitions, the source they paraphrase and links to related
terms, plus a DefinedTermSet JSON-LD block and a client-side filter box.
assets/js/glossary.js links its popovers to these anchors.

Run on its own with:  python -m pipeline.glossary
"""

from __future__ import annotations

import inspect
import re
import unicodedata

from .common import DATA, REFERENCE, ROOT, read_json
from .render_pages import SITE, breadcrumb, e, page, website, write_text

SRC = REFERENCE / "glossary.json"
OUT = ROOT / "pages" / "glossary.html"
PAGE_URL = f"{SITE}pages/glossary.html"
# Stylesheet for this page and the popovers. Set to None once glossary.css is merged into site.css.
GLOSSARY_CSS: str | None = None  # merged into site.css


def letter_of(term: str) -> str:
    base = unicodedata.normalize("NFKD", term)
    for ch in base:
        if ch.isalnum():
            return ch.upper() if ch.isalpha() else "#"
    return "#"


def also_known(t: dict) -> list[str]:
    """Aliases worth showing: not already part of the term's name and not a mere plural."""
    name = t["term"].lower()
    out: list[str] = []
    for a in t.get("aliases") or []:
        al = a.lower()
        if al in name or any(al == o.lower() + "s" or al == o.lower() for o in out):
            continue
        if any(al.rstrip("s") == o.lower() for o in out):
            continue
        out.append(a)
    return out[:5]


def entry(t: dict, names: dict[str, str]) -> str:
    aka = also_known(t)
    aka_html = f' <span class="gl-aka">also: {e(", ".join(aka))}</span>' if aka else ""
    long = f'<dd class="gl-long">{e(t["long"])}</dd>' if t.get("long") else ""
    src = t.get("source") or {}
    meta = []
    if src.get("url"):
        meta.append(f'Source: <a href="{e(src["url"])}" rel="noopener" target="_blank">{e(src.get("label") or src["url"])}</a> (paraphrased)')
    rel = [r for r in t.get("related") or [] if r in names]
    if rel:
        meta.append("Related: " + ", ".join(f'<a href="#{e(r)}">{e(names[r])}</a>' for r in rel))
    meta_html = f'<dd class="gl-meta">{" · ".join(meta)}</dd>' if meta else ""
    search = " ".join([t["term"], *(t.get("aliases") or []), t["short"]]).lower()
    return (f'<div class="gl-entry" id="{e(t["id"])}" data-search="{e(search)}">'
            f'<dt><a href="#{e(t["id"])}">{e(t["term"])}</a>{aka_html}</dt>'
            f'<dd class="gl-short">{e(t["short"])}</dd>{long}{meta_html}</div>')


FILTER_JS = """<script type="module">
const box = document.getElementById('gl-q');
const count = document.getElementById('gl-count');
const entries = [...document.querySelectorAll('.gl-entry')];
const letters = [...document.querySelectorAll('.gl-letter')];
const total = entries.length;
function apply() {
  const words = box.value.trim().toLowerCase().split(/\\s+/).filter(Boolean);
  let shown = 0;
  for (const el of entries) {
    const hit = words.every(w => el.dataset.search.includes(w));
    el.hidden = !hit;
    if (hit) shown++;
  }
  for (const h of letters) {
    const list = document.getElementById(h.dataset.list);
    const any = list && [...list.children].some(c => !c.hidden);
    h.hidden = !any;
    if (list) list.hidden = !any;
  }
  count.textContent = words.length ? `${shown} of ${total} terms` : `${total} terms`;
}
box.addEventListener('input', apply);
const q = new URLSearchParams(location.search).get('q');
if (q) { box.value = q; }
apply();
</script>"""


def render() -> list[str]:
    data = read_json(SRC)
    terms = sorted(data["terms"], key=lambda t: unicodedata.normalize("NFKD", t["term"]).lower())
    names = {t["id"]: t["term"] for t in terms}
    manifest = read_json(DATA / "datasets.json")
    updated = manifest["site"].get("updated", "")

    groups: dict[str, list[dict]] = {}
    for t in terms:
        groups.setdefault(letter_of(t["term"]), []).append(t)
    letters = sorted(groups)
    az = "".join(f'<li><a href="#letter-{e(L.lower())}">{e(L)}</a></li>' for L in letters)
    sections = []
    for L in letters:
        lid = f"letter-{L.lower()}"
        sections.append(f'<h2 class="gl-letter" id="{e(lid)}" data-list="{e(lid)}-list">{e(L)}</h2>\n'
                        f'<dl class="gl-list" id="{e(lid)}-list">\n'
                        + "\n".join(entry(t, names) for t in groups[L]) + "\n</dl>")

    body = f"""<div class="gl-page" data-no-glossary>
<nav class="cp-crumbs" aria-label="Breadcrumb"><a href="../">Apprentix</a> <span aria-hidden="true">›</span> <span aria-current="page">Glossary</span></nav>
<header class="gl-intro">
  <div class="mono">Plain language</div>
  <h1>Glossary</h1>
  <p class="lede">What the words and abbreviations on this site mean — VET, EQF, NEET, the flags after numbers and more — explained simply, for learners, parents and teachers as well as policy readers.</p>
  <p>Across the site, the first time one of these terms appears on a page it has a dotted underline: hover over it, tab to it or tap it to see the definition. The definitions are short paraphrases; each links to the official source, which remains authoritative.</p>
</header>
<div class="gl-filter" role="search">
  <label for="gl-q">Filter terms</label>
  <input id="gl-q" type="search" autocomplete="off" spellcheck="false" placeholder="e.g. apprenticeship, ISCED, flag">
  <span class="gl-count" id="gl-count" aria-live="polite">{len(terms)} terms</span>
</div>
<nav aria-label="Glossary A to Z"><ul class="gl-az">{az}</ul></nav>
{chr(10).join(sections)}
<p class="provenance">Definitions written by Apprentix in plain English, paraphrasing Cedefop's <em>Terminology of European education and training policy</em>, the Eurostat <em>Statistics Explained</em> glossary, Europass and European Commission pages. Where wording differs, the source is authoritative. Spotted a mistake or a missing term? <a href="https://github.com/costirezlescu/apprentix.eu/issues">Tell us on GitHub</a>.</p>
</div>
{FILTER_JS}"""

    set_id = PAGE_URL + "#terms"
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "DefinedTermSet", "@id": set_id, "name": "Apprentix glossary of apprenticeship and VET terms",
         "url": PAGE_URL, "inLanguage": "en", "dateModified": updated,
         "publisher": {"@type": "Organization", "name": "Apprentix", "url": SITE},
         "hasDefinedTerm": [
             {"@type": "DefinedTerm", "@id": f"{PAGE_URL}#{t['id']}", "name": t["term"],
              "description": t["short"], "url": f"{PAGE_URL}#{t['id']}", "inDefinedTermSet": set_id,
              **({"alternateName": also_known(t)} if also_known(t) else {}),
              **({"subjectOf": {"@type": "WebPage", "name": t["source"]["label"], "url": t["source"]["url"]}}
                 if (t.get("source") or {}).get("url") else {})}
             for t in terms]},
        website(), breadcrumb([("Apprentix", SITE), ("Glossary", PAGE_URL)], PAGE_URL)]}

    kwargs = dict(title="Glossary of apprenticeship and VET terms — Apprentix",
                  description="Plain-language explanations of the terms on Apprentix: VET, IVET, apprenticeship, work-based learning, EQF and ISCED levels, NEET, EU targets, Erasmus+, statistical flags and more.",
                  canonical=PAGE_URL, root="../", body=body, json_ld_obj=ld, current=None, updated=updated)
    if GLOSSARY_CSS:
        tag = f'<link rel="stylesheet" href="{GLOSSARY_CSS}">'
        if "head_extra" in inspect.signature(page).parameters:
            kwargs["head_extra"] = tag
        else:
            kwargs["body"] = tag + "\n" + body
    html = page(**kwargs)
    changed = write_text(OUT, html)
    return [str(OUT)] if changed else []


if __name__ == "__main__":
    out = render()
    print(f"Rendered pages/glossary.html ({'changed' if out else 'unchanged'})")
