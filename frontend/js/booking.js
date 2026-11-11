/* Booking modal (create / reschedule) and the session drawer with lifecycle actions */
const BK = { editing: null, clientId: null, slots: [], sub: null };

function findClientByLabel(label) { const m = label.match(/\((.*)\)$/); return S.clients.find(c => `${c.name} (${c.phone})` === label) || (m ? S.clients.find(c => c.phone === m[1]) : null); }
function clientLabel(c) { return `${c.name} (${c.phone})`; }

async function openBookingModal(appointmentId, prefill = {}) {
  BK.editing = null; BK.clientId = prefill.clientId || null; BK.sub = null;
  $('client-options').innerHTML = S.clients.map(c => `<option value="${esc(clientLabel(c))}">`).join('');
  fillSelect('booking-service', serviceOptions(prefill.serviceId)); fillSelect('booking-staff', staffOptions(prefill.staffId));
  $('booking-currency').textContent = `(${S.currency})`;
  setVal('booking-id', ''); setVal('booking-notes', ''); setVal('booking-client-phone', ''); setVal('booking-client-email', '');
  setVal('booking-client', BK.clientId ? clientLabel(S.clients.find(c => c.id === BK.clientId)) : '');
  setVal('booking-date', prefill.date || CAL.anchor || todayKey()); setVal('booking-time', prefill.time || '10:00');
  $('booking-notify').checked = true; $('booking-conflict').style.display = 'none';
  setVal('booking-repeat', '0'); setVal('booking-repeat-count', 8); $('booking-repeat-group').style.display = appointmentId ? 'none' : ''; bookingRepeatChanged();
  $('booking-client-group').style.display = ''; $('booking-title').textContent = 'Book session'; $('booking-save').textContent = 'Book session';
  if (appointmentId) {
    const a = await api('GET', `/appointments/${appointmentId}`);
    BK.editing = a; BK.clientId = a.client_id;
    $('booking-title').textContent = 'Reschedule / edit session'; $('booking-save').textContent = 'Save changes';
    setVal('booking-client', clientLabel(a.client)); $('booking-client-group').style.display = 'none';
    setVal('booking-service', a.service_id); setVal('booking-staff', a.staff_id || ''); setVal('booking-notes', a.notes || '');
    setVal('booking-date', dateKey(parseISO(a.start_time))); setVal('booking-time', timeKey(parseISO(a.start_time))); setVal('booking-price', a.price);
  }
  bookingClientChanged(!appointmentId);
  openModal('booking-modal');
  bookingLoadSlots();
}

async function bookingClientChanged(resetPrice = true) {
  const c = findClientByLabel(val('booking-client'));
  BK.clientId = BK.editing ? BK.editing.client_id : (c ? c.id : null);
  const isNew = !BK.editing && !c && val('booking-client').trim().length > 0;
  $('new-client-fields').style.display = isNew ? 'grid' : 'none';
  $('booking-client-help').textContent = isNew ? 'New client will be created with this name.' : (c ? `${c.completed_appointments} past sessions · ${c.sessions_remaining} package sessions left` : '');
  BK.sub = null; $('booking-sub-group').style.display = 'none';
  if (c && c.sessions_remaining > 0 && !BK.editing) {
    const subs = await api('GET', `/subscriptions/?client_id=${c.id}&active=true`);
    if (subs.length) { BK.sub = subs[0]; $('booking-sub-group').style.display = ''; $('booking-sub-label').textContent = `Use ${subs[0].plan.name} (${subs[0].sessions_remaining} left)`; $('booking-use-sub').checked = true; }
  }
  if (resetPrice) bookingSubToggle();
}
function bookingSubToggle() {
  const svc = S.services.find(s => s.id == val('booking-service'));
  const useSub = BK.sub && $('booking-use-sub').checked;
  setVal('booking-price', useSub ? 0 : (svc ? (svc.price || 0) : 0));
}
$('booking-service').addEventListener('change', () => { if (!BK.editing) bookingSubToggle(); });

async function bookingLoadSlots() {
  const sid = val('booking-service'), date = val('booking-date'); if (!sid || !date) return;
  const staff = val('booking-staff');
  const box = $('booking-slots'); box.innerHTML = '<span class="muted small">Loading...</span>';
  try {
    const av = await api('GET', `/appointments/availability?service_id=${sid}&date=${date}${staff ? '&staff_id=' + staff : ''}${BK.editing ? '&exclude_id=' + BK.editing.id : ''}`);
    BK.slots = av.slots;
    $('booking-slots-info').textContent = av.open ? `· open ${av.open_time}–${av.close_time}` : '· closed this day';
    if (!av.slots.length) { box.innerHTML = '<span class="muted small">Studio is closed. You can still type a time and save with override.</span>'; return; }
    box.innerHTML = av.slots.map(s => { const t = timeKey(parseISO(s.start_time)); return `<button type="button" class="slot ${s.available ? '' : 'taken'} ${t === val('booking-time') ? 'selected' : ''}" title="${esc(s.reason || '')}" onclick="pickSlot('${t}')">${esc(s.label)}</button>`; }).join('');
  } catch (e) { box.innerHTML = `<span class="muted small">${esc(e.message)}</span>`; }
}
function pickSlot(t) { setVal('booking-time', t); document.querySelectorAll('#booking-slots .slot').forEach(b => b.classList.toggle('selected', b.textContent.trim() === fmtTime(zonedToDate(val('booking-date'), t).toISOString()))); }

function bookingRepeatChanged() {
  if (BK.editing) return;
  const every = +val('booking-repeat'), n = Math.min(Math.max(parseInt(val('booking-repeat-count')) || 2, 2), 52);
  $('booking-repeat-count-group').style.display = every ? '' : 'none';
  $('booking-save').textContent = every ? `Book ${n} sessions` : 'Book session';
  if (every && val('booking-date')) $('booking-repeat-help').textContent = `Last session: ${fmtKeyLong(addDays(val('booking-date'), (n - 1) * every * 7))}`;
}
$('booking-date').addEventListener('change', bookingRepeatChanged);

/* Says what really happened to the confirmation message, instead of always claiming it was sent. */
function notifySummary(res) {
  const r = res.notify_result;
  if (!r || !r.length) return { text: '', bad: false };
  const ok = r.filter(x => x.status === 'sent'), bad = r.filter(x => x.status !== 'sent');
  if (!bad.length) return { text: ` Confirmation sent via ${ok.map(x => x.channel).join(', ')}.`, bad: false };
  const why = bad.map(x => `${x.channel ? x.channel + ': ' : ''}${(x.detail || x.status).replace(/^(whatsapp|sms|email): /, '')}`).join(' · ');
  return { text: `${ok.length ? ` Sent via ${ok.map(x => x.channel).join(', ')}.` : ''} Confirmation NOT sent — ${why}`, bad: true };
}

async function saveBooking(force = false) {
  const date = val('booking-date'), time = val('booking-time');
  if (!date || !time) return toast('Pick a date and time', true);
  const payload = { service_id: +val('booking-service'), staff_id: val('booking-staff') ? +val('booking-staff') : null,
    start_time: zonedToDate(date, time).toISOString(), notes: val('booking-notes') || null, price: parseFloat(val('booking-price')) || 0,
    send_notification: $('booking-notify').checked, force };
  if (!BK.editing && +val('booking-repeat') > 0) { payload.repeat_interval_weeks = +val('booking-repeat'); payload.repeat_count = Math.min(Math.max(parseInt(val('booking-repeat-count')) || 2, 2), 52); }
  try {
    if (BK.editing) {
      await api('PUT', `/appointments/${BK.editing.id}`, payload);
      toast('Session updated' + (payload.send_notification ? '. Client notified.' : ''));
    } else {
      if (BK.clientId) payload.client_id = BK.clientId;
      else { payload.client_name = val('booking-client').trim(); payload.client_phone = val('booking-client-phone').trim(); payload.client_email = val('booking-client-email').trim() || null;
        if (!payload.client_name || !payload.client_phone) return toast('Enter the new client name and phone', true); }
      payload.use_subscription = BK.sub ? $('booking-use-sub').checked : false;
      const btn = $('booking-save'); btn.disabled = true; let res;
      try { res = await api('POST', '/appointments/', payload); } finally { btn.disabled = false; }
      const n = notifySummary(res), skipped = res.series_skipped || [];
      let msg = res.series_created ? `${res.series_created} sessions booked.` : 'Session booked.';
      if (skipped.length) msg += ` ${skipped.length} skipped (${skipped.map(x => x.date.replace(/^\w+, /, '').replace(/ \d{4}$/, '')).join(', ')}: not free).`;
      toast(msg + n.text, n.bad || skipped.length > 0);
    }
    closeModal('booking-modal'); await refreshLookups(); refreshCurrent();
  } catch (e) {
    if (e.status === 409 && !force) { const c = $('booking-conflict'); c.style.display = 'flex'; c.innerHTML = `⚠️ ${esc(e.message)} <button class="btn btn-warn btn-sm" style="margin-left:auto" onclick="saveBooking(true)">Book anyway</button>`; }
    else toast(e.message, true);
  }
}
function refreshCurrent() { if (PAGES[S.page]) PAGES[S.page]().catch(() => {}); }

/* ---------- session drawer ---------- */
async function openAppointment(id) {
  const a = await api('GET', `/appointments/${id}`);
  const logs = await api('GET', `/notifications/logs?limit=20&client_id=${a.client_id}`);
  const mine = logs.filter(l => l.appointment_id === a.id);
  const base = S.settings.public_base_url ? S.settings.public_base_url.replace(/\/$/, '') : location.origin;
  const manageLink = `${base}/a/${a.public_token}`;
  $('drawer-title').innerHTML = `${esc(a.service.name)} ${badge(a.status)}`;
  $('drawer-body').innerHTML = `
    <dl class="kv">
      <dt>Client</dt><dd><a href="#" onclick="closeDrawer();openClientDetail(${a.client_id});return false">${esc(a.client.name)}</a><div class="tiny muted">${esc(a.client.phone)}${a.client.email ? ' · ' + esc(a.client.email) : ''}</div></dd>
      <dt>When</dt><dd>${fmtDateShort(a.start_time)}, ${fmtTime(a.start_time)} – ${fmtTime(a.end_time)}<div class="tiny muted">${relTime(a.start_time)} · ${a.service.duration_minutes} min</div></dd>
      <dt>Trainer</dt><dd>${a.staff ? esc(a.staff.name) : '<span class="muted">Unassigned</span>'}</dd>
      <dt>Price</dt><dd>${a.subscription_id ? '<span class="chip">Covered by package</span>' : money(a.price)}${!a.subscription_id && a.price > 0 ? ` · paid ${money(a.paid_amount)}${a.balance_due > 0 ? ` · <span style="color:var(--bad)">due ${money(a.balance_due)}</span>` : ' · <span style="color:var(--good)">settled</span>'}` : ''}</dd>
      ${a.series_id ? `<dt>Repeat</dt><dd><span class="chip">🔁 Part of a repeat booking</span></dd>` : ''}
      <dt>Booked via</dt><dd>${a.source === 'online' ? 'Online booking page' : 'Admin'} · ${fmtDate(a.created_at)}</dd>
      ${a.notes ? `<dt>Notes</dt><dd>${esc(a.notes)}</dd>` : ''}
      ${a.cancel_reason || a.cancelled_by ? `<dt>Cancelled</dt><dd>by ${esc(a.cancelled_by || 'admin')}${a.cancel_reason ? ': ' + esc(a.cancel_reason) : ''}</dd>` : ''}
      <dt>Client link</dt><dd><input class="input input-sm" value="${esc(manageLink)}" readonly onclick="this.select()"><div class="tiny muted">Client can confirm or cancel from this link (sent in messages).</div></dd>
    </dl>
    ${(a.status === 'scheduled' || a.status === 'confirmed') ? `<div class="mt" style="display:flex;gap:6px;flex-wrap:wrap">
      ${a.status === 'scheduled' ? `<button class="btn btn-success btn-sm" onclick="setStatus(${a.id}, 'confirmed')">✓ Confirm</button>` : ''}
      <button class="btn btn-primary btn-sm" onclick="completeFlow(${a.id})">Complete</button>
      <button class="btn btn-warn btn-sm" onclick="setStatus(${a.id}, 'no_show')">No-show</button>
      <button class="btn btn-secondary btn-sm" onclick="closeDrawer();openBookingModal(${a.id})">Reschedule</button>
      <button class="btn btn-danger btn-sm" onclick="cancelFlow(${a.id})">Cancel</button>
      ${a.series_id ? `<button class="btn btn-danger btn-sm" onclick="cancelSeriesFlow(${a.id})">Cancel this + all following</button>` : ''}</div>` : ''}
    ${a.status === 'completed' && a.balance_due > 0 ? `<div class="mt"><button class="btn btn-primary btn-sm" onclick="openPaymentModal({client_id:${a.client_id}, appointment_id:${a.id}, amount:${a.balance_due}, label:'${esc(a.service.name)} on ${fmtDateShort(a.start_time)}'})">Record payment ${money(a.balance_due)}</button></div>` : ''}
    ${a.status === 'cancelled' || a.status === 'no_show' ? `<div class="mt"><button class="btn btn-secondary btn-sm" onclick="setStatus(${a.id}, 'scheduled')">Re-open as scheduled</button></div>` : ''}
    <div class="mt" style="display:flex;gap:6px;flex-wrap:wrap">
      <button class="btn btn-secondary btn-sm" onclick="sendReminder(${a.id})">Send reminder</button>
      <button class="btn btn-secondary btn-sm" onclick="resendConfirmation(${a.id})">Resend confirmation</button>
    </div>
    <div class="card-title mt" style="font-size:.85rem">Messages for this session</div>
    ${mine.length ? mine.map(l => `<div class="small" style="padding:6px 0;border-bottom:1px solid var(--border)"><span class="badge badge-${l.status}">${l.status}</span> <span class="chip">${l.channel}</span> ${esc(l.type.replace(/_/g, ' '))} <span class="muted tiny">${fmtDT(l.created_at)}</span></div>`).join('') : '<div class="muted small">No messages yet.</div>'}`;
  $('drawer-footer').innerHTML = `<div class="left"><button class="btn btn-ghost btn-sm" style="color:var(--bad)" onclick="deleteAppointment(${a.id})">Delete</button></div><button class="btn btn-secondary" onclick="closeDrawer()">Close</button>`;
  openDrawer();
}
async function setStatus(id, status, extra = {}) { await guard(async () => { await api('POST', `/appointments/${id}/status`, { status, ...extra }); toast(`Marked ${status.replace('_', ' ')}`); await openAppointment(id); refreshCurrent(); }); }
function completeFlow(id) {
  api('GET', `/appointments/${id}`).then(a => {
    const needsPay = !a.subscription_id && a.balance_due > 0;
    confirmBox('Complete session', `<p>Mark <strong>${esc(a.client.name)}</strong>'s ${esc(a.service.name)} as completed.</p>` + (needsPay ? `
      <div class="form-row"><div class="form-group"><label>Payment received</label><input type="number" step="0.01" id="cp-amount" class="input" value="${a.balance_due}"></div>
      <div class="form-group"><label>Method</label><select id="cp-method" class="input"><option value="cash">Cash</option><option value="card">Card</option><option value="transfer">Bank transfer</option><option value="online">Online</option><option value="">Not paid yet</option></select></div></div>` : '<p class="muted small">Covered by package or already paid.</p>'),
      'Complete', async () => { const amt = needsPay ? parseFloat(val('cp-amount')) : 0; const m = needsPay ? val('cp-method') : '';
        await api('POST', `/appointments/${id}/status`, { status: 'completed', payment_amount: m ? amt : null, payment_method: m || null }); toast('Session completed'); await openAppointment(id); refreshCurrent(); });
  });
}
function cancelFlow(id) {
  confirmBox('Cancel session', `<div class="form-group"><label>Reason (included in the client's message)</label><input id="cx-reason" class="input" placeholder="Optional"></div><label class="check"><input type="checkbox" id="cx-notify" checked> Notify client</label><p class="small muted mt">If this session used a package, the session is returned to the client's balance.</p>`,
    'Cancel session', async () => { await api('POST', `/appointments/${id}/status`, { status: 'cancelled', reason: val('cx-reason') || null, send_notification: $('cx-notify').checked }); toast('Session cancelled'); await openAppointment(id); refreshCurrent(); }, 'btn-danger');
}
function cancelSeriesFlow(id) {
  confirmBox('Cancel repeat booking', `<p>Cancels this session and every later session of the same repeat booking. Earlier sessions are kept.</p><div class="form-group"><label>Reason (included in the client's message)</label><input id="cs-reason" class="input" placeholder="Optional"></div><label class="check"><input type="checkbox" id="cs-notify" checked> Notify client (one message)</label>`,
    'Cancel sessions', async () => { const r = await api('POST', `/appointments/${id}/cancel-series`, { reason: val('cs-reason') || null, send_notification: $('cs-notify').checked }); toast(`${r.cancelled} session(s) cancelled`); await openAppointment(id); refreshCurrent(); }, 'btn-danger');
}
function deleteAppointment(id) { confirmBox('Delete session', '<p>Delete this session permanently? Prefer <strong>Cancel</strong> to keep history.</p>', 'Delete', async () => { await api('DELETE', `/appointments/${id}`); closeDrawer(); toast('Deleted'); refreshCurrent(); }, 'btn-danger'); }
async function sendReminder(id) { await guard(async () => { const r = await api('POST', `/notifications/${id}/reminder`); toast(r.length ? `Reminder sent via ${r.map(l => l.channel).join(', ')}` : 'No channel enabled for this client'); openAppointment(id); }); }
async function resendConfirmation(id) { await guard(async () => { const r = await api('POST', `/notifications/${id}/confirmation`); toast(r.length ? `Confirmation sent via ${r.map(l => l.channel).join(', ')}` : 'No channel enabled for this client'); openAppointment(id); }); }
