"""The site's visual design, switchable in one place.

  DESIGN = "studio"    Studio (design proposal 6, chosen 18 October 2026): Bricolage Grotesque and
                       Instrument Sans, blue for data, tomato for actions, pastel start cards.
  DESIGN = "current"   the original look (Newsreader, Public Sans, teal): site.css on its own.

To switch, change DESIGN and run  python -m pipeline.run --build-only  (or  python -m pipeline.design
to restyle the pages without a full build). Generated pages take their <head> from head_links();
apply() rewrites the hand-written ones (index.html, pages/*.html, embed/*.html).

site.css is never changed by a design: a design is a stylesheet loaded after it
(assets/css/<design>.css) plus its fonts. Cedefop Daily (/daily) links site.css but never a
design stylesheet, so it keeps its own look whichever design is chosen.
"""

from __future__ import annotations

import re

from .common import ROOT

DESIGN = "studio"

DESIGNS = {
    "current": {
        "fonts": "https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600"
                 "&family=Public+Sans:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap",
        "css": None,
    },
    "studio": {
        "fonts": "https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500..800"
                 "&family=Instrument+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap",
        "css": "assets/css/studio.css",
    },
}

# Early connections to Google Fonts, so the fonts arrive sooner after the first paint.
PRECONNECT = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
PRECONNECT_LINK = re.compile(r'<link rel="preconnect" href="https://fonts\.(?:googleapis|gstatic)\.com"(?: crossorigin)?>\n?')

# Any main-site Google Fonts link (either design), the site stylesheet, and any design stylesheet.
FONTS_LINK = re.compile(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com/css2\?family=(?:Newsreader|Bricolage\+Grotesque)[^"]*">')
SITE_LINK = re.compile(r'<link rel="stylesheet" href="(?P<root>[./]*)assets/css/site\.css(?:\?v=[0-9a-f]{8})?">')
DESIGN_LINK = re.compile(r'\n?<link rel="stylesheet" href="[./]*assets/css/(?:' + "|".join(
    re.escape(d["css"].rsplit("/", 1)[1][:-4]) for d in DESIGNS.values() if d["css"]) + r')\.css(?:\?v=[0-9a-f]{8})?">')


def fonts_href() -> str:
    return DESIGNS[DESIGN]["fonts"].replace("&", "&amp;")


def head_links(root: str) -> str:
    """Fonts and stylesheets for a main-site page whose path to the site root is `root`."""
    d = DESIGNS[DESIGN]
    links = [PRECONNECT, f'<link rel="stylesheet" href="{fonts_href()}">', f'<link rel="stylesheet" href="{root}assets/css/site.css">']
    if d["css"]:
        links.append(f'<link rel="stylesheet" href="{root}{d["css"]}">')
    return "\n".join(links)


def restyle(text: str) -> str:
    """Point a page's fonts and design stylesheet at the current DESIGN."""
    m = SITE_LINK.search(text)
    if not m:
        return text
    text = PRECONNECT_LINK.sub("", text)
    text = FONTS_LINK.sub(lambda _: f'{PRECONNECT}\n<link rel="stylesheet" href="{fonts_href()}">', text)
    text = DESIGN_LINK.sub("", text)
    css = DESIGNS[DESIGN]["css"]
    if css:
        m = SITE_LINK.search(text)
        text = text[:m.end()] + f'\n<link rel="stylesheet" href="{m.group("root")}{css}">' + text[m.end():]
    return text


def apply() -> int:
    """Restyle the hand-written pages; returns files changed. Never touches /daily."""
    changed = 0
    for p in [ROOT / "index.html", *sorted((ROOT / "pages").glob("*.html")), *sorted((ROOT / "embed").glob("*.html"))]:
        old = p.read_text(encoding="utf-8")
        new = restyle(old)
        if new != old:
            p.write_text(new, encoding="utf-8")
            changed += 1
    return changed


if __name__ == "__main__":
    n = apply()
    from . import asset_version
    asset_version.apply()
    print(f"Design: {DESIGN} ({n} hand-written page(s) restyled; run the build to restyle generated pages)")
