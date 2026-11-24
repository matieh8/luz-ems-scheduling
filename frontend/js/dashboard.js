/* Dashboard: month-to-date KPIs, 6-month revenue & profit trend, today, packages, best sellers */
const DASH_ICONS = {
  revenue: '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
  profit: '<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
  clients: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  sessions: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18M8 15l2 2 4-4"/>',
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

function kpiCard({ icon, label, value, pct, compare, sub, spark, invert }) {
  return `<div class="kpi"><div class="kpi-ico">${dashIcon(icon)}</div>
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
    svg += `<text class="lbl" x="${x(i)}" y="${H - 9}" text-anchor="middle">${esc(monthLabel(m.period))}</text>`;
    svg += `<rect data-i="${i}" x="${padL + step * i}" y="${padT}" width="${step}" height="${ih}" fill="transparent"/>`;
  });
  el.innerHTML = svg + '</svg><div class="chart-tip"></div>';
  const tip = el.querySelector('.chart-tip');
  el.querySelectorAll('[data-i]').forEach(n => {
    n.addEventListener('mousemove', e => { const m = months[+n.dataset.i]; const r = el.getBoundingClientRect();
      tip.innerHTML = `<strong>${esc(monthLabel(m.period, true))}</strong><br>Revenue: ${money(m.revenue)}<br>Expenses: ${money(m.expenses)}<br>Profit: ${money(m.profit)}<br>${m.sessions} session(s) done`;
      tip.style.left = (e.clientX - r.left) + 'px'; tip.style.top = (e.clientY - r.top - 6) + 'px'; tip.style.display = 'block'; });
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

function rankList(rows, emptyText) {
  if (!rows.length) return `<div class="empty small">${emptyText}</div>`;
  const max = Math.max(...rows.map(r => r.count), 1);
  return rows.map((r, i) => `<div class="rank"><span class="rank-n">${i + 1}</span><div class="rank-main"><div class="rank-top"><strong title="${esc(r.name)}">${esc(r.name)}</strong><span class="mono">${r.count}×</span></div>
    <div class="progress"><div style="width:${100 * r.count / max}%"></div></div><div class="tiny muted">${money(r.value)}</div></div></div>`).join('');
}

async function loadDashboard() {
  const [d, o] = await Promise.all([api('GET', '/dashboard/'), api('GET', '/dashboard/overview')]);
  const k = o.kpis, m = o.months;
  $('dash-greeting').textContent = greeting();
  $('dash-date').textContent = `${fmtKeyLong(o.today)} · here is how ${monthLabel(o.today.slice(0, 7), true)} is going`;
  $('dash-alerts').innerHTML = d.alerts.map(a => `<div class="alert alert-${a.level}" onclick="${a.link ? `dismissAlert('${a.key}', '${a.link}')` : ''}">${esc(a.text)}<span style="margin-left:auto;display:flex;gap:14px;align-items:center;font-size:.8rem">${a.link ? '<span>View →</span>' : ''}<button class="alert-x" title="Dismiss" aria-label="Dismiss" onclick="event.stopPropagation();dismissAlert('${a.key}')">✕</button></span></div>`).join('');

  const cmp = o.compare_label;
  $('dash-stats').innerHTML = [
    kpiCard({ icon: 'revenue', label: 'Revenue this month', value: money(k.revenue.value), pct: k.revenue.change_pct, compare: cmp, sub: cmp, spark: m.map(x => x.revenue) }),
    kpiCard({ icon: 'profit', label: 'Net profit', value: money(k.profit.value), pct: k.profit.change_pct, compare: cmp, sub: `after ${money(k.expenses.value)} expenses`, spark: m.map(x => x.profit) }),
    kpiCard({ icon: 'clients', label: 'Active clients', value: k.active_clients.value, pct: k.active_clients.change_pct, compare: 'vs the 30 days before', sub: 'booked in the last 30 days' }),
    kpiCard({ icon: 'sessions', label: 'Sessions this month', value: k.sessions.value, pct: k.sessions.change_pct, compare: cmp, sub: `${k.sessions.today} today`, spark: m.map(x => x.sessions) }),
  ].join('');

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
    o.recent_payments.map(p => `<tr><td><strong>${esc(p.client_name)}</strong></td><td class="muted">${esc(p.label)}</td><td class="muted">${fmtDate(p.paid_at)}</td><td class="num"><strong>${money(p.amount)}</strong> <span class="chip">${esc(p.method)}</span></td></tr>`).join('')}</tbody></table></div>`
    : '<div class="empty small">No payments recorded yet.</div>';

  const pk = o.packages;
  $('dash-packages').innerHTML = `<div class="pk">
      ${donut([{ v: pk.active, c: 'var(--accent)' }, { v: pk.expiring, c: 'var(--series-4)' }, { v: pk.ended, c: 'var(--series-2)' }])}
      <ul class="pk-legend">
        <li><span class="dot" style="background:var(--accent)"></span>Active<b>${pk.active}</b></li>
        <li><span class="dot" style="background:var(--series-4)"></span>Running low / expiring<b>${pk.expiring}</b></li>
        <li><span class="dot" style="background:var(--series-2)"></span>Ended, last 30 days<b>${pk.ended}</b></li>
      </ul></div>
    ${o.expiring_list.length ? `<div class="pk-list"><div class="tiny muted bold" style="margin:6px 0">Follow up soon</div>${o.expiring_list.map(s => `<div class="pk-row" onclick="go('subscriptions')" role="button" tabindex="0"><div><strong>${esc(s.client_name)}</strong><div class="tiny muted">${esc(s.plan)}</div></div><div class="tiny" style="text-align:right">${s.remaining} left${s.end_date ? `<div class="muted">until ${fmtDate(s.end_date)}</div>` : ''}</div></div>`).join('')}</div>` : ''}`;

  $('dash-top-services').innerHTML = rankList(o.top_services, 'No sessions booked this month yet.');
  $('dash-top-plans').innerHTML = rankList(o.top_plans, 'No packages sold this month yet.');
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
