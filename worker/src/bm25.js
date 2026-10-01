/* BM25 search over the Apprentix AI index (data/ai/search-index.json).
   Dependency-free. The tokenizer folds accents, drops common stop words in several
   European languages, maps frequent non-English terms (apprenticeship words, country
   names) onto the English vocabulary of the index, and applies a light suffix stemmer. */

const STOP = new Set((
  // English
  'a an and are as at be by can do does for from has have how i in is it its me my of on or our ' +
  'should than that the their them there these this those to was were what when where which who why ' +
  'will with would you your about into most more much many any all also between since per vs versus ' +
  'tell show give list compare please country countries data europe european eu ' +
  // French
  'le la les un une des du de et en au aux est sont pour par sur dans que qui quel quelle quels quelles ' +
  'comment combien pays ce cette ces se sa son ses leur leurs ou plus ' +
  // German
  'der die das den dem des ein eine einer eines und ist sind fur von mit im zu zum zur wie viele welche ' +
  'welcher welches was wo wer auf aus bei nach oder land lander ' +
  // Spanish / Italian / Portuguese
  'el los las y es son para por con como cuantos cuantas que cual cuales pais paises il lo gli di ' +
  'della delle dei del e sono per con come quanti quante quale quali paese paesi o os as um uma do da ' +
  'dos das em no na quantos quantas'
).split(/\s+/).filter(Boolean));

// Folded (accent-free, lower-case) term -> index vocabulary.
const SYNONYMS = {
  // apprenticeship in other languages
  lehre: 'apprenticeship', lehrling: 'apprentice', lehrlinge: 'apprentices', ausbildung: 'apprenticeship',
  duale: 'dual', dualen: 'dual', berufsausbildung: 'vocational', berufsbildung: 'vocational',
  apprentissage: 'apprenticeship', apprenti: 'apprentice', apprentis: 'apprentices', alternance: 'apprenticeship',
  apprendistato: 'apprenticeship', apprendista: 'apprentice', apprendisti: 'apprentices',
  aprendizaje: 'apprenticeship', aprendiz: 'apprentice', aprendices: 'apprentices', aprendizagem: 'apprenticeship',
  leerling: 'apprentice', leerlingen: 'apprentices', leerlingwezen: 'apprenticeship', bbl: 'bbl',
  laerling: 'apprentice', larling: 'apprentice', laerlinger: 'apprentices', larlingar: 'apprentices',
  oppisopimus: 'apprenticeship', praktyka: 'apprenticeship', ucen: 'apprentice', ucenik: 'apprentice',
  ucenistvo: 'apprenticeship', ucnovstvi: 'apprenticeship', mathiteia: 'apprenticeship',
  // vocational / training / wage
  formation: 'training', professionnelle: 'vocational', professionnel: 'vocational', berufliche: 'vocational',
  formazione: 'training', professionale: 'vocational', formacion: 'training', profesional: 'vocational',
  beroepsonderwijs: 'vocational', yrkesutbildning: 'vocational', yrkesfag: 'vocational',
  salaire: 'wage', lohn: 'wage', gehalt: 'wage', verguetung: 'wage', vergutung: 'wage', salario: 'wage',
  retribuzione: 'wage', remuneration: 'wage', pay: 'pay', paid: 'pay', salary: 'wage',
  emploi: 'employment', beschaftigung: 'employment', occupazione: 'employment', empleo: 'employment',
  financement: 'financing', finanzierung: 'financing', finanziamento: 'financing', financiacion: 'financing',
  funding: 'financing', funded: 'financing', levy: 'levy', abgabe: 'levy', taxe: 'tax',
  qualification: 'qualification', qualifikation: 'qualification', diplome: 'qualification', abschluss: 'qualification',
  titolo: 'qualification', titulo: 'qualification', eqr: 'eqf', cec: 'eqf', dqr: 'nqf',
  // countries (folded endonyms and common exonyms)
  osterreich: 'austria', oesterreich: 'austria', autriche: 'austria',
  belgique: 'belgium', belgie: 'belgium', belgien: 'belgium', belgio: 'belgium', belgica: 'belgium',
  deutschland: 'germany', allemagne: 'germany', germania: 'germany', alemania: 'germany', duitsland: 'germany', tyskland: 'germany', niemcy: 'germany',
  france: 'france', frankreich: 'france', francia: 'france', frankrijk: 'france', frankrike: 'france', francja: 'france',
  italia: 'italy', italien: 'italy', italie: 'italy',
  espana: 'spain', spanien: 'spain', espagne: 'spain', spagna: 'spain', hiszpania: 'spain',
  portugal: 'portugal', portogallo: 'portugal',
  nederland: 'netherlands', niederlande: 'netherlands', holland: 'netherlands',
  danmark: 'denmark', danemark: 'denmark', danimarca: 'denmark', dinamarca: 'denmark',
  sverige: 'sweden', schweden: 'sweden', suede: 'sweden', svezia: 'sweden', suecia: 'sweden',
  suomi: 'finland', finnland: 'finland', finlande: 'finland', finlandia: 'finland',
  norge: 'norway', norwegen: 'norway', norvege: 'norway', norvegia: 'norway', noruega: 'norway',
  island: 'iceland', islande: 'iceland', islanda: 'iceland', islandia: 'iceland',
  irland: 'ireland', irlande: 'ireland', irlanda: 'ireland', eire: 'ireland',
  polska: 'poland', polen: 'poland', pologne: 'poland', polonia: 'poland',
  cesko: 'czechia', czech: 'czechia', tschechien: 'czechia', tchequie: 'czechia',
  slovensko: 'slovakia', slowakei: 'slovakia', slovaquie: 'slovakia',
  slovenija: 'slovenia', slowenien: 'slovenia', slovenie: 'slovenia',
  magyarorszag: 'hungary', ungarn: 'hungary', hongrie: 'hungary', ungheria: 'hungary', hungria: 'hungary',
  romania: 'romania', rumanien: 'romania', roumanie: 'romania',
  bulgaria: 'bulgaria', bulgarien: 'bulgaria', bulgarie: 'bulgaria', balgariya: 'bulgaria',
  hrvatska: 'croatia', kroatien: 'croatia', croatie: 'croatia', croazia: 'croatia',
  ellada: 'greece', griechenland: 'greece', grece: 'greece', grecia: 'greece',
  kypros: 'cyprus', zypern: 'cyprus', chypre: 'cyprus', cipro: 'cyprus', chipre: 'cyprus',
  eesti: 'estonia', estland: 'estonia', estonie: 'estonia',
  latvija: 'latvia', lettland: 'latvia', lettonie: 'latvia', lettonia: 'latvia',
  lietuva: 'lithuania', litauen: 'lithuania', lituanie: 'lithuania', lituania: 'lithuania',
  luxemburg: 'luxembourg', lussemburgo: 'luxembourg', luxemburgo: 'luxembourg',
  malte: 'malta',
  schweiz: 'switzerland', suisse: 'switzerland', svizzera: 'switzerland', suiza: 'switzerland',
  turkiye: 'turkiye', turkey: 'turkiye', turkei: 'turkiye', turquie: 'turkiye',
  srbija: 'serbia', serbien: 'serbia', serbie: 'serbia',
  uk: 'kingdom', britain: 'kingdom', england: 'england', grossbritannien: 'kingdom', angleterre: 'england', inghilterra: 'england',
};

const SUFFIXES = ['ships', 'ship', 'ations', 'ation', 'ments', 'ment', 'ings', 'ing', 'ies', 'es', 's'];

export function fold(s) {
  return String(s ?? '').normalize('NFKD').replace(/\p{M}+/gu, '').toLowerCase()
    .replace(/ß/g, 'ss').replace(/æ/g, 'ae').replace(/ø/g, 'o').replace(/œ/g, 'oe').replace(/ł/g, 'l').replace(/đ/g, 'd');
}

export function stem(t) {
  if (t.length <= 4 || /\d/.test(t)) return t;
  for (const suf of SUFFIXES) {
    if (t.endsWith(suf) && t.length - suf.length >= 4) {
      t = suf === 'ies' ? t.slice(0, -3) + 'y' : t.slice(0, -suf.length);
      break;
    }
  }
  if (t.length > 4 && t.endsWith('e')) t = t.slice(0, -1);
  return t;
}

/** Folded, stop-word-free, stemmed tokens. */
export function tokenize(text) {
  const out = [];
  const raw = fold(text).match(/[\p{L}\p{N}]+(?:-[\p{L}\p{N}]+)*/gu) || [];
  for (let w of raw) {
    if (w.includes('-')) {
      // keep hyphenated ids whole ("eurostat-tps00215") and also their parts
      if (/\d/.test(w)) out.push(w);
      for (const part of w.split('-')) pushToken(out, part);
      continue;
    }
    pushToken(out, w);
  }
  return out;
}

function pushToken(out, w) {
  if (!w || STOP.has(w)) return;
  if (w.length < 2 && !/\d/.test(w)) return;
  const syn = SYNONYMS[w];
  if (syn) w = syn;
  out.push(stem(w));
}

/**
 * Build an in-memory BM25 index.
 * docs: [{id, title, text, ...}] — title is weighted (counted twice).
 */
export function buildIndex(docs, { k1 = 1.2, b = 0.5 } = {}) {
  const postings = new Map();   // term -> [docIdx, tf, docIdx, tf, ...]
  const lengths = new Float64Array(docs.length);
  let total = 0;
  docs.forEach((d, i) => {
    const toks = tokenize(`${d.title} ${d.title} ${d.text}`);
    lengths[i] = toks.length;
    total += toks.length;
    const tf = new Map();
    for (const t of toks) tf.set(t, (tf.get(t) || 0) + 1);
    for (const [t, n] of tf) {
      let p = postings.get(t);
      if (!p) postings.set(t, (p = []));
      p.push(i, n);
    }
  });
  return { docs, postings, lengths, avgdl: total / Math.max(1, docs.length), k1, b, N: docs.length };
}

/**
 * Rank documents for a query. Optional filter(doc) restricts candidates; optional
 * boost(doc) multiplies a document's score.
 * Returns [{doc, score}] best first; ties broken by document order (deterministic).
 */
export function search(index, query, { k = 8, filter, boost } = {}) {
  const { docs, postings, lengths, avgdl, k1, b, N } = index;
  const terms = [...new Set(tokenize(query))];
  const scores = new Map();
  for (const t of terms) {
    const p = postings.get(t);
    if (!p) continue;
    const df = p.length / 2;
    const idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
    for (let j = 0; j < p.length; j += 2) {
      const i = p[j], tf = p[j + 1];
      const s = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * lengths[i] / avgdl));
      scores.set(i, (scores.get(i) || 0) + s);
    }
  }
  const ranked = [];
  for (const [i, score] of scores) {
    if (filter && !filter(docs[i])) continue;
    ranked.push({ i, score: boost ? score * boost(docs[i]) : score });
  }
  ranked.sort((x, y) => y.score - x.score || x.i - y.i);
  return ranked.slice(0, k).map(({ i, score }) => ({ doc: docs[i], score }));
}
