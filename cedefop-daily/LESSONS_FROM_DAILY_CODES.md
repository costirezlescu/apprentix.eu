# Lessons from Daily Codes

Daily Codes (October 2026) was a daily paper for the UCL MSc in Cognitive and Decision Sciences. It had preview editions built from real data, a 567-person alumni registry built by research agents, and London talk and music listings. These are the things worth knowing before building Cedefop Daily.

## 1. Data sources: tested facts

**OpenAlex**
- Use an API key (in the macOS Keychain as `openalex-api-key`, sent as `Authorization: Bearer`). The free tier allows about $1 a day; an author search costs about $0.001. A full pull for 13 lecturers (recent works, top 50 works, papers citing them) took about a minute.
- **Clean the work lists.** Author work lists contain many records that aren't papers:
  - supplements, "Materials, Data, Code" and "Pre-registration" pages;
  - datasets (one OpenNeuro dataset appeared as 7 versions);
  - peer-review reports, and books alongside their own chapters.
  
  Filter by type and title, and remove duplicates by normalised title. eLife `.1`/`.3` and PsyArXiv `_v1`/`_v2` are the same paper.
- **The `from_created_date` filter now needs a paid plan** (checked 17 October 2026: "Plan upgrade required"). Filter by `from_publication_date` and remove items already used.
- **Dates can mislead.** `publication_date` can be a new version's date. One preprint dated 2 September 2026 had a `created_date` of December 2025. Label such items "version dated…". OpenAlex years also sometimes differ from print years (online-first dates).
- **Abstracts are sometimes missing.** This happened even for *Nature Neuroscience* 2002 and *Nature Reviews Neuroscience* 2017. **Europe PMC** (`/search?query=DOI:"…"&resultType=core`) usually has them. If neither does, say so; never summarise from the title.
- **`fulltext.search` breaks phrases into separate words.** "Testable Minds" matched unrelated papers. "testable.org" was precise (57 papers). A single distinctive word is precise too: "cedefop" gave 1,191 works in 2025. Europe PMC's full-text phrase search is precise but covers only open-access papers.
- **Author profiles can merge different people.** One lecturer showed 13 works in six weeks, including datasets. ORCID-linked profiles are cleaner.
- **Citing papers:** about 85–90 papers a fortnight cited 13 lecturers' top works. Self-citations need removing; the lecturers' own papers turned up as "citing".

**ORCID public API**
`https://pub.orcid.org/v3.0/{orcid}/works` (or `/employments`, `/activities`), with the header `Accept: application/json`. Free, no key, reliable. **An ORCID record that shows only an enrolment is not evidence of identity**, nor of a current role.

**Web search** was capped at about 200 searches per session, and the search tool sometimes declines person-lookup queries; the agents were told not to reword around that. Never fetch search-engine result pages, and never use people-data aggregators.

## 2. Identity matching (the alumni registry)

- 567 alumni were searched. 140 were found (95 high confidence, 45 medium) and 427 had no public footprint. After the first pass, a second look and a current-role pass, 110 had a known role. Older cohorts are far easier to find.
- **Confidence rules that worked:**
  - **high** means a source explicitly names the programme, or the ORCID shows the right institution in the right years;
  - **medium** means the name, the institution and a fitting field, but no explicit link;
  - **a name alone is never enough**: with a common name, medium at most.
- **Agents over-claim.** Every batch was reviewed before merging. Name matches with no institutional link were rejected, high was downgraded to medium where the evidence was thin, ORCID URLs were normalised to bare IDs, and "Recent graduate" was not accepted as a current role.
- **For Cedefop Daily, staff are not researched at all.** News about colleagues comes only through approved channels, and a public mention counts only when it names the person and Cedefop together (`PEOPLE_AND_PRIVACY.md`). These rules and scripts are here for research papers and ecosystem roles, not for staff.

## 3. Running research agents in batches

- **Batch sizes:** rounds of 30 people, split across 3 background agents of 10, with a limit of 3 searches per person.
- **Agents save often:** their output file is rewritten every 3–4 people. One round was lost when the Mac slept and the login expired. Interrupted agents can be resumed (by message) with their work intact. Use `caffeinate -i` for long runs.
- **Untrusted text:** agents treat everything fetched as data and ignore instructions embedded in it.
- **Machine-readable status:** anyone not searched is marked "NOT SEARCHED: …", and agents reply with three numbers only. That keeps agent output out of the main context.
- **Merge scripts** add a `last_checked` date and keep a `.bak` copy. They are in `scripts/from-daily-codes/`.

## 4. Event listings (London talks and music)

- **Of 40 venues, only one had a working calendar feed** (the Vortex, iCal). Gresham College has a JSON file behind its page. The Royal Institution and Cecil Sharp House have RSS feeds, but without event dates.
- **Bot checks block a lot:**
  - All UCL sites, the Institute of Philosophy, the Turing Institute, the British Academy, the RSA and Kings Place returned 403 (Cloudflare) to scripts.
  - An agent got past by reading through the user's logged-in Chrome browser. A server pipeline can't do that, and shouldn't try to get past bot checks.
  - The alternatives are mailing lists into a dedicated inbox, or asking venues for their feeds.
- **Venue lists go stale fast:**
  - one domain had expired, and one moved to an unrelated site;
  - one venue was renamed (St John's Smith Square is now Sinfonia Smith Square);
  - one ticketing widget blocked fetching.
  
  Re-verify each venue every quarter.
- **Selection rules that produced a good weekend box:**
  - copy title, performers, date, time and price exactly;
  - leave missing fields blank;
  - exclude famous names even at small venues;
  - give one "Listen for" angle only when the venue's own description supports it.
- **Bugs caught in review:**
  - a past event (a Wednesday lecture) recommended in the next Saturday's box;
  - an invented date range ("1580–1650") where the source said "16th and 17th centuries";
  - a derived claim ("first London show in three years").
  
  **Check every listing's date against the edition date.**

## 5. Writing: errors caught, and the checks they call for

- **A fabricated DOI** was written once for a preprint whose record had no DOI. It was caught by checking every link against the fetched data. **Rule: every URL in an edition must come from the data, never from the writing step.**
- **Overclaims crept in:** "the paper that named intentional binding"; "became a standard way of studying agency"; "the final, reviewed version". **Rule: only what the abstract or page says.**
- **Wrong course dates:** lecture weeks in a hand-made list didn't match Moodle (two lecturers were off by two weeks). **Rule: take schedule facts from the system of record.**
- **Charts:** a chart whose axis starts at 40% must say so.
- **Numbers must add up:** the totals in the numbers strip were recounted after removing duplicates and excluding self-citations and books.
- **House style that worked:**
  - concrete headlines with a verb, under about 70 characters;
  - a 1–2 sentence standfirst, and a body of 80–200 words;
  - sample and effect sizes when given;
  - "not peer-reviewed" on preprints;
  - no person in more than one headline a day;
  - a banned-phrase list.

## 6. Editorial structure that worked

- **A fixed core plus optional sections.** Readers don't need the same sections every time. The Field and Students were shown only when they had content.
- **The top strip has two forms.** Use the agenda when there is one, and real numbers when there isn't. For Cedefop Daily, these become "Today at Cedefop" and "This week in numbers".
- **Pacing with banks:** a weekly target, a daily maximum and a use-by date per item; thin sections run less often rather than being padded. Measured supply for 13 lecturers:

  | Item | Supply |
  |---|---|
  | New works | about 4 a week |
  | Citing papers | about 35 a week |
  | Papers from 14 journals | about 20 a week |
  | Alumni papers (21 tracked alumni) | about 1 a week |

- **The connection line** under every story ("Why you're seeing this") is generated from data by template, never by the writing model.

## 7. Infrastructure thinking

Section 2 of `reference/daily-codes/BLUEPRINT.md` covers this in full.

- **Logins:** no passwords. Use signed, expiring one-click links for actions (spike, approve, unsubscribe, "Not for me"), and an email code or magic link, or Cloudflare Access, for admin pages. At Cedefop, prefer the existing staff sign-in (or the intranet) for the web edition.
- **Reliability:** pre-build editions, and make sending independent of live systems. If the nightly build fails, the paper still goes out from what is already built.
- **Incoming email:** an allowlist of senders. The model extracts each event field, which must appear word for word in the email. Duplicates are merged, and cancellations update the existing listing. Meeting links, internal events and signature details are never published.

## 8. Moodle (UCL)

Moodle has a web-service API (`core_course_get_contents`), but a token tied to a staff account carries every staff permission. Ask for a dedicated low-privilege account. For browser reading, switch role to **Student**, read only what students see, then switch back. Never open Participants, Grades or forums. For Cedefop the same principle applies to any internal system (calendar, intranet, HR): read with the lowest privilege that works, and only what all staff can already see.

## 9. Tools used

- `scripts/shot.sh`: headless Chrome screenshots at 1280 px and 375 px. Always check the phone width.
- The OpenAlex IDs of 14 cognition and decision journals, used for "The Field":
  `S88198767` Cognition · `S58854535` Psychological Science · `S2764866340` Nature Human Behaviour · `S192051125` Trends in Cognitive Sciences · `S35223124` Psychological Review · `S62013203` JEP: General · `S78735424` Cognitive Science · `S179575189` Judgment and Decision Making · `S117214846` J. Behavioral Decision Making · `S36783443` Cognitive Psychology · `S138679565` Psychonomic Bulletin & Review · `S53787413` J. Memory and Language · `S2488191322` Open Mind · `S114020440` Current Directions in Psych. Science
