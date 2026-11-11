// Case file: an intro card when a run starts and a verdict card when it ends.
// Everything shown comes from the run's own events; nothing is made up here.
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// what each investigator does, as world.html's send() calls describe it
const ROLE = { Identifier: 'who is in the story', Archivist: 'reads the sources', Timekeeper: 'quotes the claims',
  Sceptic: 'finds where they disagree', Editor: 'writes up the case' };

document.head.insertAdjacentHTML('beforeend', `<style>
  .cf { position:fixed; z-index:1; background:#ffffffee; color:#1b1b1b; border:3px solid #1b1b1b; border-radius:14px;
    box-shadow:0 5px 0 #1b1b1b; font-family:'Nunito', ui-rounded, system-ui, sans-serif; font-weight:800; }
  .cf small { display:block; font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:#3a3a3a; }
  #cf-intro { z-index:3; left:50%; top:50%; width:min(440px,calc(100vw - 32px)); padding:18px 22px; pointer-events:none;
    transform:translate(-50%,-50%); transition:transform .5s cubic-bezier(.6,-.3,.7,.4), opacity .5s; }
  #cf-intro.away { transform:translate(-50%,-160%); opacity:0; }
  #cf-intro h2 { margin:4px 0 12px; font:900 22px/1.2 'Nunito', ui-rounded, sans-serif; }
  #cf-intro ul { list-style:none; margin:0; padding:0; display:grid; gap:5px; font-size:13px; }
  #cf-intro li b { background:var(--c); padding:0 6px; border-radius:6px; border:2px solid #1b1b1b; margin-right:6px; }
  #cf-card { right:14px; top:66px; width:min(290px,calc(100vw - 170px)); max-height:calc(100vh - 250px); overflow:auto; padding:10px 14px; font-size:13px; }
  #cf-card summary { cursor:pointer; font-weight:900; font-size:15px; line-height:1.25; list-style:none; }
  #cf-card summary::-webkit-details-marker { display:none; }
  #cf-card summary small::before { content:'▸ '; } #cf-card[open] summary small::before { content:'▾ '; }
  #cf-card summary small { margin-bottom:2px; }
  #cf-card .n { display:flex; gap:12px; margin:10px 0 4px; } #cf-card .n b { display:block; font:900 20px/1 'Nunito', sans-serif; }
  #cf-card .n .red b { color:#ff2d2d; }
  #cf-card .v { margin-top:10px; padding-top:8px; border-top:2px dashed #1b1b1b; }
  #cf-card .v b { color:#ff2d2d; font-size:16px; } #cf-card .v b.p { color:#1b1b1b; background:#ffd24a; padding:0 5px; border-radius:6px; }
  #cf-card a { display:inline-block; color:#0068b8; margin-right:6px; overflow-wrap:anywhere; }
  #cf-card .t { margin:8px 0 0; font-weight:700; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
  #cf-card .t.all { display:block; }
  #cf-card button.more { all:unset; cursor:pointer; color:#0068b8; font-weight:900; font-size:12px; text-decoration:underline; }
  #cf-card button.more:focus-visible { outline:2px solid #0068b8; }
  body:has(#cf-card) #verdict { display:none !important; }  /* the card carries the verdict text now */
  #flash { font-family:'Nunito', ui-rounded, sans-serif; font-size:clamp(28px,9vw,54px); width:max-content; max-width:calc(100vw - 24px);
    white-space:normal; text-align:center; padding:10px clamp(12px,4vw,26px); }
  #flash small { display:block; margin-top:6px; font-size:clamp(16px,5vw,24px); }
  #flash small.q { font-size:clamp(12px,3.4vw,15px); font-weight:800; opacity:.9; }
  @media (max-width:500px) {
    header { flex-wrap:wrap; padding:10px 8px; gap:8px; }
    header h1 { font-size:22px; margin:0 auto 0 4px; }
    header input { order:3; flex:1 1 100%; max-width:none; }
    header button { padding:7px 10px; font-size:12px; }
    #stats { top:116px; left:8px; right:8px; grid-auto-flow:column; gap:6px; padding:6px 10px; }
    #stats .st b, #stats .st.red b { font-size:22px; } #stats .st span { font-size:9px; display:block; line-height:1.15; }
    #key { display:none !important; }
    #via { left:8px; right:8px; bottom:8px; font-size:10px; }
    #verdict, #detail:not([hidden]) ~ #verdict { left:8px; right:8px; width:auto; transform:none; bottom:62px; }
    #detail { left:8px; right:8px; width:auto; top:180px; }
    #cf-card { top:auto; bottom:62px; left:8px; right:8px; width:auto; max-height:55vh; }
    #cf-card:not([open]) summary .l { display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  }
  @media (prefers-reduced-motion:reduce) { #cf-intro { transition:opacity .3s; } #cf-intro.away { transform:translate(-50%,-50%); } }
</style>`);

const card = (id, tag = 'div') => { document.getElementById(id)?.remove(); const el = document.createElement(tag); el.id = id; el.className = 'cf'; document.body.append(el); return el; };
let R, fmt;

export function start(premise, crew, pretty) {
  const t = new Date(), p = n => String(n).padStart(2, '0');
  R = { src: {}, claims: {}, conflicts: [], q: {}, stats: null };
  fmt = pretty;
  document.getElementById('cf-card')?.remove();
  const el = card('cf-intro');
  el.setAttribute('role', 'status');
  // the case number is the run's own start time
  el.innerHTML = `<small>Case file RS-${t.getFullYear()}${p(t.getMonth() + 1)}${p(t.getDate())}-${p(t.getHours())}${p(t.getMinutes())}</small>
    <h2>${esc(premise)}</h2><small>On the case</small>
    <ul>${Object.values(crew).map(a => `<li><b style="--c:${a.color}">${esc(a.name)}</b>${esc(ROLE[a.name] || '')}</li>`).join('')}</ul>`;
  setTimeout(() => el.classList.add('away'), 2500);
  setTimeout(() => el.remove(), 3100);
}

export function on(e) {
  if (!R) return;
  if (e.type === 'source') R.src[e.id] = e;
  else if (e.type === 'claim') R.claims[e.id] = e;
  else if (e.type === 'question') R.q[e.id] = e;
  else if (e.type === 'conflict') {
    R.conflicts.push(e);  // world.html has just shown the banner: say what conflicts
    const q = R.q[e.question_id]?.text || '';
    document.getElementById('flash').innerHTML = `Contradiction!<small>${e.values.map(v => esc(fmt(v))).join(' vs ')}</small>` +
      (q ? `<small class="q">${esc(q.length > 70 ? q.slice(0, 69) + '…' : q)}</small>` : '');
  }
  else if (e.type === 'stats') R.stats = e;
  else if (e.type === 'verdict') verdict(e);
}

function verdict(e) {
  const s = R.stats || {}, k = R.conflicts;
  const line = k.length ? `Sources disagree: ${R.q[k[0].question_id]?.text || k[0].summary}` : e.text.split(/(?<=\.)\s/)[0];
  const n = (v, label, cls = '') => `<span class="${cls}"><b>${v ?? '–'}</b>${label}</span>`;
  const el = card('cf-card', 'details');
  el.open = !matchMedia('(max-width:500px)').matches;  // on a phone it starts folded so the string stays visible
  el.innerHTML = `<summary><small>Finding</small><span class="l">${esc(line)}</span></summary>
    <div class="n">${n(s.sources, ' sources')}${n(s.claims, ' claims')}${n(s.conflicts ?? k.length, ' contradictions', 'red')}</div>
    <p class="t">${esc(e.text)}</p><button class="more" type="button">more</button>` +
    k.map(c => `<div class="v">${c.values.map(v => {
      const seen = new Set(), srcs = c.claim_ids.map(id => R.claims[id]).filter(cl => cl && cl.normalized === v)
        .map(cl => R.src[cl.source_id]).filter(x => x && !seen.has(x.url) && seen.add(x.url));
      const links = srcs.slice(0, 3).map(x => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.domain)}</a>`).join('');
      return `<div><b class="${v === c.primary_value ? 'p' : ''}">${esc(fmt(v))}</b> ${srcs.length} source${srcs.length === 1 ? '' : 's'}${v === c.primary_value ? ', matches the primary record' : ''}<br>${links}${srcs.length > 3 ? ` +${srcs.length - 3} more` : ''}</div>`;
    }).join('<div>vs</div>')}</div>`).join('');
  const t = el.querySelector('.t'), b = el.querySelector('.more');
  const fit = () => { if (el.open && !t.classList.contains('all')) b.hidden = t.scrollHeight <= t.clientHeight + 1; };
  b.onclick = () => { b.textContent = t.classList.toggle('all') ? 'less' : 'more'; };
  el.addEventListener('toggle', fit); fit();
}
