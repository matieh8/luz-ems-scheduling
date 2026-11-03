/* Settings page: business, hours, scheduling, online booking, channels, automations, catalog */
const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
async function loadSettings() {
  const [s, hours] = await Promise.all([api('GET', '/settings/'), api('GET', '/settings/hours')]); S.settings = s;
  const row = (id, label, help, type = 'text', extra = '') => `<div class="form-group"><label>${label}</label><input type="${type}" id="st-${id}" class="input" value="${esc(s[id] ?? '')}" ${extra}>${help ? `<div class="help">${help}</div>` : ''}</div>`;
  const tog = (id, label, help) => `<div class="setting-row"><div><strong>${label}</strong>${help ? `<p>${help}</p>` : ''}</div><label class="toggle"><input type="checkbox" id="st-${id}" ${s[id] ? 'checked' : ''}><span class="slider"></span></label></div>`;
  $('settings-form').innerHTML = `
    <div class="grid grid-2">
      <div class="card"><div class="card-title">Business</div>
        ${row('business_name', 'Business name')}
        <div class="form-row">${row('business_phone', 'Phone (admin alerts go here)', '', 'tel')}${row('business_email', 'Email', '', 'email')}</div>
        ${row('business_address', 'Address', 'Shown in messages as {business_address}')}
        <div class="form-row">${row('timezone', 'Time zone', 'e.g. Asia/Dubai')}${row('currency', 'Currency', '')}</div>
        ${row('public_base_url', 'Public URL', 'Used to build booking and manage links in messages, e.g. https://book.luzems.com')}
      </div>
      <div class="card"><div class="card-title">Opening hours</div>
        <div id="st-hours">${hours.map(h => `<div class="hours-row"><strong class="small">${DAYS[h.day_of_week]}</strong><input type="time" class="input input-sm" id="h-open-${h.day_of_week}" value="${h.open_time}"><span class="muted">–</span><input type="time" class="input input-sm" id="h-close-${h.day_of_week}" value="${h.close_time}"><label class="check small"><input type="checkbox" id="h-closed-${h.day_of_week}" ${h.closed ? 'checked' : ''}> Closed</label></div>`).join('')}</div>
        <div class="help mt">Bookings outside these hours are rejected unless you override. Block holidays from the calendar.</div>
      </div>
      <div class="card"><div class="card-title">Scheduling rules</div>
        <div class="form-row">${row('slot_interval_minutes', 'Slot interval (min)', 'Start times offered every N minutes', 'number')}${row('max_concurrent_sessions', 'Machines / rooms', 'How many sessions can run at once', 'number')}</div>
        ${tog('auto_complete_past', 'Auto-complete past sessions', 'Scheduled sessions become "completed" once their end time passes')}
      </div>
      <div class="card"><div class="card-title">Online booking <a class="small" href="/book" target="_blank">open page ↗</a></div>
        ${tog('online_booking_enabled', 'Allow clients to book online', 'Public page at /book')}
        <div class="form-row-3 mt">${row('online_min_notice_hours', 'Min notice (h)', '', 'number')}${row('online_max_days_ahead', 'Max days ahead', '', 'number')}${row('online_allow_cancel_hours', 'Cancel up to (h) before', '', 'number')}</div>
        ${tog('notify_admin_online_booking', 'Alert me on new online bookings', 'Sent to the business phone / email')}
      </div>
      <div class="card"><div class="card-title">Automations</div>
        ${row('reminder_hours_before', 'Reminder hours before session', '0 disables reminders', 'number')}
        ${tog('follow_up_enabled', 'Send follow-up after sessions', 'Thank-you message with remaining package sessions')}
        ${row('follow_up_hours_after', 'Follow-up hours after session', '', 'number')}
        <div class="form-row">${row('subscription_low_threshold', 'Package low alert at (sessions)', '', 'number')}${row('subscription_expiry_notice_days', 'Package expiry notice (days)', '', 'number')}</div>
      </div>
      <div class="card"><div class="card-title">Messaging channels</div>
        ${tog('demo_mode', 'Demo mode', 'Messages are logged in the Messages page but not actually sent. Turn off when you go live.')}
        <div class="form-group mt"><label>WhatsApp provider</label><select id="st-whatsapp_provider" class="input" onchange="stProvider()"><option value="demo" ${s.whatsapp_provider === 'demo' ? 'selected' : ''}>None (demo)</option><option value="whatsapp_web" ${s.whatsapp_provider === 'whatsapp_web' ? 'selected' : ''}>WhatsApp Web (free, your own number)</option><option value="twilio" ${s.whatsapp_provider === 'twilio' ? 'selected' : ''}>Twilio WhatsApp Business API</option></select></div>
        ${tog('whatsapp_enabled', 'WhatsApp enabled')}
        <div id="st-wa-web" style="display:${s.whatsapp_provider === 'whatsapp_web' ? 'block' : 'none'};padding:14px;background:var(--bg);border-radius:12px;margin:10px 0"><strong>WhatsApp Web pairing</strong><p class="small muted">Scan with the business phone: WhatsApp → Linked devices → Link a device.</p><div id="whatsapp-qr" style="text-align:center"><em class="small">Loading status…</em></div></div>
        <div id="st-twilio" style="display:${s.whatsapp_provider === 'twilio' || s.sms_enabled ? 'block' : 'none'}">
          <div class="form-row">${row('twilio_account_sid', 'Twilio Account SID')}${row('twilio_auth_token', 'Twilio Auth Token', '', 'password')}</div>
          ${row('twilio_phone_number', 'Twilio WhatsApp sender', 'e.g. whatsapp:+14155238886')}
        </div>
        ${tog('sms_enabled', 'SMS enabled (Twilio)', 'Only for clients who opted in to SMS')}
        ${row('twilio_sms_number', 'Twilio SMS number', 'e.g. +971…')}
        ${tog('email_enabled', 'Email enabled (SMTP)')}
        <div class="form-row">${row('smtp_host', 'SMTP host')}${row('smtp_port', 'SMTP port', '587 (STARTTLS) or 465 (SSL)', 'number')}</div>
        <div class="form-row">${row('smtp_username', 'SMTP username')}${row('smtp_password', 'SMTP password', '', 'password')}</div>
        ${row('smtp_from', 'From address', 'e.g. LUZ EMS <hello@luzems.com>')}
      </div>
      <div class="card"><div class="card-title">Security</div>
        <div class="form-group"><label>Current password</label><input type="password" id="pw-current" class="input" autocomplete="current-password"></div>
        <div class="form-group"><label>New password</label><input type="password" id="pw-new" class="input" autocomplete="new-password"></div>
        <button class="btn btn-secondary" onclick="changePassword()">Change password</button>
      </div>
      <div class="card" style="border-color:var(--bad-bg)"><div class="card-title" style="color:var(--bad)">Danger zone</div>
        <p class="small muted">Clear all bookings, packages, payments, blocked times and message history. Services, trainers, plans, templates and settings are kept. Use this to remove demo data before going live.</p>
        <label class="small" style="display:flex;align-items:center;gap:8px;margin:8px 0"><input type="checkbox" id="reset-keep-clients"> Keep the client list (only clear their history)</label>
        <div class="form-group"><label>Type DELETE to confirm</label><input id="reset-confirm" class="input" placeholder="DELETE" autocomplete="off"></div>
        <button class="btn btn-danger" onclick="resetData()">Clear all data</button>
      </div>
    </div>`;
  if (s.whatsapp_provider === 'whatsapp_web') loadWhatsAppStatus();
}
function stProvider() { const p = val('st-whatsapp_provider'); $('st-wa-web').style.display = p === 'whatsapp_web' ? 'block' : 'none'; $('st-twilio').style.display = p === 'twilio' || $('st-sms_enabled').checked ? 'block' : 'none'; if (p === 'whatsapp_web') loadWhatsAppStatus(); }
async function loadWhatsAppStatus() {
  const box = $('whatsapp-qr'); if (!box) return;
  try { const st = await api('GET', '/notifications/whatsapp-status');
    if (st.ready) box.innerHTML = '<div style="color:var(--good);font-weight:600">✓ Connected and ready</div>';
    else if (st.qr_image) { box.innerHTML = `<img src="${st.qr_image}" style="max-width:260px;border-radius:12px" alt="QR"><p class="small muted">Scan with the business phone</p>`; setTimeout(loadWhatsAppStatus, 5000); }
    else { box.innerHTML = `<em class="small">Waiting for QR code… (${esc(st.status)})</em>`; if (st.status !== 'bridge_offline') setTimeout(loadWhatsAppStatus, 3000); else box.innerHTML = `<div style="color:var(--bad);font-weight:600">WhatsApp bridge is offline</div><p class="small muted">${esc(st.reason || 'Node bridge not running')}</p><p class="small muted">Until it is running, WhatsApp messages will fail. Turn on <strong>Demo mode</strong> to log messages without sending, or use the Twilio provider.</p>`; }
  } catch (e) { box.innerHTML = '<em class="small">Status unavailable.</em>'; }
}
async function saveSettings() {
  guard(async () => {
    const ids = ['business_name', 'business_phone', 'business_email', 'business_address', 'timezone', 'currency', 'public_base_url', 'slot_interval_minutes', 'max_concurrent_sessions', 'online_min_notice_hours', 'online_max_days_ahead', 'online_allow_cancel_hours', 'reminder_hours_before', 'follow_up_hours_after', 'subscription_low_threshold', 'subscription_expiry_notice_days', 'whatsapp_provider', 'twilio_account_sid', 'twilio_auth_token', 'twilio_phone_number', 'twilio_sms_number', 'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'smtp_from'];
    const toggles = ['auto_complete_past', 'online_booking_enabled', 'notify_admin_online_booking', 'follow_up_enabled', 'demo_mode', 'whatsapp_enabled', 'sms_enabled', 'email_enabled'];
    const payload = {};
    ids.forEach(i => { const el = $('st-' + i); let v = el.value; if (el.type === 'number') v = v === '' ? null : +v; else v = v.trim() || null; payload[i] = v; });
    ['business_name', 'timezone', 'currency'].forEach(k => { if (!payload[k]) throw new Error(`${k.replace('_', ' ')} is required`); });
    toggles.forEach(i => payload[i] = $('st-' + i).checked);
    await api('PUT', '/settings/', payload);
    await api('PUT', '/settings/hours', DAYS.map((_, d) => ({ day_of_week: d, open_time: val(`h-open-${d}`), close_time: val(`h-close-${d}`), closed: $(`h-closed-${d}`).checked })));
    CAL.hours = []; toast('Settings saved'); await refreshLookups(); loadSettings();
  });
}
async function changePassword() { guard(async () => { if (!val('pw-current') || !val('pw-new')) throw new Error('Enter both passwords'); await api('POST', '/auth/password', { current_password: val('pw-current'), new_password: val('pw-new') }); toast('Password changed'); setVal('pw-current', ''); setVal('pw-new', ''); }); }

/* ---------- services & team ---------- */
async function loadCatalog() {
  const [services, staff] = await Promise.all([api('GET', '/services/'), api('GET', '/staff/')]); S.services = services; S.staff = staff;
  $('services-list').innerHTML = !services.length ? '<div class="card empty">No services yet.</div>' : `<table><thead><tr><th>Service</th><th class="num">Duration</th><th class="num">Price</th><th>Online</th><th></th></tr></thead><tbody>` + services.map(s => `<tr>
    <td><span class="dot" style="background:${s.color}"></span><strong>${esc(s.name)}</strong>${!s.active ? ' <span class="chip">inactive</span>' : ''}<div class="tiny muted">${esc(s.description || '')}</div></td>
    <td class="num">${s.duration_minutes} min${s.buffer_minutes ? `<div class="tiny muted">+${s.buffer_minutes} buffer</div>` : ''}</td><td class="num">${s.price ? money(s.price) : '<span class="muted">free</span>'}</td><td>${s.online_bookable ? '✓' : '—'}</td>
    <td class="num"><button class="btn btn-ghost btn-xs" onclick="editService(${s.id})">Edit</button><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteService(${s.id})">Delete</button></td></tr>`).join('') + '</tbody></table>';
  $('staff-list').innerHTML = !staff.length ? '<div class="card empty">No trainers yet. Sessions can still be booked unassigned.</div>' : `<table><thead><tr><th>Trainer</th><th>Contact</th><th></th></tr></thead><tbody>` + staff.map(s => `<tr>
    <td><span class="dot" style="background:${s.color}"></span><strong>${esc(s.name)}</strong>${!s.active ? ' <span class="chip">inactive</span>' : ''}<div class="tiny muted">${esc(s.role || '')}</div></td><td class="small">${esc(s.phone || '')}<div class="tiny muted">${esc(s.email || '')}</div></td>
    <td class="num"><button class="btn btn-ghost btn-xs" onclick="editStaff(${s.id})">Edit</button><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteStaff(${s.id})">Delete</button></td></tr>`).join('') + '</tbody></table>';
}
function openServiceModal() { $('service-modal-title').textContent = 'Add service'; ['service-id', 'service-name', 'service-price', 'service-description', 'service-category'].forEach(i => setVal(i, '')); setVal('service-duration', 45); setVal('service-buffer', 15); setVal('service-color', PALETTE[S.services.length % PALETTE.length]); $('service-online').checked = true; $('service-active').checked = true; openModal('service-modal'); }
function editService(id) { const s = S.services.find(x => x.id === id); openServiceModal(); $('service-modal-title').textContent = 'Edit service'; setVal('service-id', s.id); setVal('service-name', s.name); setVal('service-duration', s.duration_minutes); setVal('service-buffer', s.buffer_minutes); setVal('service-price', s.price); setVal('service-color', s.color); setVal('service-category', s.category); setVal('service-description', s.description); $('service-online').checked = s.online_bookable; $('service-active').checked = s.active; }
async function saveService() { guard(async () => { const id = val('service-id'); const payload = { name: val('service-name').trim(), duration_minutes: +val('service-duration'), buffer_minutes: +val('service-buffer') || 0, price: val('service-price') === '' ? null : parseFloat(val('service-price')), color: val('service-color'), category: val('service-category') || null, description: val('service-description') || null, online_bookable: $('service-online').checked, active: $('service-active').checked };
  if (!payload.name || !payload.duration_minutes) throw new Error('Name and duration are required'); if (id) await api('PUT', `/services/${id}`, payload); else await api('POST', '/services/', payload); closeModal('service-modal'); toast('Service saved'); await refreshLookups(); loadCatalog(); }); }
function deleteService(id) { confirmBox('Delete service', '<p>Delete this service? If it has bookings it will be deactivated instead.</p>', 'Delete', async () => { const r = await api('DELETE', `/services/${id}`); toast(r.detail); await refreshLookups(); loadCatalog(); }, 'btn-danger'); }
function openStaffModal() { $('staff-modal-title').textContent = 'Add trainer'; ['staff-id', 'staff-name', 'staff-phone', 'staff-email'].forEach(i => setVal(i, '')); setVal('staff-role', 'Trainer'); setVal('staff-color', PALETTE[(S.staff.length + 6) % PALETTE.length]); $('staff-active').checked = true; openModal('staff-modal'); }
function editStaff(id) { const s = S.staff.find(x => x.id === id); openStaffModal(); $('staff-modal-title').textContent = 'Edit trainer'; setVal('staff-id', s.id); setVal('staff-name', s.name); setVal('staff-role', s.role); setVal('staff-phone', s.phone); setVal('staff-email', s.email); setVal('staff-color', s.color); $('staff-active').checked = s.active; }
async function saveStaff() { guard(async () => { const id = val('staff-id'); const payload = { name: val('staff-name').trim(), role: val('staff-role') || null, phone: val('staff-phone') || null, email: val('staff-email') || null, color: val('staff-color'), active: $('staff-active').checked };
  if (!payload.name) throw new Error('Name is required'); if (id) await api('PUT', `/staff/${id}`, payload); else await api('POST', '/staff/', payload); closeModal('staff-modal'); toast('Trainer saved'); await refreshLookups(); loadCatalog(); }); }
function deleteStaff(id) { confirmBox('Delete trainer', '<p>Delete this trainer? If they have sessions they will be deactivated instead.</p>', 'Delete', async () => { const r = await api('DELETE', `/staff/${id}`); toast(r.detail); await refreshLookups(); loadCatalog(); }, 'btn-danger'); }

async function resetData() {
  if (val('reset-confirm').trim().toUpperCase() !== 'DELETE') { toast('Type DELETE to confirm', true); return; }
  if (!confirm('Clear all bookings, payments, packages and message history? This cannot be undone.')) return;
  guard(async () => {
    const r = await api('POST', '/settings/reset-data', { confirm: 'DELETE', keep_clients: $('reset-keep-clients').checked });
    setVal('reset-confirm', '');
    toast(`Cleared: ${Object.entries(r.deleted).map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(', ')}`);
    await refreshLookups();
  });
}
