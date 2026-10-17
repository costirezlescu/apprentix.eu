# People at Cedefop: news, rules and privacy

The brief asks for "news (if any) on the people working at Cedefop". This is the part of the paper most likely to go wrong. It can be wrong about a person, intrusive, or embarrassing to forward. The design below keeps it useful and small.

**Known so far:** Jürgen Siebel, Executive Director (named by you on 17 October 2026). As asked, nobody was searched in this session. `data/people.csv` holds this one row.

## 1. Two kinds of people news

| Kind | Who | Allowed sources | Examples (of form, not real items) |
|---|---|---|---|
| **Public role** | The Executive Director; Cedefop staff acting publicly for Cedefop (speakers, authors, interviewees); public office holders in the ecosystem, tracked by role (BLUEPRINT, section 3) | Cedefop's own public pages (news, events, publications); EU institution pages; media monitoring; research databases with a **Cedefop affiliation** | "Jürgen Siebel opens the Brussels seminar on…" · "Cedefop expert quoted in Handelsblatt on apprenticeship numbers" · "Paper by Cedefop staff in the Journal of Education and Work" |
| **Colleague news** | Any member of staff | **Only** approved internal channels: HR announcements, Communications, and items staff submit about themselves | New colleagues, a new head of department, retirements, a colleague's award, a book, a marathon (if they submit it) |

**Never used:**
- web searches about individual staff;
- people-data aggregators;
- personal social-media accounts;
- family, health, appraisal, disciplinary or salary matters;
- the reasons anyone leaves;
- rumours.

**Social media:** only Cedefop's official accounts. Even those need editor approval (carried over).

## 2. How each channel works

**HR and Communications inbox** (a dedicated address, allowlisted senders only):
- The model extracts fields that must appear word for word in the email.
- Nothing is invented or embellished.
- The item runs as a short notice, with an embargo if given.

**Self-submission** ("Tell the Daily", a form or an email address):
- A colleague submits news about themselves, and confirms that it may appear in the paper.
- They can withdraw it until 07:45 on the day it runs.
- If the item names other colleagues, those colleagues must agree before it runs.

**Public-role monitoring:**
- **Matching:** a mention counts only when the source names the person **and** Cedefop together, for example an article that says "Cedefop expert Maria Example" or an author affiliation that reads "Cedefop".
- **Name-only matches never run** (the Daily Codes identity rule).
- **Affiliation check:** OpenAlex attaches some unrelated papers to Cedefop's institution ID. On 17 October 2026, two Portuguese health papers were listed under Cedefop. Match on the **raw affiliation string** ("Cedefop" or "European Centre for the Development of Vocational Training"), not the institution ID.

**Staff list (optional, phase 3):**
- **What it is:** a list of names, units and job titles from HR, with an agreed purpose.
- **What it allows:** connection lines like "Cedefop expert in the Department for …", and a check that a public mention really is a colleague.
- **When it can be used:** only after the DPO agrees.
- **What it doesn't allow:** searching for anyone.

## 3. Rules on the page

- **Headlines:** no person in more than one headline a day.
- **The Director:**
  - appears when the event is the story: a speech, a launch, an interview, a meeting with a Commissioner or minister;
  - is not front-page material every day;
  - a soft cap of three headline appearances a week, with the editor able to override.
- **Opt-out:** any colleague can opt out of colleague news at any time, with one email. The opt-out list is checked at build time.
- **Opt-out link:** the footer of every edition links to the opt-out and to the editor.
- **Sensitive categories hold the edition** until the editor decides (BLUEPRINT, section 8). They include:
  - deaths;
  - illness;
  - litigation;
  - OLAF and audit matters;
  - Ombudsman cases;
  - staff disputes.
- **Hold-list:** the editor can keep a list of people or topics that never run without approval.

## 4. Data protection (EUDPR)

- **Law.** Cedefop is covered by **Regulation (EU) 2018/1725**. The paper processes staff personal data, even if only names and job titles.
- **Before phase 3:**
  1. Write a record of processing. Its purpose is internal communication. Its legal basis is likely Article 5(1)(a), a task in the public interest, or consent for self-submitted items. Confirm with the DPO.
  2. Publish a short privacy statement on the intranet, linked from the footer.
  3. Set retention:
     - staff-news items: 12 months;
     - the opt-out list: kept while the person is employed.
- **Option C keeps it minimal** (BLUEPRINT, section 11). The external pipeline holds no staff addresses. With this option, staff data outside Cedefop is limited to approved news items and, if used, the HR staff list.
- **No profiling of readers.**
  - Click counts are kept only in aggregate.
  - The Number's guesses are anonymous.
  - Per-reader topic follows (phase 6) would need their own record of processing.

## 5. Ecosystem people (outside Cedefop)

- **Public office holders are covered in their public role only.** This includes Commissioners, Directors-General, MEPs, ministers, agency directors and social-partner leaders.
- **Track roles, not names.** The `roles` table resolves each role to its current holder from an official page, and is re-checked monthly. The paper then follows people as they change jobs, without anyone keeping a list of names.
- **Researchers** appear as authors of the papers covered, as in Daily Codes, with their affiliations as printed.
