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

The only external request is the Google Fonts stylesheet.

---

## Previewing it locally

The site uses JavaScript modules and `fetch()`, which browsers block when you open a
page straight from disk. **Double-clicking `index.html` will not work.** You need a
local web server. There is one included, requiring no installation:

```powershell
pwsh -File scripts/serve.ps1
```

Then open <http://localhost:8080>. Press `Ctrl+C` in the terminal to stop it.

If port 8080 is busy: `pwsh -File scripts/serve.ps1 -Port 8081`

(If you use VS Code, the *Live Server* extension does the same job — right-click
`index.html` → "Open with Live Server".)

---

## Repository layout

```
apprentix.eu/
├─ index.html                     Landing page: lists the datasets
├─ pages/
│  ├─ explore.html                The explorer — works for ANY dataset
│  ├─ about.html
│  └─ data.html                   Sources, licensing, caveats
├─ assets/
│  ├─ css/site.css                All styling, light + dark
│  ├─ js/data.js                  Loading, filtering, helpers
│  ├─ js/explore.js               The explorer UI
│  └─ img/
├─ data/
│  ├─ datasets.json               Site config + which datasets exist
│  ├─ raw/                        ← YOU DUMP ORIGINAL FILES HERE
│  └─ published/                  ← what the site actually reads
│     └─ apprenticeship-schemes/
│        ├─ meta.json             describes the fields
│        └─ records.json          the records
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
