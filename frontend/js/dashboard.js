/* Dashboard: month-to-date KPIs, 6-month revenue & profit trend, today, packages, best sellers */
const DASH_ICONS = {
  revenue: '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
  profit: '<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
  clients: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  sessions: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18M8 15l2 2 4-4"/>',
  expenses: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20M6 15h4"/>',
  today: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  upcoming: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18M12 14v4M10 16h4"/>',
  owed: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  expiring: '<path d="M5 22h14M5 2h14M17 22v-4.2a2 2 0 0 0-.6-1.4L12 12l-4.4 4.4a2 2 0 0 0-.6 1.4V22M7 2v4.2a2 2 0 0 0 .6 1.4L12 12l4.4-4.4a2 2 0 0 0 .6-1.4V2"/>',
  leads: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/>',
};
const dashIcon = k => `<svg viewBox="0 0 24 24" aria-hidden="true">${DASH_ICONS[k]}</svg>`;

function greeting() {
  const h = tzParts(new Date()).h;
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

function changePill(pct, label, invert) {
  if (pct === null || pct === undefined) return `<span class="kpi-change flat" title="${esc(label)}">no data last month</span>`;
  const up = pct >= 0, good = invert ? !up : up;
  return `<span class="kpi-change ${good ? 'up' : 'down'}" title="${esc(label)}">${up ? '↑' : '↓'} ${Math.abs(pct).toFixed(1)}%</span>`;
}

function sparkBars(values) {
  if (!values || !values.some(v => v)) return '';
  const max = Math.max(...values.map(v => Math.max(v, 0)), 1);
  return `<svg class="kpi-spark" viewBox="0 0 ${values.length * 8} 28" aria-hidden="true">${values.map((v, i) => {
    const h = Math.max(2, 26 * Math.max(v, 0) / max);
    return `<rect x="${i * 8 + 1}" y="${28 - h}" width="5" height="${h}" rx="1.5" opacity="${i === values.length - 1 ? 1 : .45}"/>`; }).join('')}</svg>`;
}

function kpiCard({ icon, label, value, pct, compare, sub, spark, invert, open }) {
  return `<div class="kpi${open ? ' clickable' : ''}"${open ? ` role="button" tabindex="0" onclick="${open}"` : ''}><div class="kpi-ico">${dashIcon(icon)}</div>
    <div class="kpi-body"><div class="kpi-label">${esc(label)}</div><div class="kpi-value">${value}</div>
    <div class="kpi-foot">${changePill(pct, compare, invert)}<span class="kpi-sub">${sub}</span></div></div>${sparkBars(spark)}</div>`;
}

function monthLabel(period, long) {
  const [y, m] = period.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('en-GB', { timeZone: 'UTC', month: long ? 'long' : 'short', ...(long ? { year: 'numeric' } : {}) });
}

/* Revenue area + profit line over expense bars, one point per month */
function trendChart(el, months) {
  if (!months.length || !months.some(m => m.revenue || m.expenses)) { el.innerHTML = '<div class="empty small">No payments or expenses in the last 6 months yet.</div>'; return; }
  // Draw at the real width so labels keep their size on a phone instead of shrinking with the SVG
  const W = Math.max(300, Math.round(el.clientWidth || 720)), H = W < 480 ? 210 : 240;
  const padL = 42, padR = 12, padT = 16, padB = 30, iw = W - padL - padR, ih = H - padT - padB;
  const hi = Math.max(1, ...months.map(m => Math.max(m.revenue, m.expenses)));
  const lo = Math.min(0, ...months.map(m => m.profit));
  const top = niceMax(hi), bottom = lo < 0 ? -niceMax(-lo) : 0, span = top - bottom;
  const y = v => padT + ih * (top - v) / span;
  const step = iw / months.length, x = i => padL + step * i + step / 2;
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Revenue, expenses and profit by month">
    <defs><linearGradient id="revfill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--series-1)" stop-opacity=".22"/><stop offset="1" stop-color="var(--series-1)" stop-opacity="0"/></linearGradient></defs>`;
  for (let i = 0; i <= 4; i++) { const v = bottom + span * i / 4, yy = y(v);
    svg += `<line class="axis" x1="${padL}" x2="${W - padR}" y1="${yy}" y2="${yy}" ${v ? 'stroke-dasharray="2 3"' : ''}/><text class="lbl" x="${padL - 6}" y="${yy + 3}" text-anchor="end">${v < 0 ? '-' : ''}${shortNum(Math.abs(v))}</text>`; }
  const bw = Math.min(26, step * .34);
  months.forEach((m, i) => { if (m.expenses > 0) svg += `<path fill="var(--series-2)" opacity=".55" d="${roundedTop(x(i) - bw / 2, y(m.expenses), bw, y(0) - y(m.expenses), 4)}"/>`; });
  const rev = months.map((m, i) => [x(i), y(m.revenue)]), prof = months.map((m, i) => [x(i), y(m.profit)]);
  const line = pts => pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  svg += `<path d="${line(rev)} L${rev[rev.length - 1][0]},${y(0)} L${rev[0][0]},${y(0)} Z" fill="url(#revfill)"/>`;
  svg += `<path d="${line(rev)}" fill="none" stroke="var(--series-1)" stroke-width="2.5" stroke-linejoin="round"/>`;
  svg += `<path d="${line(prof)}" fill="none" stroke="var(--text)" stroke-width="1.6" stroke-dasharray="5 4"/>`;
  rev.forEach(p => { svg += `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="var(--surface)" stroke="var(--series-1)" stroke-width="2.2"/>`; });
  months.forEach((m, i) => {
    svg += `<text class="lbl${i === months.length - 1 ? ' lbl-now' : ''}" x="${x(i)}" y="${H - 9}" text-anchor="middle">${esc(monthLabel(m.period))}</text>`;
    svg += `<rect data-i="${i}" x="${padL + step * i}" y="${padT}" width="${step}" height="${ih}" fill="transparent"/>`;
  });
  el.innerHTML = svg + '</svg><div class="chart-tip"></div>';
  const tip = el.querySelector('.chart-tip');
  el.querySelectorAll('[data-i]').forEach(n => {
    const show = e => { const m = months[+n.dataset.i]; const r = el.getBoundingClientRect(), p = e.touches ? e.touches[0] : e;
      tip.innerHTML = `<strong>${esc(monthLabel(m.period, true))}</strong><br>Revenue: ${money(m.revenue)}<br>Expenses: ${money(m.expenses)}<br>Profit: ${money(m.profit)}<br>${m.sessions} session(s) done`;
      tip.style.left = Math.min(Math.max(p.clientX - r.left, 70), r.width - 70) + 'px'; tip.style.top = (p.clientY - r.top - 6) + 'px'; tip.style.display = 'block'; };
    n.addEventListener('mousemove', show);
    n.addEventListener('touchstart', show, { passive: true });  // phones: tap a month to see its numbers
    n.addEventListener('mouseleave', () => tip.style.display = 'none');
  });
}

function donut(parts) {
  const total = parts.reduce((a, p) => a + p.v, 0);
  const R = 46, C = 2 * Math.PI * R;
  let off = 0, rings = '';
  if (total) parts.forEach(p => { if (!p.v) return; const len = C * p.v / total;
    rings += `<circle r="${R}" cx="60" cy="60" fill="none" stroke="${p.c}" stroke-width="14" stroke-dasharray="${Math.max(len - 2, 0.1)} ${C}" stroke-dashoffset="${-off}" transform="rotate(-90 60 60)"/>`; off += len; });
  return `<svg class="donut" viewBox="0 0 120 120" role="img" aria-label="Packages"><circle r="${R}" cx="60" cy="60" fill="none" stroke="var(--bg)" stroke-width="14"/>${rings}
    <text x="60" y="58" text-anchor="middle" class="donut-n">${total}</text><text x="60" y="74" text-anchor="middle" class="donut-l">packages</text></svg>`;
}

function rankList(rows, emptyText, kind) {
  if (!rows.length) return `<div class="empty small">${emptyText}</div>`;
  const max = Math.max(...rows.map(r => r.count), 1);
  return rows.map((r, i) => `<div class="rank clickable" role="button" tabindex="0" onclick="dashDetail('${kind}', ${esc(JSON.stringify(r.name))})"><span class="rank-n">${i + 1}</span><div class="rank-main"><div class="rank-top"><strong title="${esc(r.name)}">${esc(r.name)}</strong><span class="mono">${r.count}×</span></div>
    <div class="progress"><div style="width:${100 * r.count / max}%"></div></div><div class="tiny muted">${money(r.value)}</div></div></div>`).join('');
}

async function loadDashboard() {
  const [d, o] = await Promise.all([api('GET', '/dashboard/'), api('GET', '/dashboard/overview')]);
  const k = o.kpis, m = o.months;
  DASH_TODAY = o.today; DASH_O = o;
  $('dash-greeting').textContent = greeting();
  $('dash-date').textContent = `${fmtKeyLong(o.today)} · here is how ${monthLabel(o.today.slice(0, 7), true)} is going`;
  $('dash-alerts').innerHTML = d.alerts.map(a => `<div class="alert alert-${a.level}" onclick="${a.link ? `dismissAlert('${a.key}', '${a.link}')` : ''}">${esc(a.text)}<span style="margin-left:auto;display:flex;gap:14px;align-items:center;font-size:.8rem">${a.link ? '<span>View →</span>' : ''}<button class="alert-x" title="Dismiss" aria-label="Dismiss" onclick="event.stopPropagation();dismissAlert('${a.key}')">✕</button></span></div>`).join('');

  const cmp = o.compare_label;
  $('dash-stats').innerHTML = [
    kpiCard({ open: "dashDetail('revenue')", icon: 'revenue', label: 'Revenue this month', value: money(k.revenue.value), pct: k.revenue.change_pct, compare: cmp, sub: cmp, spark: m.map(x => x.revenue) }),
    kpiCard({ open: "dashDetail('expenses')", icon: 'expenses', label: 'Expenses this month', value: money(k.expenses.value), pct: k.expenses.change_pct, compare: cmp, sub: cmp, spark: m.map(x => x.expenses), invert: true }),
    kpiCard({ open: "dashDetail('profit')", icon: 'profit', label: 'Net profit', value: money(k.profit.value), pct: k.profit.change_pct, compare: cmp, sub: 'revenue − expenses', spark: m.map(x => x.profit) }),
    kpiCard({ open: "dashDetail('clients')", icon: 'clients', label: 'Active clients', value: k.active_clients.value, pct: k.active_clients.change_pct, compare: 'vs the 30 days before', sub: 'booked in the last 30 days' }),
  ].join('');

  // Today at a glance: each tile opens the list behind its number
  const t = o.today_sessions, up = o.upcoming, lead = k.leads, plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  $('dash-pulse').innerHTML = [
    pulseTile({ open: "dashDetail('today')", icon: 'today', label: "Today's sessions", value: t.total, sub: t.total ? `${t.done} done · ${t.to_come} to come${t.no_show ? ` · ${t.no_show} no-show` : ''}` : 'nothing booked' }),
    pulseTile({ open: "dashDetail('upcoming')", icon: 'upcoming', label: 'Upcoming bookings', value: up.count, sub: `next ${up.days} days${up.unconfirmed ? ` · <span class="warn">${up.unconfirmed} not confirmed</span>` : ''}` }),
    pulseTile({ open: "dashDetail('sessions')", icon: 'sessions', label: 'Sessions this month', value: k.sessions.value, sub: `${changePill(k.sessions.change_pct, cmp)} ${esc(cmp)}` }),
    pulseTile({ open: "dashDetail('owed')", icon: 'owed', label: 'Outstanding payments', value: money(o.due.amount), sub: o.due.count ? plural(o.due.count, 'unpaid session') : 'all paid up', tone: o.due.amount ? 'bad' : '' }),
    pulseTile({ open: "dashDetail('expiring')", icon: 'expiring', label: 'Expiring packages', value: o.packages.expiring, sub: o.packages.expiring ? 'running low or ending soon' : 'none right now', tone: o.packages.expiring ? 'warn' : '' }),
    pulseTile({ open: "setVal('lead-status', ''); go('leads')", icon: 'leads', label: 'New leads', value: lead.value, sub: `this month · ${lead.open} open${lead.follow_ups_due ? ` · <span class="warn">${plural(lead.follow_ups_due, 'follow-up')} due</span>` : ''}` }),
  ].join('');
  $('dash-updated').textContent = `Updated ${fmtTime(o.updated_at)} · refreshes every minute`;
  dashAutoRefresh();

  trendChart($('dash-chart'), m);
  window._dashMonths = m;
  const cur = m[m.length - 1], prev = m[m.length - 2];
  $('dash-chart-note').textContent = prev ? `${monthLabel(cur.period, true)} so far: ${money(cur.revenue)} in, ${money(cur.profit)} profit. ${monthLabel(prev.period, true)}: ${money(prev.revenue)} in, ${money(prev.profit)} profit.` : '';

  const today = d.today_appointments;
  $('dash-today').innerHTML = today.length ? today.map(a => `<div class="sched" onclick="openAppointment(${a.id})" role="button" tabindex="0">
      <div class="sched-time mono">${fmtTime(a.start_time)}</div><span class="sched-bar" style="background:${a.service.color}"></span>
      <div class="sched-main"><strong>${esc(a.client.name)}</strong><div class="tiny muted">${esc(a.service.name)}${a.staff ? ' · ' + esc(a.staff.name) : ''}${a.subscription_id ? ' · package' : ''}</div></div>${badge(a.status)}</div>`).join('')
    : `<div class="empty small">No sessions today.<br><a href="#" onclick="openBookingModal();return false">Book one</a></div>`;

  $('dash-payments').innerHTML = o.recent_payments.length ? `<div class="table-wrap"><table class="plain"><thead><tr><th>Client</th><th>For</th><th>Date</th><th class="num">Amount</th></tr></thead><tbody>${
    o.recent_payments.map(p => `<tr class="clickable" onclick="${p.client_id ? `openClientDetail(${p.client_id}, 'pays')` : "go('payments')"}"><td><strong>${esc(p.client_name || 'Other income')}</strong></td><td class="muted">${esc(p.label)}</td><td class="muted">${fmtDate(p.paid_at)}</td><td class="num"><strong>${money(p.amount)}</strong> <span class="chip">${esc(p.method)}</span></td></tr>`).join('')}</tbody></table></div>`
    : '<div class="empty small">No payments recorded yet.</div>';

  const pk = o.packages;
  $('dash-packages').innerHTML = `<div class="pk">
      ${donut([{ v: pk.active, c: 'var(--accent)' }, { v: pk.expiring, c: 'var(--series-4)' }, { v: pk.ended, c: 'var(--series-2)' }])}
      <ul class="pk-legend">
        <li class="clickable" onclick="go('subscriptions')"><span class="dot" style="background:var(--accent)"></span>Active<b>${pk.active}</b></li>
        <li class="clickable" onclick="go('subscriptions')"><span class="dot" style="background:var(--series-4)"></span>Running low / expiring<b>${pk.expiring}</b></li>
        <li class="clickable" onclick="go('subscriptions')"><span class="dot" style="background:var(--series-2)"></span>Ended, last 30 days<b>${pk.ended}</b></li>
      </ul></div>
    ${o.expiring_list.length ? `<div class="pk-list"><div class="tiny muted bold" style="margin:6px 0">Follow up soon</div>${o.expiring_list.slice(0, 5).map(s => `<div class="pk-row" onclick="openClientDetail(${s.client_id}, 'subs')" role="button" tabindex="0"><div><strong>${esc(s.client_name)}</strong><div class="tiny muted">${esc(s.plan)}</div></div><div class="tiny" style="text-align:right">${s.remaining} left${s.end_date ? `<div class="muted">until ${fmtDate(s.end_date)}</div>` : ''}</div></div>`).join('')}</div>` : ''}`;

  $('dash-top-services').innerHTML = rankList(o.top_services, 'No sessions booked this month yet.', 'service');
  $('dash-top-plans').innerHTML = rankList(o.top_plans, 'No packages sold this month yet.', 'plan');
  $('dash-owed').innerHTML = `
    <div class="owed" onclick="go('payments')" role="button" tabindex="0"><div class="tiny muted">Unpaid completed sessions</div><div class="owed-v ${o.due.amount ? 'bad' : ''}">${money(o.due.amount)}</div><div class="tiny muted">${o.due.count} session(s) · tap to collect</div></div>
    <div class="owed" onclick="go('subscriptions')" role="button" tabindex="0"><div class="tiny muted">Sessions left on active packages</div><div class="owed-v">${o.sessions_remaining}</div><div class="tiny muted">still to be booked and delivered</div></div>`;

  $('dash-upcoming').innerHTML = d.upcoming.length ? apptTable(d.upcoming, { withDate: true }) : '<div class="empty small">Nothing upcoming.</div>';
}

// Redraw the trend chart at the new width when the window or phone rotates
let _dashResize;
window.addEventListener('resize', () => { clearTimeout(_dashResize); _dashResize = setTimeout(() => {
  if (window._dashMonths && $('page-dashboard').classList.contains('active')) trendChart($('dash-chart'), window._dashMonths); }, 150); });

async function dismissAlert(key, link) {
  const el = [...document.querySelectorAll('#dash-alerts .alert')].find(x => x.innerHTML.includes(`'${key}'`));
  if (el) el.remove();
  try { await api('POST', `/dashboard/alerts/${key}/dismiss`); } catch (e) {}
  if (link) go(link);
}

/* ---------- tap a box: the list behind its number ---------- */
let DASH_TODAY = null, DASH_O = null, _dashTimer = null;
function pulseTile({ icon, label, value, sub, open, tone }) {
  return `<div class="pulse clickable${tone ? ' ' + tone : ''}" role="button" tabindex="0" onclick="${open}">
    <div class="pulse-top"><span class="pulse-ico">${dashIcon(icon)}</span><span class="pulse-label">${esc(label)}</span></div>
    <div class="pulse-value">${value}</div><div class="pulse-sub">${sub}</div></div>`;
}
// Live: reload the numbers every minute while the dashboard is on screen, and as soon as the tab comes back.
function dashAutoRefresh() {
  if (_dashTimer) return;
  _dashTimer = setInterval(() => { if (S.page === 'dashboard' && !document.hidden && !document.querySelector('.modal-overlay.active, .drawer.active')) loadDashboard().catch(() => {}); }, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && S.page === 'dashboard') loadDashboard().catch(() => {}); });
}
async function monthExpenses(y, mo, to) {
  const ex = ((await api('GET', `/expenses/summary?year=${y}&month=${mo}`)).expenses || []).filter(e => parseISO(e.date) < to), outSum = ex.reduce((a, e) => a + e.amount, 0);
  return [outSum, `<div class="section-label">Expenses · ${money(outSum)}</div>` + (ex.length ? `<div class="table-wrap"><table><thead><tr><th>Date</th><th>Category</th><th class="num">Amount</th></tr></thead><tbody>${
    ex.sort((a, b) => a.date < b.date ? 1 : -1).map(e => `<tr class="clickable" onclick="closeModal('detail-modal');go('expenses')"><td>${fmtDate(e.date)}</td><td>${expLogo(e.category)} ${esc(e.category)}${e.paid === false ? ' <span class="chip chip-bad">unpaid</span>' : ''}${e.notes ? `<div class="tiny muted">${esc(e.notes)}</div>` : ''}</td><td class="num bold">${money(e.amount)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty small">No expenses.</div>')];
}
function showDetail(title, html) { $('detail-title').textContent = title; $('detail-body').innerHTML = html; openModal('detail-modal'); }
async function dashDetail(kind, arg) {
  guard(async () => {
    const ym = (DASH_TODAY || todayKey()).slice(0, 7), [y, mo] = ym.split('-').map(Number);
    const from = zonedToDate(`${ym}-01`, '00:00'), to = zonedToDate(addDays(DASH_TODAY || todayKey(), 1), '00:00');  // month so far, like the boxes
    const range = `from_date=${from.toISOString()}&to_date=${to.toISOString()}`, label = monthLabel(ym, true);
    if (kind === 'revenue' || kind === 'profit') {
      const pays = await api('GET', `/payments/?${range}&limit=100000`), inSum = pays.reduce((a, p) => a + p.amount, 0);
      let html = `<div class="section-label">Money in · ${money(inSum)}</div>` + paymentsTable(pays);
      if (kind === 'profit') {
        const [outSum, exHtml] = await monthExpenses(y, mo, to);
        html = `<p class="mb">${money(inSum)} in − ${money(outSum)} expenses = <strong>${money(inSum - outSum)}</strong></p>` + html + exHtml;
      }
      return showDetail(`${kind === 'revenue' ? 'Revenue' : 'Net profit'} · ${label}`, html);
    }
    if (kind === 'expenses') { const [outSum, exHtml] = await monthExpenses(y, mo, to); return showDetail(`Expenses · ${label} (${money(outSum)})`, exHtml); }
    if (kind === 'today' || kind === 'upcoming') {
      const f = kind === 'today' ? zonedToDate(DASH_TODAY, '00:00') : new Date(), t2 = kind === 'today' ? zonedToDate(addDays(DASH_TODAY, 1), '00:00') : new Date(Date.now() + 7 * 864e5);
      const list = (await api('GET', `/appointments/?from_date=${f.toISOString()}&to_date=${t2.toISOString()}&limit=5000`))
        .filter(a => kind === 'today' ? a.status !== 'cancelled' : ['scheduled', 'confirmed'].includes(a.status)).sort((a, b) => a.start_time < b.start_time ? -1 : 1);
      return showDetail(kind === 'today' ? `Today's sessions (${list.length})` : `Upcoming bookings · next 7 days (${list.length})`, list.length ? apptTable(list, { withDate: kind !== 'today' }) : '<div class="empty small">Nothing booked.</div>');
    }
    if (kind === 'owed') {
      const list = await api('GET', '/appointments/?status=completed&unpaid=true&limit=2000');
      return showDetail(`Outstanding payments (${money(list.reduce((a, x) => a + x.balance_due, 0))})`,
        list.length ? apptTable(list.reverse(), { withDate: true }) + `<p class="small muted mt">Open a session to record its payment.</p>` : '<div class="empty small">Everything is paid up.</div>');
    }
    if (kind === 'expiring') {
      const rows = (DASH_O && DASH_O.expiring_list) || [];
      return showDetail(`Expiring packages (${rows.length})`, rows.length ? `<div class="table-wrap"><table><thead><tr><th>Client</th><th>Package</th><th class="num">Left</th><th>Ends</th></tr></thead><tbody>${
        rows.map(s => `<tr class="clickable" onclick="openClientDetail(${s.client_id}, 'subs')"><td><div class="who">${avatar(s.client_name)}<strong>${esc(s.client_name)}</strong></div></td><td>${esc(s.plan)}</td><td class="num"><strong>${s.remaining}</strong></td><td>${s.end_date ? fmtDate(s.end_date) : '<span class="muted">no end date</span>'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty small">No packages are running low or ending soon.</div>');
    }
    if (kind === 'sessions' || kind === 'service') {
      let list = await api('GET', `/appointments/?${range}&limit=5000`);
      list = kind === 'sessions' ? list.filter(a => a.status === 'completed') : list.filter(a => a.service.name === arg && ['scheduled', 'confirmed', 'completed'].includes(a.status));
      return showDetail(`${kind === 'sessions' ? 'Sessions done' : arg} · ${label} (${list.length})`, apptTable(list, { withDate: true }));
    }
    if (kind === 'clients') {
      const now = new Date(), list = (await api('GET', `/appointments/?from_date=${new Date(now - 30 * 864e5).toISOString()}&to_date=${now.toISOString()}&limit=5000`))
        .filter(a => ['scheduled', 'confirmed', 'completed'].includes(a.status));
      const by = {}; list.forEach(a => { const r = by[a.client_id] = by[a.client_id] || { c: a.client, n: 0, last: a.start_time }; r.n++; if (a.start_time > r.last) r.last = a.start_time; });
      const rows = Object.entries(by).sort((a, b) => b[1].n - a[1].n);
      return showDetail(`Active clients · last 30 days (${rows.length})`, rows.length ? `<div class="table-wrap"><table><thead><tr><th>Client</th><th class="num">Sessions</th><th>Last</th></tr></thead><tbody>${
        rows.map(([id, r]) => `<tr class="clickable" onclick="openClientDetail(${id})"><td><div class="who">${avatar(r.c.name)}<div><strong>${esc(r.c.name)}</strong><div class="tiny muted">${esc(r.c.phone)}</div></div></div></td><td class="num">${r.n}</td><td>${fmtDate(r.last)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty small">No sessions in the last 30 days.</div>');
    }
    if (kind === 'plan') {
      const subs = (await api('GET', '/subscriptions/')).filter(s => s.plan.name === arg && s.status !== 'cancelled' && parseISO(s.created_at) >= from);
      return showDetail(`${arg} · sold in ${label} (${subs.length})`, subsTable(subs));
    }
  });
}
