// Crew personalities: newsroom banter between the five investigators, driven only by real event fields.
// Pure module, no imports: banter(event, state) returns lines; the caller shows and speaks them.

export const PERSONAS = {
  Identifier: { attitude: 'eager rookie, names everyone, thinks out loud', emoji: ['🔎', '🙋', '👀'], speech: { pitch: 1.2, rate: 1.1 } },
  Archivist: { attitude: 'pedantic about dates and counts, keeps the tally', emoji: ['📚', '🗂️', '🧾'], speech: { pitch: 0.95, rate: 0.95 } },
  Timekeeper: { attitude: 'brisk, reads quotes aloud, minds the clock', emoji: ['⏱️', '📌', '🗞️'], speech: { pitch: 1.05, rate: 1.15 } },
  Sceptic: { attitude: 'dry, suspicious, trusts nothing twice', emoji: ['🧐', '🚩', '🪢'], speech: { pitch: 0.7, rate: 0.9 } },
  Editor: { attitude: 'calm chief, rules on disputes, wants it printable', emoji: ['🖋️', '📰', '✅'], speech: { pitch: 0.85, rate: 1.0 } },
};

const GAP_MS = 2500, STEP_MS = 2200;  // STEP_MS: spacing between lines returned together
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// ISO dates read better aloud as "20 Sep 2017"; anything else is shown as given
const show = v => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v)); return m ? `${+m[3]} ${MONTHS[m[2] - 1]} ${m[1]}` : String(v); };
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;

function pick(state, key, variants) {  // rotate through variants, skipping any line already said this run
  for (let k = 0; k < variants.length; k++) {
    const i = state.rot[key] = ((state.rot[key] ?? -1) + 1) % variants.length;
    if (variants[i].length && !variants[i].some(l => state.said.has(l.text))) return variants[i];
  }
  return [];
}
const line = (who, text, to) => ({ who, ...(to && { to }), text, emoji: PERSONAS[who].emoji[text.length % 3] });

function chatter(e, s) {  // the line an event earns on its own; counters update whether or not it gets said
  if (e.type === 'source') {
    const n = ++s.sources; s.dom[e.id] = e.domain;
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
      [line('Timekeeper', `Hold on, someone says ${v}.`), line('Sceptic', `I'm watching that one.`, 'Timekeeper')],
      [line('Identifier', `@Sceptic another answer just landed: ${v}.`, 'Sceptic'), line('Sceptic', `${towers} answers now. Interesting.`, 'Identifier')]]);
    if (n === 1) return pick(s, 'tower1', [
      [line('Timekeeper', `First answer on the board: ${v}.`)],
      [line('Identifier', `We've got an answer: ${v}.`)],
      [line('Archivist', `New answer tower: ${v}. Filed.`)]]);
    if ([2, 5, 10].includes(n)) return pick(s, 'agree', [
      [line('Timekeeper', `Another source backs ${v}. That's ${n}.`)],
      [line('Archivist', `${v} now has ${plural(n, 'source')}. Noted.`), line('Sceptic', 'Agreement is not proof.', 'Archivist')],
      [line('Identifier', `@Sceptic ${n} sources say ${v}.`, 'Sceptic'), line('Sceptic', 'Then the odd one out matters more.', 'Identifier')]]);
    return [];
  }
  if (e.type === 'question') { s.questions++; return []; }
  if (e.type === 'entity') return pick(s, 'ent', [[line('Identifier', `Adding ${e.name} to the wall.`)], [line('Identifier', `${e.name}, noted. Who else?`)]]);
  return [];
}

function filler(e, s) {  // small talk when the room has been quiet: every number and name from the event or the tally
  if (e.type === 'source') return pick(s, 'fsrc', [
    [line('Archivist', `${e.domain}, filed. That's ${s.sources}.`)],
    [line('Sceptic', `${e.domain}? Quote it or it didn't happen.`)],
    [line('Identifier', `${e.domain} is on this story too.`)],
    [line('Timekeeper', `${s.sources} sources in. Clock's running.`)]]);
  if (e.type === 'claim') {
    const v = show(e.normalized), n = s.answers[e.question_id][e.normalized], d = s.dom[e.source_id];
    return pick(s, 'fclaim', [
      d ? [line('Timekeeper', `${d} says ${v}.`)] : [],
      [line('Archivist', `${v}: ${plural(n, 'source')} so far.`)],
      n > 1 ? [line('Sceptic', `${v} again? That's ${n}. Hmm.`)] : [],
      d ? [line('Identifier', `@Archivist ${d} gives ${v}.`, 'Archivist')] : []]);
  }
  if (e.type === 'stats') return pick(s, 'fstats', [
    [line('Archivist', `Tally: ${e.sources} sources, ${e.claims} claims.`)],
    [line('Editor', `${e.searches} searches, ${e.sources} sources. Keep going.`)]]);
  if (e.type === 'question') return pick(s, 'fq', [
    [line('Identifier', `Question ${s.questions} is up. I'll take it.`)],
    [line('Editor', `That's ${s.questions} questions. Split them up.`)]]);
  return [];
}

function scene(e, s) {  // the red-string moment: a fixed little scene, every value from the event
  const [a, b] = e.values.map(show);
  const out = [line('Sceptic', `Stop. ${a} versus ${b}. Can't both be true.`)];
  if (e.primary_value) out.push(line('Archivist', `The primary record says ${show(e.primary_value)}.`, 'Sceptic'));
  out.push(...pick(s, 'react', [[line('Timekeeper', 'Red string going up. Nobody touch it.')], [line('Identifier', `@Sceptic so which one's real?`, 'Sceptic')]]));
  // the Editor's ruling waits for the scene to finish: a verdict arriving meanwhile merges it with the sign-off
  s.ruling = { run: e.primary_value ? `We run ${show(e.primary_value)}` : 'We report both', at: s.now0 + out.length * STEP_MS };
  return out;
}

function closing(s) {  // the verdict payoff: counts are this run's own tally of events
  const answered = Object.keys(s.answers).length;
  if (!s.conflicts) return [
    line('Sceptic', `${plural(s.sources, 'source')}, ${plural(s.claims, 'claim')}, no contradictions. Annoying.`),
    line('Archivist', `${plural(answered, 'question')} answered. Every claim quoted.`, 'Sceptic'),
    line('Editor', `If the Sceptic's satisfied, I'm satisfied. Signed off.`)];
  const ruling = s.ruling; s.ruling = null;
  return [
    line('Sceptic', `${plural(s.conflicts, 'red string')} on the wall. Told you.`),
    line('Editor', ruling ? `${ruling.run}, dispute flagged. Signed off.` : `${plural(s.sources, 'source')} read, dispute flagged. Signed off.`)];
}

export function banter(event, state) {
  state.rot ??= {}; state.answers ??= {}; state.dom ??= {}; state.said ??= new Set();
  state.sources ??= 0; state.claims ??= 0; state.questions ??= 0; state.conflicts ??= 0; state.last ??= -Infinity;
  const now = state.now0 = state.now ?? Date.now();  // state.now lets a replay or a test drive the clock
  let lines, base = 0;
  if (event.type === 'conflict' && event.values?.length >= 2) { state.conflicts++; lines = scene(event, state); }
  else if (event.type === 'verdict') { base = Math.max(0, (state.ruling?.at ?? 0) - now, state.last + STEP_MS - now); lines = closing(state); }
  else if (state.ruling && now >= state.ruling.at) {  // a mid-run scene: the ruling goes out on the next event after it
    lines = [line('Editor', `${state.ruling.run} and flag the dispute.`)]; state.ruling = null;
  } else {
    lines = chatter(event, state);
    if (now - state.last < GAP_MS) return [];
    if (!lines.length) lines = filler(event, state);
    lines = lines.slice(0, 2);
  }
  lines = lines.filter(l => !state.said.has(l.text));  // never the same line twice in a run
  lines.forEach((l, i) => { l.wait = base + i * STEP_MS; state.said.add(l.text); });  // wait: ms the caller holds the line
  if (lines.length) state.last = now + lines.at(-1).wait;
  return lines;
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
  ok(c.length === 3 && c.every((l, i) => l.wait === i * 2200), 'scene is 3 spaced lines');
  ok(/20 Sep 2017/.test(c[0].text) && /22 Sep 2017/.test(c[0].text) && c[0].who === 'Sceptic', 'Sceptic quotes both values');
  ok(c.some(l => l.who === 'Archivist'), 'Archivist notes primary');
  const vd = banter({ type: 'verdict' }, { ...s, said: new Set(s.said), now: 45200 });
  ok(vd.filter(l => l.who === 'Editor').length === 1 && /We run 20 Sep 2017, dispute flagged. Signed off./.test(vd.at(-1).text), 'Editor merges ruling and sign-off');
  ok(vd[0].wait >= 2200 * 3 - 100, 'verdict payoff waits for the scene');
  s.now = 52000; const rl = banter({ type: 'source', domain: 'w.com' }, s);
  ok(rl.length === 1 && rl[0].who === 'Editor' && /We run 20 Sep 2017 and flag/.test(rl[0].text), 'mid-run ruling follows the scene');
  const c2 = banter({ type: 'conflict', question_id: 'q9', values: ['A', 'B'] }, s);
  ok(!c2.some(l => l.who === 'Archivist'), 'no primary claim when the event has none');
  s.ruling = null; ok(at(52500, { type: 'source', domain: 'y.com' }).length === 0, 'scene resets the rate limit');
  for (const l of [...all, ...c2]) ok(words(l) <= 12, 'too long: ' + l.text), ok(PERSONAS[l.who], 'unknown speaker ' + l.who);
  let last = -Infinity;
  for (let i = 0; i < 200; i++) { s.now = 50000 + i * 300; if (banter({ type: 'source', domain: 'z.com' }, s).length) { ok(s.now - last >= GAP_MS, 'gap'); last = s.now; } }
  const v = closing({ sources: 3, claims: 7, conflicts: 0, answers: { q1: {}, q2: {} } });
  ok(v[0].who === 'Sceptic' && /3 sources, 7 claims/.test(v[0].text) && /2 questions/.test(v[1].text) && v.at(-1).who === 'Editor', 'no-contradiction payoff quotes the tally');
  // a full fake run at the replay pace (60ms per event): never quiet for 5s, never a repeat
  const r = { now: 0 }, said = [], times = [];
  const kinds = i => i % 7 === 0 ? { type: 'stats', searches: i >> 3, sources: i >> 1, claims: i >> 2 } : i % 3 ? { type: 'source', id: 's' + i, domain: ['a.com', 'b.org', 'c.net'][i % 3] }
    : { type: 'claim', question_id: 'q' + (i % 2), source_id: 's' + (i - 1), normalized: String(i % 4) };
  for (let i = 0; i < 300; i++) { r.now = i * 60; const out = banter(kinds(i), r); if (out.length) times.push(r.now); said.push(...out.map(l => l.text)); }
  said.push(...banter({ type: 'verdict' }, r).map(l => l.text));
  ok(new Set(said).size === said.length, 'a line repeated within the run');
  ok(Math.max(...times.map((t, i) => t - (times[i - 1] ?? 0))) < 5000, 'quiet for 5s or more');
  for (const t of said) ok(t.split(/\s+/).length <= 12, 'too long: ' + t);
  console.log('persona selfTest ok');
  return true;
}
