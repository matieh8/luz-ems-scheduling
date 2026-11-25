/* Team: staff logins, roles and commission (owner), trainer performance report (Revenue page) */
const ROLE_HELP = {
  none: 'No login. They can still be assigned sessions.',
  trainer: 'Calendar and clients only: sessions, notes, measurements, photos (they can see what a client paid). No reports, expenses, payments or settings.',
  reception: 'Calendar, clients, packages, payments, leads and messages. No expenses, reports or settings.',
  manager: 'Everything except Settings, backups, the activity log and team logins.',
};
function staffAccess(id) {
  const s = S.staff.find(x => x.id === id); if (!s) return;
  confirmBox(`Login & pay: ${esc(s.name)}`, `
    <div class="form-group"><label>Access</label><select id="sa-access" class="input" onchange="$('sa-help').textContent = ROLE_HELP[this.value]; $('sa-login').style.display = this.value === 'none' ? 'none' : ''">
      ${Object.keys(ROLE_HELP).map(k => `<option value="${k}" ${(s.access_role || 'none') === k ? 'selected' : ''}>${k === 'none' ? 'No login' : k[0].toUpperCase() + k.slice(1)}</option>`).join('')}</select>
      <div class="help" id="sa-help">${ROLE_HELP[s.access_role || 'none']}</div></div>
    <div id="sa-login" style="${s.access_role ? '' : 'display:none'}">
      <div class="form-row"><div class="form-group"><label>Username</label><input id="sa-user" class="input" autocomplete="off" autocapitalize="none" value="${esc(s.login_username || s.name.split(' ')[0].toLowerCase())}"></div>
        <div class="form-group"><label>${s.has_password ? 'New password (leave empty to keep)' : 'Password'}</label><input type="password" id="sa-pass" class="input" autocomplete="new-password" placeholder="at least 8 characters"></div></div>
      <p class="tiny muted" style="margin:0 0 10px">Give them the username and password yourself. Changing the password or switching to "No login" signs them out everywhere.</p></div>
    <div class="form-row"><div class="form-group"><label>Commission</label><select id="sa-ctype" class="input"><option value="none">None</option><option value="percent">% of session value</option><option value="per_session">Fixed per completed session</option></select></div>
      <div class="form-group"><label>Amount</label><input type="number" min="0" step="0.5" id="sa-cval" class="input" value="${s.commission_value ?? ''}" placeholder="e.g. 10 (%) or 30 (${esc(S.currency)})"></div></div>`, 'Save', async () => {
    const access = val('sa-access'), pass = val('sa-pass');
    if (access !== (s.access_role || 'none') || pass || (access !== 'none' && val('sa-user').trim() !== (s.login_username || ''))) {
      if (access !== 'none' && pass && pass.length < 8) throw new Error('Password must be at least 8 characters');
      await api('PUT', `/staff/${id}/account`, access === 'none' ? { access } : { access, username: val('sa-user').trim(), ...(pass ? { password: pass } : {}) });
    }
    const ctype = val('sa-ctype');
    await api('PUT', `/staff/${id}`, { commission_type: ctype, commission_value: ctype === 'none' ? null : (parseFloat(val('sa-cval')) || 0) });
    toast('Saved'); await refreshLookups(); loadCatalog();
  });
  setVal('sa-ctype', s.commission_type || 'none');
}

async function loadTeamReport() {
  const el = $('team-report'); if (!el || typeof REP === 'undefined' || !REP.from) return;
  const r = await api('GET', `/reports/staff?from=${REP.from}&to=${REP.to}`);
  el.innerHTML = r.staff.length ? `<div class="table-wrap"><table class="plain"><thead><tr><th>Trainer</th><th class="num">Sessions</th><th class="num">Clients</th><th class="num">Show rate</th><th class="num">No-shows</th><th class="num">Late</th><th class="num">Value delivered</th><th class="num">Commission</th></tr></thead><tbody>${r.staff.map(s => `<tr>
      <td><span class="dot" style="background:${s.color}"></span><strong>${esc(s.name)}</strong></td><td class="num">${s.completed}</td><td class="num">${s.clients}</td>
      <td class="num">${s.show_rate !== null ? s.show_rate + '%' : '—'}</td><td class="num">${s.no_show}</td><td class="num">${s.late}</td>
      <td class="num">${money(s.value)}<div class="tiny muted">avg ${money(s.avg_value)}</div></td>
      <td class="num"><strong>${money(s.commission)}</strong><div class="tiny muted">${s.commission_type === 'percent' ? s.commission_value + '%' : s.commission_type === 'per_session' ? money(s.commission_value) + '/session' : 'none set'}</div></td></tr>`).join('')}</tbody>
      <tfoot><tr><td colspan="7"><strong>Total commission due</strong></td><td class="num"><strong>${money(r.total_commission)}</strong></td></tr></tfoot></table></div>`
    : '<div class="empty small">No trainers with sessions in this period.</div>';
}
