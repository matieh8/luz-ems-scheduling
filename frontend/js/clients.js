/* Clients list, client profile (CRM), client modal */
const RISK = {
  new: { label: 'New', cls: 'badge-neutral', tip: 'Fewer than two sessions so far' },
  regular: { label: 'Regular', cls: 'badge-active', tip: 'Coming at their usual rhythm, or already booked' },
  slipping: { label: 'Slipping', cls: 'badge-queued', tip: 'Gap since last session is 1.5x their usual gap' },
  at_risk: { label: 'At risk', cls: 'badge-no_show', tip: 'Gap is 2.5x their usual: likely to stop, reach out' },
  lapsed: { label: 'Lapsed', cls: 'badge-cancelled', tip: 'No session for 4x their usual gap or 60+ days' },
};
function riskBadge(c) { const r = RISK[c.risk] || RISK.new; return `<span class="badge ${r.cls}" title="${esc(r.tip)}">${r.label}</span>`; }

async function loadClients() {
  const q = val('client-search'); const inactive = $('client-inactive').checked; const risk = $('client-risk') ? val('client-risk') : '';
  let clients = await api('GET', `/clients/?q=${encodeURIComponent(q)}${inactive ? '&include_inactive=true' : ''}`);
  S.clients = clients.filter(c => c.active);
  if (risk) clients = clients.filter(c => risk === 'attention' ? ['slipping', 'at_risk', 'lapsed'].includes(c.risk) : c.risk === risk);
  $('clients-sub').textContent = `${clients.length} client${clients.length === 1 ? '' : 's'}`;
  const div = $('clients-list');
  if (!clients.length) { div.innerHTML = '<div class="card empty">No clients found.</div>'; return; }
  div.innerHTML = `<table class="clients-table"><thead><tr><th>Client</th><th>Contact</th><th>Package</th><th>Status</th><th class="num">Sessions left</th><th>Package ends</th><th class="num">Paid</th><th class="num">Owed</th><th></th></tr></thead><tbody>` +
    clients.map(c => { const soon = c.package_end && (parseISO(c.package_end) - new Date()) < 7 * 864e5; return `<tr class="clickable" onclick="openClientDetail(${c.id})">
      <td><div class="who">${avatar(c.name)}<div><strong>${esc(c.name)}</strong>${c.health_notes ? ' <span class="chip chip-bad" title="' + esc(c.health_notes) + '">health</span>' : ''}<div class="tiny">${riskBadge(c)}</div></div></div></td>
      <td>${esc(c.phone)}<div class="tiny muted">${esc(c.email || '')}</div></td>
      <td>${c.package_name ? esc(c.package_name) : '<span class="muted">Pay per session</span>'}</td>
      <td>${clientStatus(c)}</td>
      <td class="num">${c.sessions_remaining ? `<strong>${c.sessions_remaining}</strong>` : '<span class="muted">—</span>'}</td>
      <td>${c.package_end ? `<span${soon ? ' style="color:var(--bad);font-weight:600"' : ''}>${fmtDate(c.package_end)}</span>` : '<span class="muted">—</span>'}</td>
      <td class="num">${money(c.total_spent)}</td>
      <td class="num">${c.outstanding > 0 ? `<strong style="color:var(--bad)">${money(c.outstanding)}</strong>` : '<span class="muted">—</span>'}</td>
      <td class="num nowrap"><button class="btn btn-secondary btn-xs" onclick="event.stopPropagation();openClientDetail(${c.id})">View profile</button></td></tr>`; }).join('') + '</tbody></table>';
}

// Initials in a colour picked from the name: the same client always gets the same colour.
function avatar(name, size = '') {
  const n = String(name || '?').trim(), hue = [...n].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) % 360, 7);
  const ini = n.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
  return `<span class="avatar ${size}" style="--h:${hue}" aria-hidden="true">${esc(ini)}</span>`;
}
// Active = still coming: a package with sessions left, a booking ahead, or a visit in the last 30 days.
function clientIsActive(c) { return c.active && (c.sessions_remaining > 0 || !!c.next_visit || (c.days_since_last !== null && c.days_since_last !== undefined && c.days_since_last <= 30)); }
function clientStatus(c) { return clientIsActive(c) ? '<span class="badge badge-active">Active</span>' : '<span class="badge badge-neutral" title="No package left, nothing booked and no visit in 30 days">Inactive</span>'; }
const ICO = {
  mail: '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>',
  phone: '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z"/></svg>',
  card: '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>',
};
// Body composition: latest value, the check-in date, and whether it moved the right way since the one before.
function bodyCards(ms) {
  const cards = [['weight_kg', 'Weight', 'kg', true], ['body_fat_pct', 'Body fat', '%', true], ['muscle_kg', 'Muscle', 'kg', false], ['waist_cm', 'Waist', 'cm', true]]
    .map(([k, label, unit, lowerIsBetter]) => {
      const withK = ms.filter(m => m[k] !== null && m[k] !== undefined); // newest first
      if (!withK.length) return '';
      const cur = withK[0][k], prev = withK[1] ? withK[1][k] : null;
      const tag = prev === null || cur === prev ? ['badge-neutral', prev === null ? 'First' : 'Steady'] : ((cur < prev) === lowerIsBetter ? ['badge-active', 'Good'] : ['badge-queued', 'Watch']);
      return `<div class="body-card"><div class="body-card-head"><span>${label}</span><span class="badge ${tag[0]}">${tag[1]}</span></div>
        <div class="body-card-value">${Number(cur).toLocaleString('en', { maximumFractionDigits: 1 })}<small> ${unit}</small></div>
        <div class="tiny muted">${fmtDate(withK[0].measured_at)} · check-in${prev !== null && cur !== prev ? ` · ${cur > prev ? '+' : ''}${(cur - prev).toFixed(1)} ${unit}` : ''}</div></div>`;
    }).join('');
  return cards ? `<div class="section-label">Body composition</div><div class="body-cards">${cards}</div>` : `<div class="section-label">Body composition</div><div class="empty small">No check-ins yet. Add one in the Progress tab.</div>`;
}

/* ---------- profile ---------- */
const MEASURE_FIELDS = [
  ['weight_kg', 'Weight', 'kg'], ['body_fat_pct', 'Body fat', '%'], ['muscle_kg', 'Muscle', 'kg'], ['waist_cm', 'Waist', 'cm'],
  ['hips_cm', 'Hips', 'cm'], ['chest_cm', 'Chest', 'cm'], ['arm_cm', 'Arm', 'cm'], ['thigh_cm', 'Thigh', 'cm'],
];
const NOTE_KINDS = { note: 'Note', call: 'Call', whatsapp: 'WhatsApp', visit: 'Visit', email: 'Email', injury: 'Injury / health' };
let CD = null; // the open client's history

async function openClientDetail(id, tab) {
  const h = await api('GET', `/clients/${id}/history`);
  CD = h;
  const c = h.client;
  $('cd-title').innerHTML = `<span class="muted" style="font-weight:500">Clients /</span> ${esc(c.name)}${c.active ? '' : ' <span class="chip">archived</span>'}`;
  const upcoming = h.appointments.filter(a => ['scheduled', 'confirmed'].includes(a.status) && parseISO(a.start_time) > new Date()).reverse();
  const past = h.appointments.filter(a => !upcoming.includes(a));
  const r = RISK[c.risk] || RISK.new;
  $('cd-body').innerHTML = `<div class="cd-layout">
    <aside class="cd-side">
      ${avatar(c.name, 'xl')}
      <h2 class="cd-name">${esc(c.name)}</h2>
      <div class="cd-badges">${clientStatus(c)} ${riskBadge(c)}</div>
      <div class="cd-contact">
        <div>${ICO.mail}<span>${c.email ? `<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>` : '<span class="muted">No email</span>'}</span></div>
        <div>${ICO.phone}<span><a href="tel:${esc(c.phone)}">${esc(c.phone)}</a></span></div>
        <div class="clickable" onclick="cdGo('subs')">${ICO.card}<span>${c.package_name ? `${esc(c.package_name)}<div class="tiny muted">${c.sessions_remaining} session${c.sessions_remaining === 1 ? '' : 's'} left${c.package_end ? ' · until ' + fmtDate(c.package_end) : ''}</div>` : '<span class="muted">No active package</span>'}</span></div>
      </div>
      <div class="section-label">Assigned staff</div>
      ${c.main_trainer ? `<div class="cd-staff">${avatar(c.main_trainer)}<div><div class="tiny muted">Coach</div><strong>${esc(c.main_trainer)}</strong></div></div>` : '<div class="tiny muted">No trainer yet</div>'}
      <div class="section-label">Client since</div>
      <div class="small">${fmtDate(c.created_at)}${c.source ? ' · ' + esc(c.source) : ''}</div>
      ${c.health_notes ? `<div class="health-flag" style="margin-top:14px"><strong>Health &amp; restrictions</strong><div>${esc(c.health_notes)}</div></div>` : ''}
    </aside>
    <div class="cd-main">
    <div class="tabs tabs-scroll">
      <button class="tab" data-t="overview" onclick="cdTab('overview', this)">Overview</button>
      <button class="tab" data-t="appts" onclick="cdTab('appts', this)">Sessions (${h.appointments.length})</button>
      <button class="tab" data-t="progress" onclick="cdTab('progress', this)">Progress (${h.measurements.length + (h.photos || []).length})</button>
      <button class="tab" data-t="notes" onclick="cdTab('notes', this)">Notes &amp; contact (${h.notes.length})</button>
      <button class="tab" data-t="subs" onclick="cdTab('subs', this)">Packages (${h.subscriptions.length})</button>
      <button class="tab" data-t="pays" onclick="cdTab('pays', this)">Payments (${h.payments.length})</button>
      <button class="tab" data-t="msgs" onclick="cdTab('msgs', this)">Messages (${h.messages.length})</button>
    </div>
    <div id="cd-overview" class="subpanel">
    <div class="grid grid-4 mb">
      <div class="stat clickable" role="button" tabindex="0" onclick="cdGo('appts')"><div class="stat-label">Sessions done</div><div class="stat-value">${c.completed_appointments}</div><div class="stat-sub">${c.no_shows} no-shows · ${c.late_count || 0} late${c.attendance_rate !== null && c.attendance_rate !== undefined ? ` · ${c.attendance_rate}% attended` : ''}</div></div>
      <div class="stat clickable" role="button" tabindex="0" onclick="cdGo('pays')"><div class="stat-label">Total paid</div><div class="stat-value">${money(c.total_spent)}</div><div class="stat-sub">${c.outstanding > 0 ? `<span style="color:var(--bad)">owes ${money(c.outstanding)}</span>` : 'nothing owed'}</div></div>
      <div class="stat clickable" role="button" tabindex="0" onclick="cdGo('subs')"><div class="stat-label">Package left</div><div class="stat-value">${c.sessions_remaining}</div><div class="stat-sub">sessions</div></div>
      <div class="stat clickable" role="button" tabindex="0" onclick="cdGo('appts')"><div class="stat-label">Regularity</div><div class="stat-value" style="font-size:1.1rem">${r.label}</div><div class="stat-sub">${c.days_since_last !== null && c.days_since_last !== undefined ? `last ${c.days_since_last}d ago` : 'no sessions yet'}${c.avg_gap_days ? ` · usually every ${Math.round(c.avg_gap_days)}d` : ''}</div></div>
    </div>
    ${bodyCards(h.measurements)}
    <div class="section-label">Next sessions</div>
    ${upcoming.length ? apptTable(upcoming.slice(0, 3), { withDate: true }) : '<div class="empty small">Nothing booked.</div>'}
    <dl class="kv" style="margin-top:14px"><dt>Notifications</dt><dd>${[c.notify_whatsapp && 'WhatsApp', c.notify_sms && 'SMS', c.notify_email && 'Email'].filter(Boolean).join(', ') || 'none'}</dd>${c.date_of_birth ? `<dt>Birthday</dt><dd>${esc(c.date_of_birth)}</dd>` : ''}${c.notes ? `<dt>Notes</dt><dd>${esc(c.notes)}</dd>` : ''}</dl>
    </div>
    <div id="cd-appts" class="subpanel">${cdAdd(`openBookingModal(null, {clientId:${c.id}})`, '+ Book session')}${upcoming.length ? '<div class="agenda-day">Upcoming</div>' + apptTable(upcoming, { withDate: true }) : ''}${past.length ? '<div class="agenda-day">History</div>' + apptTable(past, { withDate: true }) : ''}${!h.appointments.length ? '<div class="empty small">No sessions yet.</div>' : ''}</div>
    <div id="cd-progress" class="subpanel">${progressPanel(h)}</div>
    <div id="cd-notes" class="subpanel">${notesPanel(h)}</div>
    <div id="cd-subs" class="subpanel">${cdAdd(`openSubscriptionModal(null, ${c.id})`, '+ Sell package')}${subsTable(h.subscriptions)}</div>
    <div id="cd-pays" class="subpanel">${cdAdd(`openPaymentModal({client_id:${c.id}})`, '+ Record payment')}${paymentsTable(h.payments, true)}</div>
    <div id="cd-msgs" class="subpanel">${messagesTable(h.messages, true)}</div>
    </div></div>`;
  const start = document.querySelector(`#cd-body .tab[data-t="${tab || 'overview'}"]`);
  cdTab(tab || 'overview', start);
  $('cd-footer').innerHTML = `<div class="left"><button class="btn btn-secondary btn-sm" onclick="editClient(${c.id})">Edit</button><button class="btn btn-danger btn-sm" onclick="deleteClient(${c.id}, ${jsArg(c.name)})">Delete</button><button class="btn btn-secondary btn-sm" onclick="openCustomMessageModal(${c.id})">Message</button><button class="btn btn-secondary btn-sm" onclick="openClientLink(${c.id}, ${jsArg(c.name)})">Client link</button><button class="btn btn-secondary btn-sm" onclick="openPaymentModal({client_id:${c.id}})">Record payment</button><button class="btn btn-secondary btn-sm" onclick="openSubscriptionModal(null, ${c.id})">Sell package</button></div><button class="btn btn-primary" onclick="openBookingModal(null, {clientId:${c.id}})">Book session</button>`;
  openModal('client-detail-modal');
}
function cdAdd(onclick, label) { return `<div class="cd-add"><button class="btn btn-secondary btn-sm" onclick="${onclick}">${label}</button></div>`; }
function cdGo(t) { cdTab(t, document.querySelector(`#cd-body .tab[data-t="${t}"]`)); }
function cdTab(t, el) {
  document.querySelectorAll('#cd-body .tab').forEach(x => x.classList.remove('active')); if (el) el.classList.add('active');
  document.querySelectorAll('#cd-body .subpanel').forEach(p => p.classList.toggle('active', p.id === 'cd-' + t));
  if (t === 'progress') { drawProgressChart(); loadPhotos(); }
}

function fmtNum(v, unit) { return v === null || v === undefined ? '<span class="muted">—</span>' : `${Number(v).toLocaleString('en', { maximumFractionDigits: 1 })}<span class="tiny muted"> ${unit}</span>`; }
function delta(cur, first, unit, lowerIsBetter = true) {
  if (cur === null || cur === undefined || first === null || first === undefined || cur === first) return '';
  const d = cur - first, good = lowerIsBetter ? d < 0 : d > 0;
  return `<span class="delta ${good ? 'good' : 'bad'}">${d > 0 ? '+' : ''}${d.toFixed(1)} ${unit}</span>`;
}

function progressPanel(h) {
  const ms = h.measurements; // newest first
  const latest = ms[0], first = ms[ms.length - 1];
  const firstOf = k => { for (let i = ms.length - 1; i >= 0; i--) if (ms[i][k] !== null && ms[i][k] !== undefined) return ms[i][k]; return null; };
  const latestOf = k => { for (const m of ms) if (m[k] !== null && m[k] !== undefined) return m[k]; return null; };
  const summary = ms.length ? `<div class="grid grid-4 mb">${[['weight_kg', 'Weight', 'kg', true], ['body_fat_pct', 'Body fat', '%', true], ['muscle_kg', 'Muscle', 'kg', false], ['waist_cm', 'Waist', 'cm', true]].map(([k, l, u, low]) =>
      { const d = delta(latestOf(k), firstOf(k), u, low); return `<div class="stat"><div class="stat-label">${l}</div><div class="stat-value" style="font-size:1.25rem">${fmtNum(latestOf(k), u)}</div><div class="stat-sub">${d ? d + ' since ' + fmtDate(first.measured_at) : latestOf(k) === null ? 'not measured yet' : 'no change yet'}</div></div>`; }).join('')}</div>
      <div class="card mb" style="padding:14px"><div class="card-title" style="margin-bottom:6px">Weight &amp; body fat over time</div><div id="cd-progress-chart" class="chart"></div></div>` : '';
  const form = `<details class="add-box" ${ms.length ? '' : 'open'}><summary>+ Add measurements</summary>
    <div class="measure-grid">
      <div class="form-group"><label>Date</label><input type="date" id="ms-date" class="input" value="${todayKey()}"></div>
      ${MEASURE_FIELDS.map(([k, l, u]) => `<div class="form-group"><label>${l} (${u})</label><input type="number" step="0.1" min="0" inputmode="decimal" id="ms-${k}" class="input"></div>`).join('')}
    </div>
    <div class="form-group"><label>Notes</label><input type="text" id="ms-notes" class="input" placeholder="e.g. measured on InBody, after breakfast"></div>
    <button class="btn btn-primary btn-sm" onclick="saveMeasurement(${h.client.id})">Save measurements</button></details>`;
  const table = ms.length ? `<div class="table-wrap mt"><table><thead><tr><th>Date</th>${MEASURE_FIELDS.map(([, l]) => `<th class="num">${l}</th>`).join('')}<th></th></tr></thead><tbody>${
    ms.map(m => `<tr><td>${fmtDate(m.measured_at)}${m.notes ? `<div class="tiny muted">${esc(m.notes)}</div>` : ''}</td>${MEASURE_FIELDS.map(([k, , u]) => `<td class="num">${fmtNum(m[k], u)}</td>`).join('')}
      <td class="num"><button class="btn btn-ghost btn-xs" title="Delete" aria-label="Delete measurement" onclick="deleteMeasurement(${m.id}, ${h.client.id})">✕</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty small">No measurements yet. Add the first check-in to start tracking progress.</div>';
  return summary + form + table + photosSection(h);
}

/* ---------- before / after photos (only with the client's consent) ---------- */
const POSES = { front: 'Front', side: 'Side', back: 'Back', other: 'Other' };
function photosSection(h) {
  const c = h.client, ph = h.photos || [];
  const head = `<div class="card-title mt" style="margin-bottom:8px">Before &amp; after photos</div>`;
  if (!c.photo_consent) return head + `<div class="consent-box"><p><strong>No consent recorded.</strong> Photos can only be kept once the client agrees. Ask them first, then tick the box.</p>
    <label class="check"><input type="checkbox" onchange="if(this.checked) setPhotoConsent(${c.id}, true)"> The client agreed to progress photos being taken and kept privately in this app</label></div>`;
  // Compare the earliest and latest photo of the same pose
  const pairs = Object.keys(POSES).map(k => { const list = ph.filter(p => p.pose === k); return list.length > 1 ? [k, list[list.length - 1], list[0]] : null; }).filter(Boolean);
  const compare = pairs.length ? `<div class="compare">${pairs.map(([k, before, after]) => `<div class="compare-pair"><div class="tiny muted bold">${POSES[k]}</div><div class="compare-imgs">
      <figure><img data-photo="${before.id}" alt="${POSES[k]} before, ${fmtDate(before.taken_at)}"><figcaption>Before · ${fmtDate(before.taken_at)}</figcaption></figure>
      <figure><img data-photo="${after.id}" alt="${POSES[k]} latest, ${fmtDate(after.taken_at)}"><figcaption>Latest · ${fmtDate(after.taken_at)}</figcaption></figure></div></div>`).join('')}</div>` : '';
  const upload = `<details class="add-box" ${ph.length ? '' : 'open'}><summary>+ Add photo</summary><div class="measure-grid">
      <div class="form-group"><label>Photo</label><input type="file" id="ph-file" class="input" accept="image/jpeg,image/png,image/webp,image/heic,image/heif"></div>
      <div class="form-group"><label>Pose</label><select id="ph-pose" class="input">${Object.entries(POSES).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}</select></div>
      <div class="form-group"><label>Date</label><input type="date" id="ph-date" class="input" value="${todayKey()}"></div></div>
      <div class="form-group"><label>Notes</label><input type="text" id="ph-notes" class="input" placeholder="e.g. Week 1, morning, same lighting"></div>
      <button class="btn btn-primary btn-sm" id="ph-save" onclick="uploadPhoto(${c.id})">Upload photo</button></details>`;
  const grid = ph.length ? `<div class="photo-grid">${ph.map(p => `<figure class="photo"><img data-photo="${p.id}" alt="${POSES[p.pose] || p.pose}, ${fmtDate(p.taken_at)}" loading="lazy">
      <figcaption><span>${POSES[p.pose] || p.pose} · ${fmtDate(p.taken_at)}</span><button class="btn btn-ghost btn-xs" aria-label="Delete photo" title="Delete" onclick="deletePhoto(${p.id}, ${c.id})">✕</button></figcaption>${p.notes ? `<div class="tiny muted">${esc(p.notes)}</div>` : ''}</figure>`).join('')}</div>`
    : '<div class="empty small">No photos yet.</div>';
  const consent = `<div class="tiny muted mt">Consent recorded ${c.photo_consent_at ? fmtDate(c.photo_consent_at) : ''}. <a href="#" onclick="setPhotoConsent(${c.id}, false);return false">Withdraw consent and delete all photos</a></div>`;
  return head + compare + upload + grid + consent;
}

const _photoURLs = {};
async function loadPhotos() {
  for (const img of document.querySelectorAll('#cd-body img[data-photo]')) {
    const id = img.dataset.photo;
    try {
      if (!_photoURLs[id]) { const r = await fetch(`${API}/clients/photos/${id}/file`, { headers: { Authorization: `Bearer ${S.token}` } }); if (!r.ok) continue; _photoURLs[id] = URL.createObjectURL(await r.blob()); }
      img.src = _photoURLs[id];
    } catch (e) { /* leave the frame empty */ }
  }
}
async function uploadPhoto(clientId) {
  guard(async () => {
    const f = $('ph-file').files[0]; if (!f) throw new Error('Choose a photo first');
    const fd = new FormData(); fd.append('file', f); fd.append('pose', val('ph-pose'));
    const d = val('ph-date'); if (d) fd.append('taken_at', zonedToDate(d, '09:00').toISOString());
    if (val('ph-notes').trim()) fd.append('notes', val('ph-notes').trim());
    $('ph-save').disabled = true;
    try {
      const r = await fetch(`${API}/clients/${clientId}/photos`, { method: 'POST', headers: { Authorization: `Bearer ${S.token}` }, body: fd });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Upload failed');
    } finally { $('ph-save').disabled = false; }
    toast('Photo saved'); openClientDetail(clientId, 'progress');
  });
}
async function deletePhoto(id, clientId) {
  if (!await ask('Delete this photo? It is removed for good.')) return;
  guard(async () => { await api('DELETE', `/clients/photos/${id}`); openClientDetail(clientId, 'progress'); });
}
async function setPhotoConsent(clientId, on) {
  if (!on && !await ask('Withdraw consent? All of this client\'s progress photos will be deleted for good.')) return;
  guard(async () => { await api('PUT', `/clients/${clientId}`, { photo_consent: on }); toast(on ? 'Consent recorded' : 'Consent withdrawn, photos deleted'); openClientDetail(clientId, 'progress'); });
}

function drawProgressChart() {
  const el = $('cd-progress-chart'); if (!el || !CD) return;
  const ms = [...CD.measurements].reverse().filter(m => m.weight_kg || m.body_fat_pct);
  if (ms.length < 2) { el.innerHTML = '<div class="tiny muted">Add a second check-in to see the trend.</div>'; return; }
  const W = Math.max(300, el.clientWidth || 600), H = 170, padL = 36, padR = 36, padT = 12, padB = 24, iw = W - padL - padR, ih = H - padT - padB;
  const t0 = parseISO(ms[0].measured_at).getTime(), t1 = parseISO(ms[ms.length - 1].measured_at).getTime() || t0 + 1;
  const x = m => padL + iw * (parseISO(m.measured_at).getTime() - t0) / Math.max(t1 - t0, 1);
  const scale = vals => { const v = vals.filter(n => n !== null && n !== undefined); if (!v.length) return null; let lo = Math.min(...v), hi = Math.max(...v); if (hi - lo < 1) { lo -= 1; hi += 1; } const pad = (hi - lo) * .15; return { lo: lo - pad, hi: hi + pad }; };
  const sw = scale(ms.map(m => m.weight_kg)), sf = scale(ms.map(m => m.body_fat_pct));
  const y = (v, s) => padT + ih * (s.hi - v) / (s.hi - s.lo);
  const path = (k, s) => ms.filter(m => m[k] !== null && m[k] !== undefined).map((m, i) => `${i ? 'L' : 'M'}${x(m).toFixed(1)},${y(m[k], s).toFixed(1)}`).join(' ');
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Weight and body fat over time">`;
  [0, .5, 1].forEach(f => { const yy = padT + ih * f; svg += `<line class="axis" x1="${padL}" x2="${W - padR}" y1="${yy}" y2="${yy}" stroke-dasharray="2 3"/>`;
    if (sw) svg += `<text class="lbl" x="${padL - 5}" y="${yy + 3}" text-anchor="end">${(sw.hi - (sw.hi - sw.lo) * f).toFixed(0)}</text>`;
    if (sf) svg += `<text class="lbl" x="${W - padR + 5}" y="${yy + 3}">${(sf.hi - (sf.hi - sf.lo) * f).toFixed(0)}%</text>`; });
  if (sw) { svg += `<path d="${path('weight_kg', sw)}" fill="none" stroke="var(--series-1)" stroke-width="2.4"/>`; ms.forEach(m => { if (m.weight_kg) svg += `<circle cx="${x(m)}" cy="${y(m.weight_kg, sw)}" r="3.5" fill="var(--surface)" stroke="var(--series-1)" stroke-width="2"><title>${fmtDate(m.measured_at)}: ${m.weight_kg} kg</title></circle>`; }); }
  if (sf) { svg += `<path d="${path('body_fat_pct', sf)}" fill="none" stroke="var(--series-4)" stroke-width="2" stroke-dasharray="5 4"/>`; ms.forEach(m => { if (m.body_fat_pct) svg += `<circle cx="${x(m)}" cy="${y(m.body_fat_pct, sf)}" r="3" fill="var(--series-4)"><title>${fmtDate(m.measured_at)}: ${m.body_fat_pct}% fat</title></circle>`; }); }
  svg += `<text class="lbl" x="${padL}" y="${H - 6}">${fmtDate(ms[0].measured_at)}</text><text class="lbl" x="${W - padR}" y="${H - 6}" text-anchor="end">${fmtDate(ms[ms.length - 1].measured_at)}</text></svg>`;
  el.innerHTML = svg + `<div class="legend"><span style="--c:var(--series-1)">Weight (kg, left)</span><span style="--c:var(--series-4)">Body fat (%, right)</span></div>`;
}

async function saveMeasurement(clientId) {
  guard(async () => {
    const body = { notes: val('ms-notes').trim() || null };
    const d = val('ms-date'); if (d) body.measured_at = zonedToDate(d, '09:00').toISOString();
    MEASURE_FIELDS.forEach(([k]) => { const v = val('ms-' + k); if (v !== '') body[k] = Number(v); });
    if (!MEASURE_FIELDS.some(([k]) => body[k] !== undefined)) throw new Error('Enter at least one measurement');
    await api('POST', `/clients/${clientId}/measurements`, body);
    toast('Measurements saved'); openClientDetail(clientId, 'progress');
  });
}
async function deleteMeasurement(id, clientId) {
  if (!await ask('Delete this check-in? This cannot be undone.')) return;
  guard(async () => { await api('DELETE', `/clients/measurements/${id}`); openClientDetail(clientId, 'progress'); });
}

function notesPanel(h) {
  const form = `<div class="note-form">
    <select id="note-kind" class="input" aria-label="Type">${Object.entries(NOTE_KINDS).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}</select>
    <textarea id="note-text" class="input" placeholder="What happened? e.g. Called about renewal, will decide next week" aria-label="Note"></textarea>
    <button class="btn btn-primary btn-sm" onclick="saveNote(${h.client.id})">Add to log</button></div>`;
  const list = h.notes.length ? `<div class="timeline">${h.notes.map(n => `<div class="tl-item kind-${n.kind}"><div class="tl-head"><span class="chip">${NOTE_KINDS[n.kind] || n.kind}</span><span class="tiny muted">${fmtDT(n.created_at)}${n.author ? ' · ' + esc(n.author) : ''}</span>
      <button class="btn btn-ghost btn-xs" style="margin-left:auto" title="Delete" aria-label="Delete note" onclick="deleteNote(${n.id}, ${h.client.id})">✕</button></div><div class="tl-text">${esc(n.text)}</div></div>`).join('')}</div>`
    : '<div class="empty small">No notes yet. Log calls, chats, visits and trainer observations here.</div>';
  return form + list;
}
async function saveNote(clientId) {
  guard(async () => {
    const text = val('note-text').trim(); if (!text) throw new Error('Write the note first');
    await api('POST', `/clients/${clientId}/notes`, { kind: val('note-kind'), text });
    toast('Added to the log'); openClientDetail(clientId, 'notes');
  });
}
async function deleteNote(id, clientId) {
  if (!await ask('Delete this note? This cannot be undone.')) return;
  guard(async () => { await api('DELETE', `/clients/notes/${id}`); openClientDetail(clientId, 'notes'); });
}

/* ---------- add / edit ---------- */
function openClientModal() {
  $('client-modal-title').textContent = 'Add client';
  ['client-id', 'client-name', 'client-phone', 'client-email', 'client-notes', 'client-dob', 'client-health'].forEach(i => setVal(i, ''));
  setVal('client-source', 'walk-in'); setVal('client-active', 'true');
  fillSelect('client-referrer', '<option value="">—</option>' + clientOptions()); setVal('client-referrer', '');
  $('client-nwa').checked = true; $('client-nsms').checked = false; $('client-nemail').checked = true;
  openModal('client-modal');
}
async function editClient(id) {
  const c = S.clients.find(x => x.id === id) || await api('GET', `/clients/${id}`);
  openClientModal();
  $('client-modal-title').textContent = 'Edit client';
  setVal('client-id', c.id); setVal('client-name', c.name); setVal('client-phone', c.phone); setVal('client-email', c.email); setVal('client-notes', c.notes);
  setVal('client-dob', c.date_of_birth); setVal('client-source', c.source || ''); setVal('client-active', String(c.active)); setVal('client-health', c.health_notes);
  setVal('client-referrer', c.referred_by_client_id || '');
  $('client-nwa').checked = c.notify_whatsapp; $('client-nsms').checked = c.notify_sms; $('client-nemail').checked = c.notify_email;
}
async function saveClient() {
  guard(async () => {
    const id = val('client-id');
    const payload = { name: val('client-name').trim(), phone: val('client-phone').trim(), email: val('client-email').trim() || null, notes: val('client-notes') || null,
      date_of_birth: val('client-dob') || null, source: val('client-source') || null, active: val('client-active') === 'true',
      health_notes: val('client-health').trim() || null,
      referred_by_client_id: val('client-referrer') && +val('client-referrer') !== +id ? +val('client-referrer') : null,
      notify_whatsapp: $('client-nwa').checked, notify_sms: $('client-nsms').checked, notify_email: $('client-nemail').checked };
    if (!payload.name || !payload.phone) throw new Error('Name and phone are required');
    if (id) await api('PUT', `/clients/${id}`, payload); else await api('POST', '/clients/', payload);
    closeModal('client-modal'); toast('Client saved'); await refreshLookups(); refreshCurrent();
  });
}

// The client's private page: their bookings, packages, payments, invoices and progress. Anyone with the link can see it.
async function openClientLink(id, name, fresh = false) {
  guard(async () => {
    const r = await api('POST', `/clients/${id}/portal-link${fresh ? '?new=true' : ''}`);
    const url = location.origin + r.path;
    const text = `Hi ${name.split(' ')[0]}, here is your personal ${S.business} page with your sessions, package, payments and progress: ${url}`;
    const wa = `https://wa.me/${(r.phone || '').replace(/\D/g, '')}?text=${encodeURIComponent(text)}`;
    confirmBox('Client link', `<p class="small muted" style="margin-top:0">Send this to ${esc(name)}. They open it on their phone, no password needed, and see their sessions, package, payments, invoices and progress. Staff notes, health notes and photos are never shown.</p>
      <input class="input mono small" readonly value="${esc(url)}" onclick="this.select()">
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"><a class="btn btn-success btn-sm" href="${esc(wa)}" target="_blank" rel="noopener">Send on WhatsApp</a>
      <button class="btn btn-ghost btn-sm" onclick="openClientLink(${id}, ${jsArg(name)}, true)">Make a new link (old one stops working)</button></div>`,
      'Copy link', async () => { await navigator.clipboard.writeText(url); toast('Link copied'); });
  });
}

async function deleteClient(id, name) {
  if (!await ask(`Delete ${name}?\n\nA client who has paid is archived instead, so their payments stay in your revenue reports. A client with no payments is removed permanently with their sessions, packages, measurements, notes and messages.`)) return;
  guard(async () => {
    const r = await api('DELETE', `/clients/${id}`);
    closeModal('client-detail-modal'); toast(r && r.archived ? 'Client archived (they have payments)' : 'Client deleted'); await refreshLookups(); refreshCurrent();
  });
}
