/* Core: auth, API, time zone helpers, navigation, modals, toasts, charts */
const API = '/api';
const S = { token: localStorage.getItem('luz_token') || '', tz: 'Asia/Dubai', currency: 'AED', business: 'LUZ EMS',
            services: [], staff: [], clients: [], plans: [], settings: null, page: 'dashboard' };

async function api(method, path, body) {
  const opts = { method, headers: { 'Authorization': 'Bearer ' + S.token } };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch(API + path, opts);
  if (res.status === 401) { showLogin(); throw new Error('Please sign in'); }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    // Validation errors come as a list: show the field and the rule in plain words
    const list = Array.isArray(data.detail) ? data.detail.map(d => `${String((d.loc || []).slice(-1)[0] || '').replace(/_/g, ' ')}: ${String(d.msg || '').replace(/^Value error, /, '')}`).join(' · ') : '';
    const err = new Error(typeof data.detail === 'string' ? data.detail : list || `Error ${res.status}`);
    err.status = res.status; throw err;
  }
  return res.status === 204 ? null : res.json();
}

function showLogin() { document.getElementById('login').classList.add('active'); document.getElementById('app').style.display = 'none'; }
async function doLogin(e) {
  e.preventDefault();
  const pw = document.getElementById('login-password').value;
  const user = (document.getElementById('login-username') || { value: '' }).value.trim();
  const err = document.getElementById('login-error'); err.textContent = '';
  try {
    const r = await fetch(API + '/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(user ? { username: user, password: pw } : { password: pw }) });
    if (!r.ok) { err.textContent = (await r.json()).detail || 'Login failed'; return false; }
    S.token = (await r.json()).token; localStorage.setItem('luz_token', S.token);
    document.getElementById('login-password').value = '';
    boot();
  } catch (ex) { err.textContent = ex.message; }
  return false;
}
function logout() { localStorage.removeItem('luz_token'); S.token = ''; showLogin(); }

async function boot() {
  if (!S.token) return showLogin();
  try {
    const me = await api('GET', '/auth/me');
    S.tz = me.timezone; S.currency = me.currency; S.business = me.business_name;
    S.me = { role: me.role || 'owner', name: me.name || 'Owner', pages: me.pages || Object.keys(PAGES) };
    // Show only the pages this account may use (the server enforces it too)
    document.querySelectorAll('.nav button[data-page]').forEach(b => { b.style.display = S.me.pages.includes(b.dataset.page) ? '' : 'none'; });
    document.querySelectorAll('.nav .nav-label').forEach(l => { let n = l.nextElementSibling, any = false; while (n && !n.classList.contains('nav-label')) { if (n.style.display !== 'none') any = true; n = n.nextElementSibling; } l.style.display = any ? '' : 'none'; });
    document.body.dataset.role = S.me.role;
    const who = document.getElementById('signed-in-as'); if (who) who.textContent = S.me.role === 'owner' ? 'Owner' : `${S.me.name} · ${S.me.role}`;
    document.getElementById('login').classList.remove('active');
    document.getElementById('app').style.display = 'flex';
    document.title = `${S.business} - Scheduling`;
    const h = await fetch('/api/health').then(r => r.json()).catch(() => ({}));
    const pill = document.getElementById('env-pill');
    pill.textContent = h.env || 'local'; pill.classList.toggle('live', h.env === 'live');
    await refreshLookups();
    go(location.hash.replace('#', '') || 'dashboard');
    if (typeof pushSync === 'function') pushSync();
  } catch (e) { if (e.message !== 'Please sign in') toast(e.message, true); }
}

async function refreshLookups() {
  [S.services, S.staff, S.clients, S.plans, S.settings] = await Promise.all([
    api('GET', '/services/'), api('GET', '/staff/'), api('GET', '/clients/'), api('GET', '/subscriptions/plans'), api('GET', '/settings/')]);
  S.tz = S.settings.timezone; S.currency = S.settings.currency;
}

const PAGES = { dashboard: () => loadDashboard(), calendar: () => loadCalendar(), clients: () => loadClients(),
  subscriptions: () => loadSubscriptions(), payments: () => loadPayments(), expenses: () => loadExpenses(),
  reports: () => loadReports(), messages: () => loadMessages(), catalog: () => loadCatalog(),
  settings: () => loadSettings(), leads: () => loadLeads() };
/* Theme: light, dark, or auto (follow the device). Saved on this device only. */
function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem('luz_theme', t); } catch (e) {}
  document.querySelectorAll('.theme-switch button').forEach(b => b.classList.toggle('active', b.dataset.t === t));
  const dark = t === 'dark' || (t === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  const meta = document.querySelector('meta[name="theme-color"]'); if (meta) meta.content = dark ? '#0c1110' : '#f4f6f5';
  if (typeof window._dashMonths !== 'undefined' && $('page-dashboard').classList.contains('active')) loadDashboard(); // redraw charts
}
document.addEventListener('DOMContentLoaded', () => setTheme(document.documentElement.getAttribute('data-theme') || 'auto'));

function go(page) {
  const allowedPages = (S.me && S.me.pages) || Object.keys(PAGES);
  if (!PAGES[page] || !allowedPages.includes(page)) page = allowedPages.includes('dashboard') ? 'dashboard' : allowedPages[0];
  S.page = page; location.hash = page;
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + page));
  document.querySelectorAll('.nav button').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  PAGES[page]().catch(e => toast(e.message, true));
}
window.addEventListener('hashchange', () => { const p = location.hash.replace('#', ''); if (p && p !== S.page) go(p); });

/* ---------- time zone helpers (all display/input in the business time zone) ---------- */
function tzParts(date, tz = S.tz) {
  const f = new Intl.DateTimeFormat('en-US', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'short' });
  const p = Object.fromEntries(f.formatToParts(date).map(x => [x.type, x.value]));
  return { y: +p.year, m: +p.month, d: +p.day, h: +p.hour, mi: +p.minute, s: +p.second, wd: ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].indexOf(p.weekday) };
}
function tzOffsetMs(date, tz = S.tz) { const p = tzParts(date, tz); return Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi, p.s) - date.getTime(); }
function zonedToDate(dateStr, timeStr, tz = S.tz) {
  const [y, m, d] = dateStr.split('-').map(Number); const [h, mi] = (timeStr || '00:00').split(':').map(Number);
  const naive = Date.UTC(y, m - 1, d, h, mi);
  let utc = naive - tzOffsetMs(new Date(naive), tz);
  const off2 = tzOffsetMs(new Date(utc), tz); if (naive - off2 !== utc) utc = naive - off2;
  return new Date(utc);
}
function dateKey(date, tz = S.tz) { const p = tzParts(date, tz); return `${p.y}-${String(p.m).padStart(2,'0')}-${String(p.d).padStart(2,'0')}`; }
function timeKey(date, tz = S.tz) { const p = tzParts(date, tz); return `${String(p.h).padStart(2,'0')}:${String(p.mi).padStart(2,'0')}`; }
function todayKey() { return dateKey(new Date()); }
function addDays(key, n) { const [y, m, d] = key.split('-').map(Number); const dt = new Date(Date.UTC(y, m - 1, d + n)); return dt.toISOString().slice(0, 10); }
function weekStartKey(key) { const [y, m, d] = key.split('-').map(Number); const dt = new Date(Date.UTC(y, m - 1, d)); const wd = (dt.getUTCDay() + 6) % 7; return addDays(key, -wd); }
function parseISO(s) { return new Date(s.endsWith('Z') || s.includes('+') ? s : s + 'Z'); }
function fmtTime(s) { return parseISO(s).toLocaleTimeString('en-GB', { timeZone: S.tz, hour: '2-digit', minute: '2-digit' }); }
function fmtDate(s) { return parseISO(s).toLocaleDateString('en-GB', { timeZone: S.tz, day: 'numeric', month: 'short', year: 'numeric' }); }
function fmtDateShort(s) { return parseISO(s).toLocaleDateString('en-GB', { timeZone: S.tz, weekday: 'short', day: 'numeric', month: 'short' }); }
function fmtDT(s) { return `${fmtDateShort(s)}, ${fmtTime(s)}`; }
function fmtKey(key) { const [y, m, d] = key.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-GB', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' }); }
function fmtKeyLong(key) { const [y, m, d] = key.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-GB', { timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }); }
function money(v) { return `${S.currency} ${Number(v || 0).toLocaleString('en', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`; }
function relTime(s) { const diff = (parseISO(s) - Date.now()) / 60000; const a = Math.abs(diff); const w = a < 60 ? `${Math.round(a)} min` : a < 1440 ? `${Math.round(a / 60)} h` : `${Math.round(a / 1440)} d`; return diff > 0 ? `in ${w}` : `${w} ago`; }

/* ---------- UI helpers ---------- */
function jsArg(v) { return esc(JSON.stringify(v === null || v === undefined ? '' : String(v))); }  // a safe JS string inside an onclick="..." attribute
function esc(s) { if (s === null || s === undefined) return ''; return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;'); }
function $(id) { return document.getElementById(id); }
function val(id) { return $(id).value; }
function setVal(id, v) { const el = $(id); el.value = v === null || v === undefined ? '' : v; if (el._flatpickr) el._flatpickr.setDate(el.value || null, false); }
function badge(status) { return `<span class="badge badge-${status}">${esc(status.replace('_', ' '))}</span>`; }
function toast(msg, isError) { const t = $('toast'); t.textContent = msg; t.classList.toggle('error', !!isError); t.classList.add('show'); clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), isError ? 5000 : 3000); }
/* ---------- dialogs: keyboard, screen readers, focus ---------- */
/* Every modal and the session drawer is a real dialog: focus moves in, Tab stays
   inside, Escape closes, and focus returns to the button that opened it. */
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
const _focusStack = []; // one entry per open dialog, so stacked dialogs each give focus back to their own opener

function _focusInto(scope) {
  if (!scope) return;
  const first = scope.querySelector('[autofocus]') || scope.querySelector(FOCUSABLE);
  if (first) setTimeout(() => { try { first.focus({ preventScroll: true }); } catch (e) {} }, 30);
}
function _restoreFocus() {
  const el = _focusStack.pop();
  if (el && document.contains(el)) { try { el.focus({ preventScroll: true }); } catch (e) {} }
}
function _lockScroll(locked) { document.body.classList.toggle('modal-open', locked); }

// Each dialog opens above whatever is already open, so a form opened from a client profile shows on top of it.
function _topZ() { return 230 + 2 * document.querySelectorAll('.modal-overlay.active, .drawer.active').length; }
function openModal(id) {
  const el = $(id); if (!el) return;
  if (!el.classList.contains('active')) { _focusStack.push(document.activeElement); el.style.zIndex = _topZ(); } // re-opening keeps its opener and place
  el.classList.add('active'); el.setAttribute('aria-hidden', 'false');
  _lockScroll(true);
  _focusInto(el.querySelector('.modal') || el);
}
function closeModal(id) {
  const el = $(id); if (!el || !el.classList.contains('active')) return;
  el.classList.remove('active'); el.setAttribute('aria-hidden', 'true');
  if (!document.querySelector('.modal-overlay.active') && !$('drawer').classList.contains('active')) _lockScroll(false);
  _restoreFocus();
}
function openDrawer() {
  const d = $('drawer'); if (!d.classList.contains('active')) { _focusStack.push(document.activeElement); d.style.zIndex = _topZ(); $('drawer-backdrop').style.zIndex = d.style.zIndex - 1; }
  d.classList.add('active'); d.setAttribute('aria-hidden', 'false');
  $('drawer-backdrop').classList.add('active'); _lockScroll(true);
  _focusInto(d);
}
function closeDrawer() {
  const d = $('drawer'); if (!d.classList.contains('active')) return;
  d.classList.remove('active'); d.setAttribute('aria-hidden', 'true');
  $('drawer-backdrop').classList.remove('active');
  if (!document.querySelector('.modal-overlay.active')) _lockScroll(false);
  _restoreFocus();
}
/* keep Tab inside the dialog that is open */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    const open = [...document.querySelectorAll('.modal-overlay.active')].pop();
    if (open) closeModal(open.id); else closeDrawer();
    return;
  }
  if (e.key !== 'Tab') return;
  const overlay = [...document.querySelectorAll('.modal-overlay.active')].pop();
  const scope = overlay ? overlay.querySelector('.modal') : ($('drawer').classList.contains('active') ? $('drawer') : null);
  if (!scope) return;
  const items = [...scope.querySelectorAll(FOCUSABLE)].filter(n => n.offsetParent !== null || n === document.activeElement);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});
document.querySelectorAll('.modal-overlay').forEach(m => m.addEventListener('click', e => { if (e.target === m) closeModal(m.id); }));
const _deb = {};
function debounce(fn, ms) { return () => { clearTimeout(_deb[fn.name]); _deb[fn.name] = setTimeout(fn, ms); }; }
async function guard(fn) { try { await fn(); } catch (e) { toast(e.message, true); } }
function confirmBox(title, html, okLabel, onOk, okClass = 'btn-primary') {
  $('status-modal-title').textContent = title; $('status-modal-body').innerHTML = html;
  const ok = $('status-modal-ok'); ok.textContent = okLabel; ok.className = 'btn ' + okClass;
  ok.onclick = () => guard(async () => { await onOk(); closeModal('status-modal'); });
  openModal('status-modal');
}
function clientOptions(selected) { return S.clients.map(c => `<option value="${c.id}" ${c.id == selected ? 'selected' : ''}>${esc(c.name)} (${esc(c.phone)})</option>`).join(''); }
function staffOptions(selected, blank = 'Any / unassigned') { return `<option value="">${blank}</option>` + S.staff.filter(s => s.active || s.id == selected).map(s => `<option value="${s.id}" ${s.id == selected ? 'selected' : ''}>${esc(s.name)}</option>`).join(''); }
function serviceOptions(selected) { return S.services.filter(s => s.active || s.id == selected).map(s => `<option value="${s.id}" ${s.id == selected ? 'selected' : ''}>${esc(s.name)} · ${s.duration_minutes} min${s.price ? ' · ' + money(s.price) : ''}</option>`).join(''); }
function fillSelect(id, html) { const el = $(id); const v = el.value; el.innerHTML = html; if (v) el.value = v; }

/* ---------- charts (thin bars, hover tooltip, validated palette) ---------- */
function barChart(el, points, opts) {
  const { series, labelKey = 'label', height = 220, fmt = v => money(v) } = opts; // series: [{key, color, name}]
  el.innerHTML = '';
  if (!points.length) { el.innerHTML = '<div class="empty">No data for this range.</div>'; return; }
  const W = 720, H = height, padL = 46, padR = 8, padT = 12, padB = 28;
  const max = Math.max(1, ...points.map(p => series.reduce((a, s) => a + (p[s.key] || 0), 0)));
  const nice = niceMax(max);
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const bw = innerW / points.length, barW = Math.max(3, Math.min(28, bw * 0.62));
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bar chart">`;
  const ticks = 4;
  for (let i = 0; i <= ticks; i++) { const y = padT + innerH - innerH * i / ticks; const v = nice * i / ticks;
    svg += `<line class="axis" x1="${padL}" x2="${W - padR}" y1="${y}" y2="${y}" ${i ? 'stroke-dasharray="2 3"' : ''}/><text class="lbl" x="${padL - 6}" y="${y + 3}" text-anchor="end">${shortNum(v)}</text>`; }
  const labelEvery = Math.ceil(points.length / 12);
  points.forEach((p, i) => {
    const x = padL + bw * i + (bw - barW) / 2; let yTop = padT + innerH; const total = series.reduce((a, s) => a + (p[s.key] || 0), 0);
    series.forEach((s, si) => { const v = p[s.key] || 0; if (!v) return; const h = innerH * v / nice; yTop -= h;
      const gap = si > 0 ? 2 : 0; const r = si === series.length - 1 || !series.slice(si + 1).some(t => p[t.key]) ? 4 : 0;
      svg += `<path class="bar" data-i="${i}" fill="${s.color}" d="${roundedTop(x, yTop + gap, barW, Math.max(h - gap, 0), r)}"/>`; });
    if (i % labelEvery === 0) svg += `<text class="lbl" x="${x + barW / 2}" y="${H - 8}" text-anchor="middle">${esc(p[labelKey])}</text>`;
    svg += `<rect data-i="${i}" x="${padL + bw * i}" y="${padT}" width="${bw}" height="${innerH}" fill="transparent"/>`;
  });
  svg += '</svg><div class="chart-tip"></div>';
  el.innerHTML = svg;
  const tip = el.querySelector('.chart-tip');
  el.querySelectorAll('[data-i]').forEach(n => {
    n.addEventListener('mousemove', e => { const p = points[+n.dataset.i]; const r = el.getBoundingClientRect();
      tip.innerHTML = `<strong>${esc(p.tooltip || p[labelKey])}</strong><br>` + series.map(s => `${esc(s.name)}: ${fmt(p[s.key] || 0)}`).join('<br>') + (p.extra ? `<br>${esc(p.extra)}` : '');
      tip.style.left = (e.clientX - r.left) + 'px'; tip.style.top = (e.clientY - r.top - 6) + 'px'; tip.style.display = 'block'; });
    n.addEventListener('mouseleave', () => tip.style.display = 'none');
  });
}
function roundedTop(x, y, w, h, r) { r = Math.min(r, w / 2, h); return `M${x},${y + h} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + w - r},${y} Q${x + w},${y} ${x + w},${y + r} L${x + w},${y + h} Z`; }
function niceMax(v) { const p = Math.pow(10, Math.floor(Math.log10(v))); const n = v / p; const m = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10; return m * p; }
function shortNum(v) { return v >= 1000000 ? (v / 1000000).toFixed(1) + 'M' : v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + 'k' : String(Math.round(v)); }
function hbars(el, rows, opts = {}) { // rows: [{name, value, color, count}]
  const { fmt = v => money(v), countLabel = 'sessions' } = opts;
  if (!rows.length) { el.innerHTML = '<div class="empty small">Nothing in this range.</div>'; return; }
  const max = Math.max(...rows.map(r => r.value), 1);
  el.innerHTML = rows.map(r => `<div class="hbar"><div title="${esc(r.name)}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><span class="dot" style="background:${r.color}"></span>${esc(r.name)}</div><div class="track"><div class="fill" style="width:${100 * r.value / max}%;background:${r.color}"></div></div><div class="v">${fmt(r.value)}${r.count !== undefined ? `<div class="tiny muted">${r.count} ${countLabel}</div>` : ''}</div></div>`).join('');
}
const PALETTE = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];

/* English everywhere: the browser's own date/time fields and confirm() boxes follow the phone or computer language
   (Arabic digits, ص/م), so dates use an English picker and questions use the app's own dialog. */
const FP_FORMATS = { date: ['Y-m-d', 'D j M Y'], 'datetime-local': ['Y-m-d\\TH:i', 'D j M Y, H:i'], time: ['H:i', 'H:i'], month: ['Y-m', 'F Y'] };
function enPicker(el) {
  const type = el.getAttribute('type'), f = FP_FORMATS[type];
  if (!f || el._flatpickr || !window.flatpickr) return;
  flatpickr(el, { dateFormat: f[0], altInput: true, altFormat: f[1], disableMobile: true, time_24hr: true, minuteIncrement: 5,
    enableTime: type === 'time' || type === 'datetime-local', noCalendar: type === 'time',
    plugins: type === 'month' && window.monthSelectPlugin ? [new monthSelectPlugin({ shorthand: true, dateFormat: 'Y-m', altFormat: 'F Y' })] : [] });
}
function enPickers(root) { if (root.querySelectorAll) root.querySelectorAll('input[type=date], input[type=time], input[type=month], input[type=datetime-local]').forEach(enPicker); }
enPickers(document);
new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) { if (n.matches('input')) enPicker(n); else enPickers(n); } })))
  .observe(document.body, { childList: true, subtree: true });

function _askClosed(resolve, value) {
  const m = $('status-modal'), obs = new MutationObserver(() => { if (!m.classList.contains('active')) { obs.disconnect(); resolve(value); } });
  obs.observe(m, { attributes: true, attributeFilter: ['class'] });
}
function ask(text, okLabel = 'Yes', okClass = 'btn-danger') {
  return new Promise(resolve => {
    confirmBox('Please confirm', `<p style="white-space:pre-line;margin-top:0">${esc(text)}</p>`, okLabel, () => resolve(true), okClass);
    _askClosed(resolve, false);
  });
}
function askText(title, placeholder = '') {
  return new Promise(resolve => {
    confirmBox(title, `<input id="ask-text" class="input" autofocus autocomplete="off" placeholder="${esc(placeholder)}" onkeydown="if(event.key==='Enter')$('status-modal-ok').click()">`, 'OK', () => resolve(val('ask-text')), 'btn-primary');
    _askClosed(resolve, '');
  });
}

// Keyboard: Enter or Space on anything marked role="button" (cards, rows, tiles) works like a click.
document.addEventListener('keydown', e => {
  const t = e.target;
  if ((e.key === 'Enter' || e.key === ' ') && t && t.getAttribute && t.getAttribute('role') === 'button' && !/^(BUTTON|A|INPUT|SELECT|TEXTAREA)$/.test(t.tagName)) { e.preventDefault(); t.click(); }
});

// Files from the API (CSV exports) are fetched with the sign-in header, never with the token in a link.
async function downloadFile(path, name) {
  guard(async () => {
    const r = await fetch(API + path, { headers: { Authorization: `Bearer ${S.token}` } });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Download failed');
    const url = URL.createObjectURL(await r.blob()), a = document.createElement('a');
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
  });
}
