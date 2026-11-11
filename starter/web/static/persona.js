// Crew personalities: newsroom banter between the five investigators, driven only by real event fields.
// Pure module, no imports: banter(event, state) returns lines; the caller shows and speaks them.

export const PERSONAS = {
  Identifier: { attitude: 'eager rookie, names everyone, thinks out loud', emoji: ['🔎', '🙋', '👀'], speech: { pitch: 1.2, rate: 1.1 } },
  Archivist: { attitude: 'pedantic about dates and counts, keeps the tally', emoji: ['📚', '🗂️', '🧾'], speech: { pitch: 0.95, rate: 0.95 } },
  Timekeeper: { attitude: 'brisk, reads quotes aloud, minds the clock', emoji: ['⏱️', '📌', '🗞️'], speech: { pitch: 1.05, rate: 1.15 } },
  Sceptic: { attitude: 'dry, suspicious, trusts nothing twice', emoji: ['🧐', '🚩', '🪢'], speech: { pitch: 0.7, rate: 0.9 } },
  Editor: { attitude: 'calm chief, rules on disputes, wants it printable', emoji: ['🖋️', '📰', '✅'], speech: { pitch: 0.85, rate: 1.0 } },
};

const GAP_MS = 2500;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// ISO dates read better aloud as "20 Sep 2017"; anything else is shown as given
const show = v => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v)); return m ? `${+m[3]} ${MONTHS[m[2] - 1]} ${m[1]}` : String(v); };
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;

function pick(state, key, variants) {  // rotate so the same line never comes twice in a row
  const i = state.rot[key] = ((state.rot[key] ?? -1) + 1) % variants.length;
  return variants[i];
}
const line = (who, text, to) => ({ who, ...(to && { to }), text, emoji: PERSONAS[who].emoji[text.length % 3] });

function chatter(e, s) {  // candidate lines for one ordinary event; counters update whether or not they get said
  if (e.type === 'source') {
    const n = ++s.sources;
    if (n === 1) return pick(s, 'src1', [
      [line('Archivist', `First source on the pile: ${e.domain}.`), line('Sceptic', 'One source is a rumour, not a story.', 'Archivist')],
      [line('Archivist', `Source one is in. ${e.domain}, filed.`)]]);
    if ([10, 50, 100].includes(n)) return pick(s, 'srcN', [
      [line('Sceptic', `@Archivist that's source ${n}. You counting?`, 'Archivist'), line('Archivist', `Counting. ${n} exactly, latest from ${e.domain}.`, 'Sceptic')],
      [line('Archivist', `${n} sources read. ${e.domain} makes ${n}.`)],
      [line('Editor', `${n} sources in. Keep them coming, team.`)]]);
    if (e.primary && !s.primaryNoted) { s.primaryNoted = 1; return [line('Archivist', `${e.domain} is a primary record. Mark it gold.`)]; }
    return [];
  }
  if (e.type === 'claim') {
    s.claims++;
    const q = s.answers[e.question_id] ??= {}, n = q[e.normalized] = (q[e.normalized] ?? 0) + 1;
    const towers = Object.keys(q).length, v = show(e.normalized);
    if (n === 1 && towers > 1) return pick(s, 'tower2', [
      [line('Sceptic', `New tower: ${v}. That makes ${towers} answers.`), line('Timekeeper', 'One question, rival stories. Fun.', 'Sceptic')],
      [line('Timekeeper', `Hold on, someone says ${v}.`), line('Sceptic', `I'm watching that one.`, 'Timekeeper')]]);
    if (n === 1) return pick(s, 'tower1', [
      [line('Timekeeper', `First answer on the board: ${v}.`)],
      [line('Identifier', `We've got an answer: ${v}.`)]]);
    if ([2, 5, 10].includes(n)) return pick(s, 'agree', [
      [line('Timekeeper', `Another source backs ${v}. That's ${n}.`)],
      [line('Archivist', `${v} now has ${plural(n, 'source')}. Noted.`), line('Sceptic', 'Agreement is not proof.', 'Archivist')],
      [line('Identifier', `@Sceptic ${n} sources say ${v}.`, 'Sceptic'), line('Sceptic', 'Then the odd one out matters more.', 'Identifier')]]);
    return [];
  }
  if (e.type === 'entity') return pick(s, 'ent', [[line('Identifier', `Adding ${e.name} to the wall.`)], [], [line('Identifier', `${e.name}, noted. Who else?`)]]);
  if (e.type === 'verdict') return [line('Editor', `${plural(s.sources, 'source')} read. Case closed, print it.`)];
  return [];
}

function scene(e, s) {  // the red-string moment: a fixed little scene, every value from the event
  const [a, b] = e.values.map(show);
  const out = [line('Sceptic', `Stop. ${a} versus ${b}. Can't both be true.`)];
  if (e.primary_value) out.push(line('Archivist', `The primary record says ${show(e.primary_value)}.`, 'Sceptic'));
  out.push(pick(s, 'react', [line('Timekeeper', 'Red string going up. Nobody touch it.'), line('Identifier', `@Sceptic so which one's real?`, 'Sceptic')]));
  out.push(line('Editor', e.primary_value ? `We run ${show(e.primary_value)} and flag the dispute.` : 'We report both and flag the dispute.'));
  return out;
}

export function banter(event, state) {
  state.rot ??= {}; state.answers ??= {}; state.sources ??= 0; state.claims ??= 0; state.last ??= -Infinity;
  const now = state.now ?? Date.now();  // state.now lets a replay or a test drive the clock
  if (event.type === 'conflict' && event.values?.length >= 2) { state.last = now; return scene(event, state); }
  const lines = chatter(event, state);
  if (!lines.length || now - state.last < GAP_MS) return [];
  state.last = now;
  return lines.slice(0, 2);
}

export function selfTest() {
  const ok = (c, m) => { if (!c) throw new Error('persona selfTest: ' + m); };
  const words = l => l.text.split(/\s+/).length;
  const s = { now: 0 }, all = [];
  const at = (t, e) => { s.now = t; const r = banter(e, s); all.push(...r); return r; };
  ok(at(0, { type: 'source', id: 's1', domain: 'gao.gov', primary: true }).length >= 1, 'first source speaks');
  ok(at(100, { type: 'claim', question_id: 'q1', normalized: '2017-09-20' }).length === 0, 'rate limit holds within 2.5s');
  for (let i = 2; i <= 10; i++) at(3000 * i, { type: 'source', domain: 'x' + i + '.com' });
  ok(all.some(l => /source 10|10 sources|10 exactly|makes 10/.test(l.text)), '10th source milestone');
  at(40000, { type: 'claim', question_id: 'q1', normalized: '2017-09-20' });
  const t = at(45000, { type: 'claim', question_id: 'q1', normalized: '2017-09-22' });
  ok(t.some(l => /22 Sep 2017/.test(l.text)), 'new tower names its value');
  const c = at(45100, { type: 'conflict', question_id: 'q1', values: ['2017-09-20', '2017-09-22'], primary_value: '2017-09-20' });
  ok(c.length >= 3 && c.length <= 4, 'scene is 3-4 lines');
  ok(/20 Sep 2017/.test(c[0].text) && /22 Sep 2017/.test(c[0].text) && c[0].who === 'Sceptic', 'Sceptic quotes both values');
  ok(c.some(l => l.who === 'Archivist') && c.at(-1).who === 'Editor', 'Archivist notes primary, Editor rules');
  const c2 = banter({ type: 'conflict', question_id: 'q9', values: ['A', 'B'] }, s);
  ok(!c2.some(l => l.who === 'Archivist'), 'no primary claim when the event has none');
  ok(at(46000, { type: 'source', domain: 'y.com' }).length === 0, 'scene resets the rate limit');
  for (const l of [...all, ...c2]) ok(words(l) <= 12, 'too long: ' + l.text), ok(PERSONAS[l.who], 'unknown speaker ' + l.who);
  let last = -Infinity;
  for (let i = 0; i < 200; i++) { s.now = 50000 + i * 300; if (banter({ type: 'source', domain: 'z.com' }, s).length) { ok(s.now - last >= GAP_MS, 'gap'); last = s.now; } }
  console.log('persona selfTest ok');
  return true;
}
