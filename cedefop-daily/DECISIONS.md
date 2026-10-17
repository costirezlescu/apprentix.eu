# Cedefop Daily: decisions and status

*17 October 2026. Follows `OPEN_QUESTIONS.md`. The paper lives in the Apprentix repo and is served at apprentix.eu/daily.*

## Decisions on the open questions

| # | Question | Decision |
|---|---|---|
| 1 | Who owns it | **An independent publication on Apprentix**, not commissioned by Cedefop. It uses no Cedefop logo and carries the site-wide "Independent project" banner. The footer says it is not published or endorsed by Cedefop. There is **no "mock-up" label**: editions are numbered as real ones. |
| 2 | Who gets it | **Public but unlisted** at apprentix.eu/daily. Pages are `noindex, nofollow`, left out of `sitemap.xml`, and not linked from Apprentix's navigation or home page. Email distribution is not built. |
| 4 | Name and masthead | "Cedefop Daily", with "Thessaloniki · Brussels" under it, in Apprentix's type (Newsreader, Public Sans, IBM Plex Mono) |
| 5, 6 | Send time, calendar | Monday to Friday, with Monday's paper carrying the week ahead (to confirm with a holiday list). No email yet. |
| 7 | Where it runs | Outside Cedefop: static pages in this repo, deployed by Forge on push |
| 13 | AI transparency | The footer reads "Compiled from the linked public sources". `daily/about.html` says drafting uses software that includes a language model, without naming a model. "Reviewed by Communications" is left out, because it isn't true. |
| 16 | Languages | English |
| 17 | The Director | Public role only. No headline in No. 1; a quote in the lead story |
| 18 | Critical coverage | Sensitive topics fail the check and hold the edition (`check.py`) |
| 21, 22 | Personalisation, tracking | Neither. The Number's guess stays in `localStorage`. |
| 3, 8–12, 14, 15, 19, 20 | Editor, media monitoring, Cedefop feeds, calendar, staff news, DPO, AI service, taxonomy, Thessaloniki box, Greek Presidency | Open: they need Cedefop, or come in a later phase. With no internal calendar, the strip runs as "This week in numbers". There is no staff news. |

## Also decided

- **Apprentix features are built in.** These are the RESET data (chart in the lead), scheme portraits ("Meet the apprentices"), Country vs country links, Did you know?, Insights, Myth or fact? and the policy pulse from Cedefop's VET policy timeline. They enter the pool as `source: apprentix`, so the rule that every link comes from the data still holds.
- **Section colours (pillars):**

  | Section | Colour | Hex |
  |---|---|---|
  | At Cedefop | Apprentix teal | `#0f6b63` |
  | EU policy | blue | `#1f4f9e` |
  | Agencies | violet | `#6b3fa0` |
  | Countries | burnt orange | `#a8490f` |
  | Research | red | `#b3262f` |
  | Data | olive | `#56661a` |
  | People | magenta | `#a12f6d` |

  Each has a dark-mode variant (`daily/assets/daily.css`).
- **Pools are not committed** (about 1 MB a day). Each edition publishes `daily/<date>/sources.json` with the items it used.

## Beyond the Brussels bubble (decided 17 October 2026)

The first version read mostly from the top: institutions, agencies and Cedefop itself. Asked for: a paper that keeps staff at the edge of their field and shows **how things actually are on the ground**, plus the wider debate in international newspapers, magazines and popular science, especially how AI is changing work and skills.

- **From the field** (orange) leads the paper after At Cedefop. It draws on:
  - national and local press in the member states;
  - trade press, such as the Deutsche Handwerks Zeitung;
  - teachers' outlets (Café pédagogique, ESOS);
  - a school-students' union (OBESSU);
  - The Local's English editions;
  - UK further-education reporting.

  Stories are summarised in English and labelled "translated from …". Apprentix's portraits and policy pulse sit in this section too.
- **The wider debate** (slate, `#3e4f66`) covers international newspapers and magazines, AI and technology desks, popular science and economics columns (Social Europe, VoxEU).
- **"Also today"** is a row of four teasers under the lead, linking into the paper.
- **The source list is `pipeline/daily/press.json`.** It has 68 feeds, all tested with the pipeline's own user agent, and those that refused it are left out.
- **Relevance:** an item must touch education, training and skills directly, or AI together with work and jobs (`press_relevant`). It must also be from the last eight days.
- **Multilingual keywords** were added for DE, FR, ES, IT, NL, EL, DA, SV, FI, RO, PL and PT.
- **Copyright and privacy rules for press stories, enforced by `check.py`:**
  - stories are summarised in the paper's own words, with a link;
  - quotes from the press are at most 12 words;
  - subscription articles are marked;
  - private individuals are not named, and a possible personal name raises a warning.
- **Process fixes this round:**
  - links in an edition now name a pool item (`{"item": id}`), so the writer never types a URL. A first draft did type four press URLs from memory, and all four were wrong.
  - an edition's pool only grows: a refetch merges rather than replaces, because the Official Journal feed rolls over after 100 items.
  - the checker also verifies in-page anchors.

## How it works

```
python3 -m pipeline.daily.fetch 2026-10-19          # sources → daily/pool/2026-10-19.json (≈30 s)
python3 -m pipeline.daily.fetch 2026-10-19 --retag  # after editing pipeline/daily/topics.json
#   write daily/editions/2026-10-19.json            # the writing step: text only, items by id
python3 -m pipeline.daily.render 2026-10-19         # → daily/2026-10-19/, daily/index.html, archive, about
python3 -m pipeline.daily.check 2026-10-19          # exit 1 on any failure
```

- **Generated from data, never written:**
  - connection lines;
  - dates and source names;
  - strip numbers, counted by a rule stated in the edition;
  - charts;
  - the sources list.
- **`check.py` fails the edition when:**
  - an item or URL is not in the pool;
  - a number is not in the story's sources;
  - a quotation is not verbatim;
  - a story has no connection line;
  - it finds a banned word, a sensitive topic, a person in two headlines, or a past event in the diary.
- **`check.py` warns about:**
  - long headlines;
  - items past their use-by date;
  - the Director in a headline.
- **Tested** by injecting an invented number, quotation and URL. All three failed the check.

## Sources found on 17 October 2026 (beyond SOURCES.md)

- **Publications Office SPARQL** (`cdm:work_created_by_agent` = CEDEFOP) is the best source for **new Cedefop publications**, with dates and abstracts, and for **From the archive**.
- **Cedefop's newsletter** reaches the RSS feed **with its full text and links**. That covers the stories, the publications and the event agenda, which feeds the Diary.
- **The Commission press corner** has a public JSON document API that gives full texts: `/presscorner/api/documents?reference=STATEMENT/26/2188`.
- **Pages that refuse scripts:**
  - Council pages return 403, so only the feed's title and summary are used.
  - The **European Parliament press feed returns 202 with an empty body to any user agent that identifies itself**, but 200 to plain curl. It is left out, because getting past it would mean disguising the client. **Decide:** ask the Parliament, or accept a standard `Mozilla/5.0 (compatible; …)` user agent.
- **The EU-OSHA feed has empty titles.** The fetcher reads the article page's `<title>` instead.
- **Agency listings (ETF, ELA, EIGE, ILO) parse well** from `<time datetime>`. Article bodies come from the article pages.
- **Of 57 OpenAlex "full text cedefop" hits for 5–17 October, 15 are chapters of one Turkish book.** The hits also include Apprentix's own Zenodo record, which is excluded.

## Next

1. Automate the writing step. It needs an LLM API key in CI and the rules from BLUEPRINT §6 in the prompt. Fetch, check and render are already scripted.
2. A weekday GitHub Action that runs fetch, write, check and render, and commits only if the check passes. Like Apprentix's weekly refresh, the push deploys.
3. Press coverage to widen:
   - more member states (CZ, HU, SK, BG, HR, SI, PT, the Baltics);
   - more practitioner sources (EPALE, Education International, the European Apprentices Network, all of which refused scripts or have moved);
   - a weekly "voices" box with learners, teachers and employers, quoted from published reporting.
4. Have your say consultations. The API needs a `feedbackStatus` parameter.
5. The Parliament feed, as above. EPALE and the EP Think Tank need current addresses.
6. The use-by rules. The first edition warns about four items 13–19 days old (catch-up). Later editions should keep within the limits.
