"""The home page's opening lines, written into index.html at build time.

  python -m pipeline.home

The tagline, the blurb, the four headline numbers and "Last updated" used to be filled in only by
the page's script once data/datasets.json had loaded, so on a slow connection everything below
them jumped down after the first paint. The build now writes the same markup the script writes
(index.html's inline module still runs and rewrites identical content), so the page is laid out
right from the first paint. Deterministic.
"""

from __future__ import annotations

import re
from html import escape

from .common import DATA, ROOT, read_json

INDEX = ROOT / "index.html"


def e(v) -> str:
    return escape(str(v if v is not None else ""), quote=True)


def fill(text: str, m: dict) -> str:
    site = m["site"]
    tagline, cut = site["tagline"], site["tagline"].rfind(", ")
    tag = f'{e(tagline[:cut + 1])} <span class="h-accent">{e(tagline[cut + 2:])}</span>' if cut > 0 else e(tagline)
    n_ds = len(m["datasets"])
    stats = "".join(f'<div class="stat"><div class="n">{n}</div><div class="l">{e(label)}</div></div>' for n, label in [
        (n_ds, "Dataset" if n_ds == 1 else "Datasets"),
        (f'{sum(d.get("records") or 0 for d in m["datasets"]):,}', "Records"),
        ((m.get("indicators") or {}).get("count") or 0, "Indicators"),
        (len(m.get("planned") or []), "In preparation"),
    ])
    for pattern, inner in [
        (r'(<h1 id="site-tagline">).*?(</h1>)', tag),
        (r'(<p class="lede" id="site-blurb">).*?(</p>)', e(site["blurb"])),
        (r'(<div class="stats" id="stats">).*?(</div>)$', stats),
        (r'(<p id="foot-updated">).*?(</p>)', e(f'Last updated {site["updated"]}.')),
    ]:
        text, n = re.subn(pattern, lambda mo: mo.group(1) + inner + mo.group(2), text, count=1, flags=re.M)
        if n != 1:
            raise SystemExit(f"home: {pattern!r} not found in index.html")
    return text


def apply() -> bool:
    old = INDEX.read_text(encoding="utf-8")
    new = fill(old, read_json(DATA / "datasets.json"))
    if new != old:
        INDEX.write_text(new, encoding="utf-8")
    return new != old


if __name__ == "__main__":
    print("Home: index.html", "updated" if apply() else "unchanged")
