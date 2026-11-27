/* Message log, templates, custom messages */
let MSG = { tab: 'log', templates: [] };
function msgTab(t, el) { MSG.tab = t; document.querySelectorAll('#page-messages .tab').forEach(x => x.classList.remove('active')); el.classList.add('active'); document.querySelectorAll('#page-messages .subpanel').forEach(p => p.classList.toggle('active', p.id === 'msg-' + t)); loadMessages(); }
function messagesTable(logs, compact) {
  if (!logs.length) return '<div class="card empty">No messages yet.</div>';
  return `<div class="table-wrap"><table><thead><tr><th>Time</th>${compact ? '' : '<th>To</th>'}<th>Type</th><th>Channel</th><th>Status</th><th>Message</th><th></th></tr></thead><tbody>` + logs.map(l => `<tr>
    <td class="mono small">${fmtDT(l.created_at)}</td>${compact ? '' : `<td><strong>${esc(l.client ? l.client.name : 'Studio')}</strong><div class="tiny muted">${esc(l.recipient || '')}</div></td>`}
    <td>${esc(l.type.replace(/_/g, ' '))}</td><td><span class="chip">${l.channel}</span></td>
    <td>${(l.external_response || '').startsWith('DEMO MODE') ? '<span class="badge badge-neutral" title="Demo mode: written to the log, nobody received it">demo · not sent</span>' : badge(l.status)}${l.external_response && l.status === 'failed' ? `<div class="tiny" style="color:var(--bad);max-width:200px">${esc(l.external_response)}</div>` : ''}</td>
    <td><details><summary class="small" style="cursor:pointer;color:var(--accent)">${esc((l.subject || l.content).split('\n')[0].slice(0, 60))}…</summary><pre class="small" style="white-space:pre-wrap;margin:6px 0 0;background:var(--bg);padding:10px;border-radius:8px">${esc(l.content)}</pre></details></td>
    <td class="num">${l.status === 'failed' || l.status === 'skipped' ? `<button class="btn btn-ghost btn-xs" onclick="retryMessage(${l.id})">Retry</button>` : ''}${l.status === 'pending_approval' ? `<button class="btn btn-success btn-xs" onclick="approveMessage(${l.id})">Approve &amp; send</button><button class="btn btn-ghost btn-xs" onclick="discardMessage(${l.id})">Discard</button>` : ''}</td></tr>`).join('') + '</tbody></table></div>';
}
/* Messages the app prepared by itself (renewal offers) wait here for the owner's OK */
async function loadPending() {
  const p = await api('GET', '/notifications/pending');
  const box = $('msg-pending'); if (!box) return;
  box.innerHTML = p.count ? `<div class="card mb approval-card"><div class="card-title">Waiting for your approval <span class="badge badge-queued">${p.count}</span>
      <span class="actions"><button class="btn btn-success btn-sm" onclick="approveAllMessages(${p.count})">Approve &amp; send all</button></span></div>
      <p class="small muted" style="margin:0 0 10px">These marketing messages were prepared automatically and have not been sent. Read them, then send or discard each one.</p>
      ${messagesTable(p.messages)}</div>` : '';
}
async function approveMessage(id) { guard(async () => { const l = await api('POST', `/notifications/logs/${id}/approve`); toast(l.status === 'sent' ? 'Sent' : `Message ${l.status}`); loadMessages(); }); }
async function discardMessage(id) { guard(async () => { await api('POST', `/notifications/logs/${id}/discard`); toast('Discarded, not sent'); loadMessages(); }); }
function approveAllMessages(n) { confirmBox('Send all', `<p>Send all ${n} waiting message(s) now?</p>`, 'Send all', async () => { const r = await api('POST', '/notifications/approve-all'); toast(`${r.approved} message(s) sent`); loadMessages(); }); }
async function loadMessages() {
  if (MSG.tab === 'templates') return loadTemplates();
  if (MSG.tab === 'automations') return loadAutomations();
  loadPending();
  if (!MSG.templates.length) { MSG.templates = await api('GET', '/notifications/templates'); fillSelect('msg-type', '<option value="">All types</option>' + MSG.templates.map(t => `<option value="${t.key}">${esc(t.name)}</option>`).join('') + '<option value="custom">Custom message</option>'); }
  const q = ['status', 'channel', 'type'].map(k => val('msg-' + k) ? `&${k}=${val('msg-' + k)}` : '').join('');
  $('messages-table').innerHTML = messagesTable(await api('GET', `/notifications/logs?limit=200${q}`));
}
async function retryMessage(id) { guard(async () => { const l = await api('POST', `/notifications/logs/${id}/retry`); toast(l.status === 'sent' ? 'Message sent' : `Still ${l.status}: ${l.external_response || ''}`, l.status !== 'sent'); loadMessages(); }); }
async function runJobs() { guard(async () => { await api('POST', '/notifications/run-jobs'); toast('Reminder, follow-up and package checks ran'); loadMessages(); }); }

async function loadTemplates() {
  MSG.templates = await api('GET', '/notifications/templates');
  $('templates-list').innerHTML = `<div class="grid grid-2">` + MSG.templates.map(t => `<div class="card" style="cursor:pointer" onclick="editTemplate('${t.key}')">
    <div class="card-title">${esc(t.name)} ${t.enabled ? badge('active') : '<span class="badge badge-neutral">off</span>'}</div>
    <pre class="small muted" style="white-space:pre-wrap;margin:0;max-height:110px;overflow:hidden">${esc(t.body)}</pre></div>`).join('') + '</div>';
}
async function editTemplate(key) {
  const t = MSG.templates.find(x => x.key === key); const ph = await api('GET', '/notifications/templates/placeholders');
  $('template-title').textContent = t.name; setVal('template-key', key); setVal('template-subject', t.subject); setVal('template-body', t.body); $('template-enabled').checked = t.enabled;
  $('template-placeholders').innerHTML = ph.placeholders.map(p => `<button type="button" class="chip" style="cursor:pointer" onclick="insertPlaceholder('${p}')">{${p}}</button>`).join('');
  openModal('template-modal'); previewTemplate();
}
function insertPlaceholder(p) { const ta = $('template-body'); const s = ta.selectionStart || ta.value.length; ta.value = ta.value.slice(0, s) + `{${p}}` + ta.value.slice(s); ta.focus(); }
async function previewTemplate() { guard(async () => { await api('PUT', `/notifications/templates/${val('template-key')}`, { subject: val('template-subject'), body: val('template-body') }); const p = await api('POST', `/notifications/templates/${val('template-key')}/preview`); $('template-preview').textContent = (p.subject ? `Subject: ${p.subject}\n\n` : '') + p.body; }); }
async function saveTemplate() { guard(async () => { await api('PUT', `/notifications/templates/${val('template-key')}`, { subject: val('template-subject'), body: val('template-body'), enabled: $('template-enabled').checked }); closeModal('template-modal'); toast('Template saved'); loadTemplates(); }); }
async function resetTemplate() { guard(async () => { const t = await api('POST', `/notifications/templates/${val('template-key')}/reset`); setVal('template-subject', t.subject); setVal('template-body', t.body); previewTemplate(); }); }

function openCustomMessageModal(clientId) {
  fillSelect('cm-client', clientOptions(clientId)); if (clientId) setVal('cm-client', clientId);
  setVal('cm-subject', ''); setVal('cm-body', ''); $('cm-wa').checked = true; $('cm-sms').checked = false; $('cm-email').checked = false;
  openModal('custom-message-modal');
}
async function sendCustomMessage() { guard(async () => { const channels = [['cm-wa', 'whatsapp'], ['cm-sms', 'sms'], ['cm-email', 'email']].filter(([i]) => $(i).checked).map(([, c]) => c);
  if (!val('cm-body').trim()) throw new Error('Write a message'); if (!channels.length) throw new Error('Pick at least one channel');
  const r = await api('POST', '/notifications/custom', { client_id: +val('cm-client'), body: val('cm-body'), subject: val('cm-subject') || null, channels });
  closeModal('custom-message-modal'); toast(r.length ? `Sent via ${r.map(l => l.channel).join(', ')}` : 'Client has no contact details for those channels', !r.length); if (S.page === 'messages') loadMessages(); }); }

async function retryAllFailed() {
  if (!await ask('Send again every message that failed in the last 7 days?', 'Retry all', 'btn-primary')) return;
  guard(async () => { const r = await api('POST', '/notifications/retry-failed'); toast(r.retried ? `${r.sent} of ${r.retried} sent` : 'Nothing failed in the last 7 days', r.retried > r.sent); loadMessages(); });
}

/* ---------- Automation Center: each automation's real state ("active" only when it can reach someone) ---------- */
const AUTO_STATE = { active: ['badge-active', 'Active'], needs_approval: ['badge-queued', 'Active · you approve'], not_working: ['badge-cancelled', 'Not working'], off: ['badge-neutral', 'Off'] };
const AUTO_UNIT = { reminder: 'hours before', follow_up: 'hours after', subscription_expiring: 'days before end', subscription_low: 'sessions left',
  renewal_offer: 'days after end', payment_reminder: 'days after', win_back: 'days away', owner_session_reminder: 'hours before' };
async function loadAutomations() {
  const box = $('automations-box');
  let r; try { r = await api('GET', '/notifications/automations'); } catch (e) { box.innerHTML = `<div class="card empty">${esc(e.message)}</div>`; return; }
  const owner = !S.me || S.me.role === 'owner';
  const ch = (name, c) => `<div class="ch ${c.ok ? 'ok' : 'bad'}"><strong>${name}</strong><span>${c.ok ? 'Working' : esc(c.why)}</span></div>`;
  box.innerHTML = `${r.demo_mode ? `<div class="alert alert-serious" style="cursor:default">Demo mode is on: automations run, but messages are only written to the log. Nobody receives them. Turn Demo mode off in Settings → Messaging once WhatsApp or email is connected.</div>` : ''}
    <div class="ch-row">${ch('WhatsApp', r.channels.whatsapp)}${ch('Email', r.channels.email)}${ch('SMS', r.channels.sms)}${ch('Phone notifications (you)', { ok: r.push, why: 'No device has notifications on' })}</div>
    <div class="table-wrap"><table class="auto-table"><thead><tr><th>Automation</th><th>Status</th><th>Sends via</th><th class="num">Last 30 days</th><th></th></tr></thead><tbody>${r.automations.map(a => {
      const [cls, label] = AUTO_STATE[a.state] || AUTO_STATE.off, s = a.stats;
      const counts = a.audience === 'owner' ? '<span class="muted small">to your phone</span>' : [s.sent && `<span style="color:var(--good)">${s.sent} delivered</span>`, s.failed && `<span style="color:var(--bad)">${s.failed} failed</span>`,
        s.demo && `<span class="muted">${s.demo} logged (demo)</span>`, s.pending_approval && `<span style="color:var(--warn)">${s.pending_approval} waiting</span>`, s.skipped && `<span class="muted">${s.skipped} skipped</span>`].filter(Boolean).join('<br>') || '<span class="muted">none</span>';
      return `<tr><td><strong>${esc(a.name)}</strong><div class="tiny muted">${esc(a.trigger)}${a.audience === 'owner' ? ' · to you' : ''}</div></td>
        <td><span class="badge ${cls}">${label}</span>${a.state === 'not_working' ? `<div class="tiny" style="color:var(--bad);max-width:260px">${esc(a.why)}</div>` : ''}</td>
        <td class="small">${a.channels.length ? a.channels.join(', ') : '<span class="muted">—</span>'}</td>
        <td class="num small">${counts}${s.last ? `<div class="tiny muted">last ${fmtDT(s.last)}</div>` : ''}${a.template ? `<div><a href="#" class="tiny" onclick="autoLog('${a.template}');return false">View log</a></div>` : ''}</td>
        <td class="num nowrap">${owner ? `${AUTO_UNIT[a.key] ? `<input type="number" min="1" max="365" class="input input-sm auto-val" id="av-${a.key}" value="${a.value > 0 ? a.value : ''}" placeholder="${a.key === 'payment_reminder' ? 3 : a.key === 'win_back' ? 30 : ''}" title="${AUTO_UNIT[a.key]}" aria-label="${esc(a.name)}: ${AUTO_UNIT[a.key]}"><span class="tiny muted"> ${AUTO_UNIT[a.key]}</span> ` : ''}
          <label class="switch" title="${a.on ? 'Switch off' : 'Switch on'}"><input type="checkbox" ${a.on ? 'checked' : ''} onchange="switchAutomation('${a.key}', this.checked)" aria-label="${esc(a.name)} on or off"><span></span></label>` : ''}</td></tr>`; }).join('')}</tbody></table></div>
    <p class="tiny muted">"Active" means it is switched on and at least one channel can really deliver. Messages that fail for a temporary reason are retried automatically for 3 hours; you get a phone notification when one finally fails.</p>`;
  box.querySelectorAll('.auto-val').forEach(inp => inp.addEventListener('change', () => { const key = inp.id.slice(3); switchAutomation(key, true, +inp.value || null); }));
}
async function switchAutomation(key, on, value = null) {
  guard(async () => { await api('PUT', `/notifications/automations/${key}`, { on, value }); toast(on ? 'Switched on' : 'Switched off'); loadAutomations(); });
}
function autoLog(type) { setVal('msg-type', type); msgTab('log', document.querySelector('#page-messages .tab')); }
