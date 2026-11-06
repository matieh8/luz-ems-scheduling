/* Monthly expense tracker — calendar month view with day detail */
const EXP_ICONS = {
  'rent': '🏠', 'housing': '🏠', 'mortgage': '🏠',
  'food': '🍔', 'fast food': '🍔', 'groceries': '🛒', 'restaurant': '🍽️',
  'fuel': '⛽', 'petrol': '⛽', 'car': '🚗', 'transport': '🚕', 'taxi': '🚕',
  'utilities': '💡', 'electricity': '💡', 'internet': '🌐', 'phone': '📱',
  'shopping': '🛍️', 'clothes': '👕',
  'health': '💊', 'gym': '💪', 'medical': '🏥',
  'subscriptions': '📺', 'entertainment': '🎬',
  'education': '📚', 'travel': '✈️', 'gift': '🎁', 'other': '📝'
};
let EXPENSES = [];
let FILTERED_EXPENSES = [];
let EXPENSE_CATS = [];
let EDITING = null;
let SELECTED_DAY = null;

function expIcon(cat) {
  const key = String(cat).toLowerCase();
  return EXP_ICONS[key] || EXP_ICONS[Object.keys(EXP_ICONS).find(k => key.includes(k))] || '📝';
}

function initExpenseMonth() {
  if (!val('exp-month')) {
    const now = new Date();
    setVal('exp-month', `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`);
  }
}

async function loadExpenses() {
  initExpenseMonth();
  const [y, m] = val('exp-month').split('-').map(Number);
  const [summary, cats] = await Promise.all([
    api('GET', `/expenses/summary?year=${y}&month=${m}`),
    api('GET', '/expenses/categories')
  ]);
  EXPENSES = summary.expenses || [];
  EXPENSE_CATS = cats;
  $('exp-month-label').textContent = new Date(y, m - 1).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  $('exp-export').href = `/api/expenses/export.csv?year=${y}&month=${m}&token=${S.token}`;
  const today = dateKey(new Date());
  if (!SELECTED_DAY || !EXPENSES.some(e => dateKey(parseISO(e.date)) === SELECTED_DAY)) {
    SELECTED_DAY = EXPENSES.some(e => dateKey(parseISO(e.date)) === today) ? today : null;
  }
  applyFilters(summary.by_category);
}

function applyFilters(categorySummary) {
  const q = (val('exp-search') || '').toLowerCase();
  FILTERED_EXPENSES = q
    ? EXPENSES.filter(e =>
        (e.category || '').toLowerCase().includes(q) ||
        (e.payment_method || '').toLowerCase().includes(q) ||
        (e.notes || '').toLowerCase().includes(q) ||
        String(e.amount).includes(q)
      )
    : [...EXPENSES];
  const [y, m] = val('exp-month').split('-').map(Number);
  renderCalendar(y, m);
  renderDayDetail();
  const total = FILTERED_EXPENSES.reduce((a, e) => a + e.amount, 0);
  $('exp-grand').textContent = `Total: ${money(total)}${q ? ` · ${FILTERED_EXPENSES.length} result${FILTERED_EXPENSES.length === 1 ? '' : 's'}` : ''}`;
  if (categorySummary !== undefined) renderExpenseCats(categorySummary);
  else {
    const totals = FILTERED_EXPENSES.reduce((acc, e) => {
      const c = e.category || 'Other';
      if (!acc[c]) acc[c] = { total: 0, count: 0 };
      acc[c].total += e.amount;
      acc[c].count += 1;
      return acc;
    }, {});
    renderExpenseCats(Object.entries(totals).map(([k, v]) => ({ category: k, ...v })));
  }
  renderMethodBreakdown(FILTERED_EXPENSES);
}

function expensesByDay(list) {
  const source = list || FILTERED_EXPENSES;
  const groups = {};
  for (const e of source) {
    const key = dateKey(parseISO(e.date));
    if (!groups[key]) groups[key] = [];
    groups[key].push(e);
  }
  Object.values(groups).forEach(l => l.sort((a, b) => b.id - a.id));
  return groups;
}

function daysInMonth(y, m) {
  return new Date(y, m, 0).getDate();
}

function renderCalendar(y, m) {
  const groups = expensesByDay();
  const firstDay = new Date(y, m - 1, 1).getDay(); // 0 = Sun
  const totalDays = daysInMonth(y, m);
  const todayKeyStr = dateKey(new Date());

  const headerDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  let html = `<div class="exp-cal"><div class="exp-cal-header">` +
    headerDays.map(d => `<div class="exp-cal-hday">${d}</div>`).join('') +
    `</div><div class="exp-cal-grid">`;

  // empty cells before the 1st
  for (let i = 0; i < firstDay; i++) {
    html += `<div class="exp-cal-cell empty"></div>`;
  }

  for (let d = 1; d <= totalDays; d++) {
    const key = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const items = groups[key] || [];
    const total = items.reduce((a, e) => a + e.amount, 0);
    const isToday = key === todayKeyStr;
    const isSelected = key === SELECTED_DAY;
    html += `<div class="exp-cal-cell ${isToday ? 'today' : ''} ${isSelected ? 'selected' : ''} ${items.length ? 'has-data' : ''}" data-day="${key}" onclick="selectDay('${key}')">
      <div class="exp-cal-date">${d}</div>
      <div class="exp-cal-total">${total > 0 ? money(total) : ''}</div>
      ${items.length ? `<div class="exp-cal-dot"></div>` : ''}
    </div>`;
  }
  html += `</div></div>`;
  $('exp-list').innerHTML = html;
}

function selectDay(key) {
  SELECTED_DAY = key;
  renderCalendar(+key.split('-')[0], +key.split('-')[1]);
  renderDayDetail();
}

function renderDayDetail() {
  let box = $('exp-day-detail');
  if (!box) {
    box = document.createElement('div');
    box.id = 'exp-day-detail';
    box.className = 'mt';
    $('page-expenses').appendChild(box);
  }
  if (!SELECTED_DAY) {
    box.innerHTML = `<div class="card empty">Select a day from the calendar above to view or add expenses.</div>`;
    return;
  }
  const groups = expensesByDay();
  const items = groups[SELECTED_DAY] || [];
  const dayTotal = items.reduce((a, e) => a + e.amount, 0);
  const d = new Date(SELECTED_DAY + 'T00:00:00');
  const label = d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });

  box.innerHTML = `<div class="card">
    <div class="day-header">
      <div class="day-title"><span class="day-date">${esc(label)}</span><span class="day-count">${items.length} expense${items.length === 1 ? '' : 's'}</span></div>
      <div class="day-total">${money(dayTotal)}</div>
    </div>
    <div class="day-body">
      ${items.length ? `<table class="day-table"><tbody>` +
        items.map(e => `<tr data-id="${e.id}">
          <td class="ico">${expIcon(e.category)}</td>
          <td>${cell(e.id, 'category', e.category)}</td>
          <td>${cell(e.id, 'payment_method', e.payment_method || 'Card')}</td>
          <td>${cell(e.id, 'notes', e.notes || '')}</td>
          <td class="num bold">${cell(e.id, 'amount', money(e.amount).replace(/^AED\s*/, ''), 'right')}</td>
          <td class="num"><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteExpense(${e.id})">×</button></td>
        </tr>`).join('') +
        `</tbody></table>` : `<div class="empty small" style="padding:20px 0">No expenses for this day.</div>`}
      <button class="btn btn-primary btn-sm" style="margin-top:12px" onclick="addExpenseToDay('${SELECTED_DAY}')">+ Add expense to this day</button>
    </div>
  </div>`;
  attachCellHandlers();
}

function cell(id, field, text, align = '') {
  return `<div class="sheet-cell ${align}" data-id="${id}" data-field="${field}" tabindex="0">${esc(text)}</div>`;
}

function attachCellHandlers() {
  document.querySelectorAll('.sheet-cell').forEach(c => {
    c.addEventListener('click', startEditCell);
  });
}

function startEditCell(e) {
  const el = e.currentTarget;
  if (EDITING && EDITING.el === el) return;
  if (EDITING) finishEdit();
  const id = +el.dataset.id;
  const field = el.dataset.field;
  const expense = EXPENSES.find(x => x.id === id);
  if (!expense) return;
  EDITING = { id, field, el, original: el.textContent };

  if (field === 'amount') {
    el.innerHTML = `<input type="number" step="0.01" class="input input-sm" style="text-align:right" value="${expense.amount}" onblur="finishEdit()" onkeydown="editKey(event)">`;
  } else if (field === 'category') {
    const opts = EXPENSE_CATS.map(c => `<option value="${esc(c)}">`).join('');
    el.innerHTML = `<input list="exp-cat-dl" class="input input-sm" value="${esc(expense.category)}" onblur="finishEdit()" onkeydown="editKey(event)"><datalist id="exp-cat-dl">${opts}</datalist>`;
  } else if (field === 'payment_method') {
    el.innerHTML = `<select class="input input-sm" onblur="finishEdit()" onkeydown="editKey(event)"><option value="Card" ${(expense.payment_method || 'Card') === 'Card' ? 'selected' : ''}>Card</option><option value="Cash" ${(expense.payment_method || 'Card') === 'Cash' ? 'selected' : ''}>Cash</option></select>`;
  } else {
    el.innerHTML = `<input type="text" class="input input-sm" value="${esc(expense.notes || '')}" onblur="finishEdit()" onkeydown="editKey(event)">`;
  }
  const input = el.querySelector('input, select');
  input.focus();
  if (input.select) input.select();
}

function editKey(e) {
  if (e.key === 'Enter') { e.preventDefault(); finishEdit(); }
  if (e.key === 'Escape') { e.preventDefault(); cancelEdit(); }
}

async function finishEdit() {
  if (!EDITING) return;
  const { id, field, el, original } = EDITING;
  const input = el.querySelector('input, select');
  let value = (input.value || '').trim();
  EDITING = null;

  const expense = EXPENSES.find(x => x.id === id);
  if (!expense) return;

  let payload = {};
  if (field === 'amount') {
    const amt = parseFloat(value);
    if (isNaN(amt) || amt < 0) { el.textContent = original; return; }
    payload.amount = amt;
  } else if (field === 'category') {
    if (!value) { el.textContent = original; return; }
    payload.category = value;
  } else if (field === 'payment_method') {
    payload.payment_method = value || 'Card';
  } else if (field === 'notes') {
    payload.notes = value || null;
  }

  try {
    await api('PUT', `/expenses/${id}`, payload);
    toast('Saved');
    loadExpenses();
  } catch (e) {
    el.textContent = original;
    throw e;
  }
}

function cancelEdit() {
  if (!EDITING) return;
  const { el, original } = EDITING;
  EDITING = null;
  el.textContent = original;
}

async function addExpenseRow() {
  const today = dateKey(new Date());
  SELECTED_DAY = today;
  await createExpense(today, true);
}

async function addExpenseToDay(dayKeyStr) {
  await createExpense(dayKeyStr, true);
}

async function createExpense(dayKeyStr, focusAmount) {
  const payload = {
    date: zonedToDate(dayKeyStr, '12:00').toISOString(),
    category: 'Other',
    payment_method: 'Card',
    amount: 0,
    notes: ''
  };
  const created = await api('POST', '/expenses/', payload);
  EXPENSES.unshift(created);
  SELECTED_DAY = dayKeyStr;
  loadExpenses();
  setTimeout(() => {
    const cell = document.querySelector(`.sheet-cell[data-id="${created.id}"][data-field="${focusAmount ? 'amount' : 'category'}"]`);
    if (cell) cell.click();
  }, 50);
}

async function deleteExpense(id) {
  if (!confirm('Delete this expense?')) return;
  await api('DELETE', `/expenses/${id}`);
  EXPENSES = EXPENSES.filter(e => e.id !== id);
  loadExpenses();
  toast('Deleted');
}

function renderExpenseCats(cats) {
  const box = $('exp-cats');
  if (!cats || !cats.length) { box.innerHTML = '<div class="empty small">No spending yet.</div>'; return; }
  const sorted = [...cats].sort((a, b) => b.total - a.total);
  box.innerHTML = `<table><thead><tr><th>Category</th><th class="num">Total</th></tr></thead><tbody>` +
    sorted.map(c => `<tr><td><span class="ico">${expIcon(c.category)}</span> ${esc(c.category)}</td><td class="num bold">${money(c.total)}</td></tr>`).join('') +
    `</tbody></table>`;
}

function renderMethodBreakdown(expenses) {
  const box = $('exp-methods');
  if (!expenses.length) { box.innerHTML = '<div class="empty small">No data yet.</div>'; return; }
  const totals = expenses.reduce((acc, e) => {
    const m = e.payment_method || 'Card';
    acc[m] = (acc[m] || 0) + e.amount;
    return acc;
  }, {});
  const rows = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  box.innerHTML = `<table><thead><tr><th>Type</th><th class="num">Total</th></tr></thead><tbody>` +
    rows.map(([m, t]) => `<tr><td><span class="badge badge-neutral">${esc(m)}</span></td><td class="num bold">${money(t)}</td></tr>`).join('') +
    `</tbody></table>`;
}
