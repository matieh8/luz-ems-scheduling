/* Leads pipeline, conversion by source, referrals */
let LEADS = { tab: 'pipeline', list: [] };
const LEAD_SOURCES = ['instagram', 'whatsapp', 'tiktok', 'facebook', 'google', 'referral', 'walk-in', 'website', 'other'];
const LEAD_STATUS = { new: ['badge-scheduled', 'New'], contacted: ['badge-queued', 'Contacted'], trial_booked: ['badge-confirmed', 'Trial booked'], won: ['badge-active', 'Won'], lost: ['badge-cancelled', 'Lost'] };
const leadBadge = s => { const [c, l] = LEAD_STATUS[s] || ['badge-neutral', s]; return `<span class="badge ${c}">${l}</span>`; };

function leadTab(t, el) {
  LEADS.tab = t; document.querySelectorAll('#page-leads .tab').forEach(x => x.classList.remove('active')); el.classList.add('active');
  document.querySelectorAll('#page-leads .subpanel').forEach(p => p.classList.toggle('active', p.id === 'lead-' + t)); loadLeads();
}

async function loadLeads() {
  if (LEADS.tab === 'report') return loadLeadReport();
  if (LEADS.tab === 'referrals') return loadReferrals();
  const f = val('lead-status');
  let list = await api('GET', `/leads/${f && f !== 'open' && f !== 'month' ? '?status=' + f : ''}`);
  if (f === 'open') list = list.filter(l => ['new', 'contacted', 'trial_booked'].includes(l.status));
  if (f === 'month') { const start = zonedToDate(todayKey().slice(0, 7) + '-01', '00:00'); list = list.filter(l => parseISO(l.created_at) >= start); }  // same as the dashboard's "new leads"
  const today = todayKey(), open = l => !['won', 'lost'].includes(l.status), due = l => open(l) && l.next_follow_up && l.next_follow_up <= today;
  // Due follow-ups first (oldest first), then the next ones by date, then the rest newest first
  list.sort((a, b) => (due(b) - due(a)) || ((a.next_follow_up && open(a) ? 0 : 1) - (b.next_follow_up && open(b) ? 0 : 1))
    || (a.next_follow_up || '').localeCompare(b.next_follow_up || '') || (b.created_at || '').localeCompare(a.created_at || ''));
  LEADS.list = list;
  const nDue = list.filter(due).length;
  $('leads-sub').textContent = `${list.length} lead${list.length === 1 ? '' : 's'}${f === 'open' ? ' to follow up' : ''}${nDue ? ` · ${nDue} follow-up${nDue === 1 ? '' : 's'} due` : ''}`;
  $('leads-list').innerHTML = list.length ? `<div class="table-wrap"><table><thead><tr><th>Name</th><th>Source</th><th>Interested in</th><th>Status</th><th>Follow up</th><th></th></tr></thead><tbody>${list.map(l => `<tr>
    <td><strong>${esc(l.name)}</strong><div class="tiny muted">${esc(l.phone || '')}${l.email ? ' · ' + esc(l.email) : ''}</div></td>
    <td><span class="chip">${esc(l.source)}</span>${l.referred_by_name ? `<div class="tiny muted">by ${esc(l.referred_by_name)}</div>` : ''}</td>
    <td class="small">${esc(l.interest || '')}${l.notes ? `<div class="tiny muted" title="${esc(l.notes)}">${esc(l.notes.trim().split('\n').pop())}</div>` : ''}</td>
    <td>${leadBadge(l.status)}${l.lost_reason ? `<div class="tiny muted">${esc(l.lost_reason)}</div>` : ''}</td>
    <td class="small">${l.next_follow_up ? `<span style="${due(l) ? 'color:var(--bad);font-weight:700' : ''}">${fmtKey(l.next_follow_up)}</span>${due(l) ? ` <span class="chip chip-bad">${l.next_follow_up < today ? 'overdue' : 'today'}</span>` : ''}` : '<span class="muted">—</span>'}</td>
    <td class="num">${l.converted_client_id ? `<button class="btn btn-ghost btn-xs" onclick="openClientDetail(${l.converted_client_id})">Open client</button>`
      : `<button class="btn btn-success btn-xs" onclick="convertLead(${l.id})">Make client</button><button class="btn btn-secondary btn-xs" onclick="logLeadContact(${l.id})">Log contact</button><button class="btn btn-ghost btn-xs" onclick="openLeadForm(${l.id})">Edit</button>`}</td></tr>`).join('')}</tbody></table></div>`
    : '<div class="card empty">No leads here. Add people who message or call you, so nobody slips through.</div>';
}

function openLeadForm(id) {
  const l = id ? LEADS.list.find(x => x.id === id) : { status: 'new', source: 'instagram' };
  confirmBox(id ? 'Edit lead' : 'Add lead', `
    <div class="form-row"><div class="form-group"><label>Name</label><input id="ld-name" class="input" value="${esc(l.name || '')}"></div><div class="form-group"><label>Phone</label><input type="tel" inputmode="tel" id="ld-phone" class="input" value="${esc(l.phone || '')}"></div></div>
    <div class="form-row"><div class="form-group"><label>Came from</label><select id="ld-source" class="input">${LEAD_SOURCES.map(s => `<option ${s === l.source ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      <div class="form-group"><label>Referred by (if a client sent them)</label><select id="ld-ref" class="input"><option value="">—</option>${clientOptions(l.referred_by_client_id)}</select></div></div>
    <div class="form-group"><label>Interested in</label><input id="ld-interest" class="input" value="${esc(l.interest || '')}" placeholder="e.g. weight loss, back pain, 10-session pack"></div>
    <div class="form-row"><div class="form-group"><label>Status</label><select id="ld-status" class="input">${Object.entries(LEAD_STATUS).map(([k, [, t]]) => `<option value="${k}" ${k === l.status ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
      <div class="form-group"><label>Next follow-up</label><input type="date" id="ld-next" class="input" value="${esc(l.next_follow_up || '')}"></div></div>
    <div class="form-group"><label>If lost, why?</label><input id="ld-lost" class="input" value="${esc(l.lost_reason || '')}" placeholder="e.g. too expensive, too far, no time"></div>
    <div class="form-group"><label>Notes</label><textarea id="ld-notes" class="input" style="min-height:70px">${esc(l.notes || '')}</textarea><div class="help">Use "Log contact" to add a dated line each time you speak to them.</div></div>
    ${id ? `<button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteLead(${id})">Delete lead</button>` : ''}`, 'Save', async () => {
    const body = { name: val('ld-name').trim(), phone: val('ld-phone').trim() || null, source: val('ld-source'), interest: val('ld-interest').trim() || null,
      status: val('ld-status'), next_follow_up: val('ld-next') || null, lost_reason: val('ld-lost').trim() || null, notes: val('ld-notes').trim() || null,
      referred_by_client_id: val('ld-ref') ? +val('ld-ref') : null };
    if (!body.name) throw new Error('Enter a name');
    if (id) await api('PUT', `/leads/${id}`, body); else await api('POST', '/leads/', body);
    toast('Lead saved'); loadLeads();
  });
}
// Every call or message is added as a dated line to the notes, with the next follow-up in one step.
function logLeadContact(id) {
  const l = LEADS.list.find(x => x.id === id); if (!l) return;
  confirmBox(`Log contact: ${esc(l.name)}`, `${l.notes ? `<div class="lead-log">${esc(l.notes)}</div>` : ''}
    <div class="form-row"><div class="form-group"><label>How</label><select id="lc-how" class="input"><option>Call</option><option>WhatsApp</option><option>Instagram</option><option>Visit</option><option>Email</option></select></div>
      <div class="form-group"><label>Status now</label><select id="lc-status" class="input">${Object.entries(LEAD_STATUS).map(([k, [, t]]) => `<option value="${k}" ${k === (l.status === 'new' ? 'contacted' : l.status) ? 'selected' : ''}>${t}</option>`).join('')}</select></div></div>
    <div class="form-group"><label>What happened</label><input id="lc-text" class="input" autofocus placeholder="e.g. Interested, wants to try after Eid"></div>
    <div class="form-group"><label>Next follow-up</label><div style="display:flex;gap:6px;flex-wrap:wrap">${[[1, 'Tomorrow'], [3, 'In 3 days'], [7, 'In a week']].map(([d, t]) => `<button type="button" class="btn btn-secondary btn-sm" onclick="setVal('lc-next', addDays(todayKey(), ${d}))">${t}</button>`).join('')}
      <input type="date" id="lc-next" class="input" style="max-width:180px" value="${addDays(todayKey(), 3)}"></div><div class="help">Leave empty for no reminder.</div></div>`, 'Save', async () => {
    const text = val('lc-text').trim(); if (!text) throw new Error('Write what happened');
    const line = `${fmtKey(todayKey())} · ${val('lc-how')}: ${text}`;
    await api('PUT', `/leads/${id}`, { notes: (l.notes ? l.notes.trim() + '\n' : '') + line, status: val('lc-status'), next_follow_up: val('lc-next') || null });
    toast('Contact logged'); loadLeads();
  });
}
function convertLead(id) {
  const l = LEADS.list.find(x => x.id === id);
  confirmBox('Make client', `<p>Turn <strong>${esc(l.name)}</strong> into a client? If a client with the same phone exists, the lead is linked to them.</p>`, 'Make client', async () => {
    const r = await api('POST', `/leads/${id}/convert`); toast(`${r.client.name} is now a client`); await refreshLookups(); loadLeads(); openClientDetail(r.client.id);
  });
}
async function deleteLead(id) {
  if (!await ask('Delete this lead? This cannot be undone.')) return;
  guard(async () => { await api('DELETE', `/leads/${id}`); document.querySelectorAll('.modal-overlay.active').forEach(m => closeModal(m.id)); toast('Lead deleted'); loadLeads(); });
}

async function loadLeadReport() {
  const r = await api('GET', '/leads/report?days=90');
  const t = r.total;
  $('lead-report').innerHTML = `<div class="grid grid-4 mb">
      <div class="stat"><div class="stat-label">Leads, 90 days</div><div class="stat-value">${t.leads}</div><div class="stat-sub">${t.open} still open</div></div>
      <div class="stat"><div class="stat-label">Became clients</div><div class="stat-value">${t.won}</div><div class="stat-sub">${t.conversion_pct}% of all leads</div></div>
      <div class="stat"><div class="stat-label">Lost</div><div class="stat-value">${t.lost}</div><div class="stat-sub">${r.lost_reasons[0] ? 'top reason: ' + esc(r.lost_reasons[0].reason) : '&nbsp;'}</div></div>
      <div class="stat"><div class="stat-label">Follow-ups due</div><div class="stat-value" style="color:${r.follow_ups_due ? 'var(--bad)' : 'inherit'}">${r.follow_ups_due}</div><div class="stat-sub">today or overdue</div></div></div>
    <div class="grid grid-2">
      <div class="card"><div class="card-title">Which source converts <span class="muted small">last 90 days</span></div>${r.by_source.length ? `<div class="table-wrap"><table class="plain"><thead><tr><th>Source</th><th class="num">Leads</th><th class="num">Won</th><th class="num">Lost</th><th class="num">Conversion</th><th class="num">Days to win</th></tr></thead><tbody>${r.by_source.map(s => `<tr><td><strong>${esc(s.source)}</strong></td><td class="num">${s.leads}</td><td class="num">${s.won}</td><td class="num">${s.lost}</td><td class="num"><strong>${s.conversion_pct}%</strong></td><td class="num muted">${s.avg_days_to_win ?? '—'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty small">No leads in the last 90 days.</div>'}</div>
      <div class="card"><div class="card-title">Where your clients came from <span class="muted small">all time</span></div><div id="lead-src-bars"></div></div></div>
    ${r.lost_reasons.length ? `<div class="card mt"><div class="card-title">Why leads were lost</div>${r.lost_reasons.map(x => `<div class="rank-top" style="padding:4px 0"><span>${esc(x.reason)}</span><span class="mono">${x.count}</span></div>`).join('')}</div>` : ''}`;
  hbars($('lead-src-bars'), r.clients_by_source.map((s, i) => ({ name: s.source, value: s.revenue, count: s.clients, color: INK[i % INK.length] })), { countLabel: 'clients' });
}

async function loadReferrals() {
  const rows = await api('GET', '/leads/referrals');
  $('lead-referrals').innerHTML = `<p class="small muted" style="margin:0 0 12px">Clients who recommended LUZ. When someone they sent pays, a reward is due (e.g. a free session). Tick it once you've given it.</p>` +
    (rows.length ? rows.map(r => `<div class="card mb"><div class="card-title"><span><a href="#" onclick="openClientDetail(${r.client_id});return false">${esc(r.name)}</a> <span class="muted small">${r.referred} referred · ${money(r.referred_revenue)} brought in</span></span>
      ${r.rewards_pending ? `<span class="badge badge-queued">${r.rewards_pending} reward(s) due</span>` : r.rewards_given ? '<span class="badge badge-active">rewarded</span>' : ''}</div>
      ${r.referred_clients.map(k => `<div class="pk-row" style="cursor:default"><div><strong>${esc(k.name)}</strong><div class="tiny muted">${k.paid ? 'has paid' : 'not paid yet'}${k.reward_note ? ' · ' + esc(k.reward_note) : ''}</div></div>
        <div>${k.reward_given ? '<span class="badge badge-active">reward given</span>' : k.paid ? `<button class="btn btn-success btn-xs" onclick="giveReward(${k.id}, ${jsArg(r.name)})">Mark reward given</button>` : ''}</div></div>`).join('')}</div>`).join('')
      : '<div class="card empty">No referrals yet. Set "Referred by" on a client or lead to start tracking them.</div>');
}
function giveReward(clientId, referrer) {
  confirmBox('Reward given', `<p>What did <strong>${esc(referrer)}</strong> get?</p><div class="form-group"><input id="rw-note" class="input" value="1 free session"></div>`, 'Save', async () => {
    await api('PUT', `/clients/${clientId}`, { referral_reward_given: true, referral_reward_note: val('rw-note').trim() || null }); toast('Saved'); loadReferrals();
  });
}
