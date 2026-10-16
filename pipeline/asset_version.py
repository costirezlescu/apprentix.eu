"""Cache-busting: every reference to assets/css/*.css and assets/js/*.js carries ?v=<version>.

  python -m pipeline.asset_version

Cloudflare (and browsers) keep CSS and JavaScript for hours; without a version in the URL a
deploy can pair new HTML with an old stylesheet or script. The version is a short hash of
all CSS and JS files (with their own ?v= markers ignored, so stamping does not change it),
so it moves only when an asset changes.

Stamped: generated pages (render_pages.write_text calls stamp_html), the hand-written pages
(index.html, pages/*.html, embed/*.html) and the relative imports between modules in
assets/js/*.js — so one version of each module is loaded together. Deterministic.
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache

from .common import ROOT

CSS = ROOT / "assets" / "css"
JS = ROOT / "assets" / "js"
MARK = re.compile(r"\?v=[0-9a-f]{8}")
HTML_REF = re.compile(r"(assets/(?:css|js)/[A-Za-z0-9_.-]+\.(?:css|js))(?:\?v=[0-9a-f]{8})?")
JS_IMPORT = re.compile(r"""((?:\bfrom\s*|\bimport\s*\(\s*)(['"])\./[A-Za-z0-9_.-]+\.js)(?:\?v=[0-9a-f]{8})?(\2)""")


@lru_cache(maxsize=1)
def version() -> str:
    h = hashlib.sha256()
    for p in sorted(list(CSS.glob("*.css")) + list(JS.glob("*.js"))):
        h.update(p.name.encode())
        h.update(MARK.sub("", p.read_text(encoding="utf-8")).encode())
    return h.hexdigest()[:8]


def stamp_html(text: str) -> str:
    return HTML_REF.sub(lambda m: f"{m.group(1)}?v={version()}", text)


def stamp_js(text: str) -> str:
    return JS_IMPORT.sub(lambda m: f"{m.group(1)}?v={version()}{m.group(3)}", text)


def apply() -> int:
    """Stamp the hand-written pages and the JS modules' imports; returns files changed."""
    changed = 0
    files = [ROOT / "index.html", *sorted((ROOT / "pages").glob("*.html")), *sorted((ROOT / "embed").glob("*.html"))]
    for p in files:
        old = p.read_text(encoding="utf-8")
        new = stamp_html(old)
        if new != old:
            p.write_text(new, encoding="utf-8")
            changed += 1
    for p in sorted(JS.glob("*.js")):
        old = p.read_text(encoding="utf-8")
        new = stamp_js(old)
        if new != old:
            p.write_text(new, encoding="utf-8")
            changed += 1
    print(f"Assets: version {version()} ({changed} file(s) stamped)")
    return changed


if __name__ == "__main__":
    apply()
