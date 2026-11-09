(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const PC = {telegram:'#4de0b8', x:'#9aa8ff', youtube:'#ff8a65', tiktok:'#c792ff', instagram:'#ff7eb3', facebook:'#6aa8ff', snapchat:'#ffe066'};
const pcol = p => PC[p] || '#9ca3a3';
const LABEL = {x:'X', youtube:'YouTube', telegram:'Telegram', tiktok:'TikTok', instagram:'Instagram', facebook:'Facebook', snapchat:'Snapchat'};
const ORDER = ['x','youtube','telegram','tiktok','instagram','facebook','snapchat'];
const SIGNAL = {text_dup:'Copy-pasted text', sync:'Posting in sync', amplify:'Reshare loops', avatar:'Reused avatars', created:'Created together', handle:'Same handle'};
const SERVICES = [
  {id: 'youtube', short: 'YouTube', name: 'YouTube Data API', color: '#ff8a65', blurb: 'Videos & comments (key optional — falls back to yt-dlp)', keys: [['YOUTUBE_API_KEY', 'API key']],
   help: 'Google Cloud Console → create/select a project → enable <b>YouTube Data API v3</b> → Credentials → <b>Create API key</b>. Free daily quota. <b>Optional:</b> without a key the free yt-dlp route is used.'},
  {id: 'telegram', short: 'Telegram', name: 'Telegram', color: '#4de0b8', blurb: 'Global search of public channels (login) — or web preview of named channels', keys: [['TELEGRAM_API_ID', 'api_id'], ['TELEGRAM_API_HASH', 'api_hash']],
   help: 'my.telegram.org → <b>API development tools</b> → create an app. Then run <code>python -m coordwatch telegram-login</code> once in a terminal (phone + code). <b>With the login</b> Telegram is searched globally (channel names optional). <b>Without it</b> the public web preview is used and you must enter channel names, or channels are discovered via web search.'},
  {id: 'x', short: 'X', name: 'X (Twitter) API', color: '#9aa8ff', blurb: 'Recent search (paid credits)', keys: [['X_BEARER_TOKEN', 'Bearer token']],
   help: 'console.x.com → Apps → your app → Keys &amp; Tokens → <b>Bearer Token</b>. The API search needs paid credits. <b>Free route (experimental):</b> set <code>X_COOKIES_FILE</code> to a cookie export of a throwaway X login (see README); violates X ToS, use at your own risk.'},
  {id: 'ai', short: 'AI', name: 'AI answers (optional)', color: '#e8b86a', blurb: 'Gemini · Groq · Qwen · Grok · Ollama…', keys: [], custom: true,
   help: 'Off by default. Pick a provider, paste its key (Ollama needs none), then press <b>Save &amp; validate</b>. Free tiers change — check each provider’s current limits and data-use terms.'}
];
const STATE_LABEL = {connected: 'connected', saved: 'key saved', unset: 'not set', invalid: 'invalid key', limited: 'limited', unverified: 'saved', unreachable: 'offline', checking: 'checking…'};
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
    el.title = info.mode === 'live' ? (info.ready ? 'Live collection via ' + (info.route || 'official API') : 'No free route configured — click to see how')
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
st.conn = {};
function connState(id) {
  const svc = SERVICES.find(x => x.id === id), c = st.status.credentials, set = svc.custom ? st.status.ai.ready : svc.keys.every(([k]) => c[k].set);
  if (!set) return {state: 'unset', message: id === 'ai' ? 'Not configured (optional).' : 'Not set.'};
  return st.conn[id] || {state: 'saved', message: 'Key saved — not validated yet.'};
}
function renderConns() {
  const box = $('#conns'); if (!st.status) return;
  box.innerHTML = SERVICES.map(s => { const cs = connState(s.id); return `<button class="cn ${cs.state}" data-s="${s.id}" title="${esc(cs.message)}"><i></i>${esc(s.short)} · ${esc(STATE_LABEL[cs.state] || cs.state)}</button>`; }).join('');
  box.querySelectorAll('.cn').forEach(b => b.onclick = () => openSettings(b.dataset.s));
}
async function validateService(id, quiet) {
  st.conn[id] = {state: 'checking', message: 'Checking…'}; renderConns(); if (!$('#modal').classList.contains('hidden')) renderSettings();
  try { st.conn[id] = await api('/api/validate', {method: 'POST', body: JSON.stringify({service: id})}); if (st.conn[id].models) st.aiModels = st.conn[id].models; }
  catch (e) { st.conn[id] = {state: 'unreachable', message: e.message}; }
  renderConns(); if (!$('#modal').classList.contains('hidden')) renderSettings();
  if (quiet && window.__bootLog) { const r = st.conn[id], sv = SERVICES.find(x => x.id === id); window.__bootLog(`${sv.short.toLowerCase()} ${r.state === 'connected' ? '✓ connected' : r.state === 'unverified' ? '✓ keys saved' : r.state === 'invalid' ? '✗ invalid key' : '! ' + (STATE_LABEL[r.state] || r.state)}`, r.state === 'connected' || r.state === 'unverified' ? 'ok' : r.state === 'invalid' ? 'hot' : 'warn'); }
  return st.conn[id];
}
function autoValidate() {
  SERVICES.filter(sv => sv.id !== 'x' && connState(sv.id).state === 'saved').forEach(sv => validateService(sv.id, true));   // X is manual: its check may touch paid quota
}
function aiCardHtml(s, cs) {
  const ai = st.status.ai, pre = st.status.ai_presets, c = st.status.credentials, prov = (c.AI_PROVIDER.value || ai.provider || 'gemini');
  const p = pre[prov] || pre.gemini, keySet = prov === 'gemini' ? c.GEMINI_API_KEY.set : c.AI_API_KEY.set, models = st.aiModels || [];
  return `<div class="svc" data-s="ai"><div class="svc-top"><i class="dot" style="background:${s.color};box-shadow:0 0 8px ${s.color}"></i><b>${esc(s.name)}</b><span class="bl">${esc(s.blurb)}</span><span class="pill2 ${cs.state}">${esc(STATE_LABEL[cs.state] || cs.state)}</span></div>
    <div class="svc-msg">${esc(cs.message)}</div>
    <div class="svc-keys"><select id="ai-prov" aria-label="AI provider">${Object.entries(pre).map(([k, v]) => `<option value="${esc(k)}" ${k === prov ? 'selected' : ''}>${esc(v.label)}</option>`).join('')}</select></div>
    <div class="svc-keys"><input type="text" id="ai-base" data-k="AI_BASE_URL" aria-label="API base URL" value="${esc(c.AI_BASE_URL.value || '')}" placeholder="${esc(p.base || 'https://…/v1 (API base URL)')}" ${prov === 'gemini' ? 'disabled' : ''}>
      <input type="text" id="ai-model" data-k="AI_MODEL" list="ai-models" aria-label="Model" value="${esc(c.AI_MODEL.value || '')}" placeholder="model (blank = auto-pick)"><datalist id="ai-models">${models.map(m => `<option value="${esc(m)}">`).join('')}</datalist></div>
    <div class="svc-keys"><input type="password" autocomplete="off" id="ai-key" data-k="${prov === 'gemini' ? 'GEMINI_API_KEY' : 'AI_API_KEY'}" aria-label="AI API key" ${p.needs_key ? '' : 'disabled'}
      placeholder="${!p.needs_key ? 'no key needed (local)' : keySet ? 'API key — saved (' + esc(((prov === 'gemini' ? c.GEMINI_API_KEY : c.AI_API_KEY).source === 'env') ? 'env var' : 'file') + '), type to replace' : 'API key'}">
      <button class="btn" data-act="save">Save &amp; validate</button><button class="btn" data-act="val">Validate</button></div>
    <div class="svc-msg">Get a key: ${esc(p.hint)}${prov === 'ollama' ? '' : '. When enabled, a <b>summary</b> of a run is sent to this provider.'}</div>
    <details><summary>About this option</summary><p>${s.help}</p></details></div>`;
}
function renderSettings(focus) {
  const c = st.status.credentials;
  const keep = {}; document.querySelectorAll('#svc-list input').forEach(i => { if (i.value && i.type === 'password') keep[i.id || i.dataset.k] = i.value; });
  $('#svc-list').innerHTML = SERVICES.map(s => {
    const cs = connState(s.id);
    if (s.custom) return aiCardHtml(s, cs);
    const inputs = s.keys.map(([k, lab]) => `<input type="password" autocomplete="off" data-k="${k}" aria-label="${esc(s.name + ' ' + lab)}" placeholder="${c[k].set ? esc(lab) + ' — saved (' + (c[k].source === 'env' ? 'env var' : 'file') + '), type to replace' : esc(lab)}">`).join('');
    return `<div class="svc" data-s="${s.id}"><div class="svc-top"><i class="dot" style="background:${s.color};box-shadow:0 0 8px ${s.color}"></i><b>${esc(s.name)}</b><span class="bl">${esc(s.blurb)}</span><span class="pill2 ${cs.state}">${esc(STATE_LABEL[cs.state] || cs.state)}</span></div>
      <div class="svc-msg">${esc(cs.message)}</div>
      <div class="svc-keys">${inputs}<button class="btn" data-act="save">Save &amp; validate</button><button class="btn" data-act="val">Validate</button></div>
      <details><summary>How do I get this?</summary><p>${s.help}</p></details></div>`;
  }).join('');
  document.querySelectorAll('#svc-list input[type=password]').forEach(i => { const v = keep[i.id || i.dataset.k]; if (v) i.value = v; });
  const prov = $('#ai-prov'); if (prov) prov.onchange = () => {            // switching provider: refresh defaults, keep nothing stale
    st.status.credentials.AI_PROVIDER.value = prov.value; st.status.credentials.AI_BASE_URL.value = ''; st.status.credentials.AI_MODEL.value = ''; st.aiModels = []; renderSettings(); };
  document.querySelectorAll('#svc-list .svc').forEach(card => {
    const id = card.dataset.s;
    card.querySelector('[data-act=val]').onclick = () => validateService(id);
    card.querySelector('[data-act=save]').onclick = async () => {
      const upd = {};
      if (id === 'ai') {
        upd.AI_PROVIDER = $('#ai-prov').value; upd.AI_MODEL = $('#ai-model').value.trim();
        upd.AI_BASE_URL = $('#ai-prov').value === 'gemini' || $('#ai-base').value.trim() === (st.status.ai_presets[$('#ai-prov').value].base || '') ? '' : $('#ai-base').value.trim();
        const k = $('#ai-key'); if (k.value.trim()) upd[k.dataset.k] = k.value.trim();
      } else card.querySelectorAll('input').forEach(i => { if (i.value.trim()) upd[i.dataset.k] = i.value.trim(); });
      if (!Object.keys(upd).length) return validateService(id);
      try { st.status = await api('/api/credentials', {method: 'POST', body: JSON.stringify(upd)}); delete st.conn[id]; renderChips(); renderConns(); }
      catch (err) { alert(err.message); return; }
      card.querySelectorAll('input[type=password]').forEach(i => i.value = ''); validateService(id);
    };
  });
  if (focus) { const card = $(`#svc-list .svc[data-s="${focus}"]`); if (card) { card.scrollIntoView({block: 'center'}); const i = card.querySelector('input:not([disabled])'); if (i) i.focus(); } }
}
const _day = d => { const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000); return z.toISOString().slice(0, 10); };
function logRange() {
  const f = $('#lg-from').value, t = $('#lg-to').value; if (!f || !t) return null;
  const a = new Date(f + 'T00:00:00'), b = new Date(t + 'T23:59:59.999');   // local days -> instants
  return `from=${encodeURIComponent(a.toISOString())}&to=${encodeURIComponent(b.toISOString())}`;
}
async function logCount() {
  const r = logRange(), n = $('#lg-n'); if (!r) { n.textContent = 'pick both dates'; return; }
  try {
    const res = await fetch('/api/logs?' + r), j = await res.json();
    n.textContent = res.ok ? `${j.count} run${j.count === 1 ? '' : 's'} in range` : (j.error || 'error');
  } catch (e) { n.textContent = 'could not check'; }
}
$('#lg-from').onchange = $('#lg-to').onchange = logCount;
$('#lg-dl').onclick = () => { const r = logRange(); if (!r) return logCount(); window.location = '/api/logs?download=1&' + r; setTimeout(logCount, 800); };
$('#lg-copy').onclick = async e => {
  const r = logRange(), b = e.currentTarget; if (!r) return logCount();
  try {
    const j = await (await fetch('/api/logs?text=1&' + r)).json();
    if (!j.count) { $('#lg-n').textContent = 'no runs in that range'; return; }
    try { await navigator.clipboard.writeText(j.text); }
    catch (x) { const ta = document.createElement('textarea'); ta.value = j.text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); }
    b.textContent = 'Copied ✓'; setTimeout(() => b.textContent = 'Copy', 2000);
  } catch (x) { $('#lg-n').textContent = 'copy failed - use Export'; }
};
function openSettings(focus) {
  if (!$('#lg-to').value) { const n = new Date(); $('#lg-to').value = _day(n); $('#lg-from').value = _day(new Date(n.getTime() - 7 * 864e5)); }
  logCount();
  $('#storage-note').textContent = st.status.in_codespaces
    ? 'Codespaces detected: for permanent storage add keys as Codespaces secrets (GitHub → Settings → Codespaces → Secrets); they become environment variables automatically.'
    : 'Saved keys live in ~/.coordwatch/credentials.json on this computer (outside the repository).';
  renderSettings(focus); $('#modal').classList.remove('hidden');
}
$('#gear').onclick = () => openSettings();
$('#m-close').onclick = $('#m-done').onclick = () => $('#modal').classList.add('hidden');
$('#modal').addEventListener('mousedown', e => { if (e.target === $('#modal')) $('#modal').classList.add('hidden'); });
$('#m-valall').onclick = async () => { for (const s of SERVICES) if (connState(s.id).state !== 'unset') await validateService(s.id); };

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
  $('#o-min').classList.toggle('hidden', finished); $('#o-abort').classList.toggle('hidden', finished); $('#o-abort').disabled = !!cancelling; $('#o-close').classList.toggle('hidden', !finished); $('#o-copy').classList.toggle('hidden', !finished || !j.id);
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
async function copyRunLog(btn) {
  const j = st.job; if (!j || !j.id) return;
  try {
    const txt = await (await fetch(`/api/jobs/${j.id}/download/run_log.txt`)).text();
    try { await navigator.clipboard.writeText(txt); }
    catch (e) { const ta = document.createElement('textarea'); ta.value = txt; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); }
    btn.textContent = 'Copied ✓'; setTimeout(() => btn.textContent = 'Copy run log', 2000);
  } catch (e) { btn.textContent = 'Copy failed - use Close, then Export > run_log.txt'; }
}
$('#o-copy').onclick = e => copyRunLog(e.currentTarget);
$('#o-close').onclick = () => { st.job = null; renderJob(); };
$('#overlay').addEventListener('mousedown', e => { if (e.target === $('#overlay') && st.job) { if (st.job.running) { st.job.min = true; } else st.job = null; renderJob(); } });   // click outside = minimise, never abort
$('#jobchip').onclick = () => { if (st.job) { st.job.min = false; renderJob(); } };
$('#jobchip').addEventListener('keydown', e => { if (e.key === 'Enter' && st.job) { st.job.min = false; renderJob(); } });
$('#run').onclick = () => startRun(false);
$('#demo').onclick = $('#hero-demo').onclick = () => { $('#topic').value = 'Acme Bank'; $('#since').value = '2026-10-01'; $('#until').value = '2026-10-14'; $('#dv').checked = true; startRun(true); };
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
  const L = innerWidth <= 720 ? 8 : $('#app-sidebar').offsetWidth + 84, R = innerWidth <= 720 ? 8 : (st.selected ? 404 : 14);   // space taken by the menu + timeline and by the details panel
  const avail = Math.min(W - L - R, (H - 190) * 1.5); st.cam.tk = clamp(avail / (2 * m), .35, 1.25); st.cam.tx = (L - R) / 2; st.cam.ty = -10;
  st.cam.k = st.cam.tk * .6; st.cam.x = st.cam.tx; st.cam.y = st.cam.ty;
}

function loadResult() {
  const res = st.res, sc = st.scene = buildScene(res);
  st.selected = null; st.cursor = 1; hidePanel();
  setIdle(false);
  ['#tl', '#dock', '#exp', '#posts-btn'].forEach(s => $(s).classList.remove('hidden'));
  $('#tlr').value = 1000; renderTicks(); updateBubble();
  const m = res.meta;
  $('#kpis').innerHTML = [['Posts', m.n_posts.toLocaleString(), ''], ['Accounts', m.n_accounts.toLocaleString(), ''], ['Narratives', m.n_narratives, ''],
    ['Coordinated accts', m.coordinated_accounts, `<em>${m.n_groups} group(s)</em>`], ['Coordinated posts', Math.round(m.coordinated_post_share * 100) + '%', '']]
    .map(([a, b, c]) => `<div><small>${a}</small><b>${b}${c}</b></div>`).join('');
  $('#exp-menu').innerHTML = ['report.html', 'results.json', 'posts.csv', 'narratives.csv', 'coordinated_groups.csv', 'origins.csv', 'cross_platform.csv', 'cross_platform_summary.txt', 'volume_by_platform.csv', 'run_log.txt']
    .map(f => `<a href="/api/jobs/${st.jobId}/download/${f}" ${f === 'report.html' ? 'target="_blank" rel="noopener"' : ''}>${f === 'report.html' ? '↗ Static report (HTML)' : '⭳ ' + f}</a>`).join('');
  setScreen('graph'); fitCamera(); renderNotes(); fillPosts();
  $('#notes').classList.add('hidden');
  refreshRuns().then(renderHome);
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
  if (!sc) { if (document.body.classList.contains('idle')) ambient(T); requestAnimationFrame(frame); return; }
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

function crossHtml(c) {
  if (!c || !c.summary) return '';
  const rows = (c.narrative_overlap || []).slice(0, 5).map(o => `<li>#${o.narrative_id} ${esc(o.label)}: ${Object.entries(o.by_platform).map(([p, v]) => `${esc(LABEL[p] || p)} ${v}`).join(', ')} · first on ${esc(LABEL[o.first_platform] || o.first_platform)}</li>`).join('');
  return `<div class="sec"><h5>Cross-platform summary</h5>${c.summary.map(x => `<p class="small">${esc(x)}</p>`).join('')}${rows ? `<ul class="small st-list">${rows}</ul>` : ''}</div>`;
}
function showPanel(n) {
  const el = $('#panel'), res = st.res; let h = '<button class="x" aria-label="Close" id="p-x">✕</button>';
  if (n.kind === 'core') {
    const m = res.meta;
    h += `<div class="p-eye"><i style="background:${GOLD}"></i>Topic overview</div><h2>${esc(m.topic)}</h2>
      <div class="stats"><div class="stat"><b>${m.n_posts}</b><small>posts</small></div><div class="stat"><b>${m.n_accounts}</b><small>accounts</small></div>
      <div class="stat"><b>${m.n_narratives}</b><small>narratives</small></div><div class="stat"><b>${Math.round(m.coordinated_post_share * 100)}%</b><small>posts from coordinated accounts</small></div></div>
      <div class="sec"><h5>Platforms</h5>${platBars(countBy(st.scene.posts, 'platform'), m.n_posts)}</div>
      <div class="sec"><h5>Volume over time</h5>${volChart(res.volume.by_platform)}</div>
      ${crossHtml(res.cross_platform)}
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
  const res = st.res, out = [], os = res.origins, G = res.coordinated_groups;
  const seeded = os.filter(o => o.seeding_group);
  for (const o of seeded.slice(0, 3)) {
    const hops = o.platform_spread.map(s => `${LABEL[s.platform] || s.platform}${s.lag_minutes ? ' ' + fmtLag(s.lag_minutes) : ''}`).join(' → ');
    out.push({crit: true, t: `Narrative #${o.narrative_id} looks seeded`, b: `${o.verdict} Spread: ${hops}.`, nid: o.narrative_id});
  }
  if (seeded.length > 3) out.push({t: `${seeded.length - 3} more narratives look seeded`, b: 'Click a red narrative in the map to inspect it.'});
  const sizes = G.map(g => g.size).sort((a, b) => a - b), med = sizes.length ? sizes[sizes.length >> 1] : 0;
  if (G.length >= 5 && med <= 4) out.push({crit: false, t: `Treat these ${G.length} small groups with caution`, b: `Many groups of ${med}–${sizes[sizes.length - 1]} accounts, each sharing one message, usually mean generic comments, spam bursts or reposted quotes rather than organised campaigns. Check each group's evidence before drawing conclusions.`});
  for (const g of G.slice(0, 3)) out.push({crit: g.confidence === 'high' && g.size >= 5, t: `${g.id}: ${g.size} accounts, ${g.confidence} confidence`, b: g.reasons.slice(0, 2).join(' · '), gid: g.id});
  if (G.length > 3) out.push({t: `${G.length - 3} more coordinated groups`, b: 'Purple orbs in the map; click one to see its evidence.'});
  const fast = os.filter(o => o.platform_spread.length > 1 && o.platform_spread[1].lag_minutes < 90 && !o.seeding_group);
  fast.slice(0, 2).forEach(o => out.push({t: `Narrative #${o.narrative_id} jumped platforms quickly`, b: `Reached ${o.platform_spread[1].platform} ${fmtLag(o.platform_spread[1].lag_minutes)} after first appearing on ${o.platform_spread[0].platform}.`, nid: o.narrative_id}));
  if (!G.length) out.push({t: 'No coordinated activity detected', b: 'No group of accounts met the evidence thresholds — consistent with organic discussion for this topic and window. That does not prove absence.'});
  (res.meta.collector_notes || []).forEach(n => out.push({t: 'Data note', b: n}));
  return out;
}
function noteHtml(n, i) { return `<div class="note ${n.crit ? 'crit' : ''}"><b>${esc(n.t)}</b>${esc(n.b)}${n.nid !== undefined || n.gid ? ` <a class="go" data-i="${i}">inspect →</a>` : ''}</div>`; }
function renderNotes(extra = '') {
  const items = notesData(), head = items.slice(0, 4), rest = items.slice(4);
  $('#notes').innerHTML = `<h3><span>✦ ${extra ? 'Answer' : 'Analyst notes'}</span><button class="x" id="n-x" style="background:none;border:0;color:var(--mut)">✕</button></h3>${extra}` +
    (extra ? '<h4 class="n-sub">Analyst notes</h4>' : '') + head.map((n, i) => noteHtml(n, i)).join('') +
    (rest.length ? `<div id="n-more" class="hidden">${rest.map((n, i) => noteHtml(n, i + 4)).join('')}</div><button class="btn wide" id="n-more-btn">Show ${rest.length} more</button>` : '') +
    '<div class="mut small" style="margin-top:8px">Generated by local rules from this run’s data. Leads for a human analyst — not attribution.</div>';
  $('#n-x').onclick = () => $('#notes').classList.add('hidden');
  const mb = $('#n-more-btn'); if (mb) mb.onclick = () => { $('#n-more').classList.remove('hidden'); mb.remove(); };
  $('#notes').querySelectorAll('.go').forEach(a => a.onclick = () => { const n = items[+a.dataset.i]; const t = n.gid ? st.scene.nodes.find(x => x.kind === 'grp' && x.id === n.gid) : st.scene.byNar.get(n.nid); if (t) { select(t); $('#notes').classList.add('hidden'); } });
  $('#notes').querySelectorAll('[data-posts]').forEach(b => b.onclick = () => { openPosts(b.dataset.posts); $('#notes').classList.add('hidden'); });
}
$('#notes-btn').onclick = () => { renderNotes(); $('#notes').classList.toggle('hidden'); };
$('#ai-on').addEventListener('change', e => {
  const hint = () => { const ai = st.status.ai; $('#ai-hint').textContent = $('#ai-on').checked ? (ai.local ? 'On: answers come from your local model — nothing leaves this machine.' : `On: a summary of this run is sent to ${ai.label.split(' (')[0]}; answers are AI-generated.`) : 'Off: answers use local rules — nothing leaves your machine.'; };
  if (!e.target.checked) return hint();
  if (!st.status.ai.ready) { e.target.checked = false; openSettings('ai'); return; }
  if (!st.status.ai.local && !confirm(`Send a SUMMARY of this run to ${st.status.ai.label.split(' (')[0]} to answer your questions?\n\nIt includes narrative stats, group reasons, ~8 short quotes and the public names of the most active accounts — not all posts.\nFree tiers may use prompts to improve their products. Answers are AI-generated and may be wrong.`)) e.target.checked = false;
  hint();
});
$('#ask-form').addEventListener('submit', async e => {
  e.preventDefault(); const q = $('#ask').value.trim(); if (!q || !st.res) return; $('#ask').value = '';
  const show = html => { renderNotes(html); $('#notes').classList.remove('hidden'); };
  if (!$('#ai-on').checked) return show(`<div class="note q"><b>${esc(q)}</b>${answer(q)}</div>`);
  show(`<div class="note q"><b>${esc(q)}</b><span class="mut">✦ asking ${esc(st.status.ai.label.split(' (')[0])}… (retries automatically if it is busy)</span></div>`);
  try {
    const r = await api('/api/ask', {method: 'POST', body: JSON.stringify({ai: true, job_id: st.jobId, question: q})});
    show(`<div class="note q"><b>${esc(q)}</b><span class="badge b-warn">✦ AI-generated · ${esc(r.model)} · may be wrong</span><div style="white-space:pre-wrap;margin-top:6px">${esc(r.answer)}</div></div>`);
  } catch (err) {
    show(`<div class="note q"><b>${esc(q)}</b><span class="badge b-hot">AI unavailable</span> <span class="mut">${esc(err.message)}</span><div style="margin-top:8px"><span class="mut">Answer from local rules:</span><br>${answer(q)}</div></div>`);
  }
});
const PLAT_WORDS = {youtube: ['youtube', 'yt'], x: ['twitter', 'tweets', 'tweet', 'x'], telegram: ['telegram', 'tg'], tiktok: ['tiktok'], instagram: ['instagram', 'insta'], facebook: ['facebook'], snapchat: ['snapchat']};
const STOPQ = new Set('who what which are all the and any for with from this that these those there their they them its was were did does has had have can could would should where when why how many much most top list show give tell about like liked came come comes commented comment comments commenters commenter accounts account channels channel users user people posted post posts posters poster talking talked mention mentions mentioned discussed discussing started start began first pushed push'.split(' '));
function detectPlat(l) { for (const [p, ws] of Object.entries(PLAT_WORDS)) if (ws.some(w => new RegExp('\\b' + w + '\\b').test(l))) return p; return null; }
function accountsAnswer(q, plat) {
  const l = q.toLowerCase(); let rows = st.scene.posts.filter(p => !plat || p.platform === plat);
  if (!rows.length) return `No ${esc(LABEL[plat] || plat)} posts in this run.`;
  const wordsToDrop = new Set(Object.values(PLAT_WORDS).flat());
  const kws = (l.match(/[a-z0-9#$]+/g) || []).filter(t => t.length >= 3 && !STOPQ.has(t) && !wordsToDrop.has(t)).filter(k => { const hit = rows.filter(p => p.text.toLowerCase().includes(k)).length; return hit > 0 && hit < rows.length * .95; });
  let note = '';
  if (kws.length) { const f = rows.filter(p => kws.some(k => p.text.toLowerCase().includes(k))); if (f.length) { rows = f; note = ` mentioning “${kws.join(', ')}”`; } }
  const agg = new Map();
  rows.forEach(p => { let a = agg.get(p.account); if (!a) agg.set(p.account, a = {name: p.author_name, posts: 0, eng: 0, group: p.coordinated_group, url: p.url, top: -1}); a.posts++; a.eng += p.engagement; if (p.engagement > a.top) { a.top = p.engagement; a.url = p.url; } });
  const list = [...agg.values()].sort((a, b) => b.posts - a.posts || b.eng - a.eng), label = plat ? (LABEL[plat] || plat) : 'all platforms';
  const top = list.slice(0, 15).map(a => `<div class="acc"><b>${esc(a.name)}</b><span class="mut"> · ${a.posts} post${a.posts > 1 ? 's' : ''} · ${a.eng.toLocaleString()} engagement</span>${a.group ? ` <span class="badge b-hot">${esc(a.group)}</span>` : ''}${/^https?:/.test(a.url || '') ? ` <a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">open ↗</a>` : ''}</div>`).join('');
  return `<b>${list.length} account${list.length === 1 ? '' : 's'}</b> on ${esc(label)}${esc(note)} (${rows.length} post${rows.length === 1 ? '' : 's'}). Most active:${top}${list.length > 15 ? `<div class="mut">+${list.length - 15} more</div>` : ''}<button class="btn wide" data-posts="${plat ? 'p:' + plat : ''}">Show ${plat ? esc(LABEL[plat] || plat) + ' ' : ''}posts in the table</button>`;
}
function answer(q) {
  const res = st.res, l = q.toLowerCase(), m = l.match(/#(\d+)|\bnarrative (\d+)/), nid = m ? +(m[1] || m[2]) : null, o = nid !== null ? res.origins.find(x => x.narrative_id === nid) : null;
  const gm = l.match(/\bg(\d+)\b/), g = gm ? res.coordinated_groups.find(x => x.id.toLowerCase() === 'g' + gm[1]) : null, plat = detectPlat(l);
  if (/\b(fetch|scrape|collect|download|crawl|search for|look up|get me more|pull)\b/.test(l)) return 'I can only answer questions about the data already collected in this run — I can’t fetch new data from chat. To get more, change the <b>topic</b> (e.g. <code>NFP OR topgtraders</code>), the dates or the <b>depth</b> (Quick / Standard / Deep) above and press <b>Analyse</b>.';
  if (g) return `<b>${esc(g.id)}</b>: ${g.size} accounts, ${esc(g.confidence)} confidence (${g.score}). ${g.reasons.map(esc).join(' ')}`;
  if (/(coordinat|campaign|\bbots?\b|inauthentic|spam|astroturf|seeded|seed\b|pushed|pushing)/.test(l)) {
    if (o && o.seeding_group) { const g2 = res.coordinated_groups.find(x => x.id === o.seeding_group); return `Narrative #${o.narrative_id} was seeded by ${esc(o.seeding_group)}${g2 ? ` (${g2.size} accounts; ${esc(g2.reasons[0] || '')})` : ''}.`; }
    const G = res.coordinated_groups; if (!G.length) return 'No coordinated groups were detected in this run.';
    return `<b>${G.length} possible coordinated group${G.length > 1 ? 's' : ''}</b> (${res.meta.coordinated_accounts} accounts). Top ${Math.min(5, G.length)}:<br>` + G.slice(0, 5).map(g => `<b>${esc(g.id)}</b>: ${g.size} accounts (${esc(g.confidence)}) — ${esc(g.reasons[0] || '')}`).join('<br>') + (G.length > 5 ? `<br><span class="mut">+${G.length - 5} more — see the purple orbs in the map.</span>` : '');
  }
  if (/(where|origin|first|began|begin|start)/.test(l) && !/\bwho\b/.test(l)) {
    const t = o ? [o] : res.origins.slice(0, 3); if (!t.length) return 'No origin data.';
    return t.map(o => `<b>#${o.narrative_id}</b> ${esc(o.label)} — first seen ${esc(fmtDT(o.first_post.at))} UTC on ${esc(o.first_post.platform)} by ${esc(o.first_post.account)}. ${esc(o.verdict)}`).join('<br>');
  }
  if (/\b(who|which|list|accounts?|channels?|commenters?|users?|people|posters?|authors?)\b/.test(l)) return accountsAnswer(q, plat);
  if (/(platform|spread|hop|cross)/.test(l)) { const t = o ? [o] : res.origins.slice(0, 4); return t.map(o => `<b>#${o.narrative_id}</b>: ` + o.platform_spread.map(s => `${esc(LABEL[s.platform] || s.platform)} ${esc(fmtLag(s.lag_minutes))}`).join(' → ')).join('<br>'); }
  if (/(top|most|engag|viral|popular|best)/.test(l)) { const t = [...res.posts].filter(p => !plat || p.platform === plat).sort((a, b) => b.engagement - a.engagement).slice(0, 3); return t.map(p => `${esc(p.platform)} · <b>${esc(p.author_name)}</b> (${p.engagement.toLocaleString()} engagement): ${esc(short(p.text, 110))}`).join('<br>'); }
  if (/(biggest|largest|main|narrative|topic|what|summary|overview|talking)/.test(l)) return res.narratives.filter(n => n.id >= 0).slice(0, 4).map(n => `<b>#${n.id}</b> ${esc(n.label)} — ${n.posts} posts, ${Math.round((n.coordinated_post_share || 0) * 100)}% coordinated`).join('<br>');
  return 'Try: “who posted on YouTube?”, “which accounts mention nfp?”, “where did #0 start?”, “who is coordinating?”, “top posts”, “main narratives”, or “G1”. (Local rules, no AI model — tick AI answers for open-ended questions.)';
}

// ------------------------------------------------------------------ posts drawer: filters, sorting, media, expandable rows + export
const pf = {q: '', plat: '', nar: '', grp: '', media: '', sort: 'eng', thumbs: false, limit: 300, open: new Set()};
const isHttp = u => /^https?:\/\//i.test(u || '');
function fillPosts() {
  const sc = st.scene, res = st.res, plats = [...new Set(sc.posts.map(p => p.platform))];
  $('#f-plat').innerHTML = '<option value="">All platforms</option>' + plats.map(p => `<option value="${esc(p)}">${esc(LABEL[p] || p)}</option>`).join('');
  $('#f-nar').innerHTML = '<option value="">All narratives</option><option value="none">Unclustered</option>' + sc.nars.map(n => `<option value="${n.id}">#${n.id} ${esc(title(n.label).slice(0, 30))} (${n.posts})</option>`).join('');
  $('#f-grp').innerHTML = '<option value="">All accounts</option><option value="any">Coordinated only</option>' + res.coordinated_groups.map(g => `<option value="${esc(g.id)}">${esc(g.id)} · ${g.size} accounts</option>`).join('');
  $('#f-media').innerHTML = '<option value="">Any media</option><option value="photo">Has photo</option><option value="video">Has video</option><option value="none">No media</option>';
  $('#f-sort').innerHTML = '<option value="eng">Most engagement</option><option value="new">Newest first</option><option value="old">Oldest first</option><option value="likes">Most likes</option><option value="replies">Most replies</option>';
  resetFilters(false);
}
function syncControls() { $('#pf').value = pf.q; $('#f-plat').value = pf.plat; $('#f-nar').value = pf.nar; $('#f-grp').value = pf.grp; $('#f-media').value = pf.media; $('#f-sort').value = pf.sort; $('#f-thumbs').checked = pf.thumbs; }
function resetFilters(render = true) { Object.assign(pf, {q: '', plat: '', nar: '', grp: '', media: '', sort: 'eng', limit: 300}); pf.open.clear(); syncControls(); if (render) renderPosts(); }
function filteredPosts() {
  const q = pf.q.trim().toLowerCase();
  const rows = st.scene.posts.filter(p => {
    if (pf.plat && p.platform !== pf.plat) return false;
    if (pf.nar === 'none' ? p.narrative_id >= 0 : (pf.nar && String(p.narrative_id) !== pf.nar)) return false;
    if (pf.grp === 'any' ? !p.coordinated_group : (pf.grp && p.coordinated_group !== pf.grp)) return false;
    if (pf.media) { const has = t => p.media.some(m => m.type === t); if (pf.media === 'none' ? p.media.length > 0 : !has(pf.media)) return false; }
    if (q && !(p.text + ' ' + p.author_name + ' ' + p.account).toLowerCase().includes(q)) return false;
    return true;
  });
  const key = {eng: p => -p.engagement, new: p => -p.ts, old: p => p.ts, likes: p => -p.likes, replies: p => -p.replies}[pf.sort];
  return rows.sort((a, b) => key(a) - key(b));
}
function mediaCell(p, big) {
  return p.media.filter(m => isHttp(m.url)).slice(0, big ? 12 : 3).map(m => {
    const img = pf.thumbs && m.type === 'photo' && /\.(jpe?g|png|webp|gif)(\?|$)|ytimg\.com|twimg\.com|cdninstagram|fbcdn/i.test(m.url);
    return `<a href="${esc(m.url)}" target="_blank" rel="noopener noreferrer" title="${esc(m.url)}">${img ? `<img class="thumb" loading="lazy" referrerpolicy="no-referrer" src="${esc(m.url)}" alt="">` : ''}${m.type === 'video' ? '🎞 video' : '🖼 photo'}</a>`;
  }).join('') || '<span class="mut">–</span>';
}
function renderPosts() {
  const sc = st.scene; if (!sc) return; const rows = filteredPosts(), shown = rows.slice(0, pf.limit);
  $('#pcount').textContent = `${shown.length} of ${rows.length} (${sc.posts.length} total)`;
  $('#ptb').innerHTML = shown.map(p => {
    const k = p.platform + ':' + p.id, open = pf.open.has(k);
    const link = isHttp(p.url) ? `<a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(fmtDT(p.created_at))}</a>` : esc(fmtDT(p.created_at));
    let h = `<tr class="pr ${open ? 'open' : ''}" data-k="${esc(k)}"><td>${link}</td><td style="color:${pcol(p.platform)}">${esc(p.platform)}</td><td>${esc(p.author_name)}</td><td>${esc(short(p.text, 200))}</td>
      <td class="md">${mediaCell(p, false)}</td><td>${p.likes}</td><td>${p.shares}</td><td>${p.replies}</td><td>${p.narrative_id >= 0 ? p.narrative_id : '–'}</td><td>${esc(p.coordinated_group || '')}</td></tr>`;
    if (open) h += `<tr class="px"><td colspan="10"><div class="full">${esc(p.text)}</div><div class="mlist" style="margin-top:8px">${mediaCell(p, true)}</div>
      <div class="meta">${esc(p.platform)} · ${esc(p.account)} · ${esc(fmtDT(p.created_at))} UTC · ${p.likes} likes · ${p.shares} shares · ${p.replies} replies${p.views ? ' · ' + p.views.toLocaleString() + ' views' : ''}${p.author_created ? ' · account created ' + esc(p.author_created.slice(0, 10)) : ''}${isHttp(p.url) ? ` · <a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">open original ↗</a>` : ''}</div></td></tr>`;
    return h;
  }).join('') || '<tr><td colspan="10" class="mut" style="padding:24px;text-align:center">No posts match these filters. <a href="#" id="p-clear">Reset filters</a></td></tr>';
  $('#ptb').querySelectorAll('tr.pr').forEach(r => r.onclick = e => { if (e.target.closest('a')) return; const k = r.dataset.k; pf.open.has(k) ? pf.open.delete(k) : pf.open.add(k); renderPosts(); });
  const pc = $('#p-clear'); if (pc) pc.onclick = e => { e.preventDefault(); resetFilters(); };
  $('#p-more').innerHTML = rows.length > shown.length ? `<button class="btn" id="p-more-btn">Show ${Math.min(300, rows.length - shown.length)} more</button>` : '';
  const mb = $('#p-more-btn'); if (mb) mb.onclick = () => { pf.limit += 300; renderPosts(); };
}
function openPosts(spec) {
  resetFilters(false); const m = (spec || '').match(/^([npg]):(.+)$/);
  if (m) { if (m[1] === 'p') pf.plat = m[2]; else if (m[1] === 'n') pf.nar = m[2]; else pf.grp = m[2].toUpperCase(); } else pf.q = spec || '';
  syncControls(); renderPosts(); $('#drawer').classList.remove('hidden');
}
$('#posts-btn').onclick = () => { $('#drawer').classList.toggle('hidden'); if (!$('#drawer').classList.contains('hidden')) renderPosts(); };
$('#dr-close').onclick = () => $('#drawer').classList.add('hidden');
$('#pf').addEventListener('input', e => { pf.q = e.target.value; pf.limit = 300; renderPosts(); });
[['#f-plat', 'plat'], ['#f-nar', 'nar'], ['#f-grp', 'grp'], ['#f-media', 'media'], ['#f-sort', 'sort']].forEach(([id, k]) => $(id).addEventListener('change', e => { pf[k] = e.target.value; pf.limit = 300; renderPosts(); }));
$('#f-thumbs').addEventListener('change', e => { pf.thumbs = e.target.checked; renderPosts(); });
$('#f-reset').onclick = () => resetFilters();
$('#exp').onclick = () => $('#exp-menu').classList.toggle('hidden');
document.addEventListener('click', e => { if (!e.target.closest('#exp, #exp-menu, .side-link')) $('#exp-menu').classList.add('hidden'); });

// ------------------------------------------------------------------ landing (idle) scene
function setIdle(on) {
  document.body.classList.toggle('idle', on);
  $('#app-shell').classList.toggle('analysis-mode', !on);
  if (on) { setScreen('home'); renderHome(); }
}
$('#brand').onclick = () => {
  if ((st.job && st.job.running) || !st.res) return;
  st.res = null; st.scene = null; st.selected = null;
  ['#tl', '#legend', '#dock', '#exp', '#posts-btn', '#panel', '#notes', '#drawer', '#tip'].forEach(x => $(x).classList.add('hidden')); setIdle(true);
};
let amb = null;
function ambient(T) {
  if (!amb) { const r = mulberry(11); amb = Array.from({length: 64}, (_, i) => ({a: r() * 6.28, r: 140 + r() * 460, s: (r() - .5) * .03, z: 1.5 + r() * 1.9, camp: i < 12, p: r() * 6.28, sp: .6 + r() * 1.6, k: r() * 6.28, kr: 18 + r() * 62})); }
  const cx = W / 2, cy = H * .47, ph = (T % 8) / 8, sync = Math.pow(Math.sin(Math.PI * Math.min(1, ph * 3.4)), 2) * (ph < .3 ? 1 : 0);   // the "campaign" fires in unison every 8s
  const bx = cx + Math.min(W * .34, 430), by = cy - 30, pos = amb.map(n => n.camp ? [bx + Math.cos(n.k + T * .12) * n.kr, by + Math.sin(n.k + T * .12) * n.kr * .8] : [cx + Math.cos(n.a + T * n.s) * n.r * 1.4, cy + Math.sin(n.a + T * n.s) * n.r * .6]);
  ctx.globalCompositeOperation = 'lighter';
  const camp = amb.map((n, i) => n.camp ? i : -1).filter(i => i >= 0);
  for (let a = 0; a < camp.length; a++) for (let b = a + 1; b < camp.length; b++) {
    const p = pos[camp[a]], q = pos[camp[b]], d = Math.hypot(p[0] - q[0], p[1] - q[1]); if (d > 95) continue;
    ctx.strokeStyle = `rgba(255,122,106,${.05 + .55 * sync})`; ctx.lineWidth = .8; ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke();
  }
  ctx.lineWidth = .6;
  for (let a = 0; a < amb.length; a++) if (!amb[a].camp) for (let b = a + 1; b < amb.length; b++) { if (amb[b].camp) continue; const p = pos[a], q = pos[b], d = Math.hypot(p[0] - q[0], p[1] - q[1]); if (d < 130) { ctx.strokeStyle = `rgba(120,210,200,${.1 * (1 - d / 130)})`; ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke(); } }
  amb.forEach((n, i) => {
    const [x, y] = pos[i], tw = Math.pow(Math.sin(T * n.sp + n.p), 2);
    if (n.camp) { const a = .3 + .7 * sync; glow(x, y, 3 + 4 * sync, '#ff8a6a', .5 * a); ctx.fillStyle = `rgba(255,${170 - 60 * sync | 0},120,${a})`; }
    else ctx.fillStyle = `rgba(190,245,238,${.22 + .55 * tw})`;
    ctx.beginPath(); ctx.arc(x, y, n.camp ? 2 + sync : n.z, 0, 7); ctx.fill();
  });
  if (sync > .02) { ctx.strokeStyle = `rgba(255,140,110,${.45 * sync})`; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(bx, by, 30 + 260 * ph * 3, 0, 7); ctx.stroke(); }
  ctx.globalCompositeOperation = 'source-over';
}

// ------------------------------------------------------------------ boot splash: dots blink like ordinary accounts, a few lock into sync = "coordination detected"
function runBoot() {
  return new Promise(resolve => {
    const el = $('#boot'), cvb = $('#bc'), x = cvb.getContext('2d'), log = $('#blog');
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { el.remove(); return resolve(); }
    let w, h; const dpr = Math.min(devicePixelRatio || 1, 2), fit = () => { w = innerWidth; h = innerHeight; cvb.width = w * dpr; cvb.height = h * dpr; };
    fit(); addEventListener('resize', fit);
    const r = mulberry(5), N = 150, CL = 15, pts = Array.from({length: N}, (_, i) => ({x: r() * w, y: r() * h, p: r() * 6.28, s: .6 + r() * 1.8, c: i < CL, ang: i / CL * 6.283}));
    const cx = () => w / 2, cy = () => h * .40, ring = () => Math.min(w, h) * .16, T0 = performance.now(), ease = t => t * t * (3 - 2 * t), lerp = (a, b, t) => a + (b - a) * t;
    const lines = [[.15, 'initialising collectors…', 'dim'], [.9, 'scanning narratives…', ''], [1.5, 'linking accounts…', ''], [2.15, 'coordination detected', 'hot']];
    let li = 0, ended = false, shown = false;
    window.__bootLog = (t, c = '') => { const d = document.createElement('div'); d.className = c; d.textContent = t; log.appendChild(d); while (log.children.length > 7) log.firstChild.remove(); };
    const end = () => { if (ended) return; ended = true; removeEventListener('resize', fit); el.classList.add('out'); setTimeout(() => el.remove(), 950); resolve(); };
    el.addEventListener('click', end); addEventListener('keydown', end, {once: true});
    const frame = now => {
      if (ended) return; const t = (now - T0) / 1000;
      x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, w, h);
      while (li < lines.length && t >= lines[li][0]) { window.__bootLog(lines[li][1], lines[li][2]); li++; }
      const fade = Math.min(1, t / .8), e2 = ease(Math.max(0, Math.min(1, (t - 1.0) / 1.1))), e3 = ease(Math.max(0, Math.min(1, (t - 2.25) / .75))), sync = Math.pow(Math.sin(t * 5.2), 2);
      x.globalCompositeOperation = 'lighter';
      const P = pts.map(pt => {
        let px = pt.x + Math.sin(t * .5 + pt.p) * 7, py = pt.y + Math.cos(t * .4 + pt.p) * 7, tw = Math.pow(Math.sin(t * pt.s + pt.p), 2), a, col;
        if (pt.c) { const rr = ring() * (1 - e3), tx = cx() + Math.cos(pt.ang + t * .35) * rr, ty = cy() + Math.sin(pt.ang + t * .35) * rr * .9; px = lerp(px, tx, e2); py = lerp(py, ty, e2); a = lerp(.15 + .45 * tw, .35 + .65 * sync, e2); col = e2 > .4 ? [255, 150 + 70 * (1 - sync) | 0, 110] : [190, 245, 238]; }
        else { a = (.12 + .4 * tw) * (1 - .75 * e2) * (1 - e3); col = [190, 245, 238]; }
        return {px, py, a: a * fade, col, c: pt.c};
      });
      if (t > 1.4) { const prog = Math.min(1, (t - 1.4) / .8), C = P.filter(q => q.c); x.lineWidth = .9;
        for (let i = 0; i < C.length; i++) for (const j of [1, 4]) { const a = C[i], b = C[(i + j) % C.length]; x.strokeStyle = `rgba(255,130,100,${.5 * prog * (.4 + .6 * sync) * (1 - e3)})`; x.beginPath(); x.moveTo(a.px, a.py); x.lineTo(a.px + (b.px - a.px) * prog, a.py + (b.py - a.py) * prog); x.stroke(); } }
      for (const q of P) { const rad = q.c ? 2.2 + 1.6 * q.a : 1.4 + q.a * 1; const g = x.createRadialGradient(q.px, q.py, 0, q.px, q.py, rad * 4.5); g.addColorStop(0, `rgba(${q.col},${q.a})`); g.addColorStop(1, `rgba(${q.col},0)`); x.fillStyle = g; x.beginPath(); x.arc(q.px, q.py, rad * 4.5, 0, 7); x.fill(); }
      if (e3 > 0) { const g = x.createRadialGradient(cx(), cy(), 0, cx(), cy(), 40 + 130 * e3); g.addColorStop(0, `rgba(255,236,190,${.95 * e3})`); g.addColorStop(.35, `rgba(232,184,106,${.5 * e3})`); g.addColorStop(1, 'rgba(232,184,106,0)'); x.fillStyle = g; x.beginPath(); x.arc(cx(), cy(), 40 + 130 * e3, 0, 7); x.fill();
        x.strokeStyle = `rgba(255,217,138,${.5 * (1 - e3) + .12})`; x.lineWidth = 1.4; x.beginPath(); x.arc(cx(), cy(), 30 + 220 * e3, 0, 7); x.stroke(); }
      x.globalCompositeOperation = 'source-over';
      if (t > 2.3 && !shown) { shown = true; $('#bt').classList.add('show'); $('#bs').classList.add('show'); }
      if (t > 4.1) return end(); requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
}

// ------------------------------------------------------------------ dashboard, guided investigation and reference-led navigation
let runs = [];   // finished runs found on disk (newest first), so history survives a restart
async function refreshRuns() { try { runs = (await api('/api/runs')).runs || []; } catch (e) { runs = []; } }
async function openRun(id) { st.res = await api('/api/jobs/' + id + '/result'); st.jobId = id; st.selected = null; loadResult(); }
const runDate = r => r.started ? new Date(r.started).toLocaleDateString() : '';
const runItem = (r, i, long) => '<button class="recent-item" data-run="' + esc(r.id) + '"><span class="recent-icon">✥</span><span><b>' + esc(r.topic || 'Untitled') + '</b><small>' + esc(runDate(r)) + ' · ' + (r.n_posts || 0) + ' posts' + (long ? ' · ' + (r.n_narratives || 0) + ' themes' : '') + '</small></span><span class="recent-status">Open ›</span></button>';
const wireRuns = el => el.querySelectorAll('[data-run]').forEach(b => b.onclick = () => openRun(b.dataset.run).catch(e => alert('Could not open this run: ' + e.message)));
let activeScreen = 'home', wizardStep = 1;
function move(el, target) { if (el && target && el.parentElement !== target) target.appendChild(el); }
function stashDates() { const t = $('#top'); ['#since', '#until'].forEach(q => { const e = document.querySelector(q); if (e) t.appendChild(e); }); }   // park the date pickers before a slot is rebuilt, or they would be destroyed with it
function mountHomeInputs() {
  stashDates();
  move($('#topic'), $('#home-topic-slot')); move($('#chips'), $('#home-platform-slot'));
  const dates=$('#home-date-row'); if(dates){ dates.innerHTML='<label>From</label><label>To</label>'; const a=document.createElement('div'),b=document.createElement('div');a.appendChild($('#since'));b.appendChild($('#until'));dates.append(a,b); }
}
function mountWizardInputs(step) {
  if(step===1){move($('#topic'),$('#wizard-topic-slot'));}
  if(step===2){move($('#chips'),$('#wizard-platform-slot'));move($('#tgch'),$('#wizard-platform-slot'));}
  if(step===3){stashDates();const slot=$('#wizard-dates-slot');slot.innerHTML='';const a=document.createElement('label'),b=document.createElement('label');a.textContent='From';b.textContent='To';a.appendChild($('#since'));b.appendChild($('#until'));slot.append(a,b);}
  if(step===4){move($('#depth'),$('#wizard-advanced-slot'));move($('#dv').parentElement,$('#wizard-advanced-slot'));move($('#tgch'),$('#wizard-advanced-slot'));}
}
function setScreen(screen) {
  const priorCards=$('#analysis-cards'); if(priorCards) priorCards.remove();
  activeScreen=screen;
  const analysis=['graph','narratives','groups','spread','posts','exports','guide'].includes(screen);
  document.body.dataset.view=screen; document.body.classList.toggle('analysis',analysis&&!!st.res);
  document.querySelectorAll('.side-link[data-screen]').forEach(b=>b.classList.toggle('active',b.dataset.screen===screen));
  document.querySelectorAll('.app-screen').forEach(x=>x.classList.add('hidden'));
  $('#analysis-header').classList.add('hidden');
  $('#app-topbar').classList.remove('hidden');
  $('#crumb-main').textContent=screen==='wizard'?'New Investigation':screen==='home'?'Home':title(screen);
  $('#crumb-sub').textContent=screen==='home'?'': ' / coordwatch';
  $('#app-shell').classList.remove('analysis-mode');
  if(screen==='home'){
    $('#home-view').classList.remove('hidden'); mountHomeInputs();
  } else if(screen==='wizard'){
    $('#wizard-view').classList.remove('hidden'); showWizardStep(1);
  } else if(screen==='investigations'){
    $('#investigations-view').classList.remove('hidden'); renderInvestigationList();
  } else if(['graph','narratives','groups','spread','posts','exports','guide'].includes(screen)){
    if(!st.res){setScreen('wizard');return;}
    showAnalysisScreen(screen);
  }
}
function showWizardStep(n){
  wizardStep=Math.max(1,Math.min(4,n));
  document.querySelectorAll('.wizard-step-panel').forEach(p=>p.classList.toggle('hidden',Number(p.dataset.step)!==wizardStep));
  document.querySelectorAll('.wizard-progress .step').forEach((p,i)=>{p.classList.toggle('active',i+1===wizardStep);p.classList.toggle('done',i+1<wizardStep)});
  $('#wizard-back').disabled=wizardStep===1;
  $('#wizard-next').classList.toggle('hidden',wizardStep===4);
  $('#wizard-launch').classList.toggle('hidden',wizardStep!==4);
  mountWizardInputs(wizardStep);
  if(wizardStep===4){$('#wizard-review').innerHTML='<div class="review-line"><b>Topic</b><span>'+esc($('#topic').value||'Not entered')+'</span></div><div class="review-line"><b>Platforms</b><span>'+[...st.sel].map(p=>esc(LABEL[p]||p)).join(', ')+'</span></div><div class="review-line"><b>Date range</b><span>'+esc($('#since').value)+' – '+esc($('#until').value)+'</span></div><div class="review-line"><b>Collection depth</b><span>'+esc($('#depth').value)+'</span></div>';}
}
$('#wizard-back').onclick=()=>showWizardStep(wizardStep-1);
$('#wizard-next').onclick=()=>{if(wizardStep===1&&!$('#topic').value.trim()){$('#topic').focus();return;}if(wizardStep===2&&!st.sel.size&&!Object.keys(st.uploads).length){alert('Choose at least one source or import a file.');return;}showWizardStep(wizardStep+1);};
$('#wizard-launch').onclick=()=>{if(!$('#topic').value.trim())return showWizardStep(1);$('#run').click();};
document.querySelectorAll('[data-example]').forEach(b=>b.onclick=()=>{$('#topic').value=b.dataset.example;$('#topic').focus();});
$('#home-new').onclick=$('#investigations-new').onclick=()=>setScreen('wizard');
$('#view-investigations').onclick=()=>setScreen('investigations');
$('#home-start').onclick=()=>{if(!$('#topic').value.trim()){setScreen('wizard');return;}$('#run').click();};
$('#home-demo').onclick=()=>{$('#demo').click();};
$('#top-settings').onclick=$('#home-manage-settings').onclick=()=>openSettings();
document.querySelectorAll('.side-link[data-screen]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.screen==='settings'){openSettings();return;}setScreen(b.dataset.screen);}));
function renderHome(){
  $('#home-total').textContent=runs.length;
  $('#home-total-note').textContent=runs.length?runs.length+' saved on this computer':'Start your first investigation';
  $('#home-active').textContent=st.job&&st.job.running?'Running':'Ready';
  $('#home-active-note').textContent=st.job&&st.job.running?st.job.topic:'No collection running';
  const total=runs.reduce((n,r)=>n+(r.n_posts||0),0);
  $('#home-posts').textContent=total?total.toLocaleString():'—';
  const rl=$('#recent-list'); rl.innerHTML=runs.length?runs.slice(0,4).map((r,i)=>runItem(r,i,false)).join(''):'<div class="empty-state">Your completed investigations will appear here.</div>'; wireRuns(rl);
  $('#home-connectors').innerHTML=st.status?['youtube','telegram','x','tiktok','instagram','facebook'].map(p=>'<span class="connector-mini">'+esc(LABEL[p]||p)+' · '+(st.status.platforms[p]?.ready?'Available':'Import / setup')+'</span>').join(''):'<span class="connector-mini">Checking local services…</span>';
}
function renderInvestigationList(){const el=$('#investigations-list');el.innerHTML=runs.length?runs.map((r,i)=>runItem(r,i,true)).join(''):'<div class="empty-state">No investigations yet. Start one to see your results here.</div>';wireRuns(el);}
function showAnalysisScreen(screen){
  $('#app-shell').classList.add('analysis-mode');
  $('#graph-tools').classList.toggle('hidden',screen!=='graph');
  if(screen!=='graph') $('#panel').classList.add('hidden');
  if(screen!=='posts') $('#drawer').classList.add('hidden');
  $('#notes').classList.add('hidden');
  document.querySelectorAll('[data-analysis]').forEach(b=>b.classList.toggle('active',b.dataset.analysis===screen||(b.dataset.analysis==='timeline'&&screen==='spread')));$('#app-topbar').classList.add('hidden');$('#analysis-header').classList.remove('hidden');
  $('#analysis-title').textContent=({graph:'Constellation',narratives:'Discussion themes',groups:'Accounts acting together',spread:'How the discussion spread',posts:'Posts Explorer',exports:'Exports',guide:'Help & Guide'})[screen]||'Investigation';
  $('#analysis-subtitle').textContent=({graph:'Explore the relationships between the topic, narratives and account groups.',narratives:'Select a theme to inspect its posts, accounts and timeline.',groups:'Review the signals behind accounts grouped together.',spread:'Earliest observed posts and cross-platform movement.',posts:'Search and filter the collected evidence.',exports:'Download the data and reports from this investigation.',guide:'Understand the graph and what the evidence can tell you.'})[screen]||'';
  $('#app-main').classList.add('analysis-active');
  if(screen==='graph'){const stale=$('#analysis-cards');if(stale)stale.remove();['#drawer','#notes'].forEach(s=>$(s).classList.add('hidden'));$('#panel').classList.toggle('hidden',!st.selected);$('#graph-tools').classList.remove('hidden');}
  if(screen==='posts'){openPosts('');}
  if(screen==='narratives')renderAnalysisCards('narratives');
  if(screen==='groups')renderAnalysisCards('groups');
  if(screen==='spread')renderAnalysisCards('spread');
  $('#exp-menu').classList.toggle('hidden',screen!=='exports');
  if(screen==='guide'){$('#graph-help').classList.remove('hidden');}
}
document.querySelectorAll('[data-analysis]').forEach(b=>b.addEventListener('click',()=>setScreen(b.dataset.analysis==='timeline'?'spread':b.dataset.analysis)));
function renderAnalysisCards(kind){
  let html='<section id="analysis-cards" class="analysis-cards">';
  if(kind==='narratives')html+=st.res.narratives.filter(n=>n.id>=0).map(n=>'<button class="analysis-card" data-nar="'+n.id+'"><small>DISCUSSION THEME #'+n.id+'</small><h3>'+esc(title(n.label))+'</h3><p>'+n.posts+' posts · '+n.accounts+' accounts · '+Math.round((n.coordinated_post_share||0)*100)+'% from flagged accounts</p><span>Inspect evidence →</span></button>').join('');
  if(kind==='groups')html+=st.res.coordinated_groups.map(g=>'<button class="analysis-card" data-grp="'+esc(g.id)+'"><small>GROUP '+esc(g.id)+'</small><h3>'+g.size+' accounts · '+esc(g.confidence)+' confidence</h3><p>'+esc(g.reasons.slice(0,2).join(' · '))+'</p><span>Inspect signals →</span></button>').join('')||'<p>No account groups met the current evidence thresholds.</p>';
  if(kind==='spread')html+=st.res.origins.map(o=>'<button class="analysis-card" data-nar="'+o.narrative_id+'"><small>THEME #'+o.narrative_id+'</small><h3>'+esc(o.label)+'</h3><p>First observed: '+esc(o.first_post.platform)+' · '+esc(fmtDT(o.first_post.at))+' UTC</p><p>'+esc(o.verdict)+'</p><span>Inspect timeline →</span></button>').join('');
  html+='</section>';let old=$('#analysis-cards');if(old)old.remove();$('#app-main').appendChild(document.createRange().createContextualFragment(html));
  $('#analysis-cards').querySelectorAll('[data-nar]').forEach(b=>b.onclick=()=>{setScreen('graph');const n=st.scene.byNar.get(+b.dataset.nar);if(n)select(n);});
  $('#analysis-cards').querySelectorAll('[data-grp]').forEach(b=>b.onclick=()=>{setScreen('graph');const n=st.scene.nodes.find(x=>x.kind==='grp'&&x.id===b.dataset.grp);if(n)select(n);});
}
$('#graph-fit').onclick=()=>{if(st.scene)fitCamera();};
$('#graph-zoom-in').onclick=()=>{st.cam.tk=clamp(st.cam.tk*1.22,.3,3.2);};
$('#graph-zoom-out').onclick=()=>{st.cam.tk=clamp(st.cam.tk/1.22,.3,3.2);};
$('#graph-legend').onclick=()=>{const open=$('#legend').classList.toggle('hidden')===false;$('#graph-legend').setAttribute('aria-pressed',String(open));};
$('#graph-help-close').onclick=()=>$('#graph-help').classList.add('hidden');
let touchStart=null;
cv.addEventListener('touchstart',e=>{if(!st.scene||e.touches.length!==1)return;const t=e.touches[0],n=hit(t.clientX,t.clientY);touchStart={x:t.clientX,y:t.clientY,lastX:t.clientX,lastY:t.clientY,node:n,moved:false};},{passive:true});
cv.addEventListener('touchmove',e=>{if(!touchStart||e.touches.length!==1)return;const t=e.touches[0],dx=t.clientX-touchStart.lastX,dy=t.clientY-touchStart.lastY;if(Math.hypot(t.clientX-touchStart.x,t.clientY-touchStart.y)>7)touchStart.moved=true;if(touchStart.moved&&!touchStart.node){st.cam.tx+=dx;st.cam.ty+=dy;st.cam.x=st.cam.tx;st.cam.y=st.cam.ty;}touchStart.lastX=t.clientX;touchStart.lastY=t.clientY;},{passive:true});
cv.addEventListener('touchend',()=>{if(!touchStart)return;if(!touchStart.moved&&touchStart.node)select(touchStart.node);touchStart=null;},{passive:true});

// ------------------------------------------------------------------ collapsible menu
let sbChosen = null; try { sbChosen = localStorage.getItem('cw.sidebar'); } catch (e) { /* storage blocked: just don't remember */ }
function setSidebar(collapsed, remember) {
  document.body.classList.toggle('sb-collapsed', collapsed);
  const t = $('#sb-toggle'); t.setAttribute('aria-expanded', String(!collapsed)); t.title = collapsed ? 'Expand menu' : 'Collapse menu'; t.textContent = collapsed ? '›' : '‹';
  if (remember) { sbChosen = collapsed ? '1' : '0'; try { localStorage.setItem('cw.sidebar', sbChosen); } catch (e) { /* ignore */ } }
  if (st.scene && activeScreen === 'graph') setTimeout(fitCamera, 230);   // re-centre once the menu has finished sliding
}
document.querySelectorAll('.side-link').forEach(b => { b.title = b.textContent.trim().replace(/^\S+\s+/, ''); });
$('#sb-toggle').onclick = () => setSidebar(!document.body.classList.contains('sb-collapsed'), true);
setSidebar(sbChosen === null ? innerWidth <= 1100 : sbChosen === '1', false);
addEventListener('resize', () => { if (sbChosen === null) setSidebar(innerWidth <= 1100, false); });

// ------------------------------------------------------------------ init
(async () => {
  setDefaultDates();
  const booting = runBoot();
  try { st.status = await api('/api/status'); }
  catch (e) { $('#boot') && $('#boot').remove(); document.body.insertAdjacentHTML('beforeend', `<div class="glass" style="position:fixed;top:40%;left:30%;padding:20px;z-index:200">Cannot reach the coordwatch server: ${esc(e.message)}</div>`); return; }
  renderChips(); autoValidate(); await refreshRuns();
  await booting; setIdle(true);
})();
window.__cw = st;   // handy for debugging in the browser console
})();
