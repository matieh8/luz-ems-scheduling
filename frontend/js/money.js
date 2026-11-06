/* Packages (subscriptions & plans), payments, revenue reports */
function subsTable(subs) {
  if (!subs.length) return '<div class="card empty">No packages.</div>';
  return `<div class="table-wrap"><table><thead><tr><th>Client</th><th>Plan</th><th>Usage</th><th>Valid</th><th class="num">Price</th><th>Status</th><th></th></tr></thead><tbody>` + subs.map(s => {
    const pct = s.sessions_total ? 100 * s.sessions_used / s.sessions_total : 0;
    const expSoon = s.end_date && parseISO(s.end_date) < new Date(Date.now() + 7 * 86400000);
    return `<tr>
      <td><strong>${esc(s.client.name)}</strong><div class="tiny muted">${esc(s.client.phone)}</div></td>
      <td>${esc(s.plan.name)}</td>
      <td style="min-width:140px"><div class="small">${s.sessions_used} / ${s.sessions_total} used · <strong>${s.sessions_remaining} left</strong></div><div class="progress"><div style="width:${pct}%"></div></div></td>
      <td class="small">${fmtDate(s.start_date)} → ${s.end_date ? fmtDate(s.end_date) : 'no expiry'}${expSoon && s.status === 'active' ? '<div class="tiny" style="color:var(--warn)">expires soon</div>' : ''}</td>
      <td class="num">${money(s.price_paid)}${s.paid_amount < s.price_paid ? `<div class="tiny" style="color:var(--bad)">paid ${money(s.paid_amount)}</div>` : ''}</td>
      <td>${badge(s.status === 'active' ? 'active' : s.status === 'expired' ? 'expired' : 'neutral').replace('neutral', s.status)}</td>
      <td class="num"><button class="btn btn-ghost btn-xs" onclick="editSubscription(${s.id})">Edit</button>${s.paid_amount < s.price_paid ? `<button class="btn btn-ghost btn-xs" onclick="openPaymentModal({client_id:${s.client_id}, subscription_id:${s.id}, amount:${s.price_paid - s.paid_amount}, label:'${esc(s.plan.name)}'})">Pay</button>` : ''}<button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteSubscription(${s.id}, '${esc(s.plan.name).replace(/'/g, "\\'")}')">Delete</button></td></tr>`; }).join('') + '</tbody></table></div>';
}
let SUBS = { tab: 'active' };
function subTab(t, el) { SUBS.tab = t; document.querySelectorAll('#page-subscriptions .tab').forEach(x => x.classList.remove('active')); el.classList.add('active'); document.querySelectorAll('#page-subscriptions .subpanel').forEach(p => p.classList.toggle('active', p.id === 'sub-' + t)); loadSubscriptions(); }
async function loadSubscriptions() {
  if (SUBS.tab === 'plans') return loadPlans();
  const subs = await api('GET', `/subscriptions/${SUBS.tab === 'active' ? '?active=true' : ''}`);
  $('sub-' + SUBS.tab).innerHTML = subsTable(subs);
}
async function loadPlans() {
  const plans = await api('GET', '/subscriptions/plans'); S.plans = plans;
  $('sub-plans').innerHTML = !plans.length ? '<div class="card empty">No plans yet.</div>' : `<div class="table-wrap"><table><thead><tr><th>Plan</th><th class="num">Sessions</th><th>Validity</th><th class="num">Price</th><th class="num">Per session</th><th>Status</th><th></th></tr></thead><tbody>` +
    plans.map(p => `<tr><td><strong>${esc(p.name)}</strong><div class="tiny muted">${esc(p.description || '')}</div></td><td class="num">${p.sessions_included}</td><td>${p.duration_days ? p.duration_days + ' days' : 'No expiry'}</td><td class="num">${money(p.price)}</td><td class="num muted">${money(p.price / p.sessions_included)}</td><td>${p.active ? badge('active') : '<span class="badge badge-neutral">inactive</span>'}</td>
      <td class="num"><button class="btn btn-ghost btn-xs" onclick="editPlan(${p.id})">Edit</button><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deletePlan(${p.id})">Delete</button></td></tr>`).join('') + '</tbody></table></div>';
}
function openPlanModal() { $('plan-modal-title').textContent = 'New plan'; ['plan-id', 'plan-name', 'plan-sessions', 'plan-days', 'plan-price', 'plan-description'].forEach(i => setVal(i, '')); $('plan-active').checked = true; openModal('plan-modal'); }
function editPlan(id) { const p = S.plans.find(x => x.id === id); openPlanModal(); $('plan-modal-title').textContent = 'Edit plan'; setVal('plan-id', p.id); setVal('plan-name', p.name); setVal('plan-sessions', p.sessions_included); setVal('plan-days', p.duration_days); setVal('plan-price', p.price); setVal('plan-description', p.description); $('plan-active').checked = p.active; }
async function savePlan() { guard(async () => { const id = val('plan-id'); const payload = { name: val('plan-name'), sessions_included: +val('plan-sessions'), duration_days: val('plan-days') ? +val('plan-days') : null, price: parseFloat(val('plan-price')), description: val('plan-description') || null, active: $('plan-active').checked };
  if (!payload.name || !payload.sessions_included || isNaN(payload.price)) throw new Error('Name, sessions and price are required');
  if (id) await api('PUT', `/subscriptions/plans/${id}`, payload); else await api('POST', '/subscriptions/plans', payload); closeModal('plan-modal'); toast('Plan saved'); await refreshLookups(); loadPlans(); }); }
function deletePlan(id) { confirmBox('Delete plan', '<p>Delete this plan? If it has been sold it will be deactivated instead.</p>', 'Delete', async () => { const r = await api('DELETE', `/subscriptions/plans/${id}`); toast(r.detail); await refreshLookups(); loadPlans(); }, 'btn-danger'); }

function openSubscriptionModal(id, clientId) {
  $('subscription-modal-title').textContent = 'Sell package';
  fillSelect('subscription-client', clientOptions(clientId)); fillSelect('subscription-plan', S.plans.filter(p => p.active).map(p => `<option value="${p.id}">${esc(p.name)} · ${money(p.price)}</option>`).join(''));
  ['subscription-id', 'subscription-end', 'subscription-total', 'subscription-price', 'subscription-notes'].forEach(i => setVal(i, ''));
  setVal('subscription-start', todayKey()); setVal('subscription-used', 0); setVal('subscription-status', 'active'); setVal('subscription-method', 'cash'); $('subscription-notify').checked = true;
  $('subscription-payment-row').style.display = 'grid'; $('subscription-notify-row').style.display = 'flex';
  if (clientId) setVal('subscription-client', clientId);
  fillPlanDefaults(true); openModal('subscription-modal');
}
function fillPlanDefaults(force) {
  const plan = S.plans.find(p => p.id == val('subscription-plan')); if (!plan || val('subscription-id')) return;
  if (force || !val('subscription-total')) setVal('subscription-total', plan.sessions_included);
  if (force || !val('subscription-price')) setVal('subscription-price', plan.price);
  if (plan.duration_days && val('subscription-start')) setVal('subscription-end', addDays(val('subscription-start'), plan.duration_days));
}
async function editSubscription(id) {
  const s = (await api('GET', `/subscriptions/?client_id=0`).catch(() => [])) && (await api('GET', '/subscriptions/')).find(x => x.id === id);
  openSubscriptionModal(null, s.client_id); $('subscription-modal-title').textContent = 'Edit package';
  fillSelect('subscription-plan', S.plans.map(p => `<option value="${p.id}">${esc(p.name)} · ${money(p.price)}</option>`).join(''));
  setVal('subscription-id', s.id); setVal('subscription-plan', s.plan_id); setVal('subscription-start', dateKey(parseISO(s.start_date))); setVal('subscription-end', s.end_date ? dateKey(parseISO(s.end_date)) : '');
  setVal('subscription-total', s.sessions_total); setVal('subscription-used', s.sessions_used); setVal('subscription-price', s.price_paid); setVal('subscription-status', s.status); setVal('subscription-notes', s.notes);
  $('subscription-payment-row').querySelector('.form-group').style.display = 'none'; $('subscription-notify-row').style.display = 'none';
}
async function saveSubscription() {
  guard(async () => {
    const id = val('subscription-id');
    const payload = { client_id: +val('subscription-client'), plan_id: +val('subscription-plan'), start_date: zonedToDate(val('subscription-start'), '00:00').toISOString(),
      end_date: val('subscription-end') ? zonedToDate(val('subscription-end'), '23:59').toISOString() : null, sessions_total: +val('subscription-total'), sessions_used: +val('subscription-used'),
      price_paid: parseFloat(val('subscription-price')), status: val('subscription-status'), notes: val('subscription-notes') || null };
    if (id) await api('PUT', `/subscriptions/${id}`, payload);
    else { payload.record_payment = !!val('subscription-method'); payload.payment_method = val('subscription-method') || null; payload.send_notification = $('subscription-notify').checked; await api('POST', '/subscriptions/', payload); }
    closeModal('subscription-modal'); toast('Package saved'); await refreshLookups(); refreshCurrent();
  });
}
function deleteSubscription(id, planName) {
  confirmBox('Delete package', `<p>Delete the <strong>${esc(planName)}</strong> package? This will remove the package and unlink any payments from it. Sessions already delivered will not be deleted.</p>`, 'Delete', async () => {
    await api('DELETE', `/subscriptions/${id}`); toast('Package deleted'); await refreshLookups(); refreshCurrent();
  }, 'btn-danger');
}

/* ---------- payments ---------- */
let PAY = { tab: 'list' };
function payTab(t, el) { PAY.tab = t; document.querySelectorAll('#page-payments .tab').forEach(x => x.classList.remove('active')); el.classList.add('active'); document.querySelectorAll('#page-payments .subpanel').forEach(p => p.classList.toggle('active', p.id === 'pay-' + t)); loadPayments(); }
function paymentsTable(list, compact) {
  if (!list.length) return '<div class="card empty">No payments.</div>';
  return `<div class="table-wrap"><table><thead><tr><th>Date</th>${compact ? '' : '<th>Client</th>'}<th>For</th><th>Method</th><th class="num">Amount</th><th></th></tr></thead><tbody>` + list.map(p => `<tr>
    <td class="mono">${fmtDT(p.paid_at)}</td>${compact ? '' : `<td><strong>${esc(p.client.name)}</strong></td>`}
    <td>${p.appointment_id ? '<span class="chip">session</span>' : p.subscription_id ? '<span class="chip">package</span>' : '<span class="chip">other</span>'} <span class="small muted">${esc(p.notes || '')}</span></td>
    <td>${esc(p.method)}</td><td class="num bold">${money(p.amount)}</td>
    <td class="num"><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deletePayment(${p.id})">Delete</button></td></tr>`).join('') + '</tbody></table></div>';
}
async function loadPayments() {
  if (!val('pay-from')) { setVal('pay-from', addDays(todayKey(), -30)); setVal('pay-to', todayKey()); }
  const unpaid = await api('GET', '/appointments/?status=completed&unpaid=true&limit=2000');
  $('unpaid-count').textContent = unpaid.length || '';
  if (PAY.tab === 'unpaid') { $('unpaid-table').innerHTML = unpaid.length ? `<div class="alert alert-serious" style="cursor:default">Total outstanding: <strong>${money(unpaid.reduce((a, x) => a + x.balance_due, 0))}</strong> across ${unpaid.length} session(s)</div>` + apptTable(unpaid.reverse(), { withDate: true }) : '<div class="card empty">Everything is paid up. 🎉</div>'; return; }
  const q = `from_date=${zonedToDate(val('pay-from'), '00:00').toISOString()}&to_date=${zonedToDate(addDays(val('pay-to'), 1), '00:00').toISOString()}${val('pay-method') ? '&method=' + val('pay-method') : ''}&limit=1000`;
  const list = await api('GET', `/payments/?${q}`);
  $('pay-total').textContent = `${list.length} payments · ${money(list.reduce((a, p) => a + p.amount, 0))}`;
  $('payments-table').innerHTML = paymentsTable(list);
}
function openPaymentModal(pre = {}) {
  fillSelect('payment-client', clientOptions(pre.client_id)); if (pre.client_id) setVal('payment-client', pre.client_id);
  setVal('payment-appointment', pre.appointment_id || ''); setVal('payment-subscription', pre.subscription_id || '');
  setVal('payment-amount', pre.amount !== undefined ? pre.amount : ''); setVal('payment-method', 'cash'); setVal('payment-date', todayKey()); setVal('payment-notes', pre.label || '');
  $('payment-for').textContent = pre.label ? `For: ${pre.label}` : 'Not linked to a specific session (e.g. deposit, retail, tip).';
  openModal('payment-modal');
}
async function savePayment() { guard(async () => { const amt = parseFloat(val('payment-amount')); if (!amt || amt <= 0) throw new Error('Enter an amount');
  await api('POST', '/payments/', { client_id: +val('payment-client'), appointment_id: val('payment-appointment') ? +val('payment-appointment') : null, subscription_id: val('payment-subscription') ? +val('payment-subscription') : null,
    amount: amt, method: val('payment-method'), paid_at: zonedToDate(val('payment-date'), timeKey(new Date())).toISOString(), notes: val('payment-notes') || null });
  closeModal('payment-modal'); toast('Payment recorded'); closeDrawer(); refreshCurrent(); }); }
function deletePayment(id) { confirmBox('Delete payment', '<p>Remove this payment record?</p>', 'Delete', async () => { await api('DELETE', `/payments/${id}`); toast('Payment deleted'); refreshCurrent(); }, 'btn-danger'); }

/* ---------- revenue reports ---------- */
const REP = { preset: 'month', from: null, to: null, gran: 'day' };
function repPreset(p) { REP.preset = p; document.querySelectorAll('#rep-presets button').forEach(b => b.classList.toggle('active', b.dataset.p === p));
  const t = todayKey(); const [y, m] = t.split('-');
  const map = { today: [t, t], week: [weekStartKey(t), t], month: [`${y}-${m}-01`, t], '30': [addDays(t, -29), t], '90': [addDays(t, -89), t], year: [`${y}-01-01`, t] };
  [REP.from, REP.to] = map[p]; setVal('rep-from', REP.from); setVal('rep-to', REP.to);
  REP.gran = (p === 'year' || p === '90') ? (p === 'year' ? 'month' : 'week') : 'day'; document.querySelectorAll('#rep-gran button').forEach(b => b.classList.toggle('active', b.dataset.g === REP.gran));
  loadReports(); }
function repCustom() { REP.from = val('rep-from'); REP.to = val('rep-to'); document.querySelectorAll('#rep-presets button').forEach(b => b.classList.remove('active')); loadReports(); }
function repGran(g) { REP.gran = g; document.querySelectorAll('#rep-gran button').forEach(b => b.classList.toggle('active', b.dataset.g === g)); loadReports(); }
async function loadReports() {
  if (!REP.from) { return repPreset('month'); }
  const q = `from=${REP.from}&to=${REP.to}`;
  const [s, ts, top] = await Promise.all([api('GET', `/reports/summary?${q}`), api('GET', `/reports/timeseries?${q}&granularity=${REP.gran}`), api('GET', `/reports/top-clients?${q}`)]);
  $('rep-range-label').textContent = `${fmtKey(REP.from)} – ${fmtKey(REP.to)} · ${s.days} day${s.days > 1 ? 's' : ''}`;
  $('rep-export-pay').href = `/api/reports/export/payments.csv?${q}&token=${S.token}`; $('rep-export-appt').href = `/api/reports/export/appointments.csv?${q}&token=${S.token}`;
  $('rep-kpis').innerHTML = `
    <div class="stat accent"><div class="stat-label">Collected</div><div class="stat-value">${money(s.collected)}</div><div class="stat-sub">${s.payments_count} payments · ${money(s.collected / Math.max(s.days, 1))}/day</div></div>
    <div class="stat"><div class="stat-label">Sessions delivered</div><div class="stat-value">${s.sessions_completed}</div><div class="stat-sub">worth ${money(s.session_value)} · ${s.sessions_from_packages} from packages</div></div>
    <div class="stat"><div class="stat-label">Packages sold</div><div class="stat-value">${s.packages_sold}</div><div class="stat-sub">${money(s.packages_value)} · ${s.new_clients} new clients</div></div>
    <div class="stat"><div class="stat-label">Outstanding</div><div class="stat-value" style="color:${s.outstanding > 0 ? 'var(--bad)' : 'var(--good)'}">${money(s.outstanding)}</div><div class="stat-sub">${s.outstanding_count} unpaid session(s), all time</div></div>`;
  barChart($('rep-chart'), ts.points.map(p => ({ label: labelPeriod(p.period, REP.gran), tooltip: labelPeriod(p.period, REP.gran, true), sessions_other: p.collected - p.packages, packages: p.packages, extra: `${p.sessions} session(s) delivered` })),
    { series: [{ key: 'sessions_other', color: 'var(--series-1)', name: 'Sessions & other' }, { key: 'packages', color: 'var(--series-2)', name: 'Packages' }] });
  hbars($('rep-service'), s.by_service.map(x => ({ name: x.name, value: x.value, color: x.color, count: x.count })));
  hbars($('rep-staff'), s.by_staff.map(x => ({ name: x.name, value: x.value, color: x.color, count: x.count })));
  hbars($('rep-method'), s.by_method.map((x, i) => ({ name: x.method, value: x.amount, color: PALETTE[i % PALETTE.length], count: x.count })), { countLabel: 'payments' });
  const sc = s.status_counts, total = Object.values(sc).reduce((a, b) => a + b, 0);
  hbars($('rep-status'), ['completed', 'confirmed', 'scheduled', 'cancelled', 'no_show'].filter(k => sc[k]).map(k => ({ name: k.replace('_', ' '), value: sc[k], color: { completed: '#1baf7a', confirmed: '#2a78d6', scheduled: '#6250d6', cancelled: '#e34948', no_show: '#eda100' }[k] })), { fmt: v => `${v} (${Math.round(100 * v / Math.max(total, 1))}%)` });
  $('rep-top').innerHTML = !top.clients.length ? '<div class="empty small">No activity in this range.</div>' : `<table><thead><tr><th>#</th><th>Client</th><th class="num">Spent</th><th class="num">Sessions</th><th></th></tr></thead><tbody>` + top.clients.map((c, i) => `<tr class="clickable" onclick="openClientDetail(${c.client_id})"><td class="muted">${i + 1}</td><td><strong>${esc(c.name)}</strong><div class="tiny muted">${esc(c.phone)}</div></td><td class="num bold">${money(c.spent)}</td><td class="num">${c.sessions}</td><td class="num"><button class="btn btn-ghost btn-xs">View</button></td></tr>`).join('') + '</tbody></table>';
}
function labelPeriod(p, g, long) { if (g === 'month') { const [y, m] = p.split('-'); return new Date(Date.UTC(+y, +m - 1, 1)).toLocaleDateString('en-GB', { timeZone: 'UTC', month: long ? 'long' : 'short', year: long ? 'numeric' : '2-digit' }); }
  const [y, m, d] = p.split('-').map(Number); const dt = new Date(Date.UTC(y, m - 1, d)); return (g === 'week' ? 'w/c ' : '') + dt.toLocaleDateString('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', ...(long ? { weekday: 'short', year: 'numeric' } : {}) }); }
