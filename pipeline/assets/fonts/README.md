# Fonts for the social preview images (pipeline/og.py)

The same families the site loads from Google Fonts, bundled so the pipeline can draw
1200×630 PNG cards offline and deterministically. All are licensed under the
SIL Open Font License 1.1 (licence text next to each font, unmodified).

| File | Family | Licence | Source (github.com/google/fonts, `main` @ 9710da1) |
|---|---|---|---|
| `Newsreader-VF.ttf` | Newsreader (variable: wght, opsz) | `OFL-Newsreader.txt` | `ofl/newsreader/Newsreader[opsz,wght].ttf` |
| `PublicSans-VF.ttf` | Public Sans (variable: wght) | `OFL-PublicSans.txt` | `ofl/publicsans/PublicSans[wght].ttf` |
| `IBMPlexMono-Medium.ttf` | IBM Plex Mono Medium | `OFL-IBMPlexMono.txt` | `ofl/ibmplexmono/IBMPlexMono-Medium.ttf` |

The font files are byte-for-byte copies (only renamed); the variable fonts are
instanced at render time with Pillow (`set_variation_by_axes`), not modified.
