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
  div.innerHTML = `<table><thead><tr><th>Client</th><th>Contact</th><th>Status</th><th class="num">Sessions</th><th class="num">Package left</th><th class="num">Spent</th><th>Last visit</th><th>Next visit</th><th></th></tr></thead><tbody>` +
    clients.map(c => `<tr class="clickable" onclick="openClientDetail(${c.id})">
      <td><strong>${esc(c.name)}</strong>${!c.active ? ' <span class="chip">inactive</span>' : ''}${c.health_notes ? ' <span class="chip chip-bad" title="' + esc(c.health_notes) + '">health</span>' : ''}<div class="tiny muted">${esc(c.source || '')}${c.no_shows ? ` · ${c.no_shows} no-show${c.no_shows > 1 ? 's' : ''}` : ''}</div></td>
      <td>${esc(c.phone)}<div class="tiny muted">${esc(c.email || '')}</div></td>
      <td>${riskBadge(c)}${c.days_since_last !== null && c.days_since_last !== undefined ? `<div class="tiny muted">${c.days_since_last}d ago${c.avg_gap_days ? ` · every ~${Math.round(c.avg_gap_days)}d` : ''}</div>` : ''}</td>
      <td class="num">${c.completed_appointments}</td>
      <td class="num">${c.sessions_remaining ? `<strong>${c.sessions_remaining}</strong>` : '<span class="muted">—</span>'}</td>
      <td class="num">${money(c.total_spent)}${c.outstanding > 0 ? `<div class="tiny" style="color:var(--bad)">owes ${money(c.outstanding)}</div>` : ''}</td>
      <td>${c.last_visit ? fmtDate(c.last_visit) : '<span class="muted">—</span>'}</td>
      <td>${c.next_visit ? fmtDT(c.next_visit) : '<span class="muted">—</span>'}</td>
      <td class="num"><button class="btn btn-primary btn-xs" onclick="event.stopPropagation();openBookingModal(null, {clientId:${c.id}})">Book</button></td></tr>`).join('') + '</tbody></table>';
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
  $('cd-title').innerHTML = `${esc(c.name)} ${riskBadge(c)} ${c.active ? '' : '<span class="chip">inactive</span>'}`;
  const upcoming = h.appointments.filter(a => ['scheduled', 'confirmed'].includes(a.status) && parseISO(a.start_time) > new Date()).reverse();
  const past = h.appointments.filter(a => !upcoming.includes(a));
  const r = RISK[c.risk] || RISK.new;
  $('cd-body').innerHTML = `
    ${c.health_notes ? `<div class="health-flag"><strong>Health &amp; restrictions</strong><div>${esc(c.health_notes)}</div></div>` : ''}
    <div class="grid grid-4 mb">
      <div class="stat"><div class="stat-label">Sessions done</div><div class="stat-value">${c.completed_appointments}</div><div class="stat-sub">${c.no_shows} no-shows · ${c.late_count || 0} late${c.attendance_rate !== null && c.attendance_rate !== undefined ? ` · ${c.attendance_rate}% attended` : ''}</div></div>
      <div class="stat"><div class="stat-label">Total spent</div><div class="stat-value">${money(c.total_spent)}</div><div class="stat-sub">${c.outstanding > 0 ? `<span style="color:var(--bad)">owes ${money(c.outstanding)}</span>` : 'nothing owed'}</div></div>
      <div class="stat"><div class="stat-label">Package left</div><div class="stat-value">${c.sessions_remaining}</div><div class="stat-sub">sessions</div></div>
      <div class="stat"><div class="stat-label">Regularity</div><div class="stat-value" style="font-size:1.1rem">${r.label}</div><div class="stat-sub">${c.days_since_last !== null && c.days_since_last !== undefined ? `last ${c.days_since_last}d ago` : 'no sessions yet'}${c.avg_gap_days ? ` · usually every ${Math.round(c.avg_gap_days)}d` : ''}</div></div>
    </div>
    <dl class="kv mb"><dt>Phone</dt><dd>${esc(c.phone)}</dd><dt>Email</dt><dd>${esc(c.email || '—')}</dd><dt>Client since</dt><dd>${fmtDate(c.created_at)}${c.source ? ' · ' + esc(c.source) : ''}</dd><dt>Notifications</dt><dd>${[c.notify_whatsapp && 'WhatsApp', c.notify_sms && 'SMS', c.notify_email && 'Email'].filter(Boolean).join(', ') || 'none'}</dd>${c.date_of_birth ? `<dt>Birthday</dt><dd>${esc(c.date_of_birth)}</dd>` : ''}${c.notes ? `<dt>Notes</dt><dd>${esc(c.notes)}</dd>` : ''}</dl>
    <div class="tabs tabs-scroll">
      <button class="tab" data-t="appts" onclick="cdTab('appts', this)">Sessions (${h.appointments.length})</button>
      <button class="tab" data-t="progress" onclick="cdTab('progress', this)">Progress (${h.measurements.length + (h.photos || []).length})</button>
      <button class="tab" data-t="notes" onclick="cdTab('notes', this)">Notes &amp; contact (${h.notes.length})</button>
      <button class="tab" data-t="subs" onclick="cdTab('subs', this)">Packages (${h.subscriptions.length})</button>
      <button class="tab" data-t="pays" onclick="cdTab('pays', this)">Payments (${h.payments.length})</button>
      <button class="tab" data-t="msgs" onclick="cdTab('msgs', this)">Messages (${h.messages.length})</button>
    </div>
    <div id="cd-appts" class="subpanel">${upcoming.length ? '<div class="agenda-day">Upcoming</div>' + apptTable(upcoming, { withDate: true }) : ''}${past.length ? '<div class="agenda-day">History</div>' + apptTable(past, { withDate: true }) : ''}${!h.appointments.length ? '<div class="empty small">No sessions yet.</div>' : ''}</div>
    <div id="cd-progress" class="subpanel">${progressPanel(h)}</div>
    <div id="cd-notes" class="subpanel">${notesPanel(h)}</div>
    <div id="cd-subs" class="subpanel">${subsTable(h.subscriptions)}</div>
    <div id="cd-pays" class="subpanel">${paymentsTable(h.payments, true)}</div>
    <div id="cd-msgs" class="subpanel">${messagesTable(h.messages, true)}</div>`;
  const start = document.querySelector(`#cd-body .tab[data-t="${tab || 'appts'}"]`);
  cdTab(tab || 'appts', start);
  $('cd-footer').innerHTML = `<div class="left"><button class="btn btn-secondary btn-sm" onclick="editClient(${c.id})">Edit</button><button class="btn btn-danger btn-sm" onclick="deleteClient(${c.id}, '${esc(c.name).replace(/'/g, "\\'")}')">Delete</button><button class="btn btn-secondary btn-sm" onclick="closeModal('client-detail-modal');openCustomMessageModal(${c.id})">Message</button><button class="btn btn-secondary btn-sm" onclick="closeModal('client-detail-modal');openPaymentModal({client_id:${c.id}})">Record payment</button><button class="btn btn-secondary btn-sm" onclick="closeModal('client-detail-modal');openSubscriptionModal(null, ${c.id})">Sell package</button></div><button class="btn btn-primary" onclick="closeModal('client-detail-modal');openBookingModal(null, {clientId:${c.id}})">Book session</button>`;
  openModal('client-detail-modal');
}
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
  if (!confirm('Delete this photo? It is removed for good.')) return;
  guard(async () => { await api('DELETE', `/clients/photos/${id}`); openClientDetail(clientId, 'progress'); });
}
async function setPhotoConsent(clientId, on) {
  if (!on && !confirm('Withdraw consent? All of this client\'s progress photos will be deleted for good.')) return;
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
  if (!confirm('Delete this check-in? This cannot be undone.')) return;
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
  if (!confirm('Delete this note? This cannot be undone.')) return;
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
  closeModal('client-detail-modal'); openClientModal();
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

async function deleteClient(id, name) {
  if (!confirm(`Delete ${name}?\n\nThis permanently removes the client together with all their sessions, packages, payments, measurements, notes and message history. This cannot be undone.`)) return;
  guard(async () => {
    await api('DELETE', `/clients/${id}`);
    closeModal('client-detail-modal'); toast('Client deleted'); await refreshLookups(); refreshCurrent();
  });
}
