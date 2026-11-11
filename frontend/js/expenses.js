/* Monthly expense tracker — one card per day, every field is a live input that saves in place.
   Nothing is re-rendered while you type, so inputs never lose focus or "freeze". */
const EXP_ICONS = {
  'rent': '🏠', 'coffee': '☕', 'smoke': '🚬', 'tabby': '💳', 'darb': '🛣️', 'toll': '🛣️', 'salik': '🛣️', 'family': '👨‍👩‍👧',
  'food': '🍔', 'groceries': '🛒', 'restaurant': '🍽️',
  'fuel': '⛽', 'petrol': '⛽', 'car': '🚗', 'transport': '🚕', 'taxi': '🚕',
  'electricity': '💡', 'water': '💧', 'internet': '🌐', 'phone': '📱', 'utilities': '🔌',
  'salar': '👥', 'equipment': '🏋️', 'marketing': '📣', 'clean': '🧽', 'maintenance': '🛠️',
  'shopping': '🛍️', 'health': '💊', 'medical': '🏥', 'subscription': '📺', 'entertainment': '🎬',
  'education': '📚', 'travel': '✈️', 'gift': '🎁', 'other': '📝'
};
const PRESET_CATS = ['Rent', 'Electricity', 'Water', 'Internet', 'Phone', 'Utilities', 'Coffee', 'Salaries', 'Equipment', 'Marketing',
  'Cleaning', 'Maintenance', 'Subscriptions', 'Groceries', 'Fast food', 'Fuel', 'Transport', 'Shopping', 'Health', 'Entertainment', 'Education', 'Travel', 'Gift', 'Other'];
const EXP_METHODS = ['Card', 'Cash', 'Transfer'];
let EXPENSES = [];
let EXPENSE_CATS = [];
let EXP_LOADED_MONTH = null;

function expIcon(cat) {
  const key = String(cat || '').toLowerCase();
  return EXP_ICONS[key] || EXP_ICONS[Object.keys(EXP_ICONS).find(k => key.includes(k))] || '📝';
}
/* Accepts 12.5, 12,5, 1,250.00 and Arabic / Persian digits (١٢٫٥). Returns NaN when it is not a number. */
function expNum(v) {
  let s = String(v == null ? '' : v).trim()
    .replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d)).replace(/[۰-۹]/g, d => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d))
    .replace(/٫/g, '.').replace(/[٬\s]/g, '').replace(/[^0-9.,-]/g, '');
  if (s.includes(',') && s.includes('.')) s = s.replace(/,/g, '');
  else if (s.includes(',')) s = /,\d{1,2}$/.test(s) ? s.replace(',', '.') : s.replace(/,/g, '');
  return s === '' ? NaN : parseFloat(s);
}
function expMonth() {
  if (!val('exp-month')) setVal('exp-month', todayKey().slice(0, 7));
  return val('exp-month').split('-').map(Number);
}
function expDay(e) { return dateKey(parseISO(e.date)); }
function expAllCats() { return [...new Set([...PRESET_CATS.slice(0, -1), ...EXPENSE_CATS, ...EXPENSES.map(e => e.category)].filter(Boolean)), 'Other'].filter((c, i, a) => a.indexOf(c) === i); }

async function loadExpenses() {
  const [y, m] = expMonth();
  const [summary, cats] = await Promise.all([api('GET', `/expenses/summary?year=${y}&month=${m}`), api('GET', '/expenses/categories')]);
  EXPENSES = summary.expenses || [];
  EXPENSE_CATS = cats;
  $('exp-month-label').textContent = new Date(y, m - 1).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  $('exp-export').href = `/api/expenses/export.csv?year=${y}&month=${m}&token=${S.token}`;
  renderDays();
  refreshExpenseTotals();
  // Open on today: only when the month is (re)loaded, never while editing.
  const monthKey = `${y}-${m}`;
  const today = document.querySelector('#exp-list .day-card.today');
  if (today) setTimeout(() => today.scrollIntoView({ block: 'start', behavior: EXP_LOADED_MONTH === monthKey ? 'auto' : 'smooth' }), 80);
  EXP_LOADED_MONTH = monthKey;
}
function applyFilters() { renderDays(); refreshExpenseTotals(); }

function expVisible() {
  const q = (val('exp-search') || '').toLowerCase(), unpaidOnly = $('exp-unpaid-only') && $('exp-unpaid-only').checked;
  return EXPENSES.filter(e => (!unpaidOnly || e.paid === false) && (!q ||
    (e.category || '').toLowerCase().includes(q) || (e.payment_method || '').toLowerCase().includes(q) ||
    (e.notes || '').toLowerCase().includes(q) || String(e.amount).includes(q)));
}

function expRowHTML(e) {
  const cats = expAllCats();
  return `<div class="exp-row ${e.paid === false ? 'unpaid' : ''}" data-id="${e.id}">
    <select class="input input-sm exp-cat" aria-label="Category" onchange="expChange(${e.id}, 'category', this)">
      ${cats.map(c => `<option value="${esc(c)}" ${c === e.category ? 'selected' : ''}>${expIcon(c)} ${esc(c)}</option>`).join('')}
      <option value="__new__">➕ New category…</option></select>
    <select class="input input-sm exp-method" aria-label="Payment method" onchange="expChange(${e.id}, 'payment_method', this)">
      ${[...new Set([...EXP_METHODS, e.payment_method || 'Card'])].map(m => `<option ${m === (e.payment_method || 'Card') ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select>
    <input type="text" inputmode="decimal" autocomplete="off" class="input input-sm exp-amount" aria-label="Amount" placeholder="0" value="${e.amount ? e.amount : ''}" onfocus="this.select()" onchange="expChange(${e.id}, 'amount', this)" onkeydown="if(event.key==='Enter')this.blur()">
    <label class="exp-paid" title="Untick for a bill you still have to pay"><input type="checkbox" ${e.paid === false ? '' : 'checked'} onchange="expChange(${e.id}, 'paid', this)"> <span>${e.paid === false ? 'Unpaid' : 'Paid'}</span></label>
    <button class="btn btn-ghost btn-xs exp-del" title="Delete" onclick="deleteExpense(${e.id})">✕</button>
  </div>`;
}

function expDayHTML(key, items) {
  const [y, m, d] = key.split('-').map(Number);
  const label = new Date(y, m - 1, d).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
  const isToday = key === todayKey();
  return `<div class="day-card ${isToday ? 'today' : ''} ${items.length ? 'has-data' : 'no-data'}" data-day="${key}">
    <div class="day-header">
      <div class="day-title"><span class="day-date">${esc(label)}${isToday ? ' · Today' : ''}</span><span class="day-count" data-role="count"></span></div>
      <div class="day-total" data-role="total"></div>
    </div>
    <div class="day-body">
      <div class="exp-rows">${items.map(expRowHTML).join('')}</div>
      <button class="btn btn-ghost btn-sm add-to-day" onclick="addExpenseToDay('${key}')">+ Add expense</button>
    </div>
  </div>`;
}

function renderDays() {
  const [y, m] = expMonth();
  const groups = {};
  for (const e of expVisible()) (groups[expDay(e)] = groups[expDay(e)] || []).push(e);
  Object.values(groups).forEach(l => l.sort((a, b) => a.id - b.id));
  const total = new Date(y, m, 0).getDate();
  let html = '';
  for (let d = 1; d <= total; d++) { const key = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`; html += expDayHTML(key, groups[key] || []); }
  $('exp-list').innerHTML = html;
}

/* Recalculate every number on the page without touching the input rows. */
function refreshExpenseTotals() {
  const vis = expVisible(), byDay = {};
  for (const e of vis) (byDay[expDay(e)] = byDay[expDay(e)] || []).push(e);
  document.querySelectorAll('#exp-list .day-card').forEach(card => {
    const items = byDay[card.dataset.day] || [], sum = items.reduce((a, e) => a + e.amount, 0);
    card.classList.toggle('has-data', items.length > 0); card.classList.toggle('no-data', !items.length);
    const due = items.filter(e => e.paid === false).length;
    card.querySelector('[data-role=count]').innerHTML = items.length ? `${items.length} expense${items.length === 1 ? '' : 's'}${due ? ` · <span style="color:var(--bad)">${due} unpaid</span>` : ''}` : 'No expenses';
    card.querySelector('[data-role=total]').textContent = sum > 0 ? money(sum) : '';
  });
  const total = vis.reduce((a, e) => a + e.amount, 0), unpaid = EXPENSES.filter(e => e.paid === false), unpaidSum = unpaid.reduce((a, e) => a + e.amount, 0);
  $('exp-grand').innerHTML = `Total: ${money(total)}${unpaid.length ? ` <span class="exp-due-pill" onclick="$('exp-unpaid-only').checked = !$('exp-unpaid-only').checked; applyFilters()" title="Show unpaid only">${unpaid.length} unpaid · ${money(unpaidSum)}</span>` : ''}`;
  const cats = {}, methods = {};
  for (const e of vis) { const c = e.category || 'Other'; cats[c] = (cats[c] || 0) + e.amount; const p = e.payment_method || 'Card'; methods[p] = (methods[p] || 0) + e.amount; }
  const table = (obj, head, cellFn) => Object.keys(obj).length ? `<table><thead><tr><th>${head}</th><th class="num">Total</th></tr></thead><tbody>` +
    Object.entries(obj).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<tr><td>${cellFn(k)}</td><td class="num bold">${money(v)}</td></tr>`).join('') + '</tbody></table>' : '<div class="empty small">No spending yet.</div>';
  $('exp-cats').innerHTML = table(cats, 'Category', k => `<span class="ico">${expIcon(k)}</span> ${esc(k)}`);
  $('exp-methods').innerHTML = table(methods, 'Type', k => `<span class="badge badge-neutral">${esc(k)}</span>`);
}

async function expChange(id, field, el) {
  const e = EXPENSES.find(x => x.id === id); if (!e) return;
  let value;
  if (field === 'amount') {
    value = el.value.trim() === '' ? 0 : expNum(el.value);
    if (isNaN(value) || value < 0) { el.value = e.amount || ''; return toast('Enter the amount as a number, e.g. 250 or 12.50', true); }
    el.value = value || '';
  } else if (field === 'paid') value = el.checked;
  else if (field === 'category') {
    value = el.value;
    if (value === '__new__') {
      const name = (prompt('New category name') || '').replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/gu, '').replace(/\s+/g, ' ').trim();
      if (!name) { el.value = e.category; return; }
      value = name;
      if (![...el.options].some(o => o.value === name)) el.insertBefore(new Option(`${expIcon(name)} ${name}`, name), el.options[el.options.length - 1]);
      el.value = name; if (!EXPENSE_CATS.includes(name)) EXPENSE_CATS.push(name);
    }
  } else value = field === 'notes' ? (el.value.trim() || null) : el.value;
  if (e[field] === value) return;
  const before = e[field];
  e[field] = value;                      // optimistic: totals update at once
  if (field === 'paid') { const row = el.closest('.exp-row'); row.classList.toggle('unpaid', !value); row.querySelector('.exp-paid span').textContent = value ? 'Paid' : 'Unpaid'; }
  refreshExpenseTotals();
  try { await api('PUT', `/expenses/${id}`, { [field]: value }); }
  catch (err) {
    e[field] = before; refreshExpenseTotals();
    if (field === 'paid') { el.checked = before !== false; el.closest('.exp-row').classList.toggle('unpaid', before === false); }
    else el.value = before == null ? '' : before;
    toast(`Not saved: ${err.message}`, true);
  }
}

async function addExpenseRow() { await addExpenseToDay(todayKey()); }
async function addExpenseToDay(key) {
  if (key.slice(0, 7) !== val('exp-month')) { setVal('exp-month', key.slice(0, 7)); await loadExpenses(); }
  await guard(async () => {
    const created = await api('POST', '/expenses/', { date: zonedToDate(key, '12:00').toISOString(), category: 'Other', payment_method: 'Card', amount: 0, notes: null, paid: true });
    EXPENSES.push(created);
    const card = document.querySelector(`#exp-list .day-card[data-day="${key}"]`);
    if (!card) return loadExpenses();
    card.querySelector('.exp-rows').insertAdjacentHTML('beforeend', expRowHTML(created));   // only this row is added; nothing else is redrawn
    refreshExpenseTotals();
    const row = card.querySelector(`.exp-row[data-id="${created.id}"]`);
    row.scrollIntoView({ block: 'center', behavior: 'smooth' });
    row.querySelector('.exp-amount').focus({ preventScroll: true });
  });
}

async function deleteExpense(id) {
  if (!confirm('Delete this expense?')) return;
  await guard(async () => {
    await api('DELETE', `/expenses/${id}`);
    EXPENSES = EXPENSES.filter(e => e.id !== id);
    const row = document.querySelector(`#exp-list .exp-row[data-id="${id}"]`); if (row) row.remove();
    refreshExpenseTotals(); toast('Deleted');
  });
}
