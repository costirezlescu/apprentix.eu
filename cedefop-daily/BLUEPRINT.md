# Cedefop Daily: editorial and technical blueprint

*Version 0.1, 17 October 2026. Written at the end of the Daily Codes project. See `reference/daily-codes/BLUEPRINT.md` for the design this adapts, and `SOURCES.md` for sources tested on 17 October 2026.*

---

## 1. The idea in one paragraph

Every working morning, everyone at Cedefop gets one short, well-made paper by email, with a web version on the intranet. It covers:
- what is happening at Cedefop today;
- where Cedefop's work showed up in the world yesterday;
- what the EU institutions, the sister agencies, the member states and the research community did that touches VET, skills and the future of work;
- once in a while, news about colleagues.

Every item says why it matters to Cedefop and links to its source. It is assembled automatically and goes out unless an editor stops something.

**Six principles**
1. **Relevant to Cedefop, or it doesn't run.** The connection line under each story names the Cedefop work area it touches. If no line can be generated, the story is out.
2. **True.** Every claim links to a source. Numbers are copied, not computed into new claims. Translations are labelled.
3. **Neutral.** It reports and never editorialises. It takes no side on member-state policies, parties or social-partner disputes, and it never speaks for Cedefop. Staff are bound by the Staff Regulations, and the paper must be safe to forward.
4. **Short.** It takes 5 minutes to read, with 10–18 items on a normal day. A quiet day gives a shorter paper, not padding.
5. **Automatic.** Nobody has to act for it to go out. Communications holds the brakes (section 9).
6. **Discreet about people.** Staff news only comes from approved channels, with an opt-out (`PEOPLE_AND_PRIVACY.md`).

---

## 2. Coverage map: Cedefop's work areas become the taxonomy

Every item is tagged with one or more **work areas**. The tags drive the connection line, the section and pacing. The seed list and multilingual keywords are in `data/topics.yaml`. **Align it with the current Single Programming Document and the organigramme in the new repo**, because staff recognise their own activity names.

| Work area | What it covers | Cedefop hooks (examples to verify) |
|---|---|---|
| **VET policy and systems** | Reforms, governance, quality, financing, VET excellence, policy monitoring | Monitoring of EU VET priorities (the 2020 Council Recommendation on VET, the Osnabrück Declaration and its successor), VET in Europe database, ReferNet |
| **Apprenticeships and work-based learning** | Schemes, quality, employers, the European Alliance for Apprenticeships | European database on apprenticeship schemes |
| **Skills intelligence** | Skills needs, mismatch, forecasts, online job ads, employer and worker surveys | Skills forecast, European Skills and Jobs Survey, Skills OVATE, European skills index, RESET (regional skills ecosystems index, listed in Cedefop's RSS feed on 15 Oct 2026) |
| **Qualifications and credentials** | EQF and national frameworks, learning outcomes, validation of non-formal and informal learning, micro-credentials, Europass, ESCO | European inventory on validation; micro-credentials work |
| **Adult learning and upskilling** | Upskilling pathways, individual learning accounts, CVET, low-skilled adults, guidance | Adult participation targets |
| **Inclusion and early leaving** | Early leaving from VET, NEETs, migrants, disability, gender | VET toolkit for tackling early leaving |
| **Teachers and trainers** | VET teachers, in-company trainers, their skills | |
| **Mobility** | Learner and teacher mobility, Erasmus+ in VET | IVET mobility scoreboard |
| **Future of work** | AI and digitalisation, automation risk, green transition, demographic change, platform work | Cedefop's AI and skills research, twin transitions |
| **Labour market** | Employment, vacancies, shortages, wages, the social partners | |
| **Governance and the agencies** | EU agencies network, budgets, mandates, evaluations, the Governing Board | |

---

## 3. Relevance circles

Items are scored in circles, from Cedefop outwards. The circle sets the default section and weight. The page still leads with the day's most important item, wherever it sits.

| Circle | What | Main sources | Example connection line |
|---|---|---|---|
| **0. At Cedefop** | Today's events and launches, new publications, newsletters, vacancies, Board meetings, the Director's public appearances, staff news | Cedefop RSS (filtered), internal calendar and announcements inbox, Cedefop events pages | *Cedefop publication, out today.* |
| **1. Cedefop in the world** | Media articles mentioning Cedefop; research papers citing or using Cedefop data; EU documents citing Cedefop | Media monitoring; OpenAlex full text and citations; EUR-Lex and Commission documents | *Uses data from the European Skills and Jobs Survey.* |
| **2. EU policy** | Commission initiatives and statements, Council conclusions and EPSCO/EYCS meetings, Parliament (EMPL and CULT committees, plenary), Presidency events, consultations, the Official Journal | Commission press corner RSS, Council RSS, Parliament RSS, EUR-Lex RSS, Have Your Say | *Relevant to: adult learning · the Union of Skills.* |
| **3. Agencies and partners** | ETF, Eurofound, EU-OSHA, ELA, EIGE, FRA, JRC, Eurostat; the social partners at EU level; OECD, ILO, UNESCO-UNEVOC, World Bank | Their feeds and news pages (`SOURCES.md`) | *Eurofound, sister agency in the employment cluster.* |
| **4. Across Europe** | National VET reforms, apprenticeship schemes, skills strategies in the EU-27, Iceland and Norway (the ReferNet countries). Candidate countries where ETF and Cedefop overlap. | National ministries and agencies, ReferNet news, national press via media monitoring; translated | *Germany · translated from German · Relevant to: apprenticeships.* |
| **5. Research** | New papers in VET, skills and labour economics journals; working papers; datasets | OpenAlex (journal IDs in `data/vet_journals.csv`), IZA and similar series, Zenodo | *Journal of Vocational Education and Training.* |
| **6. Future of work and the wider debate** | AI and jobs, green skills, demography, platform work, from serious sources only | Agencies, OECD, ILO, peer-reviewed work, quality press | *Relevant to: AI and skills.* |
| **7. Thessaloniki and Brussels** (Friday, optional) | Selective talks and small-venue culture near the two offices | Venue list (to draft, the London method) | *Near the Thessaloniki office.* |

**The people circle.** The brief asks for news about people relevant to Cedefop's work: Commissioners, MEPs, directors of sister agencies, national ministers. Track these **as roles, not as names**, for example "Executive Vice-President responsible for skills" or "Chair of the EMPL committee". Resolve each role to its current holder from an official source, and re-check monthly. People then change without anyone editing a list. Coverage is limited to what they do in office: speeches, appointments and decisions.

---

## 4. Edition anatomy

```
CEDEFOP DAILY                                     Tuesday 20 October 2026
Thessaloniki · Brussels                                    No. 14 · Term 1
──────────────────────────────────────────────────────────────────────────
TODAY AT CEDEFOP   10:00 Brussels seminar (online) · Publication out: … · Consultation closes Fri
   or THIS WEEK IN NUMBERS   23 research papers cited Cedefop · 6 media mentions · …
──────────────────────────────────────────────────────────────────────────
Lead story          the day's most important item, any circle (usually 0–2)
At Cedefop          0–4   publications, events, newsletters, vacancies
Cedefop in the world 0–6  media mentions + research citing Cedefop ("Cited this week")
EU policy           1–4   always present on working days in session; "Quiet in Brussels" otherwise
Agencies & partners 0–4
Across Europe       0–4   country tag + "translated from …" label
Research            0–4   never padded (Daily Codes' "The Field")
Future of work      0–3
The number          1     a figure from Eurostat or Cedefop data; "guess" version answered next day
People              0–3   staff news by approved channel only; roles-based news on public figures
From the archive    0–1   a Cedefop publication from this week in a past year, with its date
Diary               the week's events across the ecosystem (Cedefop, agencies, Presidency, Parliament)
──────────────────────────────────────────────────────────────────────────
Footer: sources · how this paper is made · corrections · opt-out of staff news · contact the editor
```

**On Mondays:** a "Week ahead" box replaces "From the archive". It lists Council and Parliament meetings, Presidency events, consultations closing, Eurostat releases on the watchlist, and Cedefop events.

**On Fridays:** a longer edition.
- **"The week"**: five items that mattered.
- **One long read**: a report or paper worth 20 minutes.
- **An optional Thessaloniki box.**
- **"Answer to this week's number"**, where relevant.

**Today strip rule (carried over):**
- **"Today at Cedefop"** runs when the internal calendar or public pages have something today: an event, a launch, a webinar, a Board or Bureau meeting, a deadline in the next 7 days, or a public appearance by the Director.
- **"This week in numbers"** runs otherwise. It takes the four strongest numbers:
  - research papers that cited or mentioned Cedefop in the last 7 days;
  - media mentions;
  - new Cedefop publications;
  - one headline figure from a fresh Eurostat or Cedefop release.

  A number needs a source to appear. Zero values are dropped.

**Sections are optional, and the core is fixed.** The masthead, the strip, the lead story, The number and the Diary run every day. Everything else appears when it has content (section 7).

---

## 5. Recurring features

- **The number** is the habit hook, like the Daily Experiment in Daily Codes.
  - **One figure a day** from a Eurostat dataset or a Cedefop tool, with its source and year. An example form: *"Share of adults (25–64) who took part in education or training in the last four weeks, EU-27, 2025"*.
  - **Twice a week it runs as a guess.** Readers pick a range with one tap, and tomorrow's paper shows the answer and the staff's spread of guesses.
  - **Data and storage:** `localStorage`, plus an anonymous counter. No personal data.
- **From the archive.** Cedefop publications from the same week in earlier years, from 1975 onward. Each runs with its original date and a line on what has changed since, but only when the source says so.
- **Presidency tracker.** In the Diary, the current Council Presidency's VET and skills events.
  - **Order to verify:** Ireland, July–December 2026; Lithuania, January–June 2027; **Greece, July–December 2027**.
  - The Greek Presidency will matter in Thessaloniki. Plan coverage from spring 2027.
- **Consultations closing.** Commission "Have your say" consultations on Cedefop topics, with their closing dates.
- **Corrections.** A standing line. Errors are corrected the next day, in the same place.

---

## 6. Writing rules

All Daily Codes rules apply (`LESSONS_FROM_DAILY_CODES.md`, section 5). These are added:

- **Neutral register.**
  - No adjectives that judge a policy: "landmark", "ambitious", "controversial".
  - Attribute every evaluation to its source: "the Commission says", "the report finds".
  - Never write "we" for Cedefop.
- **No pre-publication.**
  - The pipeline reads only public sources and the internal calendar. It never reads drafts or embargoed outputs.
  - An item marked embargoed in the inbox is held until the embargo lifts.
- **Translations.**
  - Non-English sources are summarised in English, labelled "translated from German", and linked to the original.
  - Quotation marks are used only for text quoted in the source's language, or quoted from an official English version.
- **EU terms.**
  - Use official names: "Council Recommendation on vocational education and training for sustainable competitiveness, social fairness and resilience" on first mention, then "the 2020 VET Recommendation".
  - Spell out acronyms once per edition.
  - Keep a glossary file in the repo, and draw abbreviations from the Interinstitutional Style Guide.
- **Headlines:** under about 70 characters, concrete, with a verb.
  - Bad: "New report on skills".
  - Good: "Eurofound finds one in four workers fear AI will change their job" (this example is invented, to show form only).
- **People:**
  - no person in more than one headline a day;
  - the Director appears in a headline only when the event is the story;
  - the paper is not a house organ.
- **Banned:** speculation about appointments, budgets or restructurings; anonymous sources; social media posts from personal accounts; any item about a member of staff from outside the approved channels.

---

## 7. Calendar and pacing

**Calendar (to confirm):**
- **Working days:** an edition Monday to Friday, on Cedefop working days only. No editions on Cedefop public holidays. Use Cedefop's official holiday list, which will include Greek holidays such as 26 October (Agios Dimitrios, Thessaloniki) and 28 October. Load the list each January as a `calendar` table.
- **Summer (proposed):** three editions a week, Monday, Wednesday and Friday, from mid-July to the end of August. The end of December is treated the same way.
- **No weekend editions.** Staff have a right to disconnect. Friday is the "weekend" edition.
- **Send time:** 08:00 Athens time, which is 07:00 in Brussels.

**Pacing banks (carried over).** Each optional section has a weekly target, a daily maximum and a use-by date per item:

| Section | Measured or expected supply | Weekly target | Use-by |
|---|---|---|---|
| Research mentioning Cedefop (OpenAlex full text) | **1,191 works in 2025, about 23 a week** | 5–10 (best ones, in "Cedefop in the world") | 21 days |
| Research citing Cedefop's 50 most-cited works | **19 published between 17 September and 17 October 2026** | inside the above | 21 days |
| 10 VET and adult-learning journals | **84 papers in the same 30 days, about 20 a week** | 4–8 | 30 days |
| Cedefop's own outputs (RSS, filtered) | a few a week | all | 7 days |
| EU policy (press corner, Council, Parliament, EUR-Lex) | dozens a day before filtering | 8–15 | 3 days |
| Agencies and partners | several a week | 4–8 | 10 days |
| Across Europe | to measure once media monitoring is connected | 4–8 | 7 days |
| Staff news | rare | whatever arrives | 14 days |
| From the archive | unlimited | 3–4 | none |

The research numbers were measured on 17 October 2026 with publication dates (`SOURCES.md`). OpenAlex now charges for its "created date" filter, so counts by publication date include some future-dated items. Deduplicate against items already used.

---

## 8. Automation: zero intervention, with brakes

**Daily schedule** (Athens time):

```
03:00  Ingest: Cedefop RSS, EU institution feeds, EUR-Lex, agencies, Eurostat updates, OpenAlex, media monitoring, internal inbox
04:00  Filter and tag: work-area classifier (keywords first, model second), dedupe, country and language
04:30  Score and assign to sections; apply pacing banks and use-by dates
05:00  Write cards (headline, standfirst, 60–150 words, connection line by template); translation where needed
05:30  Checks: every URL from source data; every number found in the source; banned phrases; neutrality check;
       people rules; embargo check; date check against today (no past events in the Diary)
06:30  Build email + web edition; preview email to the editor ("Ready to go at 08:00. Reply SPIKE n to remove item n")
07:45  Lock
08:00  Send
```

**Brakes:**
- **Hold the whole edition** and alert the editor if any of these happen:
  - a check fails on the lead story;
  - more than 2 items fail checks;
  - an item mentions a member of staff without an approved channel;
  - an item touches a sensitive category: a Cedefop audit, an OLAF matter, litigation, Ombudsman findings, a staff death, a security incident.
- **Spike links.** One-click links in the preview email remove an item. Each link is signed and expires at 08:00.
- **Kill switch.** One link stops today's send. The paper then says nothing; it never sends a half-built edition.
- **Fallback.** If the build fails, a minimal edition goes out from banked items with a line saying so. Or nothing goes out, which is the editor's choice in settings.

**What people still do:**
- **Communications:** glance at the 06:30 preview, own the staff-news channel, and keep the internal calendar feed clean.
- **Once a quarter:** someone re-checks the sources list and the role holders.

---

## 9. Copyright and media monitoring

- **Press articles are copyrighted**, and press publishers have a related right in the EU (Directive 2019/790, Article 15). The paper may:
  - link to the article;
  - give its own short factual summary;
  - quote one short phrase at most.

  It must never reproduce text, images or headlines in bulk.
- **Cedefop probably already has a media monitoring contract**, or access through the Commission. Use it as the source for "Cedefop in the media" and for national press in "Across Europe". It is licensed, multilingual and already approved.
  - The JRC's Europe Media Monitor (EMM) NewsBrief exists for EU institutions. Its public RSS refused a script on 17 October 2026 (403). Ask about institutional access.
- **Research abstracts:** the same rules as Daily Codes. Summarise from the abstract and never from the title alone. Preprints are labelled "not peer-reviewed".

---

## 10. Privacy, transparency and the AI Act

- **Data protection law.** Cedefop is an EU body, so **Regulation (EU) 2018/1725 (EUDPR)** applies, not the GDPR. Any processing of staff data for the paper needs:
  - a record of processing;
  - the Data Protection Officer's view.

  `PEOPLE_AND_PRIVACY.md` sets out a design that keeps this small.
- **Recipients.** The pipeline does not need any staff email addresses if the edition is sent to one Cedefop distribution list (section 11, option C).
- **Transparency.** EU bodies are expected to be open about automated content, and the AI Act (Article 50) has transparency duties for AI-generated text on matters of public interest. Two things to settle:
  - Recommend a discreet colophon in the footer: *"Compiled automatically from the linked sources and reviewed by Communications."* It does not need to name a model.
  - Get Cedefop's legal or DPO view on whether an internal paper with a human editor needs more.
- **No tracking pixels.** Count clicks only through a redirect, in aggregate, and disclose it in the footer.
- **Model and data.** Only public source text and approved internal announcements go to the model. Use an EU-region endpoint (for example Claude on Amazon Bedrock or Google Vertex AI in an EU region). Confirm against Cedefop's own rules on generative AI.

---

## 11. Tech stack options (for an EU agency)

| Option | How | Pros | Cons |
|---|---|---|---|
| **A. Inside Cedefop IT** | Python pipeline on a Cedefop VM; email through Cedefop's mail system to the all-staff list; web edition as an intranet page | Data never leaves Cedefop; no procurement; fits IT policy | Depends on IT capacity and change process; slower to iterate |
| **B. External, EU-hosted** | Static site + Python on an EU cloud; EU-based email provider; Cloudflare Access or an EU equivalent for the web edition | Fast to build; same pattern as Daily Codes option B | Procurement, a DPO review of every processor, and staff addresses held outside |
| **C. Hybrid (recommended for a pilot)** | External pipeline builds the edition from **public** sources and sends **one** email, to a Cedefop mailbox or distribution list that Cedefop controls; the web version is a static page behind access control, or posted to the intranet by a script on Cedefop's side | Holds no staff personal data; Cedefop controls distribution; easy to stop; the editor's preview is the same email | Staff news and the internal calendar need a small bridge (a dedicated inbox or calendar feed that Cedefop shares) |
| **D. Microsoft 365 native** | Power Automate + SharePoint news + Outlook, with an approved AI service | Inside existing tools | Weak at sourcing and checks; hard to make it look like a newspaper |

**The pilot path:** start with C on 20–30 volunteer readers for four weeks, then move to A or keep C, depending on IT and DPO advice.

---

## 12. Data model (core)

```
sources        id, name, kind (rss, api, html, inbox, calendar, media_monitor), url, access, circle, language, active, last_ok
items          id, source_id, url, title, published_at, language, country, raw_text_ref, work_areas[], circle,
               entities (json: institutions, roles, people_ids), status (new, carded, used, rejected, expired), expires_at
cards          item_id, headline, standfirst, body, connection_line, translated_from, checks (json), model, created_at
editions       id, date, kind (daily, monday, friday, summer), strip_kind (today, numbers), status (built, held, sent, failed),
               items[] (ordered, with section), sent_at
section_rules  section, min, max, weekly_target, use_by_days, days_of_week
calendar       date, edition (yes/no), kind, note (holiday, closure, summer)
agenda         date, time, title, kind (event, launch, board, deadline, appearance), source (internal_calendar, public_page), public (bool)
roles          id, role_name, institution, holder_name, source_url, checked_at        (public office holders, by role)
staff_news     id, received_at, channel (hr, comms, self), person_ref, text, consent (json), embargo_until, status
numbers        id, dataset, geo, year, value, unit, source_url, used_on, guess_mode (bool)
corrections    edition_id, item_id, text, published_on
```

---

## 13. Build phases

| Phase | What | Outcome |
|---|---|---|
| **0. Inputs** | Who owns it; audience; the DPO and IT conversation; internal calendar access; media monitoring access; the holiday list; the organigramme for the taxonomy | No guesses about the institution |
| **1. Public-source edition** | Feeds and APIs in `SOURCES.md`; classifier on `topics.yaml`; cards, checks, template; preview email to the editor only | A credible paper from public sources alone |
| **2. Pilot** | 20–30 readers via option C; The number; Diary; Monday and Friday formats; feedback form | Real readers, real corrections |
| **3. People and agenda** | Staff-news inbox with consent rules; internal calendar feed; role holders | "Today at Cedefop" and People work |
| **4. Across Europe** | Media monitoring and national sources, translation, country tags | Member-state coverage |
| **5. All staff** | Distribution to everyone; corrections log; quarterly source review | The paper is routine |
| **6. Options** | Thessaloniki box; per-reader topic follows ("more on apprenticeships"); a public weekly edition | Only if wanted |
