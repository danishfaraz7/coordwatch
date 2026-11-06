(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const PC = {telegram:'#4de0b8', x:'#9aa8ff', youtube:'#ff8a65', tiktok:'#c792ff', instagram:'#ff7eb3', facebook:'#6aa8ff', snapchat:'#ffe066'};
const pcol = p => PC[p] || '#9ca3a3';
const LABEL = {x:'X', youtube:'YouTube', telegram:'Telegram', tiktok:'TikTok', instagram:'Instagram', facebook:'Facebook', snapchat:'Snapchat'};
const ORDER = ['x','youtube','telegram','tiktok','instagram','facebook','snapchat'];
const SIGNAL = {text_dup:'Copy-pasted text', sync:'Posting in sync', amplify:'Reshare loops', avatar:'Reused avatars', created:'Created together', handle:'Same handle'};
const KEYS = [['YOUTUBE_API_KEY','YouTube API key'],['TELEGRAM_API_ID','Telegram api_id'],['TELEGRAM_API_HASH','Telegram api_hash'],['X_BEARER_TOKEN','X bearer token'],['GEMINI_API_KEY','Gemini key (optional AI chat)']];
const GOLD = '#e8b86a', PINK = '#ef7aa0', VIOL = '#9a8cff', HOT = '#ff5a4d', TEAL = '#4de0d0';

const st = {status: null, sel: new Set(), uploads: {}, demo: false, jobId: null, res: null, scene: null, selected: null,
            cursor: 1, playing: false, cam: {x: 0, y: 0, k: 1, tx: 0, ty: 0, tk: 1}, hover: null, drag: null, pendingUpload: null};

async function api(path, opts = {}) {
  opts.headers = Object.assign({'X-Coordwatch': '1'}, opts.headers || {});
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
const hex2rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const rgba = (h, a) => { const [r, g, b] = hex2rgb(h); return `rgba(${r},${g},${b},${a})`; };
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const fmtDate = t => new Date(t).toISOString().slice(0, 10);
const fmtDT = s => (s || '').slice(0, 16).replace('T', ' ');
const fmtLag = m => m < 1 ? 'origin' : m < 90 ? `+${Math.round(m)}m` : m < 2880 ? `+${Math.round(m / 60)}h` : `+${Math.round(m / 1440)}d`;
const short = (t, n = 160) => { t = (t || '').replace(/\s+/g, ' ').trim(); return t.length > n ? t.slice(0, n - 1) + '…' : t; };
const title = s => s.replace(/\b\w/g, c => c.toUpperCase());

// ------------------------------------------------------------------ toolbar / platforms / settings
function renderChips() {
  const box = $('#chips'); box.innerHTML = '';
  for (const p of ORDER) {
    const info = st.status.platforms[p], up = st.uploads[p];
    const on = info.mode === 'live' ? st.sel.has(p) : !!up;
    const el = document.createElement('button');
    el.className = 'chip' + (on ? ' on' : '') + (info.mode === 'live' && !info.ready ? ' need' : '');
    const tag = info.mode === 'live' ? (info.ready ? 'live' : 'add key') : (up ? `✓ ${up.posts}` : 'import');
    el.innerHTML = `<i style="background:${pcol(p)};color:${pcol(p)}"></i>${LABEL[p]}<small>${esc(tag)}</small>`;
    el.title = info.mode === 'live' ? (info.ready ? 'Live collection via official API' : 'Needs credentials — click to add')
      : 'No public search API: import an export file (JSON/CSV). Click again to remove.';
    el.onclick = () => chipClick(p);
    box.appendChild(el);
  }
  $('#tgch').classList.toggle('hidden', !st.sel.has('telegram'));
}
function chipClick(p) {
  const info = st.status.platforms[p];
  if (info.mode === 'live') {
    if (!info.ready) return openSettings(p);
    st.sel.has(p) ? st.sel.delete(p) : st.sel.add(p);
  } else if (st.uploads[p]) delete st.uploads[p];
  else { st.pendingUpload = p; $('#fi').value = ''; $('#fi').click(); }
  renderChips();
}
$('#fi').addEventListener('change', async e => {
  const f = e.target.files[0], p = st.pendingUpload; if (!f || !p) return;
  try {
    const up = await api(`/api/upload?platform=${p}&filename=${encodeURIComponent(f.name)}`, {method: 'POST', body: await f.arrayBuffer()});
    st.uploads[p] = up; renderChips();
  } catch (err) { alert('Import failed: ' + err.message); }
});
function openSettings(focusPlat) {
  const c = st.status.credentials;
  $('#keys').innerHTML = KEYS.map(([k, lab]) => `<div class="krow"><label for="k_${k}">${esc(lab)}</label>
    <input id="k_${k}" type="password" autocomplete="off" placeholder="${c[k].set ? '•••••• saved — type to replace' : 'paste key'}" data-k="${k}">
    <span class="st ${c[k].set ? 'ok' : ''}">${c[k].set ? '✓ ' + (c[k].source === 'env' ? 'env var' : 'saved') : 'not set'}</span></div>`).join('');
  $('#storage-note').textContent = st.status.in_codespaces
    ? 'Codespaces detected: for permanent storage add these as Codespaces secrets (GitHub → Settings → Codespaces → Secrets); they become environment variables automatically.'
    : 'Saved to ~/.coordwatch/credentials.json on this computer (outside the repository, so it can never be committed).';
  $('#modal').classList.remove('hidden');
  const f = focusPlat === 'youtube' ? 'YOUTUBE_API_KEY' : focusPlat === 'x' ? 'X_BEARER_TOKEN' : focusPlat === 'telegram' ? 'TELEGRAM_API_ID' : null;
  if (f) $('#k_' + f).focus();
}
$('#gear').onclick = () => openSettings(); $('#w-key').onclick = () => openSettings();
$('#m-close').onclick = $('#m-cancel').onclick = () => $('#modal').classList.add('hidden');
$('#m-save').onclick = async () => {
  const upd = {}; document.querySelectorAll('#keys input').forEach(i => { if (i.value.trim()) upd[i.dataset.k] = i.value.trim(); });
  try { st.status = await api('/api/credentials', {method: 'POST', body: JSON.stringify(upd)}); renderChips(); $('#modal').classList.add('hidden'); }
  catch (err) { alert(err.message); }
};

// ------------------------------------------------------------------ run + poll (job card, minimise chip, abort)
function setDefaultDates() {
  const u = new Date(), s = new Date(Date.now() - 7 * 864e5);
  $('#until').value = fmtDate(u); $('#since').value = fmtDate(s);
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fmtEl = s => { s = Math.round(s); return s >= 60 ? `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s` : `${s}s`; };
let jobTimer = null;

async function startRun(demo) {
  if (st.job && st.job.running) { st.job.min = false; renderJob(); return; }       // a run is already in progress: just show it
  const topic = $('#topic').value.trim();
  if (!topic) { $('#topic').focus(); return; }
  st.demo = demo;
  const body = {topic, since: $('#since').value, until: $('#until').value, platforms: [...st.sel], depth: $('#depth').value,
    upload_ids: Object.values(st.uploads).map(u => u.id), demo, telegram_channels: $('#tgch').value, discount_verified: $('#dv').checked};
  let id;
  try { ({id} = await api('/api/run', {method: 'POST', body: JSON.stringify(body)})); }
  catch (err) { st.job = {id: null, running: false, min: false, status: 'error', log: [], error: err.message, topic, t0: Date.now(), lastChange: Date.now()}; renderJob(); return; }
  st.job = {id, running: true, min: false, status: 'running', log: [], error: null, topic, t0: Date.now(), lastChange: Date.now(), lastLen: 0};
  st.jobId = id; renderJob();
  clearInterval(jobTimer); jobTimer = setInterval(renderJob, 1000);
  pollJob(st.job);
}
async function pollJob(job) {
  try {
    while (job.running) {
      await sleep(700);
      const j = await api('/api/jobs/' + job.id);
      job.status = j.status; job.log = j.log; job.error = j.error;
      if (j.log.length !== job.lastLen) { job.lastLen = j.log.length; job.lastChange = Date.now(); }
      if (j.status === 'done') {
        job.running = false; st.res = await api(`/api/jobs/${job.id}/result`);
        clearInterval(jobTimer); $('#overlay').classList.add('hidden'); $('#jobchip').classList.add('hidden'); st.job = null; loadResult(); return;
      }
      if (j.status === 'error' || j.status === 'cancelled') { job.running = false; job.min = false; clearInterval(jobTimer); }
      renderJob();
    }
  } catch (err) { job.running = false; job.status = 'error'; job.error = 'Lost connection to the coordwatch server: ' + err.message; job.min = false; clearInterval(jobTimer); renderJob(); }
}
function renderJob() {
  const j = st.job, ov = $('#overlay'), chip = $('#jobchip'); if (!j) { ov.classList.add('hidden'); chip.classList.add('hidden'); return; }
  const el = (Date.now() - j.t0) / 1000, last = j.log.length ? j.log[j.log.length - 1].replace(/^\s*[\d.]+s\s+/, '') : 'starting…';
  const cancelling = j.running && j.cancelling, finished = !j.running;
  ov.classList.toggle('hidden', j.min && j.running); $('#o-spin').parentElement.parentElement.classList.toggle('bad', finished && j.status === 'error');
  $('#o-spin').parentElement.parentElement.classList.toggle('stopped', finished && j.status === 'cancelled');
  $('#o-title').textContent = cancelling ? 'Aborting…' : j.running ? `Analysing “${j.topic}”` : j.status === 'cancelled' ? 'Run aborted' : 'Run failed';
  $('#o-el').textContent = fmtEl(el);
  const idle = (Date.now() - j.lastChange) / 1000, hb = $('#o-hb');
  hb.className = 'o-hb' + (j.running && idle > 20 ? ' slow' : '');
  hb.textContent = !j.running ? (j.error || '') : idle > 20 ? `No new step for ${fmtEl(idle)} — still working. Big requests or API rate limits can take a while; you can minimise this and keep using the app, or abort.` : `Last update ${Math.round(idle)}s ago`;
  const pre = $('#o-log'), atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 30;
  pre.textContent = j.log.join('\n') + (finished && j.error && j.status === 'error' ? '\n\n✖ ' + j.error : ''); if (atBottom) pre.scrollTop = pre.scrollHeight;
  $('#o-min').classList.toggle('hidden', finished); $('#o-abort').classList.toggle('hidden', finished); $('#o-abort').disabled = !!cancelling; $('#o-close').classList.toggle('hidden', !finished);
  chip.classList.toggle('hidden', !(j.min && j.running)); chip.classList.toggle('bad', false);
  $('#jc-t').textContent = `${j.topic} · ${fmtEl(el)} · ${cancelling ? 'aborting…' : last}`;
}
async function abortJob() {
  const j = st.job; if (!j || !j.running || j.cancelling) return;
  if (!confirm('Abort this lookup? Posts collected so far will be discarded.')) return;
  j.cancelling = true; renderJob();
  try { await api(`/api/jobs/${j.id}/cancel`, {method: 'POST', body: '{}'}); } catch (e) { j.cancelling = false; alert(e.message); }
}
$('#o-min').onclick = () => { if (st.job) { st.job.min = true; renderJob(); } };
$('#o-abort').onclick = $('#jc-abort').onclick = e => { e.stopPropagation(); abortJob(); };
$('#o-close').onclick = () => { st.job = null; renderJob(); };
$('#overlay').addEventListener('mousedown', e => { if (e.target === $('#overlay') && st.job) { if (st.job.running) { st.job.min = true; } else st.job = null; renderJob(); } });   // click outside = minimise, never abort
$('#jobchip').onclick = () => { if (st.job) { st.job.min = false; renderJob(); } };
$('#jobchip').addEventListener('keydown', e => { if (e.key === 'Enter' && st.job) { st.job.min = false; renderJob(); } });
$('#run').onclick = () => startRun(false);
$('#demo').onclick = $('#w-demo').onclick = () => { $('#topic').value = 'Acme Bank'; $('#since').value = '2026-10-01'; $('#until').value = '2026-10-14'; $('#dv').checked = true; startRun(true); };
$('#topic').addEventListener('keydown', e => { if (e.key === 'Enter') startRun(false); });

// ------------------------------------------------------------------ scene
const cv = $('#cv'), ctx = cv.getContext('2d');
let W = 0, H = 0, DPR = 1, stars = [], dust = [];
function resize() { DPR = Math.min(window.devicePixelRatio || 1, 2); W = innerWidth; H = innerHeight; cv.width = W * DPR; cv.height = H * DPR; }
addEventListener('resize', resize); resize();

function mulberry(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function upperBound(arr, x) { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] <= x) lo = m + 1; else hi = m; } return lo; }

function buildScene(res) {
  const rnd = mulberry(7);
  const posts = res.posts.map(p => Object.assign({}, p, {ts: Date.parse(p.created_at)}));
  let t0 = Infinity, t1 = -Infinity; posts.forEach(p => { if (p.ts < t0) t0 = p.ts; if (p.ts > t1) t1 = p.ts; });
  if (t1 === t0) t1 = t0 + 3600e3;
  const acct = new Map(), narTs = new Map(), narAcct = new Map();
  for (const p of posts) {
    let a = acct.get(p.account); if (!a) acct.set(p.account, a = {id: p.account, name: p.author_name, platform: p.platform, first: p.ts, n: 0, group: p.coordinated_group});
    a.n++; a.first = Math.min(a.first, p.ts);
    if (p.narrative_id >= 0) {
      (narTs.get(p.narrative_id) || narTs.set(p.narrative_id, []).get(p.narrative_id)).push(p.ts);
      const m = narAcct.get(p.narrative_id) || narAcct.set(p.narrative_id, new Map()).get(p.narrative_id);
      if (!m.has(p.account) || m.get(p.account) > p.ts) m.set(p.account, p.ts);
    }
  }
  narTs.forEach(v => v.sort((a, b) => a - b));
  const nars = res.narratives.filter(n => n.id >= 0).sort((a, b) => b.posts - a.posts);
  const maxP = Math.max(1, ...nars.map(n => n.posts));
  const nodes = [], byNar = new Map();
  nars.forEach((n, i) => {
    const rank = nars.length > 1 ? i / (nars.length - 1) : 0, R = 150 + 190 * Math.pow(rank, 0.85), ang = i * 2.39996 + 0.6;
    const node = {kind: 'nar', id: n.id, d: n, rank: i, ang, R, x: Math.cos(ang) * R, y: Math.sin(ang) * R * 0.8, r: 12 + 26 * Math.sqrt(n.posts / maxP),
      ts: narTs.get(n.id) || [], first: Date.parse(n.first_seen), share: n.coordinated_post_share || 0, sats: []};
    const accts = [...(narAcct.get(n.id) || new Map()).entries()].sort((a, b) => a[1] - b[1]);
    const step = Math.max(1, Math.floor(accts.length / 14));
    for (let k = 0; k < accts.length && node.sats.length < 14; k += step) {
      const a = acct.get(accts[k][0]);
      node.sats.push({a, first: accts[k][1], ang0: rnd() * 6.28, rad: node.r + 10 + rnd() * 20, spd: (0.15 + rnd() * 0.35) * (rnd() < .5 ? -1 : 1)});
    }
    nodes.push(node); byNar.set(n.id, node);
  });
  const groups = res.coordinated_groups, maxG = Math.max(1, ...groups.map(g => g.size));
  groups.forEach((g, gi) => {
    let sx = 0, sy = 0, rmax = 0; const links = [];
    Object.entries(g.narratives || {}).forEach(([nid, cnt]) => { const nn = byNar.get(+nid); if (nn) { links.push({n: nn, w: cnt}); sx += Math.cos(nn.ang) * cnt; sy += Math.sin(nn.ang) * cnt; rmax = Math.max(rmax, nn.R); } });
    const ang = links.length ? Math.atan2(sy, sx) + (gi % 2 ? .25 : -.25) : gi * 1.7;
    const R = Math.max(400, rmax + 190) + (gi % 3) * 40;
    const node = {kind: 'grp', id: g.id, d: g, ang, R, x: Math.cos(ang) * R, y: Math.sin(ang) * R * 0.8, r: 10 + 16 * Math.sqrt(g.size / maxG),
      first: Date.parse(g.first_post), links, sats: []};
    g.accounts.slice(0, 30).forEach((id, k) => { const a = acct.get(id); if (a) node.sats.push({a, first: a.first, ang0: rnd() * 6.28, rad: node.r + 10 + (k % 3) * 9 + rnd() * 5, spd: (0.2 + rnd() * 0.4) * (k % 2 ? 1 : -1)}); });
    nodes.push(node);
  });
  const core = {kind: 'core', id: 'core', x: 0, y: 0, r: 30, share: res.meta.coordinated_post_share};
  nodes.push(core);
  stars = Array.from({length: 160}, () => ({x: (rnd() - .5) * 2400, y: (rnd() - .5) * 1600, r: rnd() * 1.3 + .2, p: rnd() * 6.28}));
  dust = Array.from({length: 240}, () => ({a: rnd() * 6.28, r: 36 + Math.pow(rnd(), 2) * 330, s: (rnd() - .5) * .08, z: rnd() * 1.6 + .4}));
  return {posts, acct, nodes, core, t0, t1, narTs, byNar, nars, groups};
}

function fitCamera() {
  const sc = st.scene; let m = 200; sc.nodes.forEach(n => { m = Math.max(m, Math.abs(n.x) + n.r + 90, (Math.abs(n.y) + n.r + 60) * 1.35); });
  const avail = Math.min(W - 460, (H - 190) * 1.5); st.cam.tk = clamp(avail / (2 * m), .35, 1.25); st.cam.tx = 0; st.cam.ty = -10;
  st.cam.k = st.cam.tk * .6; st.cam.x = st.cam.tx; st.cam.y = st.cam.ty;
}

function loadResult() {
  const res = st.res, sc = st.scene = buildScene(res);
  st.selected = null; st.cursor = 1; hidePanel();
  ['#welcome'].forEach(s => $(s).classList.add('hidden'));
  ['#tl', '#legend', '#dock', '#exp', '#posts-btn'].forEach(s => $(s).classList.remove('hidden'));
  $('#tlr').value = 1000; renderTicks(); updateBubble();
  const m = res.meta;
  $('#kpis').innerHTML = [['Posts', m.n_posts.toLocaleString(), ''], ['Accounts', m.n_accounts.toLocaleString(), ''], ['Narratives', m.n_narratives, ''],
    ['Coordinated accts', m.coordinated_accounts, `<em>${m.n_groups} group(s)</em>`], ['Coordinated posts', Math.round(m.coordinated_post_share * 100) + '%', '']]
    .map(([a, b, c]) => `<div><small>${a}</small><b>${b}${c}</b></div>`).join('');
  $('#exp-menu').innerHTML = ['report.html', 'results.json', 'posts.csv', 'narratives.csv', 'coordinated_groups.csv', 'origins.csv', 'volume_by_platform.csv']
    .map(f => `<a href="/api/jobs/${st.jobId}/download/${f}" ${f === 'report.html' ? 'target="_blank" rel="noopener"' : ''}>${f === 'report.html' ? '↗ Static report (HTML)' : '⭳ ' + f}</a>`).join('');
  fitCamera(); renderNotes(); fillPosts();
  $('#notes').classList.add('hidden');
}

function renderTicks() {
  const sc = st.scene, box = $('#tl-ticks'); box.innerHTML = '';
  for (let i = 0; i <= 4; i++) { const s = document.createElement('span'); s.style.top = (i * 25) + '%'; s.textContent = fmtDate(sc.t0 + (sc.t1 - sc.t0) * i / 4).slice(5); box.appendChild(s); }
}
function updateBubble() {
  const sc = st.scene; if (!sc) return; const b = $('#tl-bubble');
  b.style.top = (st.cursor * 100) + '%'; b.textContent = fmtDate(sc.t0 + (sc.t1 - sc.t0) * st.cursor).slice(5);
}
$('#tlr').addEventListener('input', e => { st.cursor = e.target.value / 1000; st.playing = false; $('#play').textContent = '▶'; updateBubble(); });
$('#play').onclick = () => { if (!st.scene) return; st.playing = !st.playing; $('#play').textContent = st.playing ? '❚❚' : '▶'; if (st.playing && st.cursor >= .999) st.cursor = 0; };

// ------------------------------------------------------------------ rendering
function visOf(first, tc) { const sc = st.scene, span = (sc.t1 - sc.t0) * .05 + 1; const v = clamp((tc - first) / span, 0, 1); return v * v * (3 - 2 * v); }
function glow(x, y, r, col, a) { const g = ctx.createRadialGradient(x, y, r * .2, x, y, r * 2.8); g.addColorStop(0, rgba(col, a)); g.addColorStop(1, rgba(col, 0)); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * 2.8, 0, 7); ctx.fill(); }
function orb(x, y, r, c1, c2) { const g = ctx.createRadialGradient(x - r * .35, y - r * .35, r * .08, x, y, r); g.addColorStop(0, c1); g.addColorStop(1, c2); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); }
function txt(s, x, y, size, col, weight = 600, align = 'left') { ctx.font = `${weight} ${size}px Inter,system-ui,sans-serif`; ctx.textAlign = align; ctx.fillStyle = col; ctx.shadowColor = '#000c'; ctx.shadowBlur = 6; ctx.fillText(s, x, y); ctx.shadowBlur = 0; }
function pill(s, x, y, col, right = false) { ctx.font = '600 10px Inter,system-ui'; const w = ctx.measureText(s).width + 10, x0 = right ? x - w : x; ctx.fillStyle = 'rgba(0,0,0,.45)'; ctx.beginPath(); ctx.roundRect(x0, y - 10, w, 15, 7); ctx.fill(); ctx.strokeStyle = rgba(col, .6); ctx.lineWidth = 1; ctx.stroke(); ctx.fillStyle = col; ctx.textAlign = 'left'; ctx.fillText(s, x0 + 5, y + 1); }

function related(n) {
  const sel = st.selected; if (!sel) return true; if (n === sel || n.kind === 'core') return true;
  if (sel.kind === 'grp') return n.kind === 'nar' && sel.links.some(l => l.n === n);
  if (sel.kind === 'nar') return n.kind === 'grp' && n.links.some(l => l.n === sel);
  return false;
}
function curR(n, tc) {
  if (n.kind === 'nar') { const c = upperBound(n.ts, tc), tot = Math.max(n.ts.length, 1); return n.r * (.4 + .6 * Math.sqrt(c / tot)); }
  return n.r;
}

let last = performance.now();
function frame(now) {
  const dt = Math.min(.05, (now - last) / 1000); last = now; const T = now / 1000;
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0); ctx.clearRect(0, 0, W, H);
  const sc = st.scene, cam = st.cam;
  cam.x += (cam.tx - cam.x) * .12; cam.y += (cam.ty - cam.y) * .12; cam.k += (cam.tk - cam.k) * .12;
  // stars
  ctx.save(); ctx.translate(W / 2 + cam.x * .3, H / 2 + cam.y * .3);
  for (const s of stars) { ctx.globalAlpha = .25 + .35 * Math.sin(T * .8 + s.p) ** 2; ctx.fillStyle = '#cfeee9'; ctx.beginPath(); ctx.arc(s.x * cam.k * .6, s.y * cam.k * .6, s.r, 0, 7); ctx.fill(); }
  ctx.restore(); ctx.globalAlpha = 1;
  if (!sc) { requestAnimationFrame(frame); return; }
  if (st.playing) { st.cursor += dt / 14; if (st.cursor >= 1) { st.cursor = 1; st.playing = false; $('#play').textContent = '▶'; } $('#tlr').value = Math.round(st.cursor * 1000); updateBubble(); }
  const tc = sc.t0 + (sc.t1 - sc.t0) * st.cursor;
  ctx.save(); ctx.translate(W / 2 + cam.x, H / 2 + cam.y); ctx.scale(cam.k, cam.k);
  ctx.globalCompositeOperation = 'lighter';
  // dust
  for (const d of dust) { d.a += d.s * dt; const x = Math.cos(d.a) * d.r, y = Math.sin(d.a) * d.r * .8; ctx.fillStyle = `rgba(232,184,106,${.18 + .12 * Math.sin(T + d.a * 4)})`; ctx.fillRect(x, y, d.z, d.z); }
  const nodes = sc.nodes;
  // group -> narrative links
  for (const g of nodes) if (g.kind === 'grp') {
    const vg = visOf(g.first, tc); if (vg <= 0) continue;
    const mw = Math.max(1, ...g.links.map(l => l.w));
    for (const l of g.links) {
      const vn = visOf(l.n.first, tc); if (vn <= 0) continue;
      const a = (related(g) && related(l.n) ? .55 : .1) * Math.min(vg, vn);
      const mx = (g.x + l.n.x) / 2 * .8, my = (g.y + l.n.y) / 2 * .8;
      ctx.strokeStyle = rgba(TEAL, a); ctx.lineWidth = .8 + 2.6 * Math.sqrt(l.w / mw);
      ctx.beginPath(); ctx.moveTo(g.x, g.y); ctx.quadraticCurveTo(mx, my, l.n.x, l.n.y); ctx.stroke();
      const f = (T * .22 + l.w * .13) % 1, u = 1 - f; const px = u * u * g.x + 2 * u * f * mx + f * f * l.n.x, py = u * u * g.y + 2 * u * f * my + f * f * l.n.y;
      ctx.fillStyle = rgba('#d8fffa', a * 1.4); ctx.beginPath(); ctx.arc(px, py, 2, 0, 7); ctx.fill();
    }
  }
  // core -> narrative gold beams (tapered, thicker = more volume)
  for (const n of nodes) if (n.kind === 'nar') {
    const v = visOf(n.first, tc); if (v <= 0) continue;
    const c = upperBound(n.ts, tc), w = (1.2 + 6 * Math.sqrt(c / Math.max(n.d.posts, 1))) * (related(n) ? 1 : .4);
    const dx = n.x, dy = n.y, L = Math.hypot(dx, dy), nx = -dy / L, ny = dx / L, a = (related(n) ? .8 : .22) * v;
    const g = ctx.createLinearGradient(0, 0, n.x, n.y); g.addColorStop(0, rgba(GOLD, .1 * a)); g.addColorStop(.6, rgba(GOLD, .55 * a)); g.addColorStop(1, rgba(n.share >= .5 ? HOT : GOLD, a));
    ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(nx * .6, ny * .6); ctx.lineTo(n.x + nx * w, n.y + ny * w); ctx.lineTo(n.x - nx * w, n.y - ny * w); ctx.lineTo(-nx * .6, -ny * .6); ctx.fill();
    for (let k = 0; k < 3; k++) { const f = (T * .18 + k / 3 + n.id * .07) % 1; ctx.fillStyle = rgba('#fff2c8', .55 * a); ctx.beginPath(); ctx.arc(n.x * f, n.y * f, 1.6, 0, 7); ctx.fill(); }
  }
  ctx.globalCompositeOperation = 'source-over';
  // satellites
  for (const n of nodes) {
    if (n.kind === 'core') continue; const v = visOf(n.first, tc); if (v <= 0) continue; const rel = related(n) ? 1 : .3;
    for (const s of n.sats) {
      const vs = visOf(s.first, tc) * v; if (vs <= 0) continue; const a = s.ang0 + T * s.spd, x = n.x + Math.cos(a) * s.rad, y = n.y + Math.sin(a) * s.rad * .85;
      const coord = !!s.a.group; ctx.globalAlpha = vs * rel;
      if (coord) { ctx.fillStyle = rgba(HOT, .35); ctx.beginPath(); ctx.arc(x, y, 5, 0, 7); ctx.fill(); }
      ctx.fillStyle = pcol(s.a.platform); ctx.beginPath(); ctx.arc(x, y, 2.6, 0, 7); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
  // nodes
  for (const n of nodes) {
    if (n.kind === 'core') continue; const v = visOf(n.first, tc); if (v <= 0) continue; const rel = related(n) ? 1 : .3, r = curR(n, tc) * (.7 + .3 * v);
    ctx.globalAlpha = v * rel; const isSel = st.selected === n, isHov = st.hover === n;
    if (n.kind === 'nar') {
      const hot = n.share >= .5, col = hot ? HOT : PINK;
      ctx.globalCompositeOperation = 'lighter'; glow(n.x, n.y, r * (hot ? 1.1 + .15 * Math.sin(T * 2.2 + n.id) : 1), col, hot ? .5 : .32); ctx.globalCompositeOperation = 'source-over';
      orb(n.x, n.y, r, hot ? '#ffb4a8' : '#ffc3d6', hot ? '#a8281d' : '#8d2c52');
      ctx.strokeStyle = rgba('#ffe9d6', .75); ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(n.x, n.y, r + 3, 0, 7); ctx.stroke();
      if (hot) { ctx.setLineDash([3, 5]); ctx.lineDashOffset = -T * 8; ctx.strokeStyle = rgba(HOT, .8); ctx.beginPath(); ctx.arc(n.x, n.y, r + 9, 0, 7); ctx.stroke(); ctx.setLineDash([]); }
      const labelled = n.rank < 10 || hot || isSel || isHov || cam.k > 1.35 || related(n) && st.selected;
      if (!labelled) { txt('#' + n.id, n.x, n.y + 3.5, 10, 'rgba(255,255,255,.8)', 700, 'center'); } else {
      const L = n.x < 0, lx = L ? n.x - r - 12 : n.x + r + 12;
      txt('#' + n.id + ' ' + title((n.d.keywords || []).slice(0, 2).join(' · ') || 'narrative'), lx, n.y - 2, 13, '#f3f6f7', 600, L ? 'right' : 'left');
      pill(Math.round(n.share * 100) + '% coord. · ' + n.d.posts + ' posts', lx, n.y + 14, hot ? '#ff9a90' : '#9fe8ff', L); }
    } else {
      glow(n.x, n.y, r, VIOL, .38); orb(n.x, n.y, r, '#e4dcff', '#4a3a9a');
      ctx.strokeStyle = rgba('#e4dcff', .8); ctx.lineWidth = 1.3; ctx.beginPath(); ctx.arc(n.x, n.y, r + 3, 0, 7); ctx.stroke();
      const L = n.x < 0, lx = L ? n.x - r - 10 : n.x + r + 10;
      txt(n.id, lx, n.y - 2, 13, '#efeaff', 700, L ? 'right' : 'left'); pill(n.d.size + ' accounts · ' + n.d.confidence, lx, n.y + 14, '#cfc6ff', L);
    }
    if (isSel || isHov) { ctx.strokeStyle = isSel ? '#fff' : rgba('#fff', .6); ctx.lineWidth = 1.6; ctx.beginPath(); ctx.arc(n.x, n.y, r + 14, 0, 7); ctx.stroke(); }
    ctx.globalAlpha = 1;
  }
  // core
  { const c = sc.core, pulse = 1 + .04 * Math.sin(T * 1.6);
    ctx.globalCompositeOperation = 'lighter'; glow(0, 0, c.r * 1.6 * pulse, GOLD, .6); ctx.globalCompositeOperation = 'source-over';
    orb(0, 0, c.r, '#fff6dc', '#b9792a');
    for (let i = 0; i < 3; i++) { ctx.setLineDash([2 + i * 3, 4 + i * 2]); ctx.lineDashOffset = T * (6 + i * 3) * (i % 2 ? -1 : 1); ctx.strokeStyle = rgba('#ffe2a6', .75 - i * .18); ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(0, 0, c.r + 7 + i * 7, 0, 7); ctx.stroke(); }
    ctx.setLineDash([]);
    txt(st.res.meta.topic, 0, -c.r - 30, 17, '#fff', 700, 'center'); pill(Math.round(c.share * 100) + '% of posts from coordinated accounts', -92, -c.r - 14, '#ffd98a');
    if (st.selected === c || st.hover === c) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.arc(0, 0, c.r + 26, 0, 7); ctx.stroke(); } }
  ctx.restore();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ------------------------------------------------------------------ interaction
function toWorld(sx, sy) { return [(sx - W / 2 - st.cam.x) / st.cam.k, (sy - H / 2 - st.cam.y) / st.cam.k]; }
function hit(sx, sy) {
  const sc = st.scene; if (!sc) return null; const [wx, wy] = toWorld(sx, sy), tc = sc.t0 + (sc.t1 - sc.t0) * st.cursor;
  for (let i = sc.nodes.length - 1; i >= 0; i--) {
    const n = sc.nodes[i]; if (n.kind !== 'core' && visOf(n.first, tc) <= 0) continue;
    if (Math.hypot(wx - n.x, wy - n.y) < curR(n, tc) + 8) return n;
  }
  return null;
}
cv.addEventListener('mousemove', e => {
  if (st.drag) { st.cam.tx = st.cam.x = st.drag.cx + e.clientX - st.drag.x; st.cam.ty = st.cam.y = st.drag.cy + e.clientY - st.drag.y; return; }
  const n = hit(e.clientX, e.clientY); st.hover = n; cv.classList.toggle('pt', !!n);
  const tip = $('#tip');
  if (n) { tip.innerHTML = n.kind === 'nar' ? `<b>#${n.id}</b> ${esc(n.d.label)}<br><span class="mut">${n.d.posts} posts · ${n.d.accounts} accounts · ${Math.round(n.share * 100)}% coordinated</span>`
      : n.kind === 'grp' ? `<b>${esc(n.id)}</b> coordinated group<br><span class="mut">${n.d.size} accounts · ${esc(n.d.confidence)} confidence</span>` : `<b>${esc(st.res.meta.topic)}</b><br><span class="mut">click for overview</span>`;
    tip.style.left = Math.min(e.clientX + 16, W - 300) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; tip.classList.remove('hidden'); } else tip.classList.add('hidden');
});
cv.addEventListener('mouseleave', () => { st.hover = null; $('#tip').classList.add('hidden'); });
cv.addEventListener('mousedown', e => { if (!hit(e.clientX, e.clientY)) { st.drag = {x: e.clientX, y: e.clientY, cx: st.cam.x, cy: st.cam.y, moved: false}; cv.classList.add('drag'); } });
addEventListener('mouseup', e => { if (st.drag) { st.drag = null; cv.classList.remove('drag'); } });
cv.addEventListener('click', e => {
  if (!st.scene) return; const n = hit(e.clientX, e.clientY);
  if (n) select(n); else if (st.selected && !st.drag) { /* keep selection; Esc or ✕ closes */ }
});
cv.addEventListener('wheel', e => { e.preventDefault(); const f = e.deltaY < 0 ? 1.1 : .91, k = clamp(st.cam.tk * f, .3, 3.2); const [wx, wy] = toWorld(e.clientX, e.clientY);
  st.cam.tk = k; st.cam.k = k; st.cam.tx = st.cam.x = e.clientX - W / 2 - wx * k; st.cam.ty = st.cam.y = e.clientY - H / 2 - wy * k; }, {passive: false});
addEventListener('keydown', e => { if (e.key === 'Escape') { if (st.job && st.job.running && !st.job.min) { st.job.min = true; renderJob(); return; } hidePanel(); $('#modal').classList.add('hidden'); $('#notes').classList.add('hidden'); $('#drawer').classList.add('hidden'); $('#exp-menu').classList.add('hidden'); } });

function select(n, focus = true) {
  st.selected = n; showPanel(n);
  if (focus) { const k = n.kind === 'core' ? st.cam.tk : clamp(Math.max(st.cam.tk, 1.15), .35, 1.6); st.cam.tk = k; st.cam.tx = -n.x * k - 190; st.cam.ty = -n.y * k; }
}
function hidePanel() { st.selected = null; $('#panel').classList.add('hidden'); }

// ------------------------------------------------------------------ side panel
function volChart(vbp) {
  const buckets = [...new Set(Object.values(vbp).flatMap(o => Object.keys(o)))].sort(); if (!buckets.length) return '';
  const plats = Object.keys(vbp), tot = buckets.map(b => plats.reduce((s, p) => s + (vbp[p][b] || 0), 0)), mx = Math.max(...tot, 1), w = 340, h = 64, bw = w / buckets.length;
  let s = `<svg viewBox="0 0 ${w} ${h}" style="width:100%"><title>posts per ${buckets.length > 1 ? 'bucket' : 'hour'}</title>`;
  buckets.forEach((b, i) => { let y = h; plats.forEach(p => { const v = vbp[p][b] || 0; if (!v) return; const bh = (h - 4) * v / mx; y -= bh; s += `<rect x="${(i * bw + 1).toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(bw - 2, 1).toFixed(1)}" height="${bh.toFixed(1)}" rx="1.5" fill="${pcol(p)}" opacity=".9"><title>${esc(b.slice(0, 13))} ${esc(p)}: ${v}</title></rect>`; }); });
  return s + '</svg>';
}
function platBars(map, total) { return `<div class="bars">${Object.entries(map).map(([p, v]) => `<i style="width:${v / total * 100}%;background:${pcol(p)}" title="${esc(p)} ${v}"></i>`).join('')}</div>
  <div class="chipl">${Object.entries(map).map(([p, v]) => `<span style="color:${pcol(p)}">${esc(LABEL[p] || p)} ${v}</span>`).join('')}</div>`; }
function postLink(p) { const t = esc(short(p.text, 150)); return p.url && /^https?:/.test(p.url) ? `<a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${t}</a>` : t; }

function showPanel(n) {
  const el = $('#panel'), res = st.res; let h = '<button class="x" aria-label="Close" id="p-x">✕</button>';
  if (n.kind === 'core') {
    const m = res.meta;
    h += `<div class="p-eye"><i style="background:${GOLD}"></i>Topic overview</div><h2>${esc(m.topic)}</h2>
      <div class="stats"><div class="stat"><b>${m.n_posts}</b><small>posts</small></div><div class="stat"><b>${m.n_accounts}</b><small>accounts</small></div>
      <div class="stat"><b>${m.n_narratives}</b><small>narratives</small></div><div class="stat"><b>${Math.round(m.coordinated_post_share * 100)}%</b><small>posts from coordinated accounts</small></div></div>
      <div class="sec"><h5>Platforms</h5>${platBars(countBy(st.scene.posts, 'platform'), m.n_posts)}</div>
      <div class="sec"><h5>Volume over time</h5>${volChart(res.volume.by_platform)}</div>
      ${(m.collector_notes || []).map(x => `<div class="note"><b>Data note</b>${esc(x)}</div>`).join('')}`;
  } else if (n.kind === 'nar') {
    const d = n.d, o = res.origins.find(x => x.narrative_id === d.id), hot = n.share >= .5;
    h += `<div class="p-eye"><i style="background:${hot ? HOT : PINK}"></i>Narrative #${d.id}</div><h2>${esc(title(d.label))}</h2>
      <span class="badge ${hot ? 'b-hot' : n.share > 0 ? 'b-warn' : 'b-ok'}">${hot ? 'Pushed by coordinated accounts' : n.share > 0 ? 'Partly coordinated' : 'Looks organic'}</span>
      <div class="stats"><div class="stat"><b>${d.posts}</b><small>posts</small></div><div class="stat"><b>${d.accounts}</b><small>accounts</small></div>
      <div class="stat"><b>${Math.round(n.share * 100)}%</b><small>from coordinated accounts</small></div><div class="stat"><b>${d.engagement.toLocaleString()}</b><small>engagement</small></div></div>
      <div class="sec"><h5>Volume (${esc(d.bucket)})</h5>${volChart(d.volume_by_platform)}</div><div class="sec"><h5>Platforms</h5>${platBars(d.platforms, d.posts)}</div>`;
    if (o) {
      h += `<div class="sec"><h5>Where it started</h5><div class="note ${o.seeding_group ? 'crit' : ''}"><b>${esc(o.verdict)}</b>First seen ${esc(fmtDT(o.first_post.at))} UTC on ${esc(o.first_post.platform)} by ${esc(o.first_post.account)}.</div>
        <div class="hop">${o.platform_spread.map((s, i) => `${i ? `<em>→ ${esc(fmtLag(s.lag_minutes))}</em>` : ''}<span style="color:${pcol(s.platform)}">${esc(LABEL[s.platform] || s.platform)}</span>`).join('')}</div></div>
        <div class="sec"><h5>First accounts</h5><div class="chipl">${o.first_accounts.map(a => `<span title="${esc(short(a.text, 120))}">${esc(a.name || a.account)} · ${esc(fmtLag(a.minutes_after_origin))}${a.coordinated_group ? ' · ' + esc(a.coordinated_group) : ''}</span>`).join('')}</div></div>`;
    }
    if (n.d.coordinated_groups && Object.keys(n.d.coordinated_groups).length) h += `<div class="sec"><h5>Pushed by</h5><div class="chipl">${Object.entries(n.d.coordinated_groups).map(([g, c]) => `<a href="#" data-g="${esc(g)}">${esc(g)} · ${c} posts</a>`).join('')}</div></div>`;
    const ex = d.representative_posts.map(id => st.scene.posts.find(p => p.id === id && p.narrative_id === d.id)).filter(Boolean);
    h += `<div class="sec"><h5>Representative posts</h5>${ex.map(p => `<div class="ex">${postLink(p)}<small>${esc(p.platform)} · ${esc(p.author_name)} · ${esc(fmtDT(p.created_at))}</small></div>`).join('')}</div>
      <button class="btn wide" data-posts="n:${d.id}">Show all ${d.posts} posts</button>`;
  } else {
    const g = n.d;
    h += `<div class="p-eye"><i style="background:${VIOL}"></i>Coordinated group</div><h2>${esc(g.id)} · ${g.size} accounts</h2>
      <span class="badge ${g.confidence === 'high' ? 'b-hot' : g.confidence === 'medium' ? 'b-warn' : 'b-ok'}">${esc(g.confidence)} confidence · ${g.score}</span>
      <div class="stats"><div class="stat"><b>${g.posts}</b><small>posts</small></div><div class="stat"><b>${Object.keys(g.platforms).length}</b><small>platform(s)</small></div></div>
      <div class="sec"><h5>Why they're grouped</h5><ul class="rs">${g.reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul></div>
      <div class="sec"><h5>Signal strength</h5>${Object.entries(g.signal_coverage).map(([s, v]) => { const [a, b] = v.split(' ')[0].split('/').map(Number), f = a / Math.max(b, 1);
        return `<div class="sig"><span>${esc(SIGNAL[s] || s)}</span><div class="b"><i style="width:${f * 100}%"></i></div><em>${Math.round(f * 100)}%</em></div>`; }).join('')}</div>
      <div class="sec"><h5>Evidence</h5>${g.evidence.slice(0, 4).map(ev => ev.type === 'near_duplicate'
        ? `<div class="q">${esc(short(ev.text, 190))}<small>near-verbatim from ${ev.accounts} accounts · ${esc(fmtDT(ev.first))} → ${esc(fmtDT(ev.last))}</small></div>`
        : `<div class="q"><small>${Math.round(ev.lag_seconds)}s apart</small>${esc(ev.a.account)}: ${esc(short(ev.a.text, 90))}<br>${esc(ev.b.account)}: ${esc(short(ev.b.text, 90))}</div>`).join('')}</div>
      <div class="sec"><h5>Narratives it pushed</h5><div class="chipl">${Object.entries(g.narratives || {}).map(([nid, c]) => `<a href="#" data-n="${esc(nid)}">#${esc(nid)} · ${c} posts</a>`).join('')}</div></div>
      <div class="sec"><h5>Members (${g.size})</h5><div class="chipl">${g.accounts.slice(0, 24).map(a => `<span style="color:${pcol(a.split(':')[0])}">${esc(a.split(':').slice(1).join(':').slice(0, 14))}</span>`).join('')}${g.size > 24 ? `<span>+${g.size - 24}</span>` : ''}</div></div>
      <button class="btn wide" data-posts="g:${esc(g.id)}">Show group's posts</button>`;
  }
  el.innerHTML = h; el.classList.remove('hidden'); el.scrollTop = 0;
  $('#p-x').onclick = hidePanel;
  el.querySelectorAll('[data-n]').forEach(a => a.onclick = e => { e.preventDefault(); const t = st.scene.byNar.get(+a.dataset.n); if (t) select(t); });
  el.querySelectorAll('[data-g]').forEach(a => a.onclick = e => { e.preventDefault(); const t = st.scene.nodes.find(x => x.kind === 'grp' && x.id === a.dataset.g); if (t) select(t); });
  el.querySelectorAll('[data-posts]').forEach(b => b.onclick = () => openPosts(b.dataset.posts));
}
function countBy(arr, k) { const o = {}; arr.forEach(x => o[x[k]] = (o[x[k]] || 0) + 1); return o; }

// ------------------------------------------------------------------ analyst notes + rule-based Q&A (no AI model)
function notesData() {
  const res = st.res, out = [], os = res.origins;
  for (const o of os.filter(o => o.seeding_group)) {
    const hops = o.platform_spread.map(s => `${LABEL[s.platform] || s.platform}${s.lag_minutes ? ' ' + fmtLag(s.lag_minutes) : ''}`).join(' → ');
    out.push({crit: true, t: `Narrative #${o.narrative_id} looks seeded`, b: `${o.verdict} Spread: ${hops}.`, nid: o.narrative_id});
  }
  for (const g of res.coordinated_groups.filter(g => g.confidence === 'high')) out.push({crit: true, t: `${g.id}: ${g.size} accounts acting together`, b: g.reasons.slice(0, 2).join(' · '), gid: g.id});
  for (const g of res.coordinated_groups.filter(g => g.confidence !== 'high')) out.push({t: `${g.id}: possible coordination (${g.confidence})`, b: g.reasons.slice(0, 2).join(' · '), gid: g.id});
  const fast = os.filter(o => o.platform_spread.length > 1 && o.platform_spread[1].lag_minutes < 90 && !o.seeding_group);
  fast.slice(0, 2).forEach(o => out.push({t: `Narrative #${o.narrative_id} jumped platforms quickly`, b: `Reached ${o.platform_spread[1].platform} ${fmtLag(o.platform_spread[1].lag_minutes)} after first appearing on ${o.platform_spread[0].platform}.`, nid: o.narrative_id}));
  if (!res.coordinated_groups.length) out.push({t: 'No coordinated activity detected', b: 'No group of accounts met the evidence thresholds — consistent with organic discussion for this topic and window. That does not prove absence.'});
  (res.meta.collector_notes || []).forEach(n => out.push({t: 'Data note', b: n}));
  return out;
}
function renderNotes(extra = '') {
  const items = notesData();
  $('#notes').innerHTML = `<h3><span>✦ Analyst notes</span><button class="x" id="n-x" style="background:none;border:0;color:var(--mut)">✕</button></h3>${extra}` +
    items.map((n, i) => `<div class="note ${n.crit ? 'crit' : ''}"><b>${esc(n.t)}</b>${esc(n.b)}${n.nid !== undefined || n.gid ? ` <a class="go" data-i="${i}">view →</a>` : ''}</div>`).join('') +
    '<div class="mut small" style="margin-top:6px">Generated by local rules from this run’s data. Leads for a human analyst — not attribution.</div>';
  $('#n-x').onclick = () => $('#notes').classList.add('hidden');
  $('#notes').querySelectorAll('.go').forEach(a => a.onclick = () => { const n = items[+a.dataset.i]; const t = n.gid ? st.scene.nodes.find(x => x.kind === 'grp' && x.id === n.gid) : st.scene.byNar.get(n.nid); if (t) { select(t); $('#notes').classList.add('hidden'); } });
}
$('#notes-btn').onclick = () => { renderNotes(); $('#notes').classList.toggle('hidden'); };
$('#ai-on').addEventListener('change', e => {
  const hint = () => { $('#ai-hint').textContent = $('#ai-on').checked ? 'On: a summary of this run is sent to Gemini; answers are AI-generated.' : 'Off: answers use local rules — nothing leaves your machine.'; setTimeout(hint, 0);
  };
  if (!e.target.checked) return hint();
  if (!st.status.credentials.GEMINI_API_KEY.set) { e.target.checked = false; openSettings(); return; }
  if (!confirm('Send a SUMMARY of this run (narrative stats, group reasons and ~8 short quotes — not all posts) to Google Gemini to answer your questions?\n\nOn free tiers Google may use prompts to improve its products. Answers are AI-generated and may be wrong.')) e.target.checked = false;
  hint();
});
$('#ask-form').addEventListener('submit', async e => {
  e.preventDefault(); const q = $('#ask').value.trim(); if (!q || !st.res) return; $('#ask').value = '';
  if (!$('#ai-on').checked) { renderNotes(`<div class="note q"><b>You asked: ${esc(q)}</b>${answer(q)}</div>`); $('#notes').classList.remove('hidden'); return; }
  renderNotes(`<div class="note q"><b>You asked: ${esc(q)}</b><span class="mut">✦ asking Gemini…</span></div>`); $('#notes').classList.remove('hidden');
  try {
    const r = await api('/api/ask', {method: 'POST', body: JSON.stringify({ai: true, job_id: st.jobId, question: q})});
    renderNotes(`<div class="note q"><b>You asked: ${esc(q)}</b><span class="badge b-warn">✦ AI-generated · ${esc(r.model)} · may be wrong</span><div style="white-space:pre-wrap;margin-top:6px">${esc(r.answer)}</div></div>`);
  } catch (err) {
    renderNotes(`<div class="note q"><b>You asked: ${esc(q)}</b><span class="badge b-hot">AI unavailable</span> ${esc(err.message)}<div style="margin-top:6px"><span class="mut">Local answer:</span> ${answer(q)}</div></div>`);
  }
});
function answer(q) {
  const res = st.res, l = q.toLowerCase(), m = l.match(/#?(\d+)/), nid = m ? +m[1] : null, o = nid !== null ? res.origins.find(x => x.narrative_id === nid) : null;
  const gm = l.match(/\bg(\d+)\b/), g = gm ? res.coordinated_groups.find(x => x.id.toLowerCase() === 'g' + gm[1]) : null;
  if (g) return `${esc(g.id)}: ${g.size} accounts, ${g.confidence} confidence (${g.score}). ${g.reasons.map(esc).join(' ')}`;
  if (/(start|origin|first|began|begin|where)/.test(l)) {
    const t = o ? [o] : res.origins.slice(0, 3); if (!t.length) return 'No origin data.';
    return t.map(o => `<b>#${o.narrative_id}</b> ${esc(o.label)} — first seen ${esc(fmtDT(o.first_post.at))} UTC on ${esc(o.first_post.platform)} by ${esc(o.first_post.account)}. ${esc(o.verdict)}`).join('<br>');
  }
  if (/(who|push|seed|coordinat|bot|group|account)/.test(l)) {
    if (o && o.seeding_group) { const g2 = res.coordinated_groups.find(x => x.id === o.seeding_group); return `Narrative #${o.narrative_id} was seeded by ${esc(o.seeding_group)}${g2 ? ` (${g2.size} accounts; ${esc(g2.reasons[0] || '')})` : ''}.`; }
    if (!res.coordinated_groups.length) return 'No coordinated groups were detected in this run.';
    return res.coordinated_groups.map(g => `<b>${esc(g.id)}</b>: ${g.size} accounts (${esc(g.confidence)}) — ${esc(g.reasons[0] || '')}`).join('<br>');
  }
  if (/(platform|spread|hop|cross)/.test(l)) { const t = o ? [o] : res.origins.slice(0, 4); return t.map(o => `<b>#${o.narrative_id}</b>: ` + o.platform_spread.map(s => `${esc(LABEL[s.platform] || s.platform)} ${esc(fmtLag(s.lag_minutes))}`).join(' → ')).join('<br>'); }
  if (/(top|most|engag|viral|popular)/.test(l)) { const t = [...res.posts].sort((a, b) => b.engagement - a.engagement).slice(0, 3); return t.map(p => `${esc(p.platform)} · ${esc(p.author_name)} (${p.engagement.toLocaleString()} engagement): ${esc(short(p.text, 110))}`).join('<br>'); }
  if (/(biggest|largest|main|narrative|topic|what)/.test(l)) return res.narratives.filter(n => n.id >= 0).slice(0, 4).map(n => `<b>#${n.id}</b> ${esc(n.label)} — ${n.posts} posts, ${Math.round((n.coordinated_post_share || 0) * 100)}% coordinated`).join('<br>');
  return 'Try: “where did #0 start?”, “who pushed it?”, “spread across platforms”, “top posts”, “main narratives”, or “G1”. (Local rules, no AI model.)';
}

// ------------------------------------------------------------------ posts drawer + export
let pfilter = '';
function fillPosts() { renderPosts(); }
function renderPosts() {
  const sc = st.scene; if (!sc) return; const f = pfilter.toLowerCase(); let rows = sc.posts;
  const m = f.match(/^([ng]):(.+)$/); if (m) rows = rows.filter(p => m[1] === 'n' ? String(p.narrative_id) === m[2] : (p.coordinated_group || '').toLowerCase() === m[2].toLowerCase());
  else if (f) rows = rows.filter(p => (p.text + ' ' + p.author_name + ' ' + p.platform).toLowerCase().includes(f));
  rows = [...rows].sort((a, b) => b.engagement - a.engagement); $('#pcount').textContent = `${Math.min(rows.length, 500)} of ${rows.length}`;
  $('#ptb').innerHTML = rows.slice(0, 500).map(p => `<tr><td>${p.url && /^https?:/.test(p.url) ? `<a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(fmtDT(p.created_at))}</a>` : esc(fmtDT(p.created_at))}</td>
    <td style="color:${pcol(p.platform)}">${esc(p.platform)}</td><td>${esc(p.author_name)}</td><td>${esc(short(p.text, 240))}</td><td>${p.likes}</td><td>${p.shares}</td><td>${p.replies}</td><td>${p.narrative_id >= 0 ? p.narrative_id : '–'}</td><td>${esc(p.coordinated_group || '')}</td></tr>`).join('');
}
function openPosts(f) { pfilter = f || ''; $('#pf').value = pfilter; renderPosts(); $('#drawer').classList.remove('hidden'); }
$('#posts-btn').onclick = () => $('#drawer').classList.toggle('hidden'); $('#dr-close').onclick = () => $('#drawer').classList.add('hidden');
$('#pf').addEventListener('input', e => { pfilter = e.target.value; renderPosts(); });
$('#exp').onclick = () => $('#exp-menu').classList.toggle('hidden');
document.addEventListener('click', e => { if (!e.target.closest('#exp') && !e.target.closest('#exp-menu')) $('#exp-menu').classList.add('hidden'); });

// ------------------------------------------------------------------ init
(async () => {
  setDefaultDates();
  try { st.status = await api('/api/status'); } catch (e) { document.body.insertAdjacentHTML('beforeend', `<div class="glass" style="position:fixed;top:40%;left:30%;padding:20px">Cannot reach the coordwatch server: ${esc(e.message)}</div>`); return; }
  renderChips();
})();
window.__cw = st;   // handy for debugging in the browser console
})();
