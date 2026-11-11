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

let audio;  // the OpenAI line now playing
let muted = localStorage.getItem('rs-mute') === '1', listening = false, speaking = null, timer;
const waiting = [], order = [];
const paint = () => { $('mute').textContent = muted ? 'Muted' : 'Voice on'; $('mute').setAttribute('aria-pressed', muted); };
const hush = () => { waiting.length = 0; speaking = null; clearTimeout(timer); synth?.cancel(); audio?.pause(); };

function next() {
  clearTimeout(timer); speaking?.row.classList.remove('now'); speaking = null;
  const job = waiting.shift();
  if (!job || muted || listening || !synth) return void (waiting.length = 0);
  speaking = job; job.row.classList.add('now');
  if (waiting[0]) tts(waiting[0]);  // prefetch: the next line downloads while this one plays
  tts(job).then(url => {
    if (speaking !== job) return url && URL.revokeObjectURL(url);
    if (!url) return speakLocal(job);  // no key (503), offline or slow: the browser voice
    audio = new Audio(url);
    audio.onended = () => { URL.revokeObjectURL(url); if (speaking === job) next(); };  // a load error rejects play() below
    audio.play().catch(() => speaking === job && speakLocal(job));
    if (waiting[0]) tts(waiting[0]);
  });
}

// OpenAI voice per crew member (POST /api/tts, cached on the server); resolves to a blob URL, or null to fall back.
let ttsOff = false;  // one 503 means no key on this server: stop asking, use the browser voice
const tts = job => job.mp3 ??= ttsOff ? Promise.resolve(null) : fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ who: job.name, text: job.text.slice(0, 300) }), signal: AbortSignal.timeout(10000) })
  .then(r => { if (r.status === 503) ttsOff = true; return r.ok ? r.blob() : null; }).then(b => b && URL.createObjectURL(b)).catch(() => null);

function speakLocal(job) {
  const u = new SpeechSynthesisUtterance(`${job.name}. ${job.text}`), i = order.indexOf(job.name);
  const en = synth.getVoices().filter(v => v.lang.startsWith('en'));
  if (en.length) u.voice = en[i % en.length];
  u.pitch = PITCH[i % PITCH.length]; u.rate = 1.15;
  u.onend = u.onerror = () => speaking === job && next();
  job.u = u;  // job.u: Chrome drops onend if the utterance is collected
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
const run = () => $(new URLSearchParams(location.search).has('replay') ? 'replay' : 'go').click();
const off = () => { listening = false; mic.classList.remove('on'); mic.textContent = 'Speak'; };
const start = label => { hush(); listening = true; mic.classList.add('on'); mic.textContent = label; };  // quiet, or the mic hears the crew
let rec, recorder, sttOff = !window.MediaRecorder || !navigator.mediaDevices?.getUserMedia;
if (Rec) {
  rec = new Rec(); rec.lang = 'en-US'; rec.interimResults = true;
  rec.onresult = e => {
    const r = e.results[e.results.length - 1];
    $('premise').value = r[0].transcript.trim();
    if (r.isFinal && $('premise').value) { off(); run(); }
  };
  rec.onend = off;
  rec.onerror = e => { off(); mic.title = 'Microphone: ' + e.error; };
}
const browserMic = () => { if (!rec) return off(); start('● Listening'); try { rec.start(); } catch { off(); } };

// OpenAI transcription first (Web Speech struggles in a noisy room); a 503 or any failure falls back to Web Speech.
async function record() {
  start('● Recording');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks = [], mine = recorder = new MediaRecorder(stream);
    mine.ondataavailable = e => chunks.push(e.data);
    mine.onstop = async () => {
      stream.getTracks().forEach(t => t.stop()); recorder = null; mic.textContent = '… Transcribing';
      const blob = new Blob(chunks, { type: mine.mimeType || 'audio/webm' });
      try {
        const r = await fetch('/api/stt', { method: 'POST', body: blob, headers: { 'Content-Type': blob.type }, signal: AbortSignal.timeout(15000) });
        if (r.status === 503) sttOff = true;  // no key on this server: go straight to Web Speech from now on
        const text = r.ok && (await r.json()).text?.trim();
        if (!text) throw new Error('no transcript');
        off(); $('premise').value = text; run();
      } catch { off(); browserMic(); }  // say it again, to the browser's recogniser
    };
    mine.start(); setTimeout(() => recorder === mine && mine.stop(), 20000);  // 20 s of opus stays far under the 2 MB cap
  } catch { sttOff = true; off(); browserMic(); }
}

mic.disabled = !rec && sttOff;
if (mic.disabled) mic.title = 'This browser cannot record. Try Chrome.';
mic.onclick = () => {  // click to start, click again to stop
  if (recorder) return recorder.stop();
  if (listening) return rec?.stop();
  sttOff ? browserMic() : record();
};
