# Cedefop Daily

A daily newspaper for the people who work at **Cedefop**, the European Centre for the Development of Vocational Training. It covers what Cedefop works on: VET, apprenticeships, skills, qualifications, adult learning and the future of work. It also covers the EU institutions, sister agencies, member states, researchers and people relevant to that work, and news about colleagues where there is any.

This folder was prepared on 17 October 2026 in a Claude Code session that built **Daily Codes**, a daily newspaper for the UCL MSc in Cognitive and Decision Sciences, and then the Testable Weekly handover. It holds everything that carries over. Move it into the new repo and start a fresh session from here.

## What's here

| File | What it is |
|---|---|
| `BRIEF.md` | The request as given, organised, plus the decisions carried over from Daily Codes |
| `BLUEPRINT.md` | **Start here.** Coverage map, relevance circles, edition anatomy, recurring features, writing rules, calendar and pacing, automation with brakes, copyright, privacy, tech options, data model, build phases |
| `PEOPLE_AND_PRIVACY.md` | How news about Cedefop staff and ecosystem people works, and what is never done; EUDPR |
| `SOURCES.md` | Sources tested from a script on 17 October 2026: what works, what's blocked, OpenAlex facts and measured supply |
| `LESSONS_FROM_DAILY_CODES.md` | What worked, what went wrong, and tested facts about the data sources |
| `OPEN_QUESTIONS.md` | 22 decisions, each with a recommended default |
| `data/sources.csv` | 30 sources with URL, circle and tested status |
| `data/topics.yaml` | Work-area taxonomy with multilingual keywords (seed) and EU policy hooks |
| `data/vet_journals.csv` | 16 OpenAlex journal IDs for VET, adult learning, labour and the future of work |
| `data/eurostat_watchlist.csv` | Eurostat datasets for "The number" (one verified, the rest to verify) |
| `data/people.csv` | One row: the Executive Director, Jürgen Siebel |
| `scripts/source_check.sh` | Re-tests every source URL |
| `scripts/shot.sh` | Headless Chrome screenshots at 1280 px and 375 px |
| `scripts/from-daily-codes/` | OpenAlex fetch for a list of people, and the batch research-round scripts. **Not for Cedefop staff** without the DPO's agreement (`PEOPLE_AND_PRIVACY.md`). |
| `reference/daily-codes/` | The Daily Codes blueprint, HTML prototypes (editions, email, newsroom), the London venue list and the research-agent briefs |

Nobody at Cedefop was searched. The folder holds no personal data beyond the Director's name and title.

## Starting the new session

Open Claude Code in the new repo and paste:

> This repo is for Cedefop Daily, a daily newspaper for Cedefop staff. Read README.md, BRIEF.md, BLUEPRINT.md, PEOPLE_AND_PRIVACY.md, SOURCES.md, LESSONS_FROM_DAILY_CODES.md and OPEN_QUESTIONS.md first. They were written at the end of the Daily Codes project and carry its decisions and lessons. Don't search for information about Cedefop staff. Let's go through OPEN_QUESTIONS.md, then build a first edition from public sources, marked as a mock-up.

Useful in the new session:
- **The OpenAlex API key** is in the macOS Keychain under service `openalex-api-key`. Send it as `Authorization: Bearer <key>`. The `from_created_date` filter now needs a paid plan, so use publication dates.
- **The design** to adapt is in `reference/daily-codes/prototype/styles.css`. Give it new section colours (pillars) for policy, agencies, countries, research, data and people.
