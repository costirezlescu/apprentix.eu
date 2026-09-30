# Raw data

Put original files here **exactly as you obtained them** — spreadsheets, CSV exports,
downloads, saved pages. Do not tidy them.

Nothing in this folder is read by the website. It exists so that every figure on the
site can be traced back to where it came from.

Suggested convention, one folder per source:

    data/raw/apprenticeship-schemes/2026-09-cedefop-fiches.csv
    data/raw/financing/2026-09-financing-export.xlsx

Include the retrieval date in the filename. When you refresh a dataset, add the new
file rather than overwriting the old one.

To turn a CSV into site data:

    pwsh -File scripts/csv-to-json.ps1 -In data/raw/<file>.csv -Out data/published/<dataset>/records.json

**Before committing:** check that nothing here is confidential, personal, or
restricted by its publisher. If in doubt, uncomment `data/raw/` in `.gitignore`
so the originals stay on your machine only.
