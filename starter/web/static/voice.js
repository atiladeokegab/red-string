// Voice for Red String: a mic button that speaks the premise in, and an Investigators' channel
// that logs every crew line and reads it aloud. Browser APIs only; world.html calls say() from send().
const $ = id => document.getElementById(id);
const synth = window.speechSynthesis;
const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
const PITCH = [1, .6, 1.5, .3, 1.9];  // one per crew member, in order of first line
const MAX_WAITING = 2;                // a replay talks faster than speech: the log keeps every line, the voice keeps up

document.head.insertAdjacentHTML('beforeend', `<style>
  #chan { position:fixed; left:10px; bottom:48px; width:270px; z-index:2; padding:6px 10px 8px; font-size:12px;
    background:#ffffffe8; color:#1b1b1b; border:3px solid #1b1b1b; border-radius:14px; box-shadow:0 5px 0 #1b1b1b; }
  #chan h2 { margin:0 0 4px; font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:.05em;
    display:flex; justify-content:space-between; align-items:center; }
  #chan-log { height:120px; overflow:auto; font-weight:700; line-height:1.3; }
  #chan-log p { margin:0 0 3px; } #chan-log p.now { background:#ffe98a; border-radius:4px; }
  #chan-log b { background:var(--c); padding:0 4px; border-radius:5px; margin-right:3px; }
  #mute { white-space:nowrap; padding:1px 8px; font-size:11px; box-shadow:0 2px 0 #1b1b1b; background:#fff; color:#1b1b1b; }
  #mic { background:#ffd24a; color:#1b1b1b; } #mic.on { background:var(--red); color:#fff; }
  @media (max-height:560px), (max-width:900px) { #chan { display:none; } }
  @media (max-width:900px) { header { flex-wrap:wrap; } }
</style>`);
$('replay').insertAdjacentHTML('afterend', '<button id="mic" title="Say what to investigate">Speak</button>');
document.body.insertAdjacentHTML('beforeend',
  `<section id="chan" aria-label="Investigators' channel"><h2>Investigators' channel <button id="mute"></button></h2><div id="chan-log" aria-live="off"></div></section>`);

let muted = localStorage.getItem('rs-mute') === '1', listening = false, speaking = null, timer;
const waiting = [], order = [];
const paint = () => { $('mute').textContent = muted ? 'Muted' : 'Voice on'; $('mute').setAttribute('aria-pressed', muted); };
const hush = () => { waiting.length = 0; speaking = null; clearTimeout(timer); synth?.cancel(); };

function next() {
  clearTimeout(timer); speaking?.row.classList.remove('now'); speaking = null;
  const job = waiting.shift();
  if (!job || muted || listening || !synth) return void (waiting.length = 0);
  const u = new SpeechSynthesisUtterance(`${job.name}. ${job.text}`), i = order.indexOf(job.name);
  const en = synth.getVoices().filter(v => v.lang.startsWith('en'));
  if (en.length) u.voice = en[i % en.length];
  u.pitch = PITCH[i % PITCH.length]; u.rate = 1.15;
  u.onend = u.onerror = () => speaking === job && next();
  speaking = job; job.u = u; job.row.classList.add('now');  // job.u: Chrome drops onend if the utterance is collected
  // Chrome sometimes never fires onend: cancel the stuck line so it does not sit ahead of the next one in the native queue
  timer = setTimeout(() => { if (speaking !== job) return; job.row.classList.remove('now'); speaking = null; synth.cancel(); next(); }, 15000);
  synth.speak(u);
}

// Called from send() for every crew line.
export function say(name, text, color) {
  if (text === 'standing by') return;  // reset noise: five at once, before every run
  if (!order.includes(name)) order.push(name);
  const row = document.createElement('p'), b = document.createElement('b');
  b.textContent = name; b.style.setProperty('--c', color || '#ddd'); row.append(b, text);
  const log = $('chan-log'); log.append(row); log.scrollTop = log.scrollHeight;
  if (muted || listening || !synth) return;
  const urgent = name === 'Sceptic' || name === 'Editor';  // the contradiction and the write-up are always spoken
  if (waiting.length >= MAX_WAITING) { const i = waiting.findIndex(j => !j.urgent); if (i >= 0) waiting.splice(i, 1); else if (!urgent) return; }
  waiting.push({ name, text, row, urgent });
  if (!speaking) next();
}

$('mute').onclick = () => { muted = !muted; localStorage.setItem('rs-mute', muted ? '1' : '0'); paint(); if (muted) hush(); };
for (const id of ['go', 'replay']) $(id).addEventListener('click', () => { hush(); $('chan-log').textContent = ''; });  // a new run starts a clean channel
paint();

const mic = $('mic');
if (!Rec) { mic.disabled = true; mic.title = 'This browser has no speech recognition. Try Chrome.'; }
else {
  const rec = new Rec(); rec.lang = 'en-US'; rec.interimResults = true;
  const off = () => { listening = false; mic.classList.remove('on'); mic.textContent = 'Speak'; };
  mic.onclick = () => {
    if (listening) return rec.stop();
    hush(); listening = true; mic.classList.add('on'); mic.textContent = '● Listening';  // quiet, or the mic hears the crew
    try { rec.start(); } catch { off(); }
  };
  rec.onresult = e => {
    const r = e.results[e.results.length - 1];
    $('premise').value = r[0].transcript.trim();
    if (r.isFinal && $('premise').value) { off(); $(new URLSearchParams(location.search).has('replay') ? 'replay' : 'go').click(); }
  };
  rec.onend = off;
  rec.onerror = e => { off(); mic.title = 'Microphone: ' + e.error; };
}
