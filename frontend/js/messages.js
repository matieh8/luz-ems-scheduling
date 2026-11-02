/* Message log, templates, custom messages */
let MSG = { tab: 'log', templates: [] };
function msgTab(t, el) { MSG.tab = t; document.querySelectorAll('#page-messages .tab').forEach(x => x.classList.remove('active')); el.classList.add('active'); document.querySelectorAll('#page-messages .subpanel').forEach(p => p.classList.toggle('active', p.id === 'msg-' + t)); loadMessages(); }
function messagesTable(logs, compact) {
  if (!logs.length) return '<div class="card empty">No messages yet.</div>';
  return `<div class="table-wrap"><table><thead><tr><th>Time</th>${compact ? '' : '<th>To</th>'}<th>Type</th><th>Channel</th><th>Status</th><th>Message</th><th></th></tr></thead><tbody>` + logs.map(l => `<tr>
    <td class="mono small">${fmtDT(l.created_at)}</td>${compact ? '' : `<td><strong>${esc(l.client ? l.client.name : 'Studio')}</strong><div class="tiny muted">${esc(l.recipient || '')}</div></td>`}
    <td>${esc(l.type.replace(/_/g, ' '))}</td><td><span class="chip">${l.channel}</span></td>
    <td>${badge(l.status)}${l.external_response && l.status === 'failed' ? `<div class="tiny" style="color:var(--bad);max-width:200px">${esc(l.external_response)}</div>` : ''}</td>
    <td><details><summary class="small" style="cursor:pointer;color:var(--accent)">${esc((l.subject || l.content).split('\n')[0].slice(0, 60))}…</summary><pre class="small" style="white-space:pre-wrap;margin:6px 0 0;background:var(--bg);padding:10px;border-radius:8px">${esc(l.content)}</pre></details></td>
    <td class="num">${l.status === 'failed' || l.status === 'skipped' ? `<button class="btn btn-ghost btn-xs" onclick="retryMessage(${l.id})">Retry</button>` : ''}</td></tr>`).join('') + '</tbody></table></div>';
}
async function loadMessages() {
  if (MSG.tab === 'templates') return loadTemplates();
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
