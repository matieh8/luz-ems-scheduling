/* Dashboard */
async function loadDashboard() {
  const t = todayKey();
  const [d, ts] = await Promise.all([api('GET', '/dashboard/'), api('GET', `/reports/timeseries?from=${addDays(t, -13)}&to=${t}&granularity=day`)]);
  $('dash-date').textContent = fmtKeyLong(t);
  $('dash-alerts').innerHTML = d.alerts.map(a => `<div class="alert alert-${a.level}" onclick="${a.link ? `dismissAlert('${a.key}', '${a.link}')` : ''}">${a.level === 'serious' ? '⚠️' : a.level === 'warning' ? '⏳' : 'ℹ️'} ${esc(a.text)}<span style="margin-left:auto;display:flex;gap:14px;align-items:center;font-size:.8rem">${a.link ? '<span>View →</span>' : ''}<button class="alert-x" title="Dismiss" onclick="event.stopPropagation();dismissAlert('${a.key}')">✕</button></span></div>`).join('');
  $('dash-stats').innerHTML = `
    <div class="stat accent"><div class="stat-label">Revenue this month</div><div class="stat-value">${money(d.revenue_this_month)}</div><div class="stat-sub">${money(d.revenue_this_week)} this week · ${money(d.revenue_today)} today</div></div>
    <div class="stat"><div class="stat-label">Sessions today</div><div class="stat-value">${d.appointments_today}</div><div class="stat-sub">${d.appointments_this_week} this week · ${d.sessions_this_month} done this month</div></div>
    <div class="stat"><div class="stat-label">Active packages</div><div class="stat-value">${d.active_subscriptions}</div><div class="stat-sub">${d.subscriptions_expiring_soon} low or expiring</div></div>
    <div class="stat"><div class="stat-label">Clients</div><div class="stat-value">${d.total_clients}</div><div class="stat-sub">+${d.new_clients_this_month} this month${d.unpaid_count ? ` · <span style="color:var(--bad)">${money(d.unpaid_amount)} unpaid</span>` : ''}</div></div>`;
  $('dash-today-count').textContent = d.today_appointments.length ? `${d.today_appointments.length} session(s)` : '';
  $('dash-today').innerHTML = d.today_appointments.length ? d.today_appointments.map(a => `<div style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="openAppointment(${a.id})">
      <div class="mono bold" style="width:52px">${fmtTime(a.start_time)}</div><div style="width:4px;height:34px;border-radius:2px;background:${a.service.color}"></div>
      <div style="flex:1;min-width:0"><strong>${esc(a.client.name)}</strong><div class="tiny muted" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(a.service.name)}${a.staff ? ' · ' + esc(a.staff.name) : ''}${a.subscription_id ? ' · package' : ''}</div></div>${badge(a.status)}</div>`).join('') : '<div class="empty small">No sessions today. <a href="#" onclick="openBookingModal();return false">Book one</a></div>';
  barChart($('dash-chart'), ts.points.map(p => ({ label: labelPeriod(p.period, 'day'), tooltip: labelPeriod(p.period, 'day', true), v: p.collected, extra: `${p.sessions} session(s)` })), { series: [{ key: 'v', color: 'var(--series-1)', name: 'Collected' }], height: 200 });
  $('dash-upcoming').innerHTML = d.upcoming.length ? apptTable(d.upcoming, { withDate: true }) : '<div class="empty small">Nothing upcoming.</div>';
}

async function dismissAlert(key, link) {
  const el = [...document.querySelectorAll('#dash-alerts .alert')].find(x => x.innerHTML.includes(`'${key}'`));
  if (el) el.remove();
  try { await api('POST', `/dashboard/alerts/${key}/dismiss`); } catch (e) {}
  if (link) go(link);
}
