// Synthesized sound for the world: Web Audio only, no files. Silent until the first user gesture (autoplay rules).
const PITCH = { Identifier: 523, Archivist: 440, Timekeeper: 392, Sceptic: 330, Editor: 587 };  // one wooden note per detective
let ctx, out, on = true, lastPop = 0, lastHop = 0;
const log = (...a) => console.debug('[sfx]', ...a);

function start() {
  if (ctx) return ctx.resume();
  ctx = new AudioContext();
  out = ctx.createGain(); out.gain.value = 0.22; out.connect(ctx.destination);  // low: the crew also speaks aloud
  // room tone: looped brown-ish noise, low-passed, barely there
  const buf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate), d = buf.getChannelData(0);
  for (let i = 0, y = 0; i < d.length; i++) d[i] = y = (y + 0.02 * (Math.random() * 2 - 1)) / 1.02;
  const src = ctx.createBufferSource(), lp = ctx.createBiquadFilter(), g = ctx.createGain();
  src.buffer = buf; src.loop = true; lp.frequency.value = 350; g.gain.value = 0.5;
  src.connect(lp).connect(g).connect(out); src.start();
  log('audio started');
}
for (const ev of ['pointerdown', 'keydown']) addEventListener(ev, start, { once: true, capture: true });

const live = () => ctx && on && ctx.state === 'running';
function env(node, t, peak, decay) {  // fast attack, exponential decay
  const g = ctx.createGain(); g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(peak, t + 0.005); g.gain.exponentialRampToValueAtTime(0.0001, t + decay);
  node.connect(g).connect(out); return g;
}
function tone(type, f, peak, decay, delay = 0, f2) {
  const t = ctx.currentTime + delay, o = ctx.createOscillator();
  if (window.speechSynthesis?.speaking) peak *= 0.4;  // duck under the crew's voice; the string twang itself stays full
  o.type = type; o.frequency.setValueAtTime(f, t); if (f2) o.frequency.exponentialRampToValueAtTime(f2, t + decay);
  env(o, t, peak, decay); o.start(t); o.stop(t + decay + 0.05);
}

export function hop(name) {  // soft wooden tok
  const now = performance.now(); if (now - lastHop < 70) return; lastHop = now;  // bursts of jobs stay a patter, not a roll
  log('hop', name); if (!live()) return;
  const f = PITCH[name] || 440;
  tone('triangle', f, 0.35, 0.09, 0, f * 0.7);
  tone('sine', f * 2.7, 0.08, 0.04);
}

export function pop() {  // light pop for an answer block; shortcut: drops pops closer than 120 ms, enough for a 50-claim burst
  const now = performance.now(); if (now - lastPop < 120) return; lastPop = now;
  log('pop'); if (!live()) return;
  tone('sine', 900 + Math.random() * 300, 0.18, 0.07, 0, 1800);
}

export function twang() {  // Karplus-Strong plucked string, then a low sting
  log('twang'); if (!live()) return;
  const sr = ctx.sampleRate, p = Math.round(sr / 196), buf = ctx.createBuffer(1, sr * 1.6, sr), d = buf.getChannelData(0);
  for (let i = 0; i < p; i++) d[i] = Math.random() * 2 - 1;
  for (let i = p; i < d.length; i++) d[i] = 0.996 * 0.5 * (d[i - p] + d[i - p + 1]);
  const s = ctx.createBufferSource(), g = ctx.createGain(); s.buffer = buf; g.gain.value = 0.5;
  s.connect(g).connect(out); s.start();
  tone('sawtooth', 73, 0.12, 1.4, 0.35); tone('sine', 55, 0.3, 1.6, 0.35);
}

export function end() {  // two-note resolve when the case is written up
  log('end'); if (!live()) return;
  tone('triangle', 392, 0.2, 0.5); tone('triangle', 523, 0.2, 0.8, 0.18);
}

// speaker toggle, next to Replay, in the existing button style
const b = document.createElement('button');
b.className = 'ghost'; b.title = 'Sound effects on or off'; b.setAttribute('aria-pressed', 'true'); b.textContent = 'Sound on';
b.onclick = () => { on = !on; b.textContent = on ? 'Sound on' : 'Sound off'; b.setAttribute('aria-pressed', on); if (out) out.gain.value = on ? 0.22 : 0; };
document.getElementById('replay')?.after(b);
