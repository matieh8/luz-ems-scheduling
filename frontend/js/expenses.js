/* Monthly expense tracker — vertical day cards, 1st to last day of month */
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
const PRESET_CATS = ['Fast food', 'Groceries', 'Fuel', 'Transport', 'Utilities', 'Subscriptions', 'Shopping', 'Health', 'Rent', 'Entertainment', 'Education', 'Travel', 'Gift'];
let EXPENSES = [];
let FILTERED_EXPENSES = [];
let EXPENSE_CATS = [];
let EDITING = null;

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
  // remove old detail panel from previous layout if present
  const old = $('exp-day-detail');
  if (old) old.remove();
  const [y, m] = val('exp-month').split('-').map(Number);
  const [summary, cats] = await Promise.all([
    api('GET', `/expenses/summary?year=${y}&month=${m}`),
    api('GET', '/expenses/categories')
  ]);
  EXPENSES = summary.expenses || [];
  EXPENSE_CATS = cats;
  $('exp-month-label').textContent = new Date(y, m - 1).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  $('exp-export').href = `/api/expenses/export.csv?year=${y}&month=${m}&token=${S.token}`;
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
  renderDays();
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

function renderDays() {
  const box = $('exp-list');
  const [y, m] = val('exp-month').split('-').map(Number);
  const totalDays = daysInMonth(y, m);
  const groups = expensesByDay();
  const todayKeyStr = dateKey(new Date());

  let html = '';
  for (let d = 1; d <= totalDays; d++) {
    const key = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const items = groups[key] || [];
    const dayTotal = items.reduce((a, e) => a + e.amount, 0);
    const dateObj = new Date(y, m - 1, d);
    const isToday = key === todayKeyStr;
    const label = dateObj.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });

    html += `<div class="day-card ${isToday ? 'today' : ''} ${items.length ? 'has-data' : 'empty'}" data-day="${key}">
      <div class="day-header">
        <div class="day-title"><span class="day-date">${esc(label)}</span>${items.length ? `<span class="day-count">${items.length} expense${items.length === 1 ? '' : 's'}</span>` : '<span class="day-count muted">No expenses</span>'}</div>
        <div class="day-total">${dayTotal > 0 ? money(dayTotal) : ''}</div>
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
          `</tbody></table>` : ''}
        <button class="btn btn-ghost btn-sm add-to-day" onclick="addExpenseToDay('${key}')">+ Add expense</button>
      </div>
    </div>`;
  }
  box.innerHTML = html;
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
    const current = expense.category || 'Other';
    const isPreset = PRESET_CATS.includes(current);
    const opts = PRESET_CATS.map(c => `<option value="${esc(c)}" ${c === current ? 'selected' : ''}>${esc(c)}</option>`).join('');
    el.innerHTML = `<div class="cat-edit-wrap" onclick="event.stopPropagation()">` +
      `<select id="cat-select-${expense.id}" class="input input-sm" onchange="onCategoryChange(${expense.id})" onblur="finishEdit()" onkeydown="editKey(event)">${opts}<option value="__other__" ${!isPreset ? 'selected' : ''}>Other</option></select>` +
      `<input id="cat-other-${expense.id}" type="text" class="input input-sm" style="margin-top:6px;display:${!isPreset ? 'block' : 'none'}" value="${esc(!isPreset ? current : '')}" placeholder="Type category..." onblur="finishEdit()" onkeydown="editKey(event)">` +
      `</div>`;
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

function onCategoryChange(id) {
  const select = $(`cat-select-${id}`);
  const other = $(`cat-other-${id}`);
  if (!select || !other) return;
  if (select.value === '__other__') {
    other.style.display = 'block';
    other.focus();
  } else {
    other.style.display = 'none';
  }
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
    const select = el.querySelector('select');
    const other = el.querySelector('input[type="text"]');
    let cat = select ? select.value : value;
    if (cat === '__other__') {
      cat = other ? other.value.trim() : '';
    }
    if (!cat) { el.textContent = original; return; }
    payload.category = cat;
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
  loadExpenses();
  setTimeout(() => {
    const cell = document.querySelector(`.sheet-cell[data-id="${created.id}"][data-field="${focusAmount ? 'amount' : 'category'}"]`);
    if (cell) cell.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (cell) cell.click();
  }, 60);
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
