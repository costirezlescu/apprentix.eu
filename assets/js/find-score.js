/* Apprentix — "Find my apprenticeship": questions, URL encoding and scoring.
   No DOM here, so it can be imported by node for tests.
   Scores come from Cedefop's coded answers (q_*) plus the hand-checked summary fields. */

/** Greece is GR in the schemes dataset and EL (Eurostat) everywhere else on the site. */
export const siteCode = (code) => (String(code || '').toUpperCase() === 'GR' ? 'EL' : String(code || '').toUpperCase());

/* Each question: id (URL key), the options (value → label, help), and what "doesn't matter" is.
   Every question is optional: no answer = doesn't matter. */
export const QUESTIONS = [
  {
    id: 'c',
    title: 'Where would you like to train?',
    help: 'Pick one or more countries, or leave it open to see all of Europe.',
    multi: true,
    options: [] // filled from the data at runtime (countries that have a scheme)
  },
  {
    id: 'age',
    title: 'How old are you?',
    help: 'Schemes are open to different ages, but most learners in each scheme fall into a typical age group.',
    options: [
      { value: 'u18', label: 'Under 18' },
      { value: '18-24', label: '18 to 24' },
      { value: '24plus', label: 'Over 24' }
    ]
  },
  {
    id: 'pay',
    title: 'Is being paid important to you?',
    help: 'Some apprentices earn a wage under a contract; others get an allowance or grant.',
    options: [
      { value: 'wage', label: 'I need a wage', help: 'Only schemes where apprentices can be paid a wage.' },
      { value: 'allowance', label: 'An allowance is fine', help: 'A wage or an allowance both work for me.' }
    ]
  },
  {
    id: 'he',
    title: 'Do you want the option to go on to university later?',
    help: 'In some schemes the qualification gives direct access to higher education.',
    options: [
      { value: 'must', label: 'Yes, that is a must', help: 'Leave out schemes without direct access.' },
      { value: 'nice', label: 'It would be nice', help: 'Rank schemes with direct access higher.' }
    ]
  },
  {
    id: 'work',
    title: 'How much of your time do you want to spend at the company?',
    help: 'Every apprenticeship mixes learning at work with learning at a school or training centre.',
    options: [
      { value: 'most', label: 'Most of it', help: 'I want to learn on the job.' },
      { value: 'half', label: 'About half', help: 'A balance of work and school.' },
      { value: 'school', label: 'Mostly at school is fine', help: 'More classroom, less company time.' }
    ]
  },
  {
    id: 'level',
    title: 'What level are you aiming for?',
    help: 'Most apprenticeships lead to an upper-secondary qualification; some go further.',
    options: [
      { value: 'secondary', label: 'A secondary-level qualification', help: 'For example after compulsory school.' },
      { value: 'higher', label: 'Post-secondary or higher', help: 'Higher technical, bachelor or master level.' }
    ]
  },
  {
    id: 'status',
    title: 'Would you rather be a worker or a student?',
    help: 'Apprentices are employees with a contract in some schemes, and students on a training agreement in others.',
    options: [
      { value: 'employee', label: 'A worker with a contract', help: 'Employment or apprenticeship contract.' },
      { value: 'student', label: 'A student', help: 'Training agreement, student status.' }
    ]
  }
];

export const DONT_MIND = { value: '', label: "Doesn't matter" };
export const DONT_KNOW_STATUS = { value: '', label: "Don't know / doesn't matter" };

const VALID = Object.fromEntries(QUESTIONS.filter(q => !q.multi).map(q => [q.id, new Set(q.options.map(o => o.value))]));

/** Answers object: { c: ['AT', ...], age: 'u18' | '', ... } from a URLSearchParams / query string. */
export function parseAnswers(search) {
  const p = search instanceof URLSearchParams ? search : new URLSearchParams(search || '');
  const a = { c: [] };
  const cs = (p.get('c') || '').split(',').map(s => s.trim().toUpperCase()).filter(s => /^[A-Z]{2}$/.test(s));
  a.c = [...new Set(cs.map(s => (s === 'EL' ? 'GR' : s)))]; // accept EL as Greece
  for (const id of Object.keys(VALID)) {
    const v = p.get(id) || '';
    a[id] = VALID[id].has(v) ? v : '';
  }
  return a;
}

/** Query string (no leading "?") for the answers; empty answers are left out. */
export function encodeAnswers(a) {
  const p = new URLSearchParams();
  if (a.c && a.c.length) p.set('c', a.c.join(','));
  for (const q of QUESTIONS) {
    if (q.multi) continue;
    if (a[q.id]) p.set(q.id, a[q.id]);
  }
  return p.toString().replace(/%2C/g, ',');
}

export const answeredCount = (a) =>
  QUESTIONS.filter(q => (q.multi ? (a[q.id] || []).length : a[q.id])).length;

/* ---------------- scoring ---------------- */

const arr = (v) => (v == null || v === '' ? [] : Array.isArray(v) ? v : [v]);
const AGE_CODE = { u18: '15–18', '18-24': '18–24', '24plus': 'Over 24' };
const AGE_TEXT = { '15–18': '15–18', '18–24': '18–24', 'Over 24': 'over 24' };

/**
 * Score one scheme for the answers.
 * Returns { excluded: string|null, score, max, reasons: [{kind:'yes'|'part'|'no'|'note', text}] }.
 * kind 'yes' → ✓, 'part' → ~ (partly), 'no' → –, 'note' → ! (caution).
 */
export function scoreScheme(rec, a) {
  const reasons = [];
  let score = 0;
  let max = 0;
  const add = (pts, of, kind, text) => { score += pts; max += of; reasons.push({ kind, text }); };

  // 1. Country — hard filter.
  if (a.c && a.c.length && !a.c.includes(String(rec.country_code).toUpperCase())) {
    return { excluded: 'Not in the countries you chose', by: 'country', score: 0, max: 0, reasons: [] };
  }

  // 2. Age → q_typical_age
  if (a.age) {
    const want = AGE_CODE[a.age];
    const ages = arr(rec.q_typical_age);
    if (!ages.length) add(1, 3, 'note', 'Typical learner age is not coded by Cedefop — check the target group');
    else if (ages.includes(want)) {
      add(ages.length === 1 ? 3 : 2.5, 3, 'yes', `Typical learners are your age (${AGE_TEXT[want]})`);
    } else {
      add(0, 3, 'no', `Most learners are ${ages.map(x => AGE_TEXT[x]).join(' or ')}`);
    }
  }

  // 3. Pay → q_compensation only (Cedefop's coded answer is authoritative; the summary is shown as a cross-check)
  if (a.pay) {
    const coded = arr(rec.q_compensation);
    const summary = String(rec.compensation || '');
    const codedWage = coded.includes('Wage');
    const summaryWage = false; // decisions use Cedefop's coded answer only
    if (a.pay === 'wage') {
      if (!codedWage && !summaryWage) {
        return { excluded: `No wage (Cedefop: ${coded.join(', ') || 'not coded'})`, by: 'pay', score: 0, max: 0, reasons: [] };
      }
      if (codedWage && coded.length === 1) add(3, 3, 'yes', 'Paid a wage');
      else if (codedWage) add(2, 3, 'part', `Can be paid a wage (Cedefop lists: ${coded.join(', ')})`);
      else add(2, 3, 'part', `Paid a wage per the Apprentix summary (Cedefop codes it as: ${coded.join(', ')})`);
      if (codedWage && summary && summary !== 'Wage') reasons.push({ kind: 'note', text: `Check pay: the summary says "${summary}"` });
    } else { // allowance is fine
      if (codedWage || summaryWage) add(3, 3, 'yes', codedWage && coded.length === 1 ? 'Paid a wage' : 'Paid a wage or allowance');
      else if (coded.includes('Allowance')) add(3, 3, 'yes', 'Paid an allowance');
      else add(0, 3, 'no', `Pay: ${coded.join(', ') || summary || 'not coded'}`);
    }
  }

  // 4. Higher education → q_access_to_he
  if (a.he) {
    const he = rec.q_access_to_he;
    if (he === 'No' && a.he === 'must') {
      return { excluded: 'No direct access to higher education', by: 'he', score: 0, max: 0, reasons: [] };
    }
    if (he === 'Yes') add(3, 3, 'yes', 'Direct access to higher education');
    else if (he === 'No') add(0, 3, 'no', 'No direct access to higher education');
    else add(1, 3, 'note', 'Access to higher education not coded — check the fiche');
  }

  // 5. Workplace time → workplace_time (summary) + q_min_workplace_share
  if (a.work) {
    const wt = String(rec.workplace_time || '');
    const share = rec.q_min_workplace_share || '';
    const mostly = wt.startsWith('Mostly');
    const half = wt.startsWith('Around half');
    const under = wt.startsWith('Under half');
    const label = mostly ? 'Mostly at the company' : half ? 'About half at the company' : under ? 'Mostly school-based' : (wt || 'Workplace time not stated');
    let pts = 0;
    if (a.work === 'most') pts = mostly ? 3 : half ? 1.5 : 0;
    else if (a.work === 'half') pts = half ? 3 : mostly ? 1.5 : under ? 1.5 : 0;
    else pts = under ? 3 : half ? 2 : 0.5;
    if (a.work === 'most' && share === '50% or more') pts = Math.min(3, pts + 0.5);
    const kind = pts >= 3 ? 'yes' : pts >= 1.5 ? 'part' : 'no';
    const lawNote = share && share !== 'No minimum' ? ` (law: ${share} at the workplace)` : '';
    add(pts, 3, kind, label + lawNote);
  }

  // 6. Level → education_level (+ q_qualification_type in the wording)
  if (a.level) {
    const lvl = String(rec.education_level || '');
    const types = arr(rec.q_qualification_type);
    const journey = types.includes('Apprenticeship qualification (journeyman etc.)') ? ' — apprenticeship (journeyman-type) qualification' : '';
    if (a.level === 'secondary') {
      if (lvl === 'Upper secondary') add(3, 3, 'yes', `Upper-secondary qualification${journey}`);
      else if (lvl === 'Multiple levels') add(2, 3, 'part', 'Offered at several levels, including secondary');
      else add(0, 3, 'no', `${lvl || 'Level not stated'} — above secondary level`);
    } else {
      if (lvl.startsWith('Post-secondary') || lvl.startsWith('Higher')) add(3, 3, 'yes', `${lvl} qualification`);
      else if (lvl === 'Multiple levels') add(2, 3, 'part', 'Offered at several levels, including post-secondary or higher');
      else add(0, 3, 'no', `${lvl || 'Level not stated'} level only`);
    }
  }

  // 7. Worker or student → q_learner_status + q_contract_type
  if (a.status) {
    const st = arr(rec.q_learner_status);
    const ct = arr(rec.q_contract_type);
    const employee = st.includes('Employee') || ct.includes('Ordinary employment contract');
    const contract = employee || ct.includes('Specific apprenticeship contract') || st.includes('Specific apprentice status');
    const student = st.includes('Student') || ct.includes('Formal agreement, not a contract');
    if (a.status === 'employee') {
      if (employee) add(3, 3, 'yes', 'Apprentices are employees (employment contract)');
      else if (contract) add(2.5, 3, 'yes', 'Apprenticeship contract with a specific apprentice status');
      else add(0, 3, 'no', 'Student status on a training agreement, not a contract');
    } else {
      if (student && !contract) add(3, 3, 'yes', 'Student status (training agreement)');
      else if (student) add(2, 3, 'part', 'Student status in some cases; a contract in others');
      else add(0, 3, 'no', 'Apprentices have a contract rather than student status');
    }
  }

  return { excluded: null, score, max, reasons };
}

const learnersNumber = (rec) => {
  const m = String(rec.learners || '').replace(/[\s  ]/g, '').match(/\d+/);
  return m ? Number(m[0]) : 0;
};

/**
 * Rank all schemes. Returns { results: [{rec, score, max, pct, reasons}], excluded: [{rec, why, by: 'country'|'pay'|'he'}] }.
 * Ties are broken by number of learners (larger schemes first), then by country.
 */
export function rankSchemes(records, a) {
  const results = [];
  const excluded = [];
  for (const rec of records) {
    const s = scoreScheme(rec, a);
    if (s.excluded) excluded.push({ rec, why: s.excluded, by: s.by });
    else results.push({ rec, score: s.score, max: s.max, pct: s.max ? Math.round((s.score / s.max) * 100) : null, reasons: s.reasons });
  }
  results.sort((x, y) =>
    (y.max ? y.score / y.max : 0) - (x.max ? x.score / x.max : 0) ||
    learnersNumber(y.rec) - learnersNumber(x.rec) ||
    String(x.rec.country).localeCompare(String(y.rec.country)));
  return { results, excluded };
}

export function fitLabel(pct) {
  if (pct == null) return '';
  if (pct >= 85) return 'Strong match';
  if (pct >= 60) return 'Good match';
  if (pct >= 35) return 'Partial match';
  return 'Weak match';
}

/* ---------------- links ---------------- */

/** Links for a result card. `names` maps site codes (EL, BE…) to country names (countries.json);
    `vetSystems` maps site codes to the vet-systems record's source_url. Paths are relative to pages/. */
export function schemeLinks(rec, { names = {}, vetSystems = {} } = {}) {
  const code = siteCode(rec.country_code);
  const countryName = names[code] || rec.country;
  const q = `I'm interested in the "${rec.name_en}" (${rec.name_original}) apprenticeship in ${rec.country}. ` +
    'Who can apply, how are apprentices paid, how long does it take, and how do I find a company to train with?';
  const links = [];
  if (rec.source_url) links.push({ kind: 'fiche', href: rec.source_url, text: 'Official Cedefop fiche', external: true });
  links.push({ kind: 'record', href: `explore.html?dataset=apprenticeship-schemes&open=${encodeURIComponent(rec.id)}`, text: 'Full record in the explorer' });
  links.push({ kind: 'country', href: `countries/${code.toLowerCase()}.html`, text: `${countryName}: country page` });
  if (vetSystems[code]) links.push({ kind: 'vet', href: vetSystems[code], text: `VET system in ${countryName} (Cedefop)`, external: true });
  links.push({ kind: 'erasmus', href: `explore.html?dataset=erasmus-vet-organisations&f.country=${encodeURIComponent(countryName)}`, text: `Erasmus+ accredited VET organisations in ${countryName}` });
  links.push({ kind: 'ask', href: `ask.html?q=${encodeURIComponent(q)}`, text: 'Ask Apprentix about this scheme' });
  return links;
}
