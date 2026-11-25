/* EMS devices and maintenance (Services & Team page) */
const DEV_STATE = {
  overdue: ['badge-cancelled', 'Service overdue'], due_soon: ['badge-queued', 'Service due soon'], ok: ['badge-active', 'Serviced'],
  never: ['badge-neutral', 'No service logged'], no_schedule: ['badge-neutral', 'No schedule'],
};
async function loadDevices() {
  const el = $('devices-list'); if (!el) return;
  const list = await api('GET', '/devices/'); window._devices = list;
  el.innerHTML = list.length ? `<div class="table-wrap"><table><thead><tr><th>Device</th><th>Status</th><th>Service</th><th class="num">Maintenance</th><th></th></tr></thead><tbody>${list.map(d => {
    const [cls, label] = DEV_STATE[d.service_state] || DEV_STATE.no_schedule;
    return `<tr><td><strong>${esc(d.name)}</strong><div class="tiny muted">${[d.model, d.serial_number && 'S/N ' + d.serial_number, d.purchased_on && 'bought ' + fmtKey(d.purchased_on)].filter(Boolean).map(esc).join(' · ')}</div></td>
      <td>${d.status === 'active' ? badge('active') : d.status === 'maintenance' ? '<span class="badge badge-queued">in repair</span>' : '<span class="badge badge-neutral">retired</span>'}</td>
      <td><span class="badge ${cls}">${label}</span><div class="tiny muted">${d.last_service_on ? 'last ' + fmtKey(d.last_service_on) : ''}${d.next_service_due ? ' · next ' + fmtKey(d.next_service_due) : ''}${d.service_every_days ? ` · every ${d.service_every_days} days` : ''}</div></td>
      <td class="num">${d.maintenance_count} · ${money(d.maintenance_cost)}</td>
      <td class="num"><button class="btn btn-success btn-xs" onclick="logMaintenance(${d.id})">Log service</button><button class="btn btn-ghost btn-xs" onclick="deviceHistory(${d.id})">History</button><button class="btn btn-ghost btn-xs" onclick="openDeviceForm(${d.id})">Edit</button></td></tr>`; }).join('')}</tbody></table></div>`
    : '<div class="card empty">No devices yet. Add your EMS machines and suits to get service reminders.</div>';
}
function openDeviceForm(id) {
  const d = id ? (window._devices || []).find(x => x.id === id) : {};
  confirmBox(id ? 'Edit device' : 'Add device', `
    <div class="form-group"><label>Name</label><input id="dv-name" class="input" value="${esc(d.name || '')}" placeholder="e.g. EMS machine 1, Suit M-2"></div>
    <div class="form-row"><div class="form-group"><label>Model</label><input id="dv-model" class="input" value="${esc(d.model || '')}"></div><div class="form-group"><label>Serial number</label><input id="dv-serial" class="input" value="${esc(d.serial_number || '')}"></div></div>
    <div class="form-row"><div class="form-group"><label>Bought on</label><input type="date" id="dv-bought" class="input" value="${esc(d.purchased_on || '')}"></div><div class="form-group"><label>Service every (days)</label><input type="number" min="1" id="dv-every" class="input" value="${d.service_every_days || ''}" placeholder="e.g. 90"></div></div>
    <div class="form-group"><label>Status</label><select id="dv-status" class="input"><option value="active">In use</option><option value="maintenance">In repair</option><option value="retired">Retired</option></select></div>
    <div class="form-group"><label>Notes</label><input id="dv-notes" class="input" value="${esc(d.notes || '')}"></div>
    ${id ? `<button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteDevice(${id})">Delete device</button>` : ''}`, 'Save', async () => {
    const body = { name: val('dv-name').trim(), model: val('dv-model').trim() || null, serial_number: val('dv-serial').trim() || null, purchased_on: val('dv-bought') || null,
      service_every_days: val('dv-every') ? +val('dv-every') : null, status: val('dv-status'), notes: val('dv-notes').trim() || null };
    if (!body.name) throw new Error('Name is required');
    if (id) await api('PUT', `/devices/${id}`, body); else await api('POST', '/devices/', body);
    toast('Device saved'); loadDevices();
  });
  if (d.status) setVal('dv-status', d.status);
}
function logMaintenance(id) {
  const d = (window._devices || []).find(x => x.id === id);
  confirmBox(`Log service: ${esc(d.name)}`, `
    <div class="form-row"><div class="form-group"><label>Date</label><input type="date" id="mt-date" class="input" value="${todayKey()}"></div>
      <div class="form-group"><label>Type</label><select id="mt-kind" class="input"><option value="service">Service</option><option value="inspection">Inspection</option><option value="repair">Repair</option><option value="cleaning">Cleaning</option></select></div></div>
    <div class="form-group"><label>Cost (${esc(S.currency)}, optional)</label><input type="number" min="0" step="0.01" id="mt-cost" class="input"></div>
    <label class="check mb"><input type="checkbox" id="mt-exp" checked> Also add the cost to Expenses (Maintenance)</label>
    <div class="form-group"><label>Notes</label><input id="mt-notes" class="input" placeholder="e.g. electrodes replaced, firmware updated"></div>`, 'Save', async () => {
    const cost = val('mt-cost') ? parseFloat(val('mt-cost')) : null;
    await api('POST', `/devices/${id}/maintenance`, { done_on: val('mt-date'), kind: val('mt-kind'), cost, notes: val('mt-notes').trim() || null, add_expense: !!cost && $('mt-exp').checked });
    toast('Logged'); loadDevices();
  });
}
async function deviceHistory(id) {
  const d = (window._devices || []).find(x => x.id === id);
  const rows = await api('GET', `/devices/${id}/maintenance`);
  confirmBox(`History: ${esc(d.name)}`, rows.length ? `<div class="table-wrap"><table class="plain"><thead><tr><th>Date</th><th>Type</th><th>Notes</th><th class="num">Cost</th></tr></thead><tbody>${rows.map(m => `<tr><td>${fmtKey(m.done_on)}</td><td>${esc(m.kind)}</td><td class="small">${esc(m.notes || '')}</td><td class="num">${m.cost ? money(m.cost) : '—'}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">Nothing logged yet.</p>', 'Close', async () => {});
}
function deleteDevice(id) {
  if (!confirm('Delete this device and its maintenance history? Expenses already recorded stay. This cannot be undone.')) return;
  guard(async () => { await api('DELETE', `/devices/${id}`); document.querySelectorAll('.modal-overlay.active').forEach(m => closeModal(m.id)); toast('Device deleted'); loadDevices(); });
}
