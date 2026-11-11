// "Powered by Parallel" strip: counts this run's Parallel API calls by endpoint, from the event stream.
const NAMES = { search: 'Search', extract: 'Extract', task: 'Task', findall: 'FindAll', monitor: 'Monitor' };
const n = {}, chip = {};

document.head.insertAdjacentHTML('beforeend', `<style>
  #hud { position:fixed; left:50%; top:100px; transform:translateX(-50%); z-index:2; display:flex; gap:6px; align-items:center;
    padding:5px 8px; background:#ffffffe8; color:#1b1b1b; border:3px solid #1b1b1b; border-radius:14px; box-shadow:0 5px 0 #1b1b1b;
    font:900 12px 'Nunito', ui-rounded, system-ui, sans-serif; white-space:nowrap; pointer-events:none; }
  #hud > span { color:#3a3a3a; font-weight:800; margin-right:2px; }
  #hud i { font-style:normal; padding:2px 8px; border:2px solid #1b1b1b; border-radius:10px; background:#00a2ff; color:#fff; }
  #hud i.off { background:#e6e3de; color:#8a8580; border-color:#b9b4ad; }
  #hud i.pulse { animation:hudpulse .45s ease-out; }
  @keyframes hudpulse { 40% { transform:scale(1.25); background:#ffd84a; color:#1b1b1b; } }
  @media (max-width:500px) { #hud { display:none; } }
</style>`);
const hud = document.createElement('div');
hud.id = 'hud'; hud.setAttribute('aria-label', 'Parallel API calls this run');
hud.innerHTML = '<span>Powered by Parallel</span>';
for (const k in NAMES) { chip[k] = document.createElement('i'); hud.append(chip[k]); }
document.body.append(hud);

function set(k, v) {
  if (v === n[k]) return;
  const up = v > (n[k] || 0); n[k] = v;
  chip[k].textContent = NAMES[k] + (v ? ' ×' + v : '');
  chip[k].classList.toggle('off', !v);
  if (up) { chip[k].classList.remove('pulse'); void chip[k].offsetWidth; chip[k].classList.add('pulse'); }  // reflow restarts the animation
}
const reset = () => { for (const k in NAMES) { n[k] = -1; set(k, 0); } };
reset();
for (const id of ['go', 'replay']) document.getElementById(id)?.addEventListener('click', reset);  // a new run starts from zero

export function on(e) {
  // the engine counts searches in stats; newer events name their endpoint. max() avoids counting a search twice.
  if (e.type === 'stats' && e.searches != null) set('search', Math.max(n.search, e.searches));
  const k = String(e.endpoint || '').toLowerCase().replace(/[^a-z]/g, '');
  if (k in NAMES) set(k, n[k] + (e.count || 1));
}
