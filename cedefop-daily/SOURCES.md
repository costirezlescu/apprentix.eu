# Sources

Tested from a script on **17 October 2026**. "Script" means a plain HTTP request with no browser, which is what a pipeline will do. The full list, with each status, is in `data/sources.csv`. Re-run `scripts/source_check.sh` before building.

## 1. What worked

| Source | Result | Use |
|---|---|---|
| **Cedefop RSS** `https://www.cedefop.europa.eu/en/rss.xml` | 200, 10 items | Circle 0. **Noisy**: a "recently changed" feed mixing news, newsletters, procurement notices, PDF attachments ("Q&A", "1. Application Form") and old pages re-saved (items from 2020 and 2021). Filter by URL path: keep `/en/news/`, `/en/publications/`, `/en/events/`, `/en/newsletters/`, `/en/press-releases/`; drop `/attachments/` and `/public-procurement/`. On 15 October it carried "Cedefop newsletter no 167" and "Regional skills ecosystems index (RESET)". |
| **European Commission press corner RSS** `…/presscorner/api/rss?language=en` | 200, 10 latest items | Circle 2. Everything the Commission publishes, so filter with `topics.yaml`. On 16 October it included a statement by Executive Vice-President Mînzatu. |
| **Council press releases RSS** `consilium.europa.eu/en/rss/pressreleases.ashx` | 200, 20 items | Circle 2 (EPSCO and EYCS meetings, conclusions) |
| **European Parliament press RSS** `europarl.europa.eu/rss/doc/press-releases/en.xml` | 200, 20 items | Circle 2 (EMPL and CULT committees, plenary) |
| **EUR-Lex Official Journal L RSS** `eur-lex.europa.eu/EN/display-feed.rss?rssId=162` | 200, 100 items | Circle 2: adopted acts. Filter by keyword and EuroVoc. |
| **Publications Office SPARQL (Cellar)** `publications.europa.eu/webapi/rdf/sparql` | 200 | EU documents by subject, author (Cedefop publications are catalogued here), date |
| **Eurostat API** `ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}` | 200 JSON. `trng_lfse_01` = "Participation rate in education and training (last 4 weeks)", updated 10 September 2026 | The number; data stories |
| **Eurostat update RSS** `…/catalogue/rss/en/statistics-update.rss` | 200, 1,739 entries | Watch only the datasets on the watchlist (`data/eurostat_watchlist.csv`) |
| **ESCO API** `ec.europa.eu/esco/api/search` | 200 JSON | Occupation and skill names; tagging |
| **EU-OSHA RSS** `osha.europa.eu/en/rss.xml` | 200, 10 items | Circle 3 |
| **ETF news, ELA news, EIGE news, ILO news, UNESCO-UNEVOC news** | 200, HTML only | Circle 3. No feed found; parse the HTML or subscribe to their newsletters (see section 3) |
| **OpenAlex** (API key) | Works; see below | Circles 1 and 5 |

## 2. What failed

| Source | Result | What to do |
|---|---|---|
| **Cedefop HTML pages** (home, news, events, publications) | **403** to scripts (a bot check) | Ask Cedefop's web team for a feed or API (the site looks like Drupal, which can expose JSON). The new repo is for Cedefop staff, so this should be an internal request, not a workaround. Never get past bot checks. |
| **Eurofound news** | 429 (rate-limited) | Retry slowly, use its newsletter, or ask for a feed |
| **Europe Media Monitor (EMM) NewsBrief RSS** | 403 | Ask for institutional access, or use Cedefop's existing media monitoring |
| **OECD** | 403 | Newsletters; OECD's own data API for figures |
| **European Parliament Think Tank RSS** (the address tried) | 404 | Find the current feed address |
| **EPALE news** (the address tried) | 404 | Find the current address |
| **Crossref**: Cedefop publications under the Publications Office prefix 10.2801 | 0 results for "cedefop" in 2026 | Use Cellar or Cedefop's own list for Cedefop publications, not Crossref |

## 3. Incoming email

As with Daily Codes, many sources are easier to read by subscribing a dedicated inbox to their newsletters than by scraping:
- the sister agencies;
- the OECD;
- national VET agencies;
- conference organisers;
- **Cedefop's own newsletter** (no. 167, 15 October 2026).

The same rules apply:
- **Senders:** allowlisted only.
- **Fields:** every one must appear word for word in the email.
- **Duplicates:** merged.
- **Never published:** personal details from signatures, or meeting links.

## 4. OpenAlex: tested facts for Cedefop

- **Cedefop's institution:** `I4210130302`, ROR `03e5p9h20`. It has 246 works.
  - Some papers are wrongly attributed to it: on 17 October 2026, two Portuguese health papers.
  - Cedefop's own reports are mostly **not** in OpenAlex as Cedefop works. Recent ones appear as Zenodo uploads (conference papers and presentations, July 2026).
  - **Match by raw affiliation string**: `raw_affiliation_strings.search:cedefop` gives 11 works in 2026.
- **Research mentioning Cedefop:** `fulltext.search:cedefop` found **1,191 works in 2025**, about 23 a week. "Cedefop" is a single distinctive word, so the full-text search is precise, unlike the phrase searches in Daily Codes.
- **Research citing Cedefop:** `cites:` on Cedefop's 50 most-cited OpenAlex works found **19 published between 17 September and 17 October 2026**. Most citations to Cedefop reports aren't linked in OpenAlex, so the full-text search above is the better measure.
- **Most-cited Cedefop works in OpenAlex:**
  - *Skills mismatch: concepts, measurement and policy approaches* (2018, 322 citations);
  - a 2022 paper on twin transitions of decarbonisation and digitalisation (117; check that it really is Cedefop's);
  - *How useful is the concept of skills mismatch?* (2017, 115).
- **The `from_created_date` filter now needs a paid plan** (Member+ or Partner). The API returns "Plan upgrade required". Use `from_publication_date` and remove items already used. Some publication dates are in the future, for example 29 October 2026.
- **VET journals:** see `data/vet_journals.csv`.
  - Ten VET and adult-learning journals published **84 papers in the 30 days to 17 October 2026**.
  - Labour-economics journals add more and need topic filtering.
  - *Empirical Research in VET* returned only 284 works, so check whether it has a second source ID.

## 5. Not yet tested

- National sources: ministries, national VET agencies, ReferNet partners. Phase 4.
- The social partners' EU-level pages: BusinessEurope, ETUC, SGI Europe, SMEunited.
- Commission "Have your say" consultations API.
- Parliament's Legislative Observatory (OEIL).
- JRC publications.
- IZA discussion papers.
- WorldSkills Europe and EuroSkills.
- The European Alliance for Apprenticeships.
- Cedefop's internal calendar.
- Thessaloniki venues.
