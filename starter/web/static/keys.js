// Presenter shortcuts: each key clicks an existing button, so behaviour stays in one place.
const $ = id => document.getElementById(id);
const KEYS = { r: ['replay', 'Replay the saved run'], b: ['board-btn', 'Open or close the board'],
  m: [null, 'Mute or unmute voice and sound'], ' ': ['mic', 'Speak (mic)'], '?': [null, 'Show these shortcuts'] };

document.head.insertAdjacentHTML('beforeend', `<style>
  #keys { position:fixed; left:50%; top:50%; transform:translate(-50%,-50%); z-index:20; padding:14px 18px; background:#ffffffee; color:#1b1b1b;
    border:3px solid #1b1b1b; border-radius:14px; box-shadow:0 5px 0 #1b1b1b; font:800 14px 'Nunito', ui-rounded, system-ui, sans-serif; }
  #keys h2 { margin:0 0 8px; font-size:16px; font-weight:900; }
  #keys kbd { display:inline-block; min-width:56px; margin-right:10px; padding:1px 6px; text-align:center; border:2px solid #1b1b1b;
    border-radius:8px; box-shadow:0 2px 0 #1b1b1b; background:#ffd84a; font:900 13px inherit; }
  #keys div { margin:6px 0; }
</style>`);
const box = document.createElement('div');
box.id = 'keys'; box.hidden = true; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'Keyboard shortcuts');
box.innerHTML = '<h2>Shortcuts</h2>' + Object.entries(KEYS).map(([k, [, what]]) =>
  `<div><kbd>${k === ' ' ? 'Space' : k.toUpperCase()}</kbd>${what}</div>`).join('') + '<div><kbd>Esc</kbd>Close</div>';
document.body.append(box);

function mute() {  // one press silences both; if both are already silent, it brings both back
  const voice = $('mute'), sound = $('sfx');
  const on = [voice?.getAttribute('aria-pressed') === 'false' && voice, sound?.getAttribute('aria-pressed') === 'true' && sound].filter(Boolean);
  (on.length ? on : [voice, sound]).forEach(b => b?.click());
}

addEventListener('keydown', e => {
  const t = e.target;
  if (e.ctrlKey || e.metaKey || e.altKey || e.repeat || t.closest?.('input, textarea, select, [contenteditable]')) return;
  const k = e.key.toLowerCase();
  if (k === 'escape') return void (box.hidden = true);
  if (!(k in KEYS)) return;
  e.preventDefault();  // Space would otherwise also press whichever button has focus
  if (k === '?') box.hidden = !box.hidden;
  else if (k === 'm') mute();
  else $(KEYS[k][0])?.click();
});
