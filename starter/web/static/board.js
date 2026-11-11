// Detective's corkboard: the run's claims pinned as paper cards, grouped by answer,
// with a red string between answers that contradict. Built only from the run's events.
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const clip = (s, n) => (s = String(s ?? '')).length > n ? s.slice(0, n - 1) + '…' : s;
const tilt = id => { let h = 0; for (const c of String(id)) h = h * 31 + c.charCodeAt(0) | 0; return (h % 7) / 2.5; };  // stable -2.4..2.4deg
const NS = 'http://www.w3.org/2000/svg';

document.head.insertAdjacentHTML('beforeend', `<style>
  #board { position:fixed; inset:0; z-index:20; overflow:auto; transform:translateY(100%); visibility:hidden;
    transition:transform .45s cubic-bezier(.2,.8,.2,1), visibility 0s .45s;
    background-color:#b98a5e;
    background-image:radial-gradient(#6e4a2c99 1.2px, transparent 2px), radial-gradient(#e0bd9266 1.4px, transparent 2.2px),
      radial-gradient(#5a3a2066 2.5px, transparent 3.5px), radial-gradient(ellipse at 30% 20%,#d2a476,transparent 60%), linear-gradient(135deg,#c49468,#a5774d);
    background-size:13px 17px, 19px 23px, 41px 37px, 100% 100%, 100% 100%; background-position:0 0, 7px 11px, 19px 5px, 0 0, 0 0;
    box-shadow:inset 0 0 0 14px #6b4426, inset 0 0 60px #0006; font-family:'Nunito', ui-rounded, system-ui, sans-serif; color:#1b1b1b; }
  #board.open { transform:none; visibility:visible; transition:transform .45s cubic-bezier(.2,.8,.2,1); }
  #board .in { position:relative; padding:24px 30px 60px; min-height:100%; box-sizing:border-box; }
  #board .top { display:flex; align-items:center; gap:12px; margin-bottom:18px; }
  #board .top h2 { margin:0; font:900 24px/1.1 'Nunito', sans-serif; color:#fff; text-shadow:0 2px 0 #4a2e18; }
  #board .top h2 b { color:#ff2d2d; text-shadow:0 2px 0 #4a2e18; }
  #board .top button { margin-left:auto; }
  #board .empty { color:#fff; font-weight:800; text-shadow:0 1px 0 #4a2e18; }
  #board section { margin:0 0 30px; }
  #board h3 { display:inline-block; margin:0 0 14px; padding:8px 14px; background:#fffef4; border-radius:2px; font:800 15px/1.3 'Nunito', sans-serif;
    box-shadow:0 3px 6px #0005; max-width:min(720px,100%); background-image:repeating-linear-gradient(transparent 0 21px,#9cc3e6 21px 22px); }
  #board .answers { display:flex; flex-wrap:wrap; gap:22px; align-items:flex-start; }
  #board .answers.red { justify-content:space-around; max-width:1100px; }
  #board .ans { display:flex; flex-direction:column; gap:12px; width:220px; }
  #board .ans > b { align-self:flex-start; padding:2px 8px; background:#efe9df; border:2px solid #1b1b1b; border-radius:6px; font-size:13px; }
  #board .ans.red > b { background:#ff2d2d; color:#fff; } #board .ans.primary > b { background:#ffd24a; }
  #board .card { position:relative; z-index:1; padding:14px 12px 10px; background:#fbf7ec; box-shadow:0 4px 8px #0006; font-size:12px; line-height:1.35;
    transform:rotate(var(--t)); }
  #board .card q { display:block; font:13px/1.4 Georgia, serif; margin:4px 0 0; }
  #board .card .d { font-weight:900; font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:#3a3a3a; overflow-wrap:anywhere; }
  #board .card.p .d::after { content:' · primary record'; color:#8a6d00; }
  #board .pin { position:absolute; left:50%; top:-6px; width:13px; height:13px; margin-left:-6.5px; border-radius:50%;
    background:radial-gradient(circle at 35% 35%,#fff8 0 2px,#d33 3px,#7a0f0f); box-shadow:0 2px 2px #0007; z-index:2; }
  #board .more { color:#fff; font-weight:800; font-size:12px; text-shadow:0 1px 0 #4a2e18; }
  #board svg { position:absolute; left:0; top:0; pointer-events:none; overflow:visible; z-index:3; }
  #board svg.under { z-index:0; }  /* agreeing thread runs behind the cards */
  #board .s { fill:none; stroke-linecap:round; }
  #board .s.red { stroke:#c8141b; stroke-width:2.6; filter:drop-shadow(0 2px 1px #0006); }
  #board .s.red.draw { animation:rs-draw 1.1s ease-out forwards; }
  #board .s.grey { stroke:#e8e2d6; stroke-width:1; opacity:.55; }
  #board .tag { position:absolute; z-index:4; transform:translate(-50%,-50%) rotate(-3deg); padding:3px 9px; background:#ff2d2d; color:#fff;
    font-weight:900; font-size:13px; border:2px solid #1b1b1b; border-radius:4px; white-space:nowrap; box-shadow:0 3px 0 #1b1b1b; }
  @keyframes rs-draw { to { stroke-dashoffset:0; } }
  @media (max-width:500px) { #board .in { padding:16px 14px 40px; } #board .ans { width:100%; } #board .answers.red { gap:14px; } #board .answers.red .ans { width:calc(50% - 7px); } #board .answers.red .ans > b { margin-bottom:34px; } #board .tag { font-size:12px; } #board .top h2 { font-size:20px; } }
  @media (prefers-reduced-motion:reduce) { #board, #board.open { transition:none; } #board .s.red.draw { animation:none; stroke-dashoffset:0 !important; } }
</style>`);

const btn = document.createElement('button');
btn.id = 'board-btn'; btn.className = 'ghost'; btn.textContent = 'Board'; btn.title = 'Open the evidence board';
btn.setAttribute('aria-expanded', 'false');
document.getElementById('replay').after(btn);
const el = document.createElement('div');
el.id = 'board'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', 'Evidence board');
document.body.append(el);

let R = null, fmt = v => v, ended = true, drawn = new Set(), queued = false;
const fresh = () => ({ q: {}, src: {}, claims: [], conflicts: [] });

function toggle(open = !el.classList.contains('open')) {
  el.classList.toggle('open', open); btn.setAttribute('aria-expanded', open);
  if (open) { render(); el.querySelector('.top button').focus(); } else btn.focus();
}
btn.onclick = () => toggle();
addEventListener('keydown', e => { if (e.key === 'Escape' && el.classList.contains('open')) toggle(false); });
addEventListener('resize', () => el.classList.contains('open') && strings());

export function reset() { R = fresh(); drawn = new Set(); ended = false; if (el.classList.contains('open')) render(); }  // every run, even after an interrupted one

export function on(e, pretty) {
  if (pretty) fmt = pretty;
  if (ended) { R = fresh(); drawn = new Set(); ended = false; }  // first event of a new run
  if (e.type === 'question') R.q[e.id] = e;
  else if (e.type === 'source') R.src[e.id] = e;
  else if (e.type === 'claim') R.claims.push(e);
  else if (e.type === 'conflict') R.conflicts.push(e);
  else if (e.type === 'verdict' || e.type === 'error' && e.question_id == null) ended = true;
  if (el.classList.contains('open') && !queued) { queued = true; requestAnimationFrame(() => { queued = false; render(); }); }
}

const MAX = 6;  // cards shown per answer; the rest are counted
function render() {
  const top = `<div class="top"><h2>Evidence <b>board</b></h2><button class="ghost">Close board</button></div>`;
  if (!R || !R.claims.length) {
    el.innerHTML = `<div class="in">${top}<p class="empty">No claims pinned yet. Press Investigate or Replay, then open the board.</p></div>`;
  } else {
    const red = {}; for (const k of R.conflicts) for (const v of k.values) red[k.question_id + '|' + v] = 1;
    const byQ = {}, hot = new Set(R.conflicts.map(k => k.question_id));
    for (const c of R.claims) ((byQ[c.question_id] ??= {})[c.normalized] ??= []).push(c);
    el.innerHTML = `<div class="in">${top}` + Object.entries(byQ).sort((a, b) => hot.has(b[0]) - hot.has(a[0])).map(([qid, ans]) => `<section>
      <h3>${esc(R.q[qid]?.text || qid)}</h3><div class="answers${hot.has(qid) ? ' red' : ''}">` +
      Object.entries(ans).sort((a, b) => b[1].length - a[1].length).map(([v, cs]) => {
        const prim = cs.some(c => R.src[c.source_id]?.primary);
        cs = [...cs].sort((a, b) => !!R.src[b.source_id]?.primary - !!R.src[a.source_id]?.primary);
        return `<div class="ans${red[qid + '|' + v] ? ' red' : prim ? ' primary' : ''}" data-k="${esc(qid + '|' + v)}">
          <b>${esc(fmt(v))} · ${cs.length} source${cs.length > 1 ? 's' : ''}</b>` +
          cs.slice(0, MAX).map(c => { const s = R.src[c.source_id] || {};
            return `<div class="card${s.primary ? ' p' : ''}" style="--t:${tilt(c.id)}deg"><i class="pin"></i>
              <span class="d">${esc(s.domain || 'source')}${s.publish_date ? ' · ' + esc(s.publish_date) : ''}</span>
              <q>${esc(clip(c.quote, 140))}</q></div>`; }).join('') +
          (cs.length > MAX ? `<span class="more">+ ${cs.length - MAX} more</span>` : '') + '</div>';
      }).join('') + '</div></section>').join('') + '</div>';
  }
  el.querySelector('.top button').onclick = () => toggle(false);
  strings();
}

// pin centre, in the coordinates of the board's scrolling content
function pin(card) {
  const r = card.querySelector('.pin').getBoundingClientRect(), o = el.firstElementChild.getBoundingClientRect();
  return [r.left + r.width / 2 - o.left, r.top + r.height / 2 - o.top];
}
function path(svg, [x1, y1], [x2, y2], cls) {
  const d = Math.hypot(x2 - x1, y2 - y1), sag = Math.min(80, 12 + d * .12);  // string droops under its own weight
  const p = document.createElementNS(NS, 'path');
  p.setAttribute('d', `M${x1},${y1} Q${(x1 + x2) / 2},${Math.max(y1, y2) + sag} ${x2},${y2}`);
  p.setAttribute('class', 's ' + cls); svg.append(p); return [p, (x1 + x2) / 2, (y1 + y2) / 2 + sag / 2];
}
function strings() {
  const inner = el.firstElementChild; if (!inner) return;
  inner.querySelectorAll('svg, .tag').forEach(n => n.remove());
  const layer = cls => { const s = document.createElementNS(NS, 'svg'); s.setAttribute('class', cls);
    s.setAttribute('width', inner.scrollWidth); s.setAttribute('height', inner.scrollHeight); inner.append(s); return s; };
  const under = layer('under'), svg = layer('');
  // faint grey thread down each answer's cards: these sources agree
  for (const a of inner.querySelectorAll('.ans')) {
    const cs = [...a.querySelectorAll('.card')];
    for (let i = 1; i < cs.length; i++) path(under, pin(cs[i - 1]), pin(cs[i]), 'grey');
  }
  for (const k of R?.conflicts || []) {
    const cards = k.values.map(v => inner.querySelector(`.ans[data-k="${CSS.escape(k.question_id + '|' + v)}"] .card`)).filter(Boolean);
    for (let i = 1; i < cards.length; i++) {
      const [p, mx, my] = path(svg, pin(cards[i - 1]), pin(cards[i]), 'red');
      const key = k.id + '|' + i, len = p.getTotalLength();
      p.style.strokeDasharray = len;
      if (!drawn.has(key)) { p.style.strokeDashoffset = len; p.classList.add('draw'); drawn.add(key); }
      const t = document.createElement('span');
      // on a phone the columns sit close, so the label goes in the gap above the pins, clear of the cards
      const y = matchMedia('(max-width:500px)').matches ? Math.min(...[cards[i - 1], cards[i]].map(c => pin(c)[1])) - 24 : my;
      t.className = 'tag'; t.style.left = mx + 'px'; t.style.top = y + 'px';
      t.textContent = fmt(k.values[i - 1]) + ' vs ' + fmt(k.values[i]);
      inner.append(t);
    }
  }
}
