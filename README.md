# Apprentix.eu

European apprenticeship and VET data, made searchable.

An independent, non-commercial project that takes publicly available European data on
apprenticeship and vocational education and republishes it in a form you can search,
filter and compare — rather than read one page at a time.

**Not affiliated with, or endorsed by, any European institution or agency.**
Every record links back to its official source, which remains authoritative.

---

## How this site is built

Deliberately plain:

- **No build step.** No npm, no bundler, no framework. Plain HTML, CSS and JavaScript.
- **No server.** Everything is static files, so it runs on GitHub Pages for free.
- **No accounts, no database, no tracking.**
- **Data-driven.** Adding a dataset means adding two JSON files — not writing code.
- **Data refreshed by a pipeline, not by the site.** A small Python pipeline (`pipeline/`)
  fetches public sources on a schedule in GitHub Actions and writes plain JSON/CSV.
  Every change arrives as a pull request you review. The site itself still has no build step.

The only external request is the Google Fonts stylesheet — plus, on the optional *Ask* page,
the question sent to the assistant's Worker (see "Ask Apprentix" below).

---

## Previewing it locally

The site uses JavaScript modules and `fetch()`, which browsers block when you open a
page straight from disk. **Double-clicking `index.html` will not work.** You need a
local web server. There is one included, requiring no installation:

```powershell
pwsh -File scripts/serve.ps1
```

Then open <http://localhost:8080>. Press `Ctrl+C` in the terminal to stop it.

No PowerShell? Any static server works, e.g. `python3 -m http.server 8080`.

If port 8080 is busy: `pwsh -File scripts/serve.ps1 -Port 8081`

(If you use VS Code, the *Live Server* extension does the same job — right-click
`index.html` → "Open with Live Server".)

---

## Repository layout

```
apprentix.eu/
├─ index.html                     Landing page: datasets, indicators
├─ pages/
│  ├─ countries/, indicators/, datasets/   generated static pages (do not edit)
│  ├─ explore.html                The explorer — works for ANY record dataset
│  ├─ indicators.html             EU targets + every statistical indicator
│  ├─ ask.html                    Ask Apprentix (AI assistant; see below)
│  ├─ about.html
│  └─ data.html                   Source catalogue, licensing, caveats
├─ assets/
│  ├─ css/site.css                All styling, light + dark (incl. chart colours)
│  ├─ js/data.js                  Loading, filtering, helpers
│  ├─ js/explore.js               The explorer UI
│  ├─ js/indicators.js            The indicators UI
│  └─ js/charts.js                Dependency-free SVG charts (map, bars, lines)
├─ data/
│  ├─ datasets.json               Site config + which datasets exist
│  ├─ sources.json                Catalogue of every upstream source (generated)
│  ├─ reference/countries.json    Country codes, names, tile-map positions
│  ├─ schemas/                    JSON Schemas the validator enforces
│  ├─ raw/                        ← ORIGINAL FILES, dated (by you or the pipeline)
│  ├─ ai/                         search index for Ask Apprentix (generated)
│  └─ published/                  ← what the site actually reads
│     ├─ apprenticeship-schemes/  meta.json + records.json (hand-curated)
│     ├─ vet-policy-timeline/     meta.json + records.json (from Cedefop)
│     └─ indicators/              <id>.json + <id>.csv, index.json
├─ pipeline/                      Python: one connector per source, build, validate
├─ worker/                        Cloudflare Worker behind Ask Apprentix (deployed with wrangler)
├─ .github/workflows/             weekly refresh (opens a PR) + validation
├─ datapackage.json               Frictionless description of all published data
├─ CITATION.cff                   How to cite
├─ scripts/
│  ├─ serve.ps1                   local preview server
│  ├─ csv-to-json.ps1             spreadsheet  -> records.json
│  └─ docx-extract.ps1            Word files   -> CSV or records.json
├─ .nojekyll                      stops GitHub Pages hiding files
└─ CNAME                          custom domain (apprentix.eu)
```

### raw vs published

- **`data/raw/`** is your working area. Put the original spreadsheets, exports and
  downloads here, exactly as you got them. Nothing here is read by the website — it is
  kept so the origin of every figure can be traced.
- **`data/published/`** is what the site loads. Clean, consistent JSON.

Keeping the two apart means you can always show where a number came from.

---

## The data pipeline

```
python3 -m pip install -r pipeline/requirements.txt
python3 -m pipeline.run --list          # all connectors
python3 -m pipeline.run                 # run everything, then rebuild indexes
python3 -m pipeline.run eurostat        # just one source
python3 -m pipeline.run --build-only    # rebuild indexes after a hand edit
python3 -m pipeline.validate            # check everything against data/schemas/
```

- **One file per source** in `pipeline/sources/` (a `SOURCE` description and a `run()`).
  Adding a file is enough; it is picked up automatically. `pipeline/sources/_catalogue.py`
  lists sources that are tracked but cannot be automated, and why.
- **Statistics** are written to `data/published/indicators/<id>.json` (with provenance:
  publisher, dataset code, licence, citation, retrieval time, SHA-256 of the original) plus a
  CSV twin. The Indicators page (`pages/indicators.html`) draws every one of them — map,
  ranking, trend, table — with no indicator-specific code.
- **Originals** go to `data/raw/<source>/<date>-<name>`. A new dated copy is kept only when
  the content changes. Very large files (Erasmus+) are hashed, not stored.
- **Build outputs**: `data/published/indicators/index.json`, `data/sources.json` (the source
  catalogue shown on *Data & sources*), record counts in `data/datasets.json`, and
  `datapackage.json` (Frictionless Data Package describing everything published).

### Automation (GitHub Actions)

- `.github/workflows/ingest.yml` runs every Monday (and on demand from the Actions tab),
  then opens a **pull request** titled "Data refresh". Review the diff, merge, and the site
  updates. The git history of `data/` is the changelog.
  *One-time setup:* Settings → Actions → General → allow GitHub Actions to create pull requests.
- `.github/workflows/validate.yml` checks every push/PR against `data/schemas/`.
- Optional API keys go in Settings → Secrets → Actions (e.g. `DESTATIS_TOKEN`); connectors
  that need a missing key are skipped, not failed.

### Keeping up with the sources (source watch)

The weekly refresh keeps every **known** dataset current by itself. After it,
`python -m pipeline.watch` looks for what needs a person, and the workflow keeps **one GitHub
issue** labelled `source-watch` up to date (you get an email; it closes itself when nothing is left):

| Check | Catches |
|---|---|
| Cedefop's catalogue on data.europa.eu | a **new Cedefop dataset**, or a revised one |
| Eurostat's table of contents | a **new Eurostat table** about VET, apprenticeship or work-based learning |
| Connector warnings and failures | a refused download where a stored (possibly old) copy was used |
| Release cycles | a source past its usual release date, e.g. a new KIVET file under a new name, or the yearly check of the hand-curated fiches |
| data.europa.eu catalogue | apprenticeship datasets newly published on national portals (candidates for connectors) |

After handling an item (or deciding to ignore it), run `python -m pipeline.watch --ack` and commit
`data/watch/known.json`. That records what has been reviewed and snoozes "probably out" reminders
for 3 months; they clear for good once the connector holds the newer release. The current report
is in `data/watch/report.json`.

### Country pages, comparison matrix, sitemap

`pipeline/render_pages.py` runs at the end of every build and writes one static, crawlable
page per country (`pages/countries/<code>.html`: schemes, key figures against the EU-27,
national statistics, recent policies, open datasets) plus `sitemap.xml`. Do not edit those
files by hand — change the renderer. `pages/compare.html` is the scheme comparison matrix,
driven by `meta.matrix` in the apprenticeship-schemes `meta.json`.

`pipeline/render_datasets.py` (called by the same step) makes everything citable and findable:

- `pages/indicators/<id>.html` — one static page per indicator (definition, what is counted,
  latest value per country, publisher, licence, citation, CSV/JSON downloads, link to the
  interactive view) and `pages/indicators/index.html` listing them by topic;
- `pages/datasets/<id>.html` — one page per record dataset in `data/datasets.json` (description,
  fields, licence, record count, download);
- schema.org **Dataset** JSON-LD on each of those pages, and a **DataCatalog** block in
  `pages/data.html` (between the `apprentix:catalog` markers — do not edit inside them);
- `data/feed.xml` — an Atom feed with one entry per indicator or dataset whose data changed
  (dated by the retrieval date, which only moves when the data does). Linked from every page.

### Cedefop scheme fiches (browser-assisted curation)

Each fiche answers the same questionnaire; 34 questions are multiple choice. To refresh them
after a new Cedefop update round:

1. In a normal browser, open Cedefop's scheme-fiche list, paste
   `pipeline/curate/fiche_extract.js` into the developer console, and wait.
2. Save the `A|` lines as `data/raw/cedefop-schemes/<date>-fiche-answers.txt`
   (copy the `META|` lines from the previous file).
3. Run `python -m pipeline.curate.merge_fiches`, then `python -m pipeline.run --build-only`.

Option labels live in `pipeline/curate/scheme_questions.py`; the merge stops if a fiche uses
an option that file does not know, so a changed questionnaire is never silently mis-read.

### Other hand-curated Cedefop databases

Read in a browser (Cedefop refuses scripts), saved under `data/raw/`, then built by a script:

| Dataset | Raw file | Build |
|---|---|---|
| Financing instruments (2016–17) | `data/raw/cedefop-financing/<date>-instruments.jsonl` | `python -m pipeline.curate.financing_instruments` |
| Qualification levels (NQF tool 2024) | `data/raw/cedefop-nqf/<date>-level-tables.txt` | `python -m pipeline.curate.nqf_levels` |
| VET systems (VET in Europe) | `data/raw/cedefop-vet-in-europe/<date>-systems.txt` | `python -m pipeline.curate.vet_systems` |
| Recognition of foreign VET qualifications | the Cedefop PDF in `data/raw/cedefop/` | `python -m pipeline.curate.recognition_pdf` (needs `pdfplumber`) |

Each script documents its raw format at the top. Then run `python -m pipeline.run --build-only`.

### Cedefop

Cedefop's web pages refuse automated requests, but its **Datasets** downloads (`/files/…xlsx`)
work. If a download is refused, put the file in `data/raw/cedefop/` (with the date prefix) and
the pipeline uses the latest copy. File names change per release: update the URL in
`pipeline/sources/cedefop_files.py`. The apprenticeship-schemes fiches remain hand-curated.

### Citing and DOIs

`CITATION.cff` tells GitHub how to cite the project. To mint a DOI for each release, log in to
[Zenodo](https://zenodo.org) with GitHub, enable this repository, then publish a GitHub
release; Zenodo archives it and issues a DOI.

---

## Adding a dataset

Three steps. No code.

**1. Create a folder** under `data/published/`, e.g. `data/published/financing/`.

**2. Add `records.json`** — an array of objects, one per record. Every record needs a
unique `id`:

```json
[
  { "id": "at-01", "country": "Austria", "name_en": "…", "compensation": "Wage" },
  { "id": "be-01", "country": "Belgium", "name_en": "…", "compensation": "Allowance" }
]
```

A field may hold a **list** where more than one answer applies —
`"compensation": ["Wage", "Allowance"]` — and filtering handles it correctly.

**3. Add `meta.json`** describing the fields. This is what drives the whole interface:
which filters appear, what the cards show, how the detail panel is laid out.

```jsonc
{
  "id": "financing",
  "title": "Financing apprenticeships",
  "tagline": "One line shown under the title.",
  "recordLabel": { "one": "arrangement", "many": "arrangements" },
  "source": {
    "name": "Cedefop — Financing apprenticeships database",
    "url": "https://…",
    "retrieved": "2026-09",
    "caveat": "How the data was obtained and what it can and cannot be used for."
  },
  "display": {
    "title": "name_en",        // headline on each card
    "subtitle": "name_original",
    "group": "country",        // small label above the title
    "badge": "flag",
    "link": "source_url",
    "summary": "overview",     // paragraph in the detail panel
    "facts": ["duration", "workplace_time", "compensation"]   // chips on the card
  },
  "fields": [
    { "key": "country",      "label": "Country",      "type": "category", "facet": true },
    { "key": "compensation", "label": "Compensation", "type": "category", "facet": true,
      "order": ["Wage", "Allowance", "Mostly unpaid"] },
    { "key": "duration",     "label": "Duration",     "type": "text" },
    { "key": "overview",     "label": "Overview",     "type": "longtext" },
    { "key": "source_url",   "label": "Official source", "type": "link" },
    { "key": "id",           "label": "Identifier",   "type": "hidden" }
  ],
  "sections": [
    { "title": "At a glance", "fields": ["country", "duration"] },
    { "title": "Money",       "fields": ["compensation"] }
  ]
}
```

**Field types:** `category` (add `"facet": true` to make it a filter, `"order"` to fix
the order of values) · `text` · `longtext` · `title` · `subtitle` · `link` · `hidden`.

**4. Register it** in `data/datasets.json` under `"datasets"`.

That's all. The explorer picks it up automatically.

---

## Getting data out of the originals

### From a spreadsheet

```powershell
pwsh -File scripts/csv-to-json.ps1 -In data/raw/financing.csv -Out data/published/financing/records.json
```

It prints the columns it found, so you can write `meta.json` against them.
For Excel, save the sheet as **CSV UTF-8** first.

Useful options:

- `-IdColumn name` — which column holds the unique id (default: the first)
- `-Split "level,compensation"` — columns holding **several** values, separated by `;` or `|`

### From Word documents

`docx-extract.ps1` reads `.docx` files directly — no Word, no installation. Point it at
a single file **or a whole folder**.

**Always start by looking:**

```powershell
pwsh -File scripts/docx-extract.ps1 -In data/raw/fiches
```

It reports, per document, how many tables there are, their column headers, and the
heading structure. That tells you which of the two routes below you need.

**If the data sits in tables:**

```powershell
pwsh -File scripts/docx-extract.ps1 -In data/raw/fiches -Mode tables -Out data/raw/tables
pwsh -File scripts/csv-to-json.ps1  -In data/raw/tables/table-1.csv -Out data/published/mine/records.json
```

**If each document is itself one record** — headings are the fields, the text beneath
each heading is the value (the usual shape for country or scheme fiches):

```powershell
pwsh -File scripts/docx-extract.ps1 -In data/raw/fiches -Mode qa -Out data/published/mine/records.json
```

One document becomes one record; the filename becomes the `id`. At the end it prints
every field key found across all the documents, ready to paste into `meta.json`.

Documents don't have to be identical — if a heading is missing from one file, that
field is simply absent from that record, and the site copes.

**If a document has no styled headings** (bold text used instead of Heading 1/2), the
inspect step will say so. Use `-Mode text` to dump the whole outline to JSON and work
from there.

---

## Ask Apprentix (AI assistant)

`pages/ask.html` lets visitors ask questions in plain language ("Which countries pay apprentices
a wage and require at least half the time at the workplace?"). Answers are written by an AI model
**only from Apprentix's own published data**, and link to the Apprentix pages and the original
publishers they used.

### How it works

```
browser (pages/ask.html, assets/js/ask.js)
   │  POST {messages}            ← URL from data/datasets.json  site.ask_endpoint
   ▼
Cloudflare Worker  worker/src/index.js      holds OPENROUTER_API_KEY (secret)
   │  tool-calling loop (max 5 rounds) ──► OpenRouter ──► x-ai/grok-4.3
   │  tools run inside the Worker, reading the site's static JSON:
   │    search_site    BM25 over data/ai/search-index.json
   │    get_country    a country's profile chunk (+ NQF levels)
   │    get_indicator  data/published/indicators/<id>.json (values + provenance)
   │    query_records  data/published/<dataset>/records.json (filters, text, count_by)
   │    list_datasets  data/datasets.json + indicator index
   ▼
{answer (markdown), sources [{title, url}], model, usage}
```

- **The key never reaches the browser.** It lives only as a Worker secret. Nothing in the repo
  contains it; `worker/.dev.vars` (local testing) is git-ignored.
- **Retrieval index.** `pipeline/build_ai_index.py` runs at the end of every build and writes
  `data/ai/search-index.json` (~2 MB, ~1,700 text chunks: country profiles, every indicator with
  its latest values, datasets, schemes with Cedefop's coded answers, financing instruments,
  recognition arrangements, VET policies, NQF levels, CoVE projects, insights) plus slim
  per-country shards of the 24,768 Europass qualifications in `data/ai/records/vet-qualifications/`
  (the full file is too large to load inside a Worker). Do not edit these files by hand.
- **Grounding.** The system prompt (in `worker/src/index.js`) tells the model to answer only from
  tool results, cite Apprentix URLs and publishers, say when the data does not cover a question,
  respect comparability caveats (national counts are not comparable; ED3SW is a proxy, not an
  apprentice count; financing data is 2016–17), give no legal/financial advice, point learners and
  employers to official services, and answer in the user's language.

### Privacy

- The page warns, above the input, that questions are sent to OpenRouter and xAI and that no
  personal data should be entered. The conversation is kept in the page's memory only — no
  cookies, no local storage; it disappears when the page is closed.
- The Worker logs nothing about questions or visitors (on error it logs only the HTTP status
  class; Workers observability is disabled in `wrangler.toml`). The rate limiter is keyed on the
  visitor's IP inside Cloudflare's rate-limiting counter, which is not stored by Apprentix.
- The browser sends no cookies to the Worker (`credentials: 'omit'`). Only the origins listed in
  `ALLOWED_ORIGINS` are accepted.
- Optional: set `DATA_COLLECTION = "deny"` in `wrangler.toml` to make OpenRouter route only to
  providers that do not retain or train on prompts (requests fail if the model has none). Also
  check your OpenRouter account's privacy settings.

### Cost controls

| Control | Where | Default |
|---|---|---|
| Per-IP rate limit (Workers Rate Limiting API) | `[[ratelimits]]` in `wrangler.toml` | 10 questions / minute |
| Daily request cap (all visitors) | `DAILY_LIMIT` var, counted in KV | 1,000 / day |
| Daily token cap | `DAILY_TOKEN_LIMIT` var | 3,000,000 tokens / day |
| Reply length | `MAX_TOKENS` var | 1,200 tokens |
| Tool rounds per question | `MAX_ROUNDS` in `src/index.js` | 5 (then the model must answer) |
| Conversation sent | `src/index.js` | last 8 messages, ≤ 2,000 characters each |
| Tool output passed to the model | `src/index.js` | ≤ 12,000 characters per tool call |

The KV counter is a soft cap (KV is eventually consistent; one write per question). As a hard
backstop, **set a credit limit on the OpenRouter key** itself (openrouter.ai → Keys → limit).

**Workers plan.** Loading and indexing the 2 MB search index takes roughly 200 ms of CPU the first
time an isolate handles a question (then it is cached in memory). The Workers **Free** plan allows
10 ms of CPU per request, so cold starts can fail there; the **Workers Paid** plan ($5/month,
30 s CPU) is recommended. KV on the free tier allows 1,000 writes/day, which matches the default
daily cap.

### Deploy (once)

You need Node.js 18+ and a Cloudflare account (apprentix.eu is already on Cloudflare).

```sh
cd worker
npx wrangler login
npx wrangler kv namespace create BUDGET
#   → copy the printed id into wrangler.toml, replacing REPLACE_WITH_KV_NAMESPACE_ID
npx wrangler secret put OPENROUTER_API_KEY
#   → paste the OpenRouter key when prompted (it is stored encrypted at Cloudflare, not in the repo)
npx wrangler deploy
#   → prints the Worker URL, e.g. https://apprentix-ask.<your-subdomain>.workers.dev
```

Then switch the page on: in `data/datasets.json` set

```json
"site": { …, "ask_endpoint": "https://apprentix-ask.<your-subdomain>.workers.dev/ask" }
```

commit and push. (`null` shows "The assistant isn't switched on yet." and disables the input —
setting it back to `null` is the off switch for the page; `npx wrangler delete` removes the Worker.)

**workers.dev URL or a route on apprentix.eu?** The `workers.dev` URL is the simplest and works
whatever the DNS setup: the browser makes a cross-origin request, which the Worker allows only for
`ALLOWED_ORIGINS`. Alternatively, serve it at `https://apprentix.eu/api/ask` (uncomment `routes` in
`wrangler.toml`; the Worker answers on `/ask` and `/api/ask`). That keeps everything on one
domain (no CORS, less likely to be blocked by privacy extensions), but **only works if the
apprentix.eu DNS record pointing at GitHub Pages is proxied through Cloudflare** (orange cloud),
with SSL/TLS mode "Full". With DNS-only (grey cloud) records, which is GitHub Pages' default
recommendation, Cloudflare never sees the traffic and the route does nothing — use workers.dev.

### Change the model or limits

Edit `[vars]` in `worker/wrangler.toml` (`MODEL` takes any OpenRouter model id that supports tool
calling) and run `npx wrangler deploy` again. Secrets are kept across deploys.

### Test

```sh
node --test worker/test         # BM25, tools (mocked fetch), CORS/limits, full loop (mocked OpenRouter)
cd worker && npx wrangler deploy --dry-run   # bundle check, no upload
```

Local end-to-end: put `OPENROUTER_API_KEY=…` in `worker/.dev.vars` (git-ignored), run
`npx wrangler dev` in `worker/`, serve the site on port 8080, and temporarily set
`ask_endpoint` to `http://localhost:8787/ask`. The local Worker still reads data from
`SITE_BASE` (the live site); run `npx wrangler dev --var SITE_BASE:http://localhost:8080` to use your
local build instead.

---

## Publishing to GitHub Pages

1. Create a repository on GitHub and push this folder to it.
2. Repository **Settings → Pages → Source: Deploy from a branch**, branch `main`, folder `/ (root)`.
3. For the custom domain, keep the `CNAME` file and point your DNS at GitHub Pages.

Without a custom domain the site lives at `https://<username>.github.io/apprentix.eu/`.
All paths in the code are relative, so both work with no changes.

---

## Before publishing data — read this

The starting dataset was read from published scheme fiches and condensed. **It has not
been checked against the source records.** Before this site is public:

- spot-check records against the official fiches;
- confirm the reuse conditions of every source and record them in `pages/data.html`;
- keep the independent-project notice visible on every page.

---

## Licence

Code: MIT (see `LICENSE`).
Data: belongs to its original publishers — see `pages/data.html`. It is not covered by
the MIT licence and its reuse conditions must be checked per source.
