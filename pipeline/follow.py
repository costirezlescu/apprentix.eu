"""Follow a country: one Atom feed per country page.

  python -m pipeline.follow

  data/feeds/<code>.xml    what changed in Apprentix's data for that country, newest first
  data/feeds/index.json    {code: {name, feed, page, entries, updated}} for the "Follow" UI

Built from data/published/changes/by-country.json (pipeline/changes.py), so a feed only
moves when the data for that country does. Every country with a country page gets a feed,
even before its first change, so a reader can subscribe now. Deterministic: no clock.
"""

from __future__ import annotations

import hashlib
from xml.sax.saxutils import escape

from .changes import BY_COUNTRY, LOG
from .common import DATA, ROOT, countries, read_json, write_json

SITE = "https://apprentix.eu/"
OUT = DATA / "feeds"
PAGES = ROOT / "pages" / "countries"


def _since() -> str:
    """Date the change log started: the 'updated' of a feed with no entries yet."""
    entries = read_json(LOG).get("entries", []) if LOG.exists() else []
    return min((e["date"] for e in entries if e.get("date")), default="2026-10-01")


def feed_xml(code: str, name: str, items: list[dict], since: str) -> str:
    x = escape
    slug = code.lower()
    self_url = f"{SITE}data/feeds/{slug}.xml"
    updated = (items[0]["date"] if items else since) + "T00:00:00Z"
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">',
           f'  <title>Apprentix — {x(name)}: apprenticeship and VET data updates</title>',
           f'  <subtitle>New figures, revisions and records about {x(name)} on apprentix.eu, newest first.</subtitle>',
           f'  <id>{self_url}</id>',
           f'  <link rel="self" type="application/atom+xml" href="{self_url}"/>',
           f'  <link rel="alternate" type="text/html" href="{SITE}pages/countries/{slug}.html"/>',
           f'  <updated>{updated}</updated>',
           f'  <author><name>Apprentix</name><uri>{SITE}</uri></author>',
           "  <rights>Each figure and record keeps its original publisher's licence; see the linked page.</rights>"]
    for it in items:
        key = hashlib.sha256(f"{it['title']}|{it['link']}".encode("utf-8")).hexdigest()[:12]
        out += ['  <entry>',
                f'    <id>tag:apprentix.eu,{it["date"]}:{slug}/{key}</id>',
                f'    <title>{x(it["title"])}</title>',
                f'    <link rel="alternate" type="text/html" href="{x(SITE + it["link"])}"/>',
                f'    <updated>{it["date"]}T00:00:00Z</updated>',
                f'    <category term="{x(it["kind"], {chr(34): "&quot;"})}"/>',
                f'    <summary>{x(it["text"])}</summary>',
                '  </entry>']
    out.append('</feed>')
    return "\n".join(out) + "\n"


def build() -> int:
    hist = read_json(BY_COUNTRY).get("countries", {}) if BY_COUNTRY.exists() else {}
    by_code = countries()["by_code"]
    codes = sorted(p.stem.upper() for p in PAGES.glob("*.html") if p.stem != "index")
    since = _since()
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    for code in codes:
        name = (by_code.get(code) or {}).get("name", code)
        items = hist.get(code, [])
        path = OUT / f"{code.lower()}.xml"
        text = feed_xml(code, name, items, since)
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
        index[code] = {"name": name, "feed": f"data/feeds/{code.lower()}.xml",
                       "page": f"pages/countries/{code.lower()}.html",
                       "entries": len(items), "updated": items[0]["date"] if items else None}
    opml = ['<?xml version="1.0" encoding="utf-8"?>', '<opml version="2.0">',
            '  <head><title>Apprentix — country update feeds</title></head>', '  <body>']
    for code, v in sorted(index.items(), key=lambda kv: kv[1]["name"]):
        opml.append(f'    <outline type="rss" text="{escape(v["name"])}" title="Apprentix — {escape(v["name"])}" '
                    f'xmlUrl="{SITE}{v["feed"]}" htmlUrl="{SITE}{v["page"]}"/>')
    opml += ['  </body>', '</opml>']
    text = "\n".join(opml) + "\n"
    path = OUT / "countries.opml"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    for p in OUT.glob("*.xml"):
        if p.stem.upper() not in index:
            p.unlink()
    write_json(OUT / "index.json", {
        "description": "One Atom feed per country: what changed in Apprentix's data for it. Written by pipeline/follow.py.",
        "countries": index,
    })
    print(f"Follow: {len(index)} country feeds")
    return len(index)


if __name__ == "__main__":
    build()
