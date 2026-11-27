/* Finance (Revenue page): cash flow, revenue per client, estimated profit per service / package, expense groups */
let FIN = { months: 6 };
function finMonths(n) { FIN.months = n; document.querySelectorAll('#fin-range button').forEach(b => b.classList.toggle('active', +b.dataset.m === n)); loadFinance(); }

function finMonthLabel(p) { const [y, m] = p.split('-').map(Number); return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('en-GB', { timeZone: 'UTC', month: 'short' }); }

/* Money in (emerald) and out (grey) bars per month, with the running balance as a line */
function cashFlowChart(el, rows) {
  if (!rows.some(r => r.money_in || r.money_out)) { el.innerHTML = '<div class="empty small">No money in or out in this period yet.</div>'; return; }
  const W = Math.max(300, Math.round(el.clientWidth || 720)), H = W < 480 ? 210 : 240, padL = 44, padR = 12, padT = 14, padB = 28;
  const iw = W - padL - padR, ih = H - padT - padB;
  const hi = Math.max(1, ...rows.map(r => Math.max(r.money_in, r.money_out, r.balance)));
  const lo = Math.min(0, ...rows.map(r => r.balance));
  const top = niceMax(hi), bottom = lo < 0 ? -niceMax(-lo) : 0, span = top - bottom;
  const y = v => padT + ih * (top - v) / span, step = iw / rows.length, bw = Math.min(22, step * .3);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Money in, money out and running balance by month">`;
  for (let i = 0; i <= 4; i++) { const v = bottom + span * i / 4; svg += `<line class="axis" x1="${padL}" x2="${W - padR}" y1="${y(v)}" y2="${y(v)}" ${v ? 'stroke-dasharray="2 3"' : ''}/><text class="lbl" x="${padL - 6}" y="${y(v) + 3}" text-anchor="end">${v < 0 ? '-' : ''}${shortNum(Math.abs(v))}</text>`; }
  rows.forEach((r, i) => {
    const cx = padL + step * i + step / 2;
    if (r.money_in > 0) svg += `<path fill="var(--series-1)" d="${roundedTop(cx - bw - 1, y(r.money_in), bw, y(0) - y(r.money_in), 3)}"/>`;
    if (r.money_out > 0) svg += `<path fill="var(--series-2)" d="${roundedTop(cx + 1, y(r.money_out), bw, y(0) - y(r.money_out), 3)}"/>`;
    svg += `<text class="lbl" x="${cx}" y="${H - 9}" text-anchor="middle">${finMonthLabel(r.period)}</text>`;
  });
  const pts = rows.map((r, i) => [padL + step * i + step / 2, y(r.balance)]);
  svg += `<path d="${pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')}" fill="none" stroke="var(--text)" stroke-width="1.8" stroke-dasharray="5 4"/>`;
  pts.forEach(p => { svg += `<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="var(--text)"/>`; });
  rows.forEach((r, i) => { svg += `<rect data-i="${i}" x="${padL + step * i}" y="${padT}" width="${step}" height="${ih}" fill="transparent"/>`; });
  el.innerHTML = svg + '</svg><div class="chart-tip"></div>';
  const tip = el.querySelector('.chart-tip');
  el.querySelectorAll('[data-i]').forEach(n => {
    n.addEventListener('mousemove', e => { const r = rows[+n.dataset.i], b = el.getBoundingClientRect();
      tip.innerHTML = `<strong>${finMonthLabel(r.period)} ${r.period.slice(0, 4)}</strong><br>In: ${money(r.money_in)}<br>Out: ${money(r.money_out)}<br>Net: ${money(r.net)}<br>Running balance: ${money(r.balance)}`;
      tip.style.left = (e.clientX - b.left) + 'px'; tip.style.top = (e.clientY - b.top - 6) + 'px'; tip.style.display = 'block'; });
    n.addEventListener('mouseleave', () => tip.style.display = 'none');
  });
}

function profitTable(rows, kind) {
  if (!rows.length) return `<div class="empty small">${kind === 'plans' ? 'No packages sold' : 'No sessions delivered'} in this period.</div>`;
  const head = kind === 'plans' ? '<th>Package</th><th class="num">Sold</th><th class="num">Revenue</th><th class="num">Per session</th>' : '<th>Service</th><th class="num">Sessions</th><th class="num">Revenue</th><th class="num">Avg price</th>';
  return `<div class="table-wrap"><table class="plain"><thead><tr>${head}<th class="num">Est. cost</th><th class="num">Est. profit</th></tr></thead><tbody>${rows.map(r => `<tr>
    <td><strong>${esc(r.name)}</strong></td><td class="num">${kind === 'plans' ? r.sold : r.sessions}</td><td class="num">${money(r.revenue)}</td>
    <td class="num muted">${money(kind === 'plans' ? r.price_per_session : r.avg_price)}</td><td class="num muted">${money(r.est_cost)}</td>
    <td class="num"><strong style="color:${r.est_profit < 0 ? 'var(--bad)' : 'var(--good)'}">${money(r.est_profit)}</strong>${r.margin_pct !== null ? `<div class="tiny muted">${r.margin_pct}% margin</div>` : ''}</td></tr>`).join('')}</tbody></table></div>`;
}

async function loadFinance() {
  const f = await api('GET', `/reports/finance?months=${FIN.months}`);
  const last = f.months[f.months.length - 1];
  $('fin-sub').textContent = `${fmtKey(f.from)} – ${fmtKey(f.to)} · money that actually moved`;
  $('fin-kpis').innerHTML = `
    <div class="stat"><div class="stat-label">Net cash, ${FIN.months} months</div><div class="stat-value" style="color:${last.balance < 0 ? 'var(--bad)' : 'inherit'}">${money(last.balance)}</div><div class="stat-sub">in ${money(f.months.reduce((a, r) => a + r.money_in, 0))} · out ${money(f.months.reduce((a, r) => a + r.money_out, 0))}</div></div>
    <div class="stat"><div class="stat-label">Clients owe you</div><div class="stat-value">${money(f.outstanding.owed_to_you)}</div><div class="stat-sub">${money(f.outstanding.owed_sessions)} sessions · ${money(f.outstanding.owed_packages)} packages</div></div>
    <div class="stat"><div class="stat-label">Bills still to pay</div><div class="stat-value" style="color:${f.outstanding.bills_to_pay ? 'var(--bad)' : 'inherit'}">${money(f.outstanding.bills_to_pay)}</div><div class="stat-sub">expenses marked unpaid</div></div>
    <div class="stat"><div class="stat-label">Average per client</div><div class="stat-value">${money(f.per_client.avg_per_client)}</div><div class="stat-sub">${f.per_client.paying_clients} paying clients · ~${money(f.per_client.avg_per_client_per_month)}/month · lifetime ${money(f.per_client.avg_lifetime_value)}</div></div>`;
  cashFlowChart($('fin-chart'), f.months);
  window._finMonths = f.months;
  $('fin-cost-note').innerHTML = f.costs.sessions_delivered
    ? `Each delivered session cost about <strong>${money(f.costs.cost_per_session)}</strong> to run (${money(f.costs.expenses_total)} of expenses ÷ ${f.costs.sessions_delivered} sessions). Profit = revenue minus that cost per session. It's an estimate: all costs are spread evenly over sessions.`
    : 'No sessions were delivered in this period, so costs can\'t be spread over sessions yet.';
  $('fin-services').innerHTML = profitTable(f.services, 'services');
  $('fin-plans').innerHTML = profitTable(f.plans, 'plans');
  const groupColor = { 'Premises & utilities': 'var(--series-1)', 'Staff': 'var(--series-3)', 'Marketing': 'var(--series-2)', 'Maintenance & equipment': 'var(--text-3)', 'Software & subscriptions': 'var(--border-strong)', 'Fuel & transport': 'var(--series-4)', 'Other': 'var(--neutral-bg)' };
  hbars($('fin-groups'), f.expense_groups.map(g => ({ name: g.group, value: g.total, color: groupColor[g.group] || '#9aa8a1' })));
}

let _finResize;
window.addEventListener('resize', () => { clearTimeout(_finResize); _finResize = setTimeout(() => {
  if (window._finMonths && $('page-reports').classList.contains('active')) cashFlowChart($('fin-chart'), window._finMonths); }, 150); });
