/* Packages (subscriptions & plans), payments, revenue reports */
function subsTable(subs) {
  if (!subs.length) return '<div class="card empty">No packages.</div>';
  return `<div class="table-wrap"><table><thead><tr><th>Client</th><th>Plan</th><th>Usage</th><th>Valid</th><th class="num">Price</th><th>Status</th><th></th></tr></thead><tbody>` + subs.map(s => {
    const pct = s.sessions_total ? 100 * s.sessions_used / s.sessions_total : 0;
    const expSoon = s.end_date && parseISO(s.end_date) < new Date(Date.now() + 7 * 86400000);
    return `<tr>
      <td><a href="#" onclick="openClientDetail(${s.client_id}, 'subs');return false"><strong>${esc(s.client.name)}</strong></a><div class="tiny muted">${esc(s.client.phone)}</div></td>
      <td>${esc(s.plan.name)}</td>
      <td style="min-width:140px"><div class="small">${s.sessions_used} / ${s.sessions_total} used · <strong>${s.sessions_remaining} left</strong></div>${s.sessions_used_before ? `<div class="tiny muted">${s.sessions_booked} booked here + ${s.sessions_used_before} before</div>` : ''}<div class="progress"><div style="width:${pct}%"></div></div></td>
      <td class="small">${fmtDate(s.start_date)} → ${s.end_date ? fmtDate(s.end_date) : 'no expiry'}${expSoon && s.status === 'active' ? '<div class="tiny" style="color:var(--warn)">expires soon</div>' : ''}</td>
      <td class="num">${money(s.price_paid)}${s.discount_code ? `<div class="tiny" style="color:var(--good)">${esc(s.discount_code)} −${money(s.discount_amount)}</div>` : ''}${s.paid_amount < s.price_paid ? `<div class="tiny" style="color:var(--bad)">paid ${money(s.paid_amount)}</div>` : ''}</td>
      <td>${badge(s.status === 'active' ? 'active' : s.status === 'expired' ? 'expired' : 'neutral').replace('neutral', s.status)}</td>
      <td class="num">${s.status !== 'renewed' && s.status !== 'cancelled' ? `<button class="btn btn-success btn-xs" onclick="renewFlow(${s.id})">Renew</button>` : ''}<button class="btn btn-ghost btn-xs" onclick="editSubscription(${s.id})">Edit</button>${s.paid_amount < s.price_paid ? `<button class="btn btn-ghost btn-xs" onclick="openPaymentModal({client_id:${s.client_id}, subscription_id:${s.id}, amount:${s.price_paid - s.paid_amount}, label:${jsArg(s.plan.name)}})">Pay</button>` : ''}<button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteSubscription(${s.id}, ${jsArg(s.plan.name)})">Delete</button></td></tr>`; }).join('') + '</tbody></table></div>';
}
async function renewFlow(id) {
  const [subs, plans] = await Promise.all([api('GET', '/subscriptions/'), api('GET', '/subscriptions/plans?active_only=true')]);
  const s = subs.find(x => x.id === id); if (!s) return toast('Package not found', true);
  const canCarry = s.status === 'active' && s.sessions_remaining > 0;
  confirmBox(`Renew ${esc(s.client.name)}'s package`, `
    <div class="form-group"><label>New package</label><select id="rn-plan" class="input">${plans.map(p => `<option value="${p.id}" ${p.id === s.plan_id ? 'selected' : ''}>${esc(p.name)} · ${p.sessions_included} sessions · ${money(p.price)}</option>`).join('')}</select></div>
    ${canCarry ? `<label class="check mb"><input type="checkbox" id="rn-carry" checked> Carry over the ${s.sessions_remaining} unused session(s) and close the current package</label>` : '<p class="small muted">The current package has no sessions left to carry over.</p>'}
    <div class="form-group"><label>Discount code (optional)</label><input type="text" id="rn-code" class="input" autocapitalize="characters"></div>
    <div class="form-group"><label>Payment</label><select id="rn-method" class="input"><option value="cash">Paid: cash</option><option value="card">Paid: card</option><option value="transfer">Paid: bank transfer</option><option value="online">Paid: online</option><option value="">Not paid yet</option></select></div>
    <label class="check"><input type="checkbox" id="rn-notify" checked> Send the client the package message</label>`,
    'Renew', async () => {
      const r = await api('POST', `/subscriptions/${id}/renew`, { plan_id: +val('rn-plan'), carry_over: canCarry ? $('rn-carry').checked : false,
        payment_method: val('rn-method') || null, record_payment: !!val('rn-method'), send_notification: $('rn-notify').checked,
        discount_code: val('rn-code').trim() || null });
      toast(`Renewed: ${r.sessions_total} sessions`); refreshCurrent();
      if ($('client-detail-modal').classList.contains('active')) openClientDetail(s.client_id, 'subs');
    });
}
let SUBS = { tab: 'active' };
function subTab(t, el) { SUBS.tab = t; document.querySelectorAll('#page-subscriptions .tab').forEach(x => x.classList.remove('active')); el.classList.add('active'); document.querySelectorAll('#page-subscriptions .subpanel').forEach(p => p.classList.toggle('active', p.id === 'sub-' + t)); loadSubscriptions(); }
async function loadSubscriptions() {
  if (SUBS.tab === 'plans') return loadPlans();
  if (SUBS.tab === 'codes') return loadCodes();
  if (SUBS.tab === 'gifts') return loadGifts();
  if (SUBS.tab === 'lapsed') return loadLapsed();
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
  $('subscription-used-help').textContent = 'Sessions already used before this package was added here. Bookings count on their own.';
  $('subscription-modal-title').textContent = 'Sell package';
  fillSelect('subscription-client', clientOptions(clientId)); fillSelect('subscription-plan', S.plans.filter(p => p.active).map(p => `<option value="${p.id}">${esc(p.name)} · ${money(p.price)}</option>`).join(''));
  ['subscription-id', 'subscription-end', 'subscription-total', 'subscription-price', 'subscription-notes', 'subscription-code'].forEach(i => setVal(i, ''));
  $('subscription-code-result').textContent = ''; $('subscription-discount-row').style.display = 'block';
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
  setVal('subscription-total', s.sessions_total); setVal('subscription-used', s.sessions_used); $('subscription-used-help').textContent = `${s.sessions_booked} booked in the system (cancelled ones don't count). Anything above that counts as used before.`; setVal('subscription-price', s.price_paid); setVal('subscription-status', s.status); setVal('subscription-notes', s.notes);
  $('subscription-payment-row').querySelector('.form-group').style.display = 'none'; $('subscription-notify-row').style.display = 'none'; $('subscription-discount-row').style.display = 'none';
}
async function saveSubscription() {
  guard(async () => {
    const id = val('subscription-id');
    const payload = { client_id: +val('subscription-client'), plan_id: +val('subscription-plan'), start_date: zonedToDate(val('subscription-start'), '00:00').toISOString(),
      end_date: val('subscription-end') ? zonedToDate(val('subscription-end'), '23:59').toISOString() : null, sessions_total: +val('subscription-total'), sessions_used: +val('subscription-used'),
      price_paid: parseFloat(val('subscription-price')), status: val('subscription-status'), notes: val('subscription-notes') || null };
    if (id) await api('PUT', `/subscriptions/${id}`, payload);
    else { payload.record_payment = !!val('subscription-method'); payload.payment_method = val('subscription-method') || null; payload.send_notification = $('subscription-notify').checked;
      if (val('subscription-code').trim()) payload.discount_code = val('subscription-code').trim();
      await api('POST', '/subscriptions/', payload); }
    closeModal('subscription-modal'); toast('Package saved'); await refreshLookups(); refreshCurrent();
  });
}
/* ---------- discount codes ---------- */
function codeStatus(d) {
  const now = new Date();
  if (!d.active) return '<span class="badge badge-neutral">off</span>';
  if (d.valid_until && parseISO(d.valid_until) < now) return '<span class="badge badge-expired">expired</span>';
  if (d.valid_from && parseISO(d.valid_from) > now) return '<span class="badge badge-scheduled">not started</span>';
  if (d.max_uses && d.used_count >= d.max_uses) return '<span class="badge badge-expired">used up</span>';
  return badge('active');
}
async function loadCodes() {
  const codes = await api('GET', '/discounts/');
  $('sub-codes').innerHTML = `<details class="add-box" ${codes.length ? '' : 'open'}><summary>+ New discount code</summary>
    <div class="measure-grid">
      <div class="form-group"><label>Code</label><input type="text" id="dc-code" class="input" placeholder="SUMMER20" autocapitalize="characters"></div>
      <div class="form-group"><label>Type</label><select id="dc-kind" class="input"><option value="percent">% off</option><option value="amount">${esc(S.currency)} off</option></select></div>
      <div class="form-group"><label>Value</label><input type="number" min="0" step="0.01" id="dc-value" class="input" placeholder="20"></div>
      <div class="form-group"><label>Max uses (optional)</label><input type="number" min="1" step="1" id="dc-max" class="input" placeholder="Unlimited"></div>
      <div class="form-group"><label>Valid from (optional)</label><input type="date" id="dc-from" class="input"></div>
      <div class="form-group"><label>Valid until (optional)</label><input type="date" id="dc-until" class="input"></div>
    </div>
    <div class="form-group"><label>Notes</label><input type="text" id="dc-notes" class="input" placeholder="e.g. Instagram summer campaign"></div>
    <button class="btn btn-primary btn-sm" onclick="saveCode()">Create code</button></details>` +
    (codes.length ? `<div class="table-wrap"><table><thead><tr><th>Code</th><th>Discount</th><th>Used</th><th>Valid</th><th>Status</th><th></th></tr></thead><tbody>${codes.map(d => `<tr>
      <td><strong class="mono">${esc(d.code)}</strong>${d.notes ? `<div class="tiny muted">${esc(d.notes)}</div>` : ''}</td>
      <td>${d.kind === 'percent' ? `${d.value}%` : money(d.value)} off packages</td>
      <td class="mono">${d.used_count}${d.max_uses ? ` / ${d.max_uses}` : ''}</td>
      <td class="small">${d.valid_from ? fmtDate(d.valid_from) : 'now'} → ${d.valid_until ? fmtDate(d.valid_until) : 'no end'}</td>
      <td>${codeStatus(d)}</td>
      <td class="num"><button class="btn btn-ghost btn-xs" onclick="toggleCode(${d.id}, ${!d.active})">${d.active ? 'Switch off' : 'Switch on'}</button><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteCode(${d.id}, ${jsArg(d.code)})">Delete</button></td></tr>`).join('')}</tbody></table></div>`
      : '<div class="card empty">No discount codes yet.</div>');
}
async function saveCode() {
  guard(async () => {
    const body = { code: val('dc-code').trim(), kind: val('dc-kind'), value: parseFloat(val('dc-value')), notes: val('dc-notes').trim() || null };
    if (!body.code || !(body.value > 0)) throw new Error('Enter a code and a value');
    if (val('dc-max')) body.max_uses = +val('dc-max');
    if (val('dc-from')) body.valid_from = zonedToDate(val('dc-from'), '00:00').toISOString();
    if (val('dc-until')) body.valid_until = zonedToDate(val('dc-until'), '23:59').toISOString();
    await api('POST', '/discounts/', body); toast(`Code ${body.code.toUpperCase()} created`); loadCodes();
  });
}
async function toggleCode(id, on) { guard(async () => { await api('PUT', `/discounts/${id}`, { active: on }); loadCodes(); }); }
function deleteCode(id, code) { confirmBox('Delete code', `<p>Delete <strong>${esc(code)}</strong>? Packages already sold with it keep their price.</p>`, 'Delete', async () => { await api('DELETE', `/discounts/${id}`); toast('Code deleted'); loadCodes(); }, 'btn-danger'); }
async function checkSubscriptionCode() {
  const code = val('subscription-code').trim(), out = $('subscription-code-result');
  if (!code) { out.textContent = ''; return; }
  const price = parseFloat(val('subscription-price'));
  const r = await api('GET', `/discounts/check?code=${encodeURIComponent(code)}&plan_id=${val('subscription-plan')}${isNaN(price) ? '' : '&price=' + price}`);
  out.innerHTML = r.valid ? `<span style="color:var(--good);font-weight:600">✓ ${esc(r.label)}: client pays ${money(r.final_price)} (saves ${money(r.discount)})</span>` : `<span style="color:var(--bad)">${esc(r.reason)}</span>`;
}

/* ---------- clients whose package ended without a renewal ---------- */
async function loadLapsed() {
  const rows = await api('GET', '/subscriptions/not-renewed');
  const offer = r => r.offer === 'pending_approval' ? '<span class="badge badge-queued">waiting for your OK</span>' : r.offer === 'sent' ? `<span class="badge badge-sent">offer sent</span>${r.offer_at ? `<div class="tiny muted">${fmtDate(r.offer_at)}</div>` : ''}` : r.offer ? `<span class="badge badge-neutral">${esc(r.offer)}</span>` : '<span class="muted small">not contacted</span>';
  $('sub-lapsed').innerHTML = `<p class="small muted" style="margin:0 0 12px">Clients whose last package ended in the last 4 months and who haven't bought another one. ${S.settings && S.settings.renewal_offer_auto === false ? 'Automatic renewal offers are off (Settings).' : 'A renewal offer is prepared automatically a few days after a package ends; it waits in Messages until you approve it.'}</p>` +
    (rows.length ? `<div class="table-wrap"><table><thead><tr><th>Client</th><th>Last package</th><th>Ended</th><th class="num">Spent</th><th>Offer</th><th></th></tr></thead><tbody>${rows.map(r => `<tr>
      <td><a href="#" onclick="openClientDetail(${r.client_id});return false"><strong>${esc(r.client_name)}</strong></a><div class="tiny muted">${esc(r.client_phone)}</div></td>
      <td>${esc(r.plan)}<div class="tiny muted">${r.sessions_used}/${r.sessions_total} used · ${esc(r.how_it_ended)}</div></td>
      <td class="small">${fmtDate(r.ended_on)}<div class="tiny muted">${r.days_since} day(s) ago</div></td>
      <td class="num">${money(r.total_spent)}</td><td>${offer(r)}</td>
      <td class="num"><button class="btn btn-success btn-xs" onclick="openSubscriptionModal(null, ${r.client_id})">Sell package</button>${r.offer !== 'sent' ? `<button class="btn btn-ghost btn-xs" onclick="sendRenewalOffer(${r.subscription_id}, ${jsArg(r.client_name)})">Send offer</button>` : ''}</td></tr>`).join('')}</tbody></table></div>`
      : '<div class="card empty">Everyone with an ended package has renewed. 🎉</div>');
}
function sendRenewalOffer(subId, name) {
  confirmBox('Send renewal offer', `<p>Send the renewal offer to <strong>${esc(name)}</strong> now? You can edit the text in Messages → Templates → "Renewal offer".</p>`, 'Send', async () => {
    const logs = await api('POST', `/subscriptions/${subId}/renewal-offer`);
    toast(logs.length ? `Offer sent on ${logs.map(l => l.channel).join(', ')}` : 'No channel available for this client', !logs.length); loadLapsed();
  });
}

/* ---------- gift cards ---------- */
function giftStatus(g) {
  if (g.status === 'active' && g.valid_until && parseISO(g.valid_until) < new Date()) return '<span class="badge badge-expired">expired</span>';
  return g.status === 'active' ? badge('active') : g.status === 'redeemed' ? '<span class="badge badge-completed">redeemed</span>' : '<span class="badge badge-cancelled">cancelled</span>';
}
async function loadGifts() {
  const [gifts, plans] = await Promise.all([api('GET', '/gift-cards/'), api('GET', '/subscriptions/plans?active_only=true')]);
  $('sub-gifts').innerHTML = `<details class="add-box" ${gifts.length ? '' : 'open'}><summary>+ Sell a gift card</summary>
    <div class="form-group"><label>Gift</label><select id="gc-plan" class="input">${plans.map(p => `<option value="${p.id}">${esc(p.name)} · ${p.sessions_included} sessions · ${money(p.price)}</option>`).join('')}</select></div>
    <div class="form-group"><label>Bought by</label><select id="gc-buyer" class="input" onchange="$('gc-new-buyer').style.display = this.value ? 'none' : 'grid'"><option value="">New person (not a client yet)</option>${clientOptions()}</select></div>
    <div class="form-row" id="gc-new-buyer"><div class="form-group"><label>Buyer's name</label><input type="text" id="gc-bname" class="input" autocomplete="off"></div><div class="form-group"><label>Buyer's phone</label><input type="tel" id="gc-bphone" class="input" inputmode="tel" autocomplete="off"></div></div>
    <div class="form-row"><div class="form-group"><label>For (recipient's name)</label><input type="text" id="gc-rname" class="input" autocomplete="off"></div><div class="form-group"><label>Recipient's phone (optional)</label><input type="tel" id="gc-rphone" class="input" inputmode="tel" autocomplete="off"></div></div>
    <div class="form-group"><label>Message on the card (optional)</label><input type="text" id="gc-msg" class="input" placeholder="Happy birthday!"></div>
    <div class="form-row"><div class="form-group"><label>Payment</label><select id="gc-method" class="input"><option value="cash">Paid: cash</option><option value="card">Paid: card</option><option value="transfer">Paid: bank transfer</option><option value="online">Paid: online</option><option value="">Not paid yet</option></select></div>
      <div class="form-group"><label>Valid for</label><select id="gc-days" class="input"><option value="90">3 months</option><option value="180">6 months</option><option value="365" selected>1 year</option></select></div></div>
    <button class="btn btn-primary btn-sm" onclick="sellGift()">Create gift card</button></details>` +
    (gifts.length ? `<div class="table-wrap"><table><thead><tr><th>Code</th><th>Gift</th><th>From → To</th><th>Valid until</th><th class="num">Price</th><th>Status</th><th></th></tr></thead><tbody>${gifts.map(g => `<tr>
      <td><strong class="mono">${esc(g.code)}</strong></td>
      <td>${esc(g.plan_name || '')}${g.message ? `<div class="tiny muted">“${esc(g.message)}”</div>` : ''}</td>
      <td class="small">${esc(g.purchaser_name || '—')} → <strong>${esc(g.recipient_name)}</strong>${g.recipient_phone ? `<div class="tiny muted">${esc(g.recipient_phone)}</div>` : ''}</td>
      <td class="small">${g.valid_until ? fmtDate(g.valid_until) : '—'}</td>
      <td class="num">${money(g.price_paid)}</td>
      <td>${giftStatus(g)}${g.redeemed_at ? `<div class="tiny muted">${fmtDate(g.redeemed_at)}</div>` : ''}</td>
      <td class="num">${g.status === 'active' ? `<button class="btn btn-success btn-xs" onclick="redeemGift(${g.id})">Redeem</button><button class="btn btn-ghost btn-xs" onclick="copyGift(${g.id})">Copy text</button><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="cancelGift(${g.id}, ${jsArg(g.code)})">Cancel</button>` : g.redeemed_client_id ? `<button class="btn btn-ghost btn-xs" onclick="openClientDetail(${g.redeemed_client_id}, 'subs')">Open client</button>` : ''}</td></tr>`).join('')}</tbody></table></div>`
      : '<div class="card empty">No gift cards sold yet.</div>');
  window._gifts = gifts;
}
async function sellGift() {
  guard(async () => {
    const body = { plan_id: +val('gc-plan'), recipient_name: val('gc-rname').trim(), recipient_phone: val('gc-rphone').trim() || null, message: val('gc-msg').trim() || null,
      payment_method: val('gc-method') || null, valid_days: +val('gc-days') };
    if (val('gc-buyer')) body.purchaser_client_id = +val('gc-buyer'); else { body.purchaser_name = val('gc-bname').trim(); body.purchaser_phone = val('gc-bphone').trim() || null; }
    if (!body.recipient_name) throw new Error("Enter the recipient's name");
    if (!body.purchaser_client_id && !body.purchaser_name) throw new Error("Choose the buyer or enter their name");
    const g = await api('POST', '/gift-cards/', body);
    toast(`Gift card ${g.code} created`); await refreshLookups(); await loadGifts();
  });
}
function giftText(g) {
  return `🎁 ${S.business} gift card\nFor: ${g.recipient_name}\nGift: ${g.plan_name}${g.message ? `\n“${g.message}”` : ''}\nCode: ${g.code}\nValid until ${g.valid_until ? fmtDate(g.valid_until) : '—'}. Show this code when you book your first session.`;
}
async function copyGift(id) {
  const g = (window._gifts || []).find(x => x.id === id); if (!g) return;
  try { await navigator.clipboard.writeText(giftText(g)); toast('Gift card text copied: paste it into WhatsApp'); }
  catch (e) { confirmBox('Gift card text', `<textarea class="input" style="min-height:140px" readonly onclick="this.select()">${esc(giftText(g))}</textarea>`, 'Done', async () => {}); }
}
function redeemGift(id) {
  const g = (window._gifts || []).find(x => x.id === id); if (!g) return;
  confirmBox(`Redeem ${esc(g.code)}`, `<p><strong>${esc(g.plan_name)}</strong> for <strong>${esc(g.recipient_name)}</strong>${g.recipient_phone ? ` (${esc(g.recipient_phone)})` : ''}.</p>
    <div class="form-group"><label>Give the package to</label><select id="gr-client" class="input"><option value="">${esc(g.recipient_name)}: create or find by phone</option>${clientOptions()}</select></div>
    <p class="small muted">A paid package is added to this client. The buyer's payment covers it.</p>`, 'Redeem', async () => {
    const sub = await api('POST', `/gift-cards/${id}/redeem`, val('gr-client') ? { client_id: +val('gr-client') } : {});
    toast(`Redeemed: ${sub.client.name} now has ${sub.sessions_total} sessions`); await refreshLookups(); loadGifts();
  });
}
function cancelGift(id, code) {
  confirmBox('Cancel gift card', `<p>Cancel <strong>${esc(code)}</strong>? It can no longer be redeemed. Refund the buyer separately if needed.</p>`, 'Cancel card', async () => { await api('POST', `/gift-cards/${id}/cancel`); toast('Gift card cancelled'); loadGifts(); }, 'btn-danger');
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
    <td class="mono">${fmtDT(p.paid_at)}</td>${compact ? '' : `<td>${p.client ? `<a href="#" onclick="openClientDetail(${p.client_id}, 'pays');return false"><strong>${esc(p.client.name)}</strong></a>` : `<strong>${esc(PAY_SOURCES[p.source] || 'Other income')}</strong>`}</td>`}
    <td>${p.appointment_id ? '<span class="chip">session</span>' : p.subscription_id ? '<span class="chip">package</span>' : p.source ? `<span class="chip">${esc(PAY_SOURCES[p.source] || p.source)}</span>` : '<span class="chip">other</span>'} <span class="small muted">${esc(p.notes || '')}</span></td>
    <td>${esc(p.method)}</td><td class="num bold">${money(p.amount)}</td>
    <td class="num"><button class="btn btn-ghost btn-xs" onclick="printInvoice(${p.id})">Invoice</button><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deletePayment(${p.id})">Delete</button></td></tr>`).join('') + '</tbody></table></div>';
}

/* ---------- invoices: printed from the browser, so "Save as PDF" works everywhere and Arabic names render ---------- */
/* UAE tax invoice. The VAT breakdown is shown as soon as a rate is known —
   from the server (inv.vat_rate) or from the constant below.
   Set rate: 5 here to switch it on today, without waiting for the backend. */
const LUZ_VAT = { rate: 0, inclusive: true };

function vatConfig(inv) {
  const src = (inv && inv.vat_rate !== undefined && inv.vat_rate !== null) ? inv.vat_rate : LUZ_VAT.rate;
  const inc = (inv && inv.vat_inclusive !== undefined && inv.vat_inclusive !== null) ? inv.vat_inclusive : LUZ_VAT.inclusive;
  return { rate: Number(src) || 0, inclusive: inc !== false };
}
const _r2 = n => Math.round((Number(n) || 0) * 100) / 100;

function invoiceHTML(inv) {
  const m = v => `${esc(inv.currency)} ${Number(v || 0).toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const b = inv.business, c = inv.client;
  const { rate, inclusive } = vatConfig(inv);
  const isTax = rate > 0;

  /* one row per line, split into net + VAT; the client always pays net + VAT */
  const rows = (inv.lines || []).map(l => {
    const amt = Number(l.amount) || 0;
    let net = amt, tax = 0;
    if (isTax) { if (inclusive) { net = amt / (1 + rate / 100); tax = amt - net; } else { tax = amt * rate / 100; } }
    net = _r2(net); tax = _r2(tax);
    return { description: l.description, net, tax, total: _r2(net + tax) };
  });
  const sumNet = _r2(rows.reduce((a, r) => a + r.net, 0));
  const sumTax = _r2(rows.reduce((a, r) => a + r.tax, 0));
  let sumTotal = _r2(sumNet + sumTax);
  let netT = sumNet, taxT = sumTax;

  /* inv.total is what the client actually paid. If it disagrees with the lines
     (an old invoice, a manual adjustment), trust it for the grand total. */
  if (inv.total !== undefined && inv.total !== null && Math.abs(Number(inv.total) - sumTotal) >= 0.01) {
    const g = _r2(inv.total);
    if (isTax) { netT = inclusive ? _r2(g / (1 + rate / 100)) : g; taxT = _r2(g - netT); sumTotal = _r2(netT + taxT); }
    else { netT = g; taxT = 0; sumTotal = g; }
  }

  const rateLabel = `${rate % 1 ? rate.toFixed(2) : rate}%`;

  const head = isTax
    ? `<tr><th>Description</th><th class="num">Net</th><th class="num">VAT ${rateLabel}</th><th class="num">Total</th></tr>`
    : `<tr><th>Description</th><th class="num">Amount</th></tr>`;

  const body = rows.map(r => isTax
    ? `<tr><td>${esc(r.description)}</td><td class="num">${r.net < 0 ? '−' : ''}${m(Math.abs(r.net))}</td><td class="num">${r.tax < 0 ? '−' : ''}${m(Math.abs(r.tax))}</td><td class="num">${r.total < 0 ? '−' : ''}${m(Math.abs(r.total))}</td></tr>`
    : `<tr><td>${esc(r.description)}</td><td class="num">${r.total < 0 ? '−' : ''}${m(Math.abs(r.total))}</td></tr>`).join('');

  const foot = isTax
    ? `<tr><td>Total excluding VAT</td><td class="num">${m(netT)}</td></tr>
       <tr><td>VAT ${rateLabel}</td><td class="num">${m(taxT)}</td></tr>
       <tr class="inv-grand"><td><strong>Total including VAT</strong></td><td class="num"><strong>${m(sumTotal)}</strong></td></tr>`
    : `<tr><td>Total paid</td><td class="num">${m(sumTotal)}</td></tr>`;

  return `<div class="invoice">
    <div class="inv-head"><div><div class="wordmark lg">LUZ<small>EMS</small></div><div class="inv-biz"><strong>${esc(b.name)}</strong>${b.address ? `<br>${esc(b.address)}` : ''}${b.phone ? `<br>${esc(b.phone)}` : ''}${b.email ? `<br>${esc(b.email)}` : ''}${b.trn ? `<br>TRN: ${esc(b.trn)}` : ''}</div></div>
      <div class="inv-meta"><h1>${isTax ? 'Tax Invoice' : 'Invoice'}</h1><div><span>Number</span><strong>${esc(inv.number)}</strong></div><div><span>Date</span><strong>${esc(inv.date)}</strong></div><div><span>Status</span><strong class="inv-paid">Paid · ${esc(inv.method)}</strong></div></div></div>
    <div class="inv-to"><span>Billed to</span><strong>${esc(c.name)}</strong>${c.phone && c.phone !== '-' ? `<br>${esc(c.phone)}` : ''}${c.email ? `<br>${esc(c.email)}` : ''}</div>
    <table class="inv-lines"><thead>${head}</thead><tbody>${body}</tbody>
      <tfoot>${foot}</tfoot></table>
    ${isTax ? `<p class="inv-foot small">Amounts in ${esc(inv.currency)}. VAT charged in accordance with UAE Federal Decree-Law No. 8 of 2017.</p>` : ''}
    <p class="inv-foot">Thank you for training with ${esc(b.name)}.</p></div>`;
}

async function printInvoice(paymentId) {
  guard(async () => {
    const inv = await api('GET', `/payments/${paymentId}/invoice`);
    let area = $('print-area');
    if (!area) { area = document.createElement('div'); area.id = 'print-area'; document.body.appendChild(area); }
    area.innerHTML = invoiceHTML(inv);
    const title = document.title; document.title = inv.number; // the PDF file name
    document.body.classList.add('printing');
    const done = () => { document.body.classList.remove('printing'); document.title = title; window.removeEventListener('afterprint', done); };
    window.addEventListener('afterprint', done);
    window.print();
    setTimeout(() => { if (!matchMedia('print').matches) done(); }, 1500);
  });
}
async function loadPayments() {
  if (!val('pay-from')) { setVal('pay-from', addDays(todayKey(), -30)); setVal('pay-to', todayKey()); }
  const unpaid = await api('GET', '/appointments/?status=completed&unpaid=true&limit=2000');
  $('unpaid-count').textContent = unpaid.length || '';
  if (PAY.tab === 'unpaid') { $('unpaid-table').innerHTML = unpaid.length ? `<div class="alert alert-serious" style="cursor:default">Total outstanding: <strong>${money(unpaid.reduce((a, x) => a + x.balance_due, 0))}</strong> across ${unpaid.length} session(s)</div>` + apptTable(unpaid.reverse(), { withDate: true }) : '<div class="card empty">Everything is paid up. 🎉</div>'; return; }
  const q = `from_date=${zonedToDate(val('pay-from'), '00:00').toISOString()}&to_date=${zonedToDate(addDays(val('pay-to'), 1), '00:00').toISOString()}${val('pay-method') ? '&method=' + val('pay-method') : ''}&limit=100000`;  // the total below must count every payment in the range
  const list = await api('GET', `/payments/?${q}`);
  $('pay-total').textContent = `${list.length} payments · ${money(list.reduce((a, p) => a + p.amount, 0))}`;
  $('payments-table').innerHTML = paymentsTable(list);
}
function openPaymentModal(pre = {}) {
  fillSelect('payment-client', clientOptions(pre.client_id)); if (pre.client_id) setVal('payment-client', pre.client_id);
  setVal('payment-appointment', pre.appointment_id || ''); setVal('payment-subscription', pre.subscription_id || '');
  setVal('payment-amount', pre.amount !== undefined ? pre.amount : ''); setVal('payment-method', 'cash'); setVal('payment-date', todayKey()); setVal('payment-notes', pre.label || '');
  $('payment-for').textContent = pre.label ? `For: ${pre.label}` : 'Not linked to a specific session (e.g. deposit, retail, tip).';
  setVal('payment-source', ''); $('payment-source').disabled = !!(pre.client_id || pre.appointment_id || pre.subscription_id); paySourceChanged();
  openModal('payment-modal');
}
function paySourceChanged() {
  const other = !!val('payment-source'); $('payment-client-row').hidden = other;
  if (other && !$('payment-source').disabled) $('payment-for').textContent = 'Income that is not from a client. Add who paid in Notes, e.g. "Instagram post for Brand X".';
}
const PAY_SOURCES = { social_media: 'Social media', ads: 'Advertising', other: 'Other income' };
async function savePayment() { guard(async () => { const amt = parseFloat(val('payment-amount')); if (!amt || amt <= 0) throw new Error('Enter an amount');
  const source = val('payment-source') || null;
  await api('POST', '/payments/', { client_id: source ? null : +val('payment-client'), source, appointment_id: val('payment-appointment') ? +val('payment-appointment') : null, subscription_id: val('payment-subscription') ? +val('payment-subscription') : null,
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
  if (typeof loadFinance === 'function') loadFinance();
  if (typeof loadTeamReport === 'function') setTimeout(loadTeamReport, 0); // after REP dates are set
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
