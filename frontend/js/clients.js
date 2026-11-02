/* Clients list, detail view, client modal */
async function loadClients() {
  const q = val('client-search'); const inactive = $('client-inactive').checked;
  const clients = await api('GET', `/clients/?q=${encodeURIComponent(q)}${inactive ? '&include_inactive=true' : ''}`);
  S.clients = clients.filter(c => c.active);
  $('clients-sub').textContent = `${clients.length} client${clients.length === 1 ? '' : 's'}`;
  const div = $('clients-list');
  if (!clients.length) { div.innerHTML = '<div class="card empty">No clients found.</div>'; return; }
  div.innerHTML = `<table><thead><tr><th>Client</th><th>Contact</th><th class="num">Sessions</th><th class="num">Package left</th><th class="num">Spent</th><th>Last visit</th><th>Next visit</th><th></th></tr></thead><tbody>` +
    clients.map(c => `<tr class="clickable" onclick="openClientDetail(${c.id})">
      <td><strong>${esc(c.name)}</strong>${!c.active ? ' <span class="chip">inactive</span>' : ''}<div class="tiny muted">${esc(c.source || '')}${c.no_shows ? ` · ${c.no_shows} no-show${c.no_shows > 1 ? 's' : ''}` : ''}</div></td>
      <td>${esc(c.phone)}<div class="tiny muted">${esc(c.email || '')}</div></td>
      <td class="num">${c.completed_appointments}</td>
      <td class="num">${c.sessions_remaining ? `<strong>${c.sessions_remaining}</strong>` : '<span class="muted">—</span>'}</td>
      <td class="num">${money(c.total_spent)}${c.outstanding > 0 ? `<div class="tiny" style="color:var(--bad)">owes ${money(c.outstanding)}</div>` : ''}</td>
      <td>${c.last_visit ? fmtDate(c.last_visit) : '<span class="muted">—</span>'}</td>
      <td>${c.next_visit ? fmtDT(c.next_visit) : '<span class="muted">—</span>'}</td>
      <td class="num"><button class="btn btn-primary btn-xs" onclick="event.stopPropagation();openBookingModal(null, {clientId:${c.id}})">Book</button></td></tr>`).join('') + '</tbody></table>';
}

async function openClientDetail(id) {
  const h = await api('GET', `/clients/${id}/history`);
  const c = h.client;
  $('cd-title').innerHTML = `${esc(c.name)} ${c.active ? '' : '<span class="chip">inactive</span>'}`;
  const upcoming = h.appointments.filter(a => ['scheduled', 'confirmed'].includes(a.status) && parseISO(a.start_time) > new Date()).reverse();
  const past = h.appointments.filter(a => !upcoming.includes(a));
  $('cd-body').innerHTML = `
    <div class="grid grid-4 mb">
      <div class="stat"><div class="stat-label">Sessions done</div><div class="stat-value">${c.completed_appointments}</div><div class="stat-sub">${c.no_shows} no-shows</div></div>
      <div class="stat"><div class="stat-label">Total spent</div><div class="stat-value">${money(c.total_spent)}</div><div class="stat-sub">${c.outstanding > 0 ? `<span style="color:var(--bad)">owes ${money(c.outstanding)}</span>` : 'nothing owed'}</div></div>
      <div class="stat"><div class="stat-label">Package left</div><div class="stat-value">${c.sessions_remaining}</div><div class="stat-sub">sessions</div></div>
      <div class="stat"><div class="stat-label">Client since</div><div class="stat-value" style="font-size:1.1rem">${fmtDate(c.created_at)}</div><div class="stat-sub">${esc(c.source || '')}</div></div>
    </div>
    <dl class="kv mb"><dt>Phone</dt><dd>${esc(c.phone)}</dd><dt>Email</dt><dd>${esc(c.email || '—')}</dd><dt>Notifications</dt><dd>${[c.notify_whatsapp && 'WhatsApp', c.notify_sms && 'SMS', c.notify_email && 'Email'].filter(Boolean).join(', ') || 'none'}</dd>${c.date_of_birth ? `<dt>Birthday</dt><dd>${esc(c.date_of_birth)}</dd>` : ''}${c.notes ? `<dt>Notes</dt><dd>${esc(c.notes)}</dd>` : ''}</dl>
    <div class="tabs">
      <button class="tab active" onclick="cdTab('appts', this)">Sessions (${h.appointments.length})</button>
      <button class="tab" onclick="cdTab('subs', this)">Packages (${h.subscriptions.length})</button>
      <button class="tab" onclick="cdTab('pays', this)">Payments (${h.payments.length})</button>
      <button class="tab" onclick="cdTab('msgs', this)">Messages (${h.messages.length})</button>
    </div>
    <div id="cd-appts" class="subpanel active">${upcoming.length ? '<div class="agenda-day">Upcoming</div>' + apptTable(upcoming, { withDate: true }) : ''}${past.length ? '<div class="agenda-day">History</div>' + apptTable(past, { withDate: true }) : ''}${!h.appointments.length ? '<div class="empty small">No sessions yet.</div>' : ''}</div>
    <div id="cd-subs" class="subpanel">${subsTable(h.subscriptions)}</div>
    <div id="cd-pays" class="subpanel">${paymentsTable(h.payments, true)}</div>
    <div id="cd-msgs" class="subpanel">${messagesTable(h.messages, true)}</div>`;
  $('cd-footer').innerHTML = `<div class="left"><button class="btn btn-secondary btn-sm" onclick="editClient(${c.id})">Edit</button><button class="btn btn-secondary btn-sm" onclick="closeModal('client-detail-modal');openCustomMessageModal(${c.id})">Message</button><button class="btn btn-secondary btn-sm" onclick="closeModal('client-detail-modal');openPaymentModal({client_id:${c.id}})">Record payment</button><button class="btn btn-secondary btn-sm" onclick="closeModal('client-detail-modal');openSubscriptionModal(null, ${c.id})">Sell package</button></div><button class="btn btn-primary" onclick="closeModal('client-detail-modal');openBookingModal(null, {clientId:${c.id}})">Book session</button>`;
  openModal('client-detail-modal');
}
function cdTab(t, el) { document.querySelectorAll('#cd-body .tab').forEach(x => x.classList.remove('active')); el.classList.add('active'); document.querySelectorAll('#cd-body .subpanel').forEach(p => p.classList.toggle('active', p.id === 'cd-' + t)); }

function openClientModal() {
  $('client-modal-title').textContent = 'Add client';
  ['client-id', 'client-name', 'client-phone', 'client-email', 'client-notes', 'client-dob'].forEach(i => setVal(i, ''));
  setVal('client-source', 'walk-in'); setVal('client-active', 'true');
  $('client-nwa').checked = true; $('client-nsms').checked = false; $('client-nemail').checked = true;
  openModal('client-modal');
}
async function editClient(id) {
  const c = S.clients.find(x => x.id === id) || await api('GET', `/clients/${id}`);
  closeModal('client-detail-modal'); openClientModal();
  $('client-modal-title').textContent = 'Edit client';
  setVal('client-id', c.id); setVal('client-name', c.name); setVal('client-phone', c.phone); setVal('client-email', c.email); setVal('client-notes', c.notes);
  setVal('client-dob', c.date_of_birth); setVal('client-source', c.source || ''); setVal('client-active', String(c.active));
  $('client-nwa').checked = c.notify_whatsapp; $('client-nsms').checked = c.notify_sms; $('client-nemail').checked = c.notify_email;
}
async function saveClient() {
  guard(async () => {
    const id = val('client-id');
    const payload = { name: val('client-name').trim(), phone: val('client-phone').trim(), email: val('client-email').trim() || null, notes: val('client-notes') || null,
      date_of_birth: val('client-dob') || null, source: val('client-source') || null, active: val('client-active') === 'true',
      notify_whatsapp: $('client-nwa').checked, notify_sms: $('client-nsms').checked, notify_email: $('client-nemail').checked };
    if (!payload.name || !payload.phone) throw new Error('Name and phone are required');
    if (id) await api('PUT', `/clients/${id}`, payload); else await api('POST', '/clients/', payload);
    closeModal('client-modal'); toast('Client saved'); await refreshLookups(); refreshCurrent();
  });
}
