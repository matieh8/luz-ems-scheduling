/* Calendar: week / day / agenda views in the business time zone */
const CAL = { view: matchMedia('(max-width: 640px)').matches ? 'day' : 'week', anchor: todayKey(), hours: [], appts: [], blocks: [] };  // phones open on one day
try { CAL.colorBy = localStorage.getItem('luz_cal_color') || 'status'; } catch (e) { CAL.colorBy = 'status'; }
// Status colours: [label, fill, edge]. "Needs update" = the time has passed and nobody marked it done / no-show yet.
const CAL_STATUS = { scheduled: ['Booked', 'var(--surface)', 'var(--text-3)'], confirmed: ['Confirmed', 'var(--good-bg)', 'var(--good)'],
  arrived: ['Arrived', 'var(--good)', 'var(--good)'], completed: ['Done', 'var(--neutral-bg)', 'var(--border-strong)'],
  no_show: ['No-show', 'var(--bad-bg)', 'var(--bad)'], overdue: ['Needs update', 'var(--warn-bg)', 'var(--warn)'] };
function calKey(a) { return ['scheduled', 'confirmed'].includes(a.status) && parseISO(a.end_time) < new Date() ? 'overdue' : a.status; }
function calColorBy(v) { CAL.colorBy = v; try { localStorage.setItem('luz_cal_color', v); } catch (e) {} loadCalendar(); }
const ROW_MIN = 30, ROW_PX = 36;

function calView(v) { CAL.view = v; CAL.agendaDays = null; document.querySelectorAll('#cal-view button').forEach(b => b.classList.toggle('active', b.dataset.v === v)); loadCalendar(); }
function addMonths(key, n) { const [y, m] = key.split('-').map(Number); const d = new Date(Date.UTC(y, m - 1 + n, 1)); return d.toISOString().slice(0, 10); }
function calMove(n) { CAL.anchor = CAL.view === 'month' ? addMonths(CAL.anchor, n) : addDays(CAL.anchor, CAL.view === 'day' ? n : 7 * n); loadCalendar(); }
function calToday() { CAL.anchor = todayKey(); loadCalendar(); }
function calOpenDay(k) { CAL.anchor = k; calView('day'); }

function calRange() {
  if (CAL.view === 'day') return [CAL.anchor, addDays(CAL.anchor, 1)];
  if (CAL.view === 'month') { const first = CAL.anchor.slice(0, 8) + '01'; const ws = weekStartKey(first); return [ws, addDays(ws, 42)]; }
  if (CAL.view === 'agenda') return [CAL.anchor, addDays(CAL.anchor, CAL.agendaDays || 14)];  // agenda: the next two weeks (7 days from the dashboard)
  const ws = weekStartKey(CAL.anchor); return [ws, addDays(ws, 7)];
}

async function loadCalendar() {
  if (!CAL.hours.length) CAL.hours = await api('GET', '/settings/hours');
  document.querySelectorAll('#cal-view button').forEach(b => b.classList.toggle('active', b.dataset.v === CAL.view));
  fillSelect('cal-staff', '<option value="">All trainers</option>' + S.staff.filter(s => s.active).map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join(''));
  const [from, to] = calRange();
  const staffId = val('cal-staff');
  const q = `from_date=${zonedToDate(from, '00:00').toISOString()}&to_date=${zonedToDate(to, '00:00').toISOString()}`;
  [CAL.appts, CAL.blocks] = await Promise.all([api('GET', `/appointments/?${q}${staffId ? '&staff_id=' + staffId : ''}`), api('GET', `/blocked-times/?${q}`)]);
  const byStatus = CAL.colorBy === 'status';
  $('cal').classList.toggle('by-status', byStatus);
  $('cal-legend').innerHTML = `<span class="seg seg-sm" role="group" aria-label="Colour sessions by"><button type="button" class="${byStatus ? 'active' : ''}" aria-pressed="${byStatus}" onclick="calColorBy('status')">Status</button><button type="button" class="${byStatus ? '' : 'active'}" aria-pressed="${!byStatus}" onclick="calColorBy('service')">Service</button></span>`
    + (byStatus ? Object.values(CAL_STATUS).map(([n, f, e]) => `<span class="lg-item"><span class="cal-sw" style="background:${f};border-color:${e}"></span>${n}</span>`)
                : S.services.filter(s => s.active).map(s => `<span class="lg-item"><span class="dot" style="background:${s.color}"></span>${esc(s.name)}</span>`)).join('');
  if (CAL.view === 'agenda') return renderAgenda(from, to);
  if (CAL.view === 'month') return renderMonth(from);
  renderGrid(from, CAL.view === 'day' ? 1 : 7);
}

function calTrainerDay(key) {
  const s = val('cal-staff') && S.staff.find(x => x.id == val('cal-staff')); if (!s || !s.work_hours) return undefined;
  const [y, m, d] = key.split('-').map(Number), dow = (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
  return s.work_hours[dow];
}
function hoursFor(key) { const [y, m, d] = key.split('-').map(Number); const dow = (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7; return CAL.hours.find(h => h.day_of_week === dow); }
function hm(s) { const [h, m] = s.split(':').map(Number); return h * 60 + m; }

function renderGrid(from, days) {
  const openMin = Math.min(...CAL.hours.filter(h => !h.closed).map(h => hm(h.open_time)), 8 * 60);
  const closeMin = Math.max(...CAL.hours.filter(h => !h.closed).map(h => hm(h.close_time)), 20 * 60);
  const gridStart = Math.floor(openMin / 60) * 60, gridEnd = Math.ceil(closeMin / 60) * 60;
  const rows = (gridEnd - gridStart) / ROW_MIN;
  const keys = Array.from({ length: days }, (_, i) => addDays(from, i));
  const today = todayKey();
  $('cal-title').textContent = days === 1 ? fmtKeyLong(from) : `${fmtKey(keys[0])} – ${fmtKey(keys[6])}`;
  let html = `<div class="cal-grid" style="--cols:${days};--row:${ROW_PX}px"><div class="cal-head"></div>`;
  keys.forEach(k => { const h = hoursFor(k); html += `<div class="cal-head ${k === today ? 'today' : ''} ${!h || h.closed ? 'closed' : ''}">${fmtKey(k).split(' ')[0]}<span class="d">${+k.split('-')[2]}</span>${!h || h.closed ? '<span class="tiny">Closed</span>' : `<span class="tiny">${h.open_time}–${h.close_time}</span>`}</div>`; });
  // time column
  html += '<div>';
  for (let r = 0; r < rows; r++) { const m = gridStart + r * ROW_MIN; html += `<div class="cal-time">${m % 60 === 0 ? fmtMin(m) : ''}</div>`; }
  html += '</div>';
  const now = new Date(), nowKey = dateKey(now), nowMin = tzParts(now).h * 60 + tzParts(now).mi;
  keys.forEach(k => {
    const h = hoursFor(k);
    html += `<div class="cal-col">`;
    const tw = calTrainerDay(k);  // the filtered trainer's own hours that day
    for (let r = 0; r < rows; r++) { const m = gridStart + r * ROW_MIN; const closed = !h || h.closed || m < hm(h.open_time) || m >= hm(h.close_time) || tw === null || (tw && (m < hm(tw[0]) || m >= hm(tw[1])));
      html += `<div class="cal-row ${m % 60 === 0 ? 'hour' : ''} ${closed ? 'closed' : ''}" onclick="openBookingModal(null, {date:'${k}', time:'${fmtMin24(m)}'})"></div>`; }
    CAL.blocks.filter(b => dateKey(parseISO(b.start_time)) <= k && dateKey(parseISO(b.end_time)) >= k).forEach(b => {
      const s = dateKey(parseISO(b.start_time)) < k ? gridStart : minOf(b.start_time), e = dateKey(parseISO(b.end_time)) > k ? gridEnd : minOf(b.end_time);
      html += `<div class="cal-block" style="top:${px(s - gridStart)}px;height:${px(e - s)}px" onclick="deleteBlock(${b.id}, ${jsArg(b.reason || 'Blocked')})">⛔ ${esc(b.reason || 'Blocked')}${b.staff ? ' · ' + esc(b.staff.name) : ''}</div>`; });
    CAL.appts.filter(a => dateKey(parseISO(a.start_time)) === k).forEach(a => {
      const s = minOf(a.start_time), e = minOf(a.end_time);
      const k = calKey(a), icon = k === 'overdue' ? '!' : a.status === 'confirmed' ? '✓' : a.status === 'arrived' ? '●' : a.status === 'completed' ? '✓✓' : a.status === 'no_show' ? '✗' : a.status === 'cancelled' ? '—' : '';
      const hpx = Math.max(px(e - s) - 2, 20), short = hpx < 34;
      const detail = `${fmtTime(a.start_time)} · ${esc(a.service.name)}${a.staff ? ' · ' + esc(a.staff.name.replace('Coach ', '')) : ''}`;
      html += `<div class="cal-ev ${a.status} st-${k} ${short ? 'short' : ''}" style="top:${px(s - gridStart)}px;height:${hpx}px;--svc:${a.service.color}" onclick="event.stopPropagation();openAppointment(${a.id})" title="${esc(a.client.name)} · ${detail} · ${(CAL_STATUS[k] || [a.status])[0]}">
        <strong>${esc(a.client.name)}${short ? ` <em>· ${fmtTime(a.start_time)}</em>` : ''}</strong><span class="dt">${detail}</span><span class="st">${icon}</span></div>`; });
    if (k === nowKey && nowMin >= gridStart && nowMin <= gridEnd) html += `<div class="cal-now" style="top:${px(nowMin - gridStart)}px"></div>`;
    html += '</div>';
  });
  html += '</div>';
  $('cal').innerHTML = html;
  if (keys.includes(nowKey)) { const y = px(Math.max(nowMin - gridStart - 90, 0)); $('cal').scrollTop = y; }
}
function px(min) { return min / ROW_MIN * ROW_PX; }
function minOf(iso) { const p = tzParts(parseISO(iso)); return p.h * 60 + p.mi; }
function fmtMin(m) { const h = Math.floor(m / 60); return h === 0 ? '12 AM' : h < 12 ? `${h} AM` : h === 12 ? '12 PM' : `${h - 12} PM`; }
function fmtMin24(m) { return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`; }

function renderMonth(from) {
  const month = CAL.anchor.slice(0, 7), today = todayKey();
  const [y, m] = month.split('-').map(Number);
  $('cal-title').textContent = new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('en-GB', { timeZone: 'UTC', month: 'long', year: 'numeric' });
  const byDay = {};
  CAL.appts.filter(a => a.status !== 'cancelled').forEach(a => { const k = dateKey(parseISO(a.start_time)); (byDay[k] = byDay[k] || []).push(a); });
  Object.values(byDay).forEach(l => l.sort((a, b) => a.start_time.localeCompare(b.start_time)));
  const keys = Array.from({ length: 42 }, (_, i) => addDays(from, i));
  // Drop a 6th week that is entirely next month
  const weeks = [0, 1, 2, 3, 4, 5].filter(w => w < 5 || keys[w * 7].slice(0, 7) === month);
  let html = `<div class="cal-month"><div class="cm-head">${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => `<div>${d}</div>`).join('')}</div><div class="cm-grid">`;
  weeks.forEach(w => keys.slice(w * 7, w * 7 + 7).forEach(k => {
    const list = byDay[k] || [], h = hoursFor(k), closed = !h || h.closed;
    html += `<div class="cm-day ${k.slice(0, 7) !== month ? 'other' : ''} ${k === today ? 'today' : ''} ${closed ? 'closed' : ''}" onclick="calOpenDay('${k}')" role="button" tabindex="0" aria-label="${fmtKeyLong(k)}, ${list.length} session(s)">
      <div class="cm-top"><span class="cm-n">${+k.slice(8)}</span>${list.length ? `<span class="cm-count">${list.length}</span>` : ''}</div>
      ${list.slice(0, 3).map(a => `<div class="cm-ev" style="--c:${CAL.colorBy === 'status' ? (CAL_STATUS[calKey(a)] || CAL_STATUS.completed)[2] : a.service.color}" onclick="event.stopPropagation();openAppointment(${a.id})" title="${esc(a.client.name)} · ${esc(a.service.name)}"><b>${fmtTime(a.start_time)}</b> ${esc(a.client.name.split(' ')[0])}</div>`).join('')}
      ${list.length > 3 ? `<div class="cm-more">+${list.length - 3} more</div>` : ''}</div>`;
  }));
  $('cal').innerHTML = html + '</div></div>';
  $('cal').scrollTop = 0;
}

function renderAgenda(from, to) {
  $('cal-title').textContent = `${fmtKey(from)} – ${fmtKey(addDays(to, -1))}`;
  const byDay = {};
  CAL.appts.forEach(a => { const k = dateKey(parseISO(a.start_time)); (byDay[k] = byDay[k] || []).push(a); });
  const keys = Object.keys(byDay).sort();
  if (!keys.length) { $('cal').innerHTML = '<div class="empty">No sessions in these two weeks.</div>'; return; }
  $('cal').innerHTML = `<div style="padding:4px 16px 16px">` + keys.map(k => `<div class="agenda-day">${fmtKeyLong(k)}${k === todayKey() ? ' · Today' : ''}</div>` + apptTable(byDay[k])).join('') + '</div>';
}

function apptTable(list, opts = {}) {
  if (!list.length) return '<div class="empty small">No sessions.</div>';
  return `<div class="table-wrap"><table><thead><tr><th>Time</th><th>Client</th><th>Service</th><th>Trainer</th><th>Status</th><th class="num">Price</th><th></th></tr></thead><tbody>` +
    list.map(a => `<tr class="clickable" onclick="openAppointment(${a.id})">
      <td class="mono">${opts.withDate ? fmtDateShort(a.start_time) + '<br>' : ''}<strong>${fmtTime(a.start_time)}</strong><div class="tiny muted">${relTime(a.start_time)}</div></td>
      <td><strong>${esc(a.client.name)}</strong><div class="tiny muted">${esc(a.client.phone)}</div></td>
      <td><span class="dot" style="background:${a.service.color}"></span>${esc(a.service.name)}</td>
      <td>${a.staff ? esc(a.staff.name) : '<span class="muted">—</span>'}</td>
      <td>${badge(a.status)}${calKey(a) === 'overdue' ? ' <span class="chip chip-warn">needs update</span>' : ''}${a.late_minutes ? ` <span class="chip" style="color:var(--warn)">${a.late_minutes}m late</span>` : ''}${a.source === 'online' ? ' <span class="chip">online</span>' : ''}</td>
      <td class="num">${a.subscription_id ? '<span class="chip">package</span>' : money(a.price)}${a.balance_due > 0 ? `<div class="tiny" style="color:var(--bad)">due ${money(a.balance_due)}</div>` : ''}</td>
      <td class="num"><button class="btn btn-ghost btn-xs" onclick="event.stopPropagation();openAppointment(${a.id})">Manage</button></td></tr>`).join('') + '</tbody></table></div>';
}

/* ---------- blocked time ---------- */
function openBlockModal() {
  fillSelect('block-staff', staffOptions('', 'Whole studio'));
  const d = CAL.anchor; setVal('block-start', `${d}T12:00`); setVal('block-end', `${d}T13:00`); setVal('block-reason', '');
  openModal('block-modal');
}
async function saveBlock() {
  guard(async () => {
    const [sd, st] = val('block-start').split('T'), [ed, et] = val('block-end').split('T');
    await api('POST', '/blocked-times/', { staff_id: val('block-staff') ? +val('block-staff') : null, start_time: zonedToDate(sd, st).toISOString(), end_time: zonedToDate(ed, et).toISOString(), reason: val('block-reason') || null });
    closeModal('block-modal'); toast('Time blocked'); loadCalendar();
  });
}
function deleteBlock(id, reason) { confirmBox('Remove blocked time', `<p>Unblock <strong>${esc(reason)}</strong>?</p>`, 'Unblock', async () => { await api('DELETE', `/blocked-times/${id}`); toast('Unblocked'); loadCalendar(); }, 'btn-danger'); }
