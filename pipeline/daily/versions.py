"""Every published version of every edition, kept at a permanent address.

  python -m pipeline.daily.versions            (also run by pipeline.daily.render)

A version is what a push to main published: each commit that changed
daily/<date>/index.html. Commits that changed nothing a reader sees (only the
version line, a stylesheet's cache-busting hash, or which stylesheets and fonts the
page links, as when the main site's fonts were swapped and swapped back) are not new
versions.

For version n of an edition this writes daily/<date>/v<n>/:
  index.html     the page as published, with a banner naming the version and
                 linking to the current one; its stylesheets point to local copies
  daily.css      the Daily's stylesheet (daily/assets/daily.css, or the theme's) as it was at that commit
  site.css       assets/css/site.css as it was at that commit
  edition.json   the edition as written
  sources.json   the items it used (when the commit had one)
Snapshots are rebuilt from git on every run, so they never drift. Deterministic.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

from ..common import ROOT

DAILY = ROOT / "daily"
ATHENS = ZoneInfo("Europe/Athens")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def show(commit: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def normalise(page: str) -> str:
    """What a reader sees: drop the version line, stylesheet links and cache-busting hashes."""
    page = re.sub(r'<span class="dm-version">.*?</span>', "", page, flags=re.S)
    page = re.sub(r'<link rel="stylesheet"[^>]*>', "", page)
    page = re.sub(r"\?v=[0-9a-f]{8}", "", page)
    return re.sub(r">\s+<", "><", re.sub(r"\s+", " ", page)).strip()


def history(date: str) -> list[dict]:
    """Published versions of one edition, oldest first: [{n, commit, time}]."""
    path = f"daily/{date}/index.html"
    try:
        log = git("log", "--reverse", "--format=%H %cI", "--", path).split("\n")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    out, last = [], None
    for line in filter(None, log):
        commit, when = line.split(" ", 1)
        page = show(commit, path)
        if page is None:
            continue
        norm = normalise(page)
        if norm == last:
            continue
        last = norm
        out.append({"n": len(out) + 1, "commit": commit, "time": when, "_norm": norm})
    return out


def current_number(date: str, rendered: str) -> tuple[int, list[dict]]:
    """The version number the page just rendered will carry once published."""
    h = history(date)
    if h and normalise(rendered) == h[-1]["_norm"]:
        return h[-1]["n"], h
    return len(h) + 1, h


def when(iso: str) -> str:
    t = dt.datetime.fromisoformat(iso).astimezone(ATHENS)
    return f"{t.day} {t.strftime('%B %Y')}, {t.strftime('%H:%M')} Athens time"


def banner(date: str, v: dict, total: int, long_date: str) -> str:
    style = ("background:#eef0f5;color:#1c2233;border-bottom:1px solid #3c4f8c;padding:10px 20px;"
             "font:500 14px/1.5 'Libre Franklin','Public Sans',system-ui,sans-serif;text-align:center")
    return (f'<div class="dc-archived" role="note" style="{style}">'
            f'<strong>Archived version {v["n"]} of {total}</strong> of Cedefop Daily for {html.escape(long_date)}, '
            f'published {html.escape(when(v["time"]))}. '
            f'<a href="/daily/{date}/" style="color:#3c4f8c">Current version</a> · '
            f'<a href="/daily/archive.html#ed-{date}" style="color:#3c4f8c">All versions</a></div>')


def snapshot(date: str, v: dict, total: int, long_date: str) -> None:
    c = v["commit"]
    page = show(c, f"daily/{date}/index.html")
    css = (re.search(r'href="/daily/assets/(daily[\w-]*\.css)', page) or [None, "daily.css"])[1]
    page = re.sub(r'href="/daily/assets/daily[\w-]*\.css(\?v=[0-9a-f]{8})?"', 'href="daily.css"', page)
    page = re.sub(r'href="/assets/css/site\.css(\?v=[0-9a-f]{8})?"', 'href="site.css"', page)
    page = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + banner(date, v, total, long_date), page, count=1)
    page = re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="https://apprentix.eu/daily/{date}/">', page)
    out = DAILY / date / f"v{v['n']}"
    out.mkdir(parents=True, exist_ok=True)
    files = {"index.html": page,
             "daily.css": show(c, f"daily/assets/{css}"),
             "site.css": show(c, "assets/css/site.css"),
             "edition.json": show(c, f"daily/editions/{date}.json"),
             "sources.json": show(c, f"daily/{date}/sources.json")}
    for name, text in files.items():
        if text is not None:
            p = out / name
            if not p.exists() or p.read_text("utf-8") != text:
                p.write_text(text, "utf-8")


def long_date_of(date: str) -> str:
    x = dt.date.fromisoformat(date)
    return f"{x.strftime('%A')} {x.day} {x.strftime('%B')} {x.year}"


def build(date: str) -> list[dict]:
    h = history(date)
    for v in h:
        snapshot(date, v, len(h), long_date_of(date))
    return h


def main(argv: list[str]) -> int:
    dates = argv or sorted(p.stem for p in (DAILY / "editions").glob("*.json"))
    for d in dates:
        h = build(d)
        print(f"{d}: {len(h)} published version(s) archived in daily/{d}/v1…v{len(h)}" if h else f"{d}: not published yet")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
