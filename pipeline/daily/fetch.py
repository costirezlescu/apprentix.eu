"""Fetch the public sources for one Cedefop Daily edition → daily/pool/<edition date>.json.

  python -m pipeline.daily.fetch 2026-10-19          (edition date; default: next working day)
  python -m pipeline.daily.fetch 2026-10-19 --retag  (re-apply topics.json to the existing pool)
  python -m pipeline.daily.fetch 2026-10-19 --weather  (only the forecast → daily/weather/<date>.json)
  python -m pipeline.daily.fetch 2026-10-19 --only consultations,apprentix   (some sources, merged into the pool)

The pool is everything the writing step may use. Every URL an edition prints must
come from it (pipeline/daily/check.py enforces this), so links are never typed by hand.

Rules carried over from the blueprint (cedefop-daily/BLUEPRINT.md, SOURCES.md):
  * plain HTTP only. A source that answers 403/202 to scripts (a bot check) is
    recorded as refused and skipped, never worked around;
  * Cedefop's RSS is a "recently changed" feed: keep news, publications, events,
    newsletters and press releases; drop procurement, vacancies older than the
    window and file attachments. An attachment that carries a DOI becomes a
    publication item with the DOI only: uploader names in the feed are never kept;
  * OpenAlex is matched on the raw affiliation string, not the institution id,
    and on publication dates (the created-date filter needs a paid plan);
  * no searches about people. Names enter the pool only as printed by a source
    (paper authors, office holders in official texts).

Every item: id, source, circle, kind, title, url, date, summary, text, work_areas,
policy_hooks, meta. Tagging is by keyword (pipeline/daily/topics.json).
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from ..common import ROOT, FetchError, fetch, html_to_text, write_json

HERE = Path(__file__).resolve().parent
POOL = ROOT / "daily" / "pool"
TOPICS = json.loads((HERE / "topics.json").read_text("utf-8"))

WINDOW_DAYS = 14          # news and policy items
RESEARCH_DAYS = 14        # papers mentioning Cedefop
JOURNAL_DAYS = 30         # papers in VET journals
AFFILIATION_DAYS = 120    # papers with a Cedefop author affiliation
SELF_DOIS = {"https://doi.org/10.5281/zenodo.23426138"}   # Apprentix itself mentions Cedefop

VET_JOURNALS = {
    "S4210171403": "Journal of Vocational Education and Training",
    "S3035624105": "Empirical Research in Vocational Education and Training",
    "S2736341217": "International Journal for Research in Vocational Education and Training",
    "S32136629": "Journal of Education and Work",
    "S9600176": "Vocations and Learning",
    "S71191459": "European Journal of Education",
    "S114439130": "International Journal of Training and Development",
    "S56255037": "International Journal of Lifelong Education",
    "S161695446": "Journal of Workplace Learning",
    "S2764516016": "European Journal of Training and Development",
    "S2764459744": "Education + Training",
}

EUROSTAT_WATCH = {
    "trng_lfse_01": "Participation rate in education and training (last 4 weeks)",
    "edat_lfse_14": "Early leavers from education and training",
    "edat_lfse_20": "Young people neither in employment nor in education and training (NEET)",
    "educ_uoe_enrs04": "Pupils enrolled in upper secondary education by programme orientation",
    "trng_aes_100": "Adult Education Survey: participation",
    "jvs_q_nace2": "Job vacancy statistics",
    "une_rt_m": "Unemployment by sex and age (monthly)",
    "lfsa_ergaed": "Employment rates by educational attainment",
    "isoc_sk_dskl_i21": "Individuals' level of digital skills",
}

STATUS: dict[str, str] = {}


# ---------------------------------------------------------------- helpers --

def _id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def _clean(s: str | None) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _date(s: str | None) -> str | None:
    """RSS (RFC 822), ISO, dd/mm/yyyy or epoch seconds → YYYY-MM-DD."""
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return dt.datetime.fromtimestamp(int(s), dt.timezone.utc).date().isoformat()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    try:
        return email.utils.parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return dt.datetime.strptime(s, "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def _norm(s: str) -> str:
    return " " + re.sub(r"[^\w]+", " ", s.lower()) + " "


_KW: list[tuple[str, re.Pattern]] = []
for _area, _spec in TOPICS["areas"].items():
    for _words in _spec["keywords"].values():
        for _w in _words:
            exact = _w.startswith("=")
            n = _norm(_w.lstrip("=")).strip()
            if n:
                tail = r"(?!\w)" if exact or len(n) <= 4 else ""
                _KW.append((_area, re.compile(r"(?<!\w)" + re.escape(n) + tail)))


def tag(*texts: str) -> tuple[list[str], list[str]]:
    t = _norm(" ".join(x or "" for x in texts))
    areas = sorted({a for a, rx in _KW if rx.search(t)})
    low = " ".join(x or "" for x in texts).lower()
    hooks = [h for h in TOPICS["policy_hooks"]
             if re.search(r"(?<!\w)" + re.escape(h.split(" (")[0].lower()) + r"(?!\w)", low)]
    return areas, hooks


def item(source: str, circle: str, kind: str, title: str, url: str, date: str | None,
         summary: str = "", text: str = "", **meta) -> dict:
    title = _clean(title)
    summary = _clean(summary)[:900]
    text = _clean(text)[:80000]
    areas, hooks = tag(title, summary, text[:6000])
    return {"id": _id(url), "source": source, "circle": circle, "kind": kind, "title": title,
            "url": url, "date": date, "summary": summary, "text": text,
            "work_areas": areas, "policy_hooks": hooks,
            "meta": {k: v for k, v in meta.items() if v not in (None, "", [], {})}}


def _links(markup: str) -> list[dict]:
    """Links with their anchor text, in page order, without duplicates."""
    out, seen = [], set()
    for m in re.finditer(r'<a\b[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', markup or "", re.S):
        url, text = html.unescape(m.group(1)), _clean(m.group(2))
        if url not in seen and text:
            seen.add(url)
            out.append({"url": url, "text": text[:160]})
    return out


def get(source: str, url: str, **kw) -> bytes | None:
    try:
        body = fetch(url, retries=2, timeout=60, **kw)
    except FetchError as e:
        STATUS[source] = f"failed: {e}"
        print(f"  {source}: {e}")
        return None
    if not body.strip():
        STATUS[source] = "refused: empty response (bot check)"
        print(f"  {source}: empty response")
        return None
    STATUS[source] = "ok"
    return body


def rss(source: str, url: str) -> list[ET.Element]:
    body = get(source, url)
    if body is None:
        return []
    try:
        return list(ET.fromstring(body).iter("item"))
    except ET.ParseError as e:
        STATUS[source] = f"failed: not XML ({e})"
        return []


def within(date: str | None, start: dt.date, end: dt.date) -> bool:
    if not date:
        return False
    d = dt.date.fromisoformat(date)
    return start <= d <= end


# ------------------------------------------------------------- circle 0 --

CEDEFOP_KEEP = ("/en/news/", "/en/publications/", "/en/events/", "/en/newsletters/",
                "/en/press-releases/", "/en/press-and-media/")


def cedefop_rss(start, end) -> list[dict]:
    out = []
    for it in rss("cedefop_rss", "https://www.cedefop.europa.eu/en/rss.xml"):
        link = (it.findtext("link") or "").strip()
        date = _date(it.findtext("pubDate"))
        title = it.findtext("title") or ""
        desc = it.findtext("description") or ""
        if not within(date, start, end):
            continue
        if "/attachments/" in link:
            # Keep publications only, by their identifiers. The feed's text names the
            # member of staff who uploaded the file; it is never stored.
            flat = _clean(desc)
            doi = re.search(r"DOI\s*(10\.\d{4,}/)\s*(\S+)", flat)
            isbn = re.search(r"ISBN\s*([\d-]{10,})", flat)
            cat = re.search(r"\b([A-Z]{2}-\d{2}-\d{2}-\d{3}-[A-Z]{2}-[A-Z])\b", flat)
            if doi:
                out.append(item("cedefop_rss", "0", "publication", title, link, date,
                                doi=doi.group(1) + doi.group(2), isbn=isbn and isbn.group(1),
                                catalogue_number=cat and cat.group(1)))
            continue
        if not any(p in link for p in CEDEFOP_KEEP):
            continue
        kind = next((k for k in ("newsletter", "publication", "event", "news", "press")
                     if f"/{k}" in link), "news")
        text = re.sub(r"\{[^{}]*\}", " ", desc)           # drop the share-widget JSON
        text = re.sub(r"#block-[^{]*\{?", " ", _clean(text))
        out.append(item("cedefop_rss", "0", kind, title, link, date, text[:400], text,
                        links=_links(desc)))
    return out


CELLAR = "https://publications.europa.eu/webapi/rdf/sparql"
CELLAR_Q = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?work ?date ?title (SAMPLE(?abs) AS ?abstract) WHERE {
  ?work cdm:work_created_by_agent <http://publications.europa.eu/resource/authority/corporate-body/CEDEFOP> ;
        cdm:work_date_document ?date .
  FILTER(%s)
  ?expr cdm:expression_belongs_to_work ?work ;
        cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> ;
        cdm:expression_title ?title .
  OPTIONAL { ?expr cdm:expression_abstract ?abs }
} GROUP BY ?work ?date ?title ORDER BY ?date LIMIT 300"""


def _cellar(source: str, flt: str) -> list[dict]:
    body = get(source, CELLAR, params={"query": CELLAR_Q % flt},
               headers={"Accept": "application/sparql-results+json"})
    if body is None:
        return []
    rows = json.loads(body)["results"]["bindings"]
    out = []
    for b in rows:
        uuid = b["work"]["value"].rsplit("/", 1)[-1]
        url = f"https://op.europa.eu/en/publication-detail/-/publication/{uuid}"
        title = b["title"]["value"].replace(" : ", ": ").rstrip(".")
        abstract = b.get("abstract", {}).get("value", "")
        out.append(item(source, "0", "publication", title, url, b["date"]["value"][:10],
                        abstract[:400], abstract, cellar=b["work"]["value"]))
    return out


def cellar_recent(start, end) -> list[dict]:
    return _cellar("cellar_recent",
                   f'?date >= "{start}"^^<http://www.w3.org/2001/XMLSchema#date> && '
                   f'?date <= "{end}"^^<http://www.w3.org/2001/XMLSchema#date>')


def cellar_archive(edition: dt.date) -> list[dict]:
    """Cedefop publications from the edition's week (±3 days) in earlier years."""
    lo, hi = edition - dt.timedelta(days=3), edition + dt.timedelta(days=3)
    if lo.month == hi.month:
        flt = f"MONTH(?date)={lo.month} && DAY(?date)>={lo.day} && DAY(?date)<={hi.day}"
    else:
        flt = (f"((MONTH(?date)={lo.month} && DAY(?date)>={lo.day}) || "
               f"(MONTH(?date)={hi.month} && DAY(?date)<={hi.day}))")
    flt += f" && YEAR(?date) < {edition.year}"
    items = _cellar("cellar_archive", flt)
    for i in items:
        i["kind"] = "archive"
    return items


# ------------------------------------------------------------- circle 1/5 --

def _openalex_key() -> str | None:
    k = os.environ.get("OPENALEX_API_KEY")
    if k or sys.platform != "darwin":
        return k
    try:
        return subprocess.run(["security", "find-generic-password", "-s", "openalex-api-key", "-w"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in pos)


def _works(source: str, flt: str, key: str | None, pages: int = 2) -> list[dict]:
    out, cursor = [], "*"
    hdrs = {"Authorization": f"Bearer {key}"} if key else {}
    for _ in range(pages):
        body = get(source, "https://api.openalex.org/works",
                   params={"filter": flt, "per-page": 100, "cursor": cursor,
                           "sort": "publication_date:desc"}, headers=hdrs)
        if body is None:
            break
        d = json.loads(body)
        out += d["results"]
        cursor = d["meta"].get("next_cursor")
        if not cursor:
            break
    return out


def _paper(w: dict, source: str, circle: str, kind: str, **extra) -> dict | None:
    if w.get("doi") in SELF_DOIS or w.get("type") in ("dataset", "peer-review", "paratext", "erratum"):
        return None
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    url = w.get("doi") or loc.get("landing_page_url") or w["id"]
    authors = []
    for a in w.get("authorships", [])[:12]:
        authors.append({"name": a["author"]["display_name"],
                        "affiliations": a.get("raw_affiliation_strings", [])[:2]})
    ab = _abstract(w.get("abstract_inverted_index"))
    return item(source, circle, kind, w.get("title") or "", url, w.get("publication_date"),
                ab[:400], ab, venue=src.get("display_name"), type=w.get("type"),
                doi=w.get("doi"), open_access=(w.get("open_access") or {}).get("is_oa"),
                authors=authors, n_authors=len(w.get("authorships", [])),
                language=w.get("language"), openalex=w["id"], **extra)


def openalex(edition: dt.date) -> list[dict]:
    key = _openalex_key()
    if not key:
        print("  openalex: no API key (OPENALEX_API_KEY); using the anonymous rate limit")
    end = edition.isoformat()
    out = []
    lo = (edition - dt.timedelta(days=RESEARCH_DAYS)).isoformat()
    for w in _works("openalex_fulltext", f"fulltext.search:cedefop,from_publication_date:{lo},"
                    f"to_publication_date:{end}", key):
        p = _paper(w, "openalex_fulltext", "1", "mentions_cedefop")
        if p:
            out.append(p)
    lo = (edition - dt.timedelta(days=AFFILIATION_DAYS)).isoformat()
    for w in _works("openalex_affiliation", f"raw_affiliation_strings.search:cedefop,"
                    f"from_publication_date:{lo}", key, pages=1):
        hits = [a for a in w.get("authorships", [])
                if any(re.search(r"cedefop|european centre for the development of vocational training", s, re.I)
                       for s in a.get("raw_affiliation_strings", []))]
        if not hits:
            continue        # institution-id noise: the raw string must name Cedefop
        p = _paper(w, "openalex_affiliation", "1", "cedefop_author",
                   future_dated=(w.get("publication_date") or "") > end)
        if p:
            out.append(p)
    lo = (edition - dt.timedelta(days=JOURNAL_DAYS)).isoformat()
    ids = "|".join(VET_JOURNALS)
    for w in _works("openalex_journals", f"primary_location.source.id:{ids},"
                    f"from_publication_date:{lo},to_publication_date:{end}", key):
        p = _paper(w, "openalex_journals", "5", "journal_paper")
        if p:
            out.append(p)
    return out


# --------------------------------------------------------------- circle 2 --

def ec_presscorner(start, end) -> list[dict]:
    out = []
    for it in rss("ec_presscorner", "https://ec.europa.eu/commission/presscorner/api/rss?language=en"):
        link = (it.findtext("link") or "").strip()
        date = _date(it.findtext("pubDate"))
        if not within(date, start, end):
            continue
        text = _clean(it.findtext("description"))
        ref = re.search(r"/detail/en/([a-z]+)_(\d+)_(\d+)", link)
        if ref:
            # Full text from the press corner's own document API (public, JSON).
            body = get("ec_presscorner_doc", "https://ec.europa.eu/commission/presscorner/api/documents",
                       params={"reference": f"{ref.group(1).upper()}/{ref.group(2)}/{ref.group(3)}",
                               "language": "en"})
            if body:
                doc = json.loads(body).get("docuLanguageResource") or {}
                text = _clean(doc.get("htmlContent")) or text
        out.append(item("ec_presscorner", "2", "press", it.findtext("title") or "", link, date,
                        text[:400], text))
    return out


def council(start, end) -> list[dict]:
    # Council pages refuse scripts (403); the feed's title and summary are all we use.
    out = []
    for it in rss("council_press", "https://www.consilium.europa.eu/en/rss/pressreleases.ashx"):
        link = (it.findtext("link") or "").strip()
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", link)
        date = _date(it.findtext("pubDate")) or (m and f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        if not within(date, start, end):
            continue
        out.append(item("council_press", "2", "press", it.findtext("title") or "", link, date,
                        it.findtext("description") or ""))
    return out


def parliament(start, end) -> list[dict]:
    out = []
    for it in rss("ep_press", "https://www.europarl.europa.eu/rss/doc/press-releases/en.xml"):
        date = _date(it.findtext("pubDate"))
        if not within(date, start, end):
            continue
        title = re.sub(r"^Press release - ", "", it.findtext("title") or "")
        desc = re.sub(r"Source : © European Union.*$", "", _clean(it.findtext("description")))
        out.append(item("ep_press", "2", "press", title, (it.findtext("link") or "").strip(),
                        date, desc))
    return out


def eurlex(start, end) -> list[dict]:
    out = []
    for it in rss("eurlex_oj_l", "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=162"):
        date = _date(it.findtext("pubDate"))
        if not within(date, start - dt.timedelta(days=WINDOW_DAYS), end):
            continue
        title = re.sub(r"^CELEX:\S+:\s*", "", it.findtext("title") or "")
        link = (it.findtext("link") or "").replace("eur-lex.europa.eu/./", "eur-lex.europa.eu/")
        out.append(item("eurlex_oj_l", "2", "act", title, link, date,
                        celex=re.sub(r"^CELEX:(\S+):.*", r"\1", it.findtext("title") or "")))
    return out


# --------------------------------------------------------------- circle 3 --

def euosha(start, end) -> list[dict]:
    out = []
    for it in rss("euosha", "https://osha.europa.eu/en/rss.xml"):
        link = (it.findtext("link") or "").strip()
        date = _date(it.findtext("pubDate"))
        if not within(date, start - dt.timedelta(days=WINDOW_DAYS), end):
            continue
        if not re.search(r"/(oshnews|highlights|publications|press-releases)/", link):
            continue          # skip wiki pages, procurement and events
        title = it.findtext("title") or ""
        text = _clean(it.findtext("description"))
        links = []
        body = get("euosha_page", link)
        if body:
            page = body.decode("utf-8", "replace")
            # The page's <h1> is the section name ("OSH News"); <title> carries the article's.
            t = re.search(r"<title>(.*?)</title>", page, re.S)
            title = title or (t and _clean(t.group(1)).split(" | ")[0]) or ""
            bodies = re.findall(r'<div[^>]+field--name-body[^>]*>(.*?)</div>', page, re.S)
            main = max(bodies, key=lambda b: len(_clean(b)), default="")
            text = _clean(main) or text
            links = _links(main)
        out.append(item("euosha", "3", "news", title, link, date, text[:400], text,
                        agency="EU-OSHA", links=links))
    return out


# Listing pages with an article link and a <time> near it. (source, url, base, link pattern, agency)
LISTINGS = [
    ("etf", "https://www.etf.europa.eu/en/news-and-events/news", "https://www.etf.europa.eu",
     r'href="(/en/news-and-events/news/[^"#?]+)"[^>]*>(.*?)</a>', "ETF"),
    ("ela", "https://www.ela.europa.eu/en/news", "https://www.ela.europa.eu",
     r'href="(/en/news/[^"#?]+)"[^>]*>(.*?)</a>', "ELA"),
    ("eige", "https://eige.europa.eu/newsroom/news", "https://eige.europa.eu",
     r'href="(/newsroom/news/[^"#?]+)[^"]*"[^>]*>(.*?)</a>', "EIGE"),
    ("ilo", "https://www.ilo.org/resource/news", "",
     r'href="(https://www\.ilo\.org/resource/news/(?!all-)[^"#?]+)"[^>]*title="([^"]+)"', "ILO"),
]


def _article(source: str, url: str) -> str:
    """Main text of an agency article page: the longest body field, else all paragraphs."""
    body = get(f"{source}_page", url)
    if body is None:
        return ""
    page = body.decode("utf-8", "replace")
    page = re.sub(r"<(nav|header|footer|aside)\b.*?</\1>", " ", page, flags=re.S | re.I)
    fields = re.findall(r'<div[^>]+(?:field--name-body|ilo--article|oe-text|ecl-paragraph)[^>]*>(.*?)</div>', page, re.S)
    best = max((_clean(f) for f in fields), key=len, default="")
    if len(best) < 300:
        best = " ".join(_clean(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", page, re.S))
    return best


def listings(start, end) -> list[dict]:
    out = []
    lo = start - dt.timedelta(days=WINDOW_DAYS)     # agencies publish less often: 4 weeks
    for source, url, base, pat, agency in LISTINGS:
        body = get(source, url)
        if body is None:
            continue
        page = body.decode("utf-8", "replace")
        seen = set()
        for m in re.finditer(pat, page, re.S):
            link = base + m.group(1)
            if link in seen:
                continue
            seen.add(link)
            near = page[m.end(): m.end() + 2500]
            t = re.search(r'<time[^>]*datetime="([^"]+)"', near)
            date = _date(t.group(1)) if t else None
            if not within(date, lo, end):
                continue
            teaser = re.search(r"<p[^>]*>(.*?)</p>", near, re.S)
            out.append(item(source, "3", "news", m.group(2), link, date,
                            teaser.group(1) if teaser else "", _article(source, link),
                            agency=agency))
    # UNESCO-UNEVOC: the date precedes the link.
    body = get("unevoc", "https://unevoc.unesco.org/home/UNEVOC+News")
    if body:
        page = body.decode("utf-8", "replace")
        for m in re.finditer(r"<font size=1>([^<]+)</font><br><a href=\"([^\"]+)\"[^>]*><b[^>]*>(.*?)</b></a><br>(.*?)<br>",
                             page, re.S):
            date = _date(m.group(1))
            if not within(date, lo, end):
                continue
            link = urllib.parse.urljoin("https://unevoc.unesco.org", m.group(2))
            out.append(item("unevoc", "3", "news", m.group(3), link, date, m.group(4),
                            agency="UNESCO-UNEVOC"))
    return out


# ------------------------------------------------------------------- data --

def eurostat(start, end) -> list[dict]:
    out = []
    for it in rss("eurostat_updates",
                  "https://ec.europa.eu/eurostat/api/dissemination/catalogue/rss/en/statistics-update.rss"):
        title = it.findtext("title") or ""
        code = re.search(r"\(([a-z0-9_]+)\)\s*$", title) or re.search(r"\b([a-z]{2,}_[a-z0-9_]+)\b", title)
        if not code or code.group(1) not in EUROSTAT_WATCH:
            continue
        date = _date(it.findtext("pubDate"))
        if not within(date, start, end):
            continue
        ds = code.group(1)
        url = f"https://ec.europa.eu/eurostat/databrowser/view/{ds}/default/table?lang=en"
        out.append(item("eurostat_updates", "data", "dataset_update", title, url, date,
                        it.findtext("description") or "", dataset=ds))
    # The number: latest EU-27 value of each watched series that answers a simple query.
    for ds, label, params in [
        ("trng_lfse_01", EUROSTAT_WATCH["trng_lfse_01"], {"sex": "T", "age": "Y25-64"}),
        ("edat_lfse_14", EUROSTAT_WATCH["edat_lfse_14"], {"sex": "T", "wstatus": "POP"}),
    ]:
        body = get("eurostat_api", f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{ds}",
                   params={"format": "JSON", "lang": "EN", "geo": "EU27_2020", "sinceTimePeriod": "2015", **params})
        if body is None:
            continue
        d = json.loads(body)
        times = {i: t for t, i in d["dimension"]["time"]["category"]["index"].items()}
        if len(d["value"]) != len(times) and len(d["value"]) > len(times):
            print(f"  eurostat {ds}: query not specific enough; skipped")
            continue
        series = {times[int(k)]: v for k, v in sorted(d["value"].items(), key=lambda kv: int(kv[0]))}
        unit = list(d["dimension"]["unit"]["category"]["label"].values())[0]
        url = f"https://ec.europa.eu/eurostat/databrowser/view/{ds}/default/table?lang=en"
        latest = max(series)
        text = f"{d['label']}, EU-27, {unit}: " + "; ".join(f"{y}: {v}" for y, v in series.items())
        out.append(item("eurostat_api", "data", "number", f"{label}, EU-27", url,
                        (d.get("updated") or "")[:10], text, text, dataset=ds, unit=unit,
                        latest_year=latest, latest_value=series[latest], series=series,
                        query=params, api_label=d["label"]))
    return out


# ---------------------------------------------------- press and the field --

PRESS = json.loads((HERE / "press.json").read_text("utf-8"))["feeds"]
PRESS_DAYS = 8            # "current": the last eight days
PRESS_PAGES = 10          # article pages read per feed, at most (politeness)
EDU = {"vet_policy", "apprenticeships", "adult_learning", "qualifications", "skills_intelligence"}


LIVES_DAYS = 60           # human stories do not go stale
CORE = {"vet_policy", "apprenticeships", "adult_learning", "qualifications"}
PROFILE = re.compile(r"(\b\d{2}\b[- ]?(jährig|year|ans\b|años|anni|χρον|vuotias|år\b|ani\b))|(-jährige)|"
                     r"(\bwho\b.*\b(apprentice|retrain))|(weltmeister|world champion|champion du monde|campeón)", re.I)


def press_relevant(areas: list[str], group: str = "press") -> bool:
    """Press is noisy. Field reporting must touch education and training directly (a core
    VET or skills term in the title or summary); the debate may also be AI with work and jobs."""
    a = set(areas)
    if group == "field":
        return bool(a & EDU)
    return bool(a & EDU) or {"future_of_work", "labour_market"} <= a


def _feed_entries(body: bytes) -> list[dict]:
    """RSS <item> or Atom <entry> → title, link, date, summary."""
    root = ET.fromstring(body)
    out = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        f = {c.tag.split("}")[-1]: c for c in el}
        link = (f["link"].text or f["link"].get("href") or "") if "link" in f else ""
        if not link.strip() and "link" in f:
            link = f["link"].get("href", "")
        summary = next((f[k].text for k in ("description", "summary", "content", "encoded") if k in f and f[k].text), "")
        date = next((f[k].text for k in ("pubDate", "published", "updated", "date") if k in f and f[k].text), None)
        out.append({"title": (f["title"].text if "title" in f else "") or "", "link": link.strip(),
                    "date": _date(date), "summary": summary})
    return out


def _page_text(source: str, url: str) -> str:
    """The article's openly served paragraphs, for summarising (never republished).
    A paywall simply leaves the teaser; nothing is worked around."""
    body = get(f"{source}_page", url)
    if body is None:
        return ""
    page = body.decode("utf-8", "replace")
    page = re.sub(r"<(script|style|nav|header|footer|aside|figure|form)\b.*?</\1>", " ", page, flags=re.S | re.I)
    art = re.search(r"<article\b.*?</article>", page, re.S | re.I)
    paras = [_clean(p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", art.group(0) if art else page, re.S)]
    return " ".join(p for p in paras if len(p) > 60)[:8000]


def _press_feed(f: dict, lo: dt.date, end: dt.date) -> list[dict]:
    body = get(f["id"], f["url"])
    if body is None:
        return []
    try:
        entries = _feed_entries(body)
    except ET.ParseError as e:
        STATUS[f["id"]] = f"failed: not XML ({e})"
        return []
    out, pages = [], 0
    lives_lo = end - dt.timedelta(days=LIVES_DAYS)
    for x in entries:
        if not x["link"] or not within(x["date"], lives_lo, end):
            continue
        areas, _ = tag(x["title"], _clean(x["summary"]))
        head = x["title"] + " " + _clean(x["summary"])
        lives = f["group"] in ("field", "press") and bool(set(areas) & CORE) and bool(PROFILE.search(head))
        if not lives and (not within(x["date"], lo, end) or not press_relevant(areas, f["group"])):
            continue
        text = ""
        if pages < PRESS_PAGES:
            text, pages = _page_text(f["id"], x["link"]), pages + 1
        if lives:
            text = _page_text(f["id"], x["link"])
        it = item(f["id"], "press" if f["group"] != "field" else "4", "lives" if lives else f["group"], x["title"],
                  x["link"], x["date"], x["summary"], text or x["summary"], outlet=f["name"], country=f["country"],
                  language=f["lang"], group=f["group"], lives_candidate=lives or None)
        if lives or press_relevant(it["work_areas"], f["group"]):
            out.append(it)
    return out


def press(edition: dt.date) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    end = min(edition, dt.date.today())
    lo = end - dt.timedelta(days=PRESS_DAYS)
    with ThreadPoolExecutor(8) as ex:
        batches = list(ex.map(lambda f: _press_feed(f, lo, end), PRESS))
    seen, out = set(), []
    for b in batches:
        for i in b:
            key = re.sub(r"\W+", " ", i["title"].lower()).strip()
            if key not in seen:        # the same story in two feeds of one outlet
                seen.add(key)
                out.append(i)
    return out


# -------------------------------------------------------------- apprentix --

SITE = "https://apprentix.eu/"


HYS = "https://ec.europa.eu/info/law/better-regulation"
HYS_STAGE = {"PLANNING_WORKFLOW": "Call for evidence", "ISC_WORKFLOW": "Draft act", "OPC_LAUNCHED": "Public consultation",
             "ADOPTION_WORKFLOW": "Commission proposal"}


def consultations() -> list[dict]:
    """Initiatives open for feedback on the Commission's "Have your say" portal (its public JSON API).
    All are kept; tagging decides which touch Cedefop's work, and the closing date goes in meta."""
    out, page = [], 0
    while True:
        d = json.loads(fetch(f"{HYS}/brpapi/searchInitiatives", params={"page": page, "size": 50, "language": "EN",
                                                                      "feedbackStatus": "OPEN"},
                             headers={"Accept": "application/json"}))["initiativeResultDtoPage"]
        for x in d["content"]:
            st = next((s for s in x["currentStatuses"] if s.get("isCurrent")), x["currentStatuses"][0])
            title = x["shortTitle"].strip()
            slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
            stage = HYS_STAGE.get(st.get("frontEndStage"), "Feedback")
            until = st.get("feedbackEndDate", "")[:10].replace("/", "-")
            topics = [t["label"] for t in x["topics"]]
            out.append(item("have_your_say", "2", "consultation", title,
                            f"{HYS}/have-your-say/initiatives/{int(x['id'])}-{slug}_en",
                            st.get("feedbackStartDate", "")[:10].replace("/", "-") or None,
                            f"{stage}, open for feedback until {until}. Topics: {', '.join(topics)}.",
                            f"{title}. {stage}, open for feedback until {until}. Topics: {', '.join(topics)}.",
                            stage=stage, until=until, topics=topics, reference=x.get("reference")))
        page += 1
        if page >= d.get("totalPages", 1):
            break
    STATUS["have_your_say"] = "ok"
    return out


def event_pages(edition: dt.date) -> list[dict]:
    """The event pages that the week's "Out this week" picks link to (bank: "out"), read from the
    venues' own sites so that check.py can verify each date, time and price against the page.
    Plain HTTP only: a venue that refuses scripts is recorded and its events cannot run."""
    bank = ROOT / "daily" / "bank" / f"{edition}.json"
    if not bank.exists():
        return []
    out_days = json.loads(bank.read_text("utf-8")).get("out", {})
    urls = {x["url"] for d in out_days.values() for x in d.get("items", []) + d.get("also", [])}
    out = []
    for url in sorted(urls):
        body = get("venues", url)
        if body is None:
            continue
        page = body.decode("utf-8", "replace")
        title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        page = re.sub(r"<(script|style|noscript|svg)\b.*?</\1>", " ", page, flags=re.S | re.I)
        out.append(item("venues", "out", "event", html.unescape(title.group(1)) if title else url, url, None,
                        "", html_to_text(page)[:60000], host=urllib.parse.urlparse(url).netloc))
    STATUS["venues"] = "ok" if out else STATUS.get("venues", "no event pages")
    return out


def indicator_data(ind_id: str) -> dict:
    """An Apprentix indicator, compacted for charts: the default breakdown only, every country's
    values by year. The values also go into the item's text, so check.py can find any number used."""
    path = ROOT / "data" / "published" / "indicators" / f"{ind_id}.json"
    if not path.exists():
        return {}
    d = json.loads(path.read_text("utf-8"))
    default = {x["key"]: x.get("default") for x in d.get("dims", [])}
    by: dict = {}
    for r in d.get("series", []):
        if all(r.get("dims", {}).get(k) == v for k, v in default.items() if v is not None) and r.get("value") is not None:
            by.setdefault(r["geo"], {})[str(r["time"])] = r["value"]
    return {"unit": d.get("unit"), "values": by, "target": d.get("target"),
            "source_url": (d.get("provenance") or {}).get("source_url")}


def apprentix() -> list[dict]:
    """Apprentix's own published analyses of Cedefop, Eurostat and national data.
    Read from the repository, not the web: they are rebuilt weekly by pipeline/build.py."""
    pub = ROOT / "data" / "published"
    rd = lambda p: json.loads((pub / p).read_text("utf-8"))
    out = []
    for f in rd("facts/facts.json")["items"]:
        out.append(item("apprentix", "data", "fact", f["text"], SITE + f["link"] + "#fact-" + f["id"],
                        None, f["text"], f["text"], fact_id=f["id"], highlight=f["highlight"],
                        countries=f["countries"], publisher=f["source"], weight=f["weight"]))
    for i in rd("insights/insights.json")["items"]:
        text = " ".join([i["finding"], *i.get("detail", [])])
        out.append(item("apprentix", "data", "insight", i["title"], f"{SITE}pages/insights.html#{i['id']}",
                        None, i["finding"], text, insight_id=i["id"]))
    for sid, p in rd("portraits/portraits.json")["portraits"].items():
        out.append(item("apprentix", "data", "portrait", f"{p['name']} ({p['country']})",
                        f"{SITE}pages/countries/{ {'GR': 'el'}.get(p['country_code'], p['country_code'].lower()) }.html#scheme-{sid}", None,
                        " ".join(p["story"]), " ".join(p["story"]), scheme=sid,
                        country_code=p["country_code"], html=p["html"], facts=p["facts"],
                        publisher="Cedefop’s European database on apprenticeship schemes"))
    for m in rd("myths/myths.json")["items"]:
        out.append(item("apprentix", "data", "myth", m["statement"], f"{SITE}pages/myths.html#{m['id']}",
                        None, m["answer"], f"{m['answer']} {m.get('detail', '')}", verdict=m["verdict"],
                        publisher=m["source"]))
    pulse = rd("pulse/pulse.json")
    for kind, rows in pulse["items"].items():
        for r in rows:
            out.append(item("apprentix", "data", "policy", r["title"], SITE + r["link"], None,
                            f"{r['country']} · {r['type']} · {kind} in {pulse['year']}",
                            country=r["country"], country_code=r["country_code"], flag=r["flag"],
                            change=kind, year=pulse["year"],
                            publisher=pulse["source"]["name"] if isinstance(pulse["source"], dict) else pulse["source"]))
    meta = rd("regional-skills-ecosystems/meta.json")
    regions = [{k: r[k] for k in ("nuts2", "region", "country_code", "reset", "eu_rank", "country_rank",
                                   "s_SkillSupply", "s_SkillDemand", "s_SkillMatch", "s_SkillEnvironment")}
               for r in rd("regional-skills-ecosystems/records.json")]
    out.append(item("apprentix", "data", "dataset", meta["title"],
                    f"{SITE}pages/explore.html?dataset=regional-skills-ecosystems", meta["source"]["retrieved"],
                    meta["description"], meta["description"] + " " + meta["source"].get("caveat", ""),
                    regions=regions, citation=meta["source"].get("citation"),
                    licence=meta["source"].get("licence_id")))
    for ind in rd("indicators/index.json")["indicators"]:
        data = indicator_data(ind["id"])
        values = " ".join(f"{g} {y}: {v};" for g, ys in sorted(data.get("values", {}).items()) for y, v in sorted(ys.items()))
        out.append(item("apprentix", "data", "indicator", ind["title"],
                        f"{SITE}pages/indicators.html?id={ind['id']}", None, ind.get("description", "")[:400],
                        ind.get("description", "") + " " + values,
                        indicator=ind["id"], publisher=(ind.get("provenance") or {}).get("publisher"),
                        unit=data.get("unit"), values=data.get("values"), target=data.get("target"),
                        source_url=data.get("source_url")))
    for meta_path in sorted(pub.glob("*/meta.json")):
        src = json.loads(meta_path.read_text("utf-8")).get("source") or {}
        if src.get("url"):
            out.append(item("apprentix", "data", "source_page", src.get("name") or src["url"], src["url"], None))
    duel = rd("duel/countries.json")
    codes = sorted(duel.get("countries", duel).keys()) if isinstance(duel, dict) else []
    out.append(item("apprentix", "data", "tool", "Country vs country", f"{SITE}pages/duel.html",
                    None, "Compare two countries' schemes, outcomes, money and mobility side by side.",
                    countries=codes))
    for page, title in [("compare.html", "Compare all apprenticeship schemes side by side"),
                        ("play.html", "Higher or lower?"), ("find.html", "Find my apprenticeship")]:
        out.append(item("apprentix", "data", "tool", title, SITE + "pages/" + page, None))
    STATUS["apprentix"] = "ok"
    return out


# ------------------------------------------------------------------- main --

def next_working_day(d: dt.date) -> dt.date:
    d += dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def retag(edition: dt.date) -> int:
    """Re-apply topics.json to an existing pool without fetching again."""
    path = POOL / f"{edition}.json"
    pool = json.loads(path.read_text("utf-8"))
    for i in pool["items"]:
        i["work_areas"], i["policy_hooks"] = tag(i["title"], i["summary"], i["text"][:6000])
    write_json(path, pool)
    print(f"Re-tagged {path.relative_to(ROOT)}: {sum(1 for i in pool['items'] if i['work_areas'])} items with a work area")
    return 0


# The forecast for the paper's top row: Open-Meteo (open data, CC BY 4.0, no key).
CITIES = [("Thessaloniki", 40.64, 22.94, "Europe/Athens"), ("Brussels", 50.85, 4.35, "Europe/Brussels")]
WMO = [((0,), "sunny"), ((1,), "mostly sunny"), ((2,), "partly cloudy"), ((3,), "cloudy"), ((45, 48), "fog"),
       (range(51, 58), "drizzle"), (range(61, 68), "rain"), (range(71, 78), "snow"), (range(80, 83), "showers"),
       ((85, 86), "snow showers"), (range(95, 100), "thunderstorms")]


def weather(edition: dt.date) -> int:
    """Forecast for the edition's week, written to daily/weather/<edition>.json (committed)."""
    days = {}
    for city, lat, lon, tz in CITIES:
        d = json.loads(fetch("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "timezone": tz, "start_date": edition.isoformat(),
            "end_date": (edition + dt.timedelta(days=4)).isoformat(),
            "daily": "weather_code,temperature_2m_max,temperature_2m_min"}))["daily"]
        for date, code, hi, lo in zip(d["time"], d["weather_code"], d["temperature_2m_max"], d["temperature_2m_min"]):
            sky = next((w for codes, w in WMO if code in codes), "")
            days.setdefault(date, []).append({"city": city, "max": round(hi), "min": round(lo), "sky": sky})
    path = ROOT / "daily" / "weather" / f"{edition}.json"
    write_json(path, {"source": "Open-Meteo", "url": "https://open-meteo.com/", "fetched_at":
                      dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "days": days})
    print(f"Wrote {path.relative_to(ROOT)}: forecast for {len(days)} days")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("-")]
    edition = dt.date.fromisoformat(args[0]) if args else next_working_day(dt.date.today())
    if "--retag" in argv:
        return retag(edition)
    if "--weather" in argv:
        return weather(edition)
    only = next((a.split("=", 1)[1] if "=" in a else argv[argv.index(a) + 1] for a in argv if a.startswith("--only")), "")
    end = min(edition, dt.date.today())
    start = end - dt.timedelta(days=WINDOW_DAYS)
    print(f"Cedefop Daily pool for {edition} (news from {start} to {end})")
    items: list[dict] = []
    for name, fn in [("Cedefop RSS", lambda: cedefop_rss(start, end)),
                     ("Cellar, recent", lambda: cellar_recent(start - dt.timedelta(days=WINDOW_DAYS), end)),
                     ("Cellar, archive", lambda: cellar_archive(edition)),
                     ("OpenAlex", lambda: openalex(edition)),
                     ("Commission", lambda: ec_presscorner(start, end)),
                     ("Council", lambda: council(start, end)),
                     ("Parliament", lambda: parliament(start, end)),
                     ("EUR-Lex", lambda: eurlex(start, end)),
                     ("EU-OSHA", lambda: euosha(start, end)),
                     ("Agency listings", lambda: listings(start, end)),
                     ("Eurostat", lambda: eurostat(start, end)),
                     ("Press and the field", lambda: press(edition)),
                     ("Consultations", consultations),
                     ("Events", lambda: event_pages(edition)),
                     ("Apprentix", apprentix)]:
        if only and name.lower().replace(" ", "_").split(",")[0] not in only.lower().split(","):
            continue
        try:
            got = fn()
        except Exception as e:      # one broken source must not stop the others
            print(f"- {name}: failed ({e!r})")
            STATUS[name] = f"failed: {e!r}"
            continue
        print(f"- {name}: {len(got)} items")
        items += got
    seen, pool = set(), []
    for i in items:
        if i["id"] not in seen:
            seen.add(i["id"])
            pool.append(i)
    out = {"edition": edition.isoformat(), "fetched_at": dt.datetime.now(dt.timezone.utc)
           .replace(microsecond=0).isoformat(), "window": [start.isoformat(), end.isoformat()],
           "sources": STATUS, "count": len(pool), "items": pool}
    path = POOL / f"{edition}.json"
    if path.exists():
        # An edition's pool only grows: feeds roll over (the Official Journal keeps 100 items),
        # and a story already written must keep its source. Fresh copies replace old ones.
        old = json.loads(path.read_text("utf-8"))
        kept = [i for i in old["items"] if i["id"] not in seen]
        pool += kept
        out.update(count=len(pool), items=pool, carried_over=len(kept), sources={**old["sources"], **STATUS})
        if only:
            out.update(fetched_at=old["fetched_at"], window=old["window"])
    write_json(path, out)
    print(f"Wrote {path.relative_to(ROOT)}: {len(pool)} items; "
          f"{sum(1 for i in pool if i['work_areas'])} tagged with a work area")
    try:
        if not only or "weather" in only:
            weather(edition)
    except Exception as e:
        print(f"- Weather: failed ({e!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
