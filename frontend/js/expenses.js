/* Monthly expense tracker — spreadsheet-like inline editing */
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
let EXPENSE_CATS = [];
let EDITING = null; // {id, field}

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
  EXPENSES.sort((a, b) => new Date(b.date) - new Date(a.date));
  $('exp-month-label').textContent = new Date(y, m - 1).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  $('exp-export').href = `/api/expenses/export.csv?year=${y}&month=${m}&token=${S.token}`;
  renderExpenseFilter();
  renderExpenseCats(summary.by_category);
  renderMethodBreakdown(EXPENSES);
}

function renderExpenseFilter() {
  const q = (val('exp-search') || '').toLowerCase();
  const list = q
    ? EXPENSES.filter(e =>
        (e.category || '').toLowerCase().includes(q) ||
        (e.payment_method || '').toLowerCase().includes(q) ||
        (e.notes || '').toLowerCase().includes(q) ||
        String(e.amount).includes(q)
      )
    : EXPENSES;
  renderExpenseList(list);
  const total = list.reduce((a, e) => a + e.amount, 0);
  $('exp-grand').textContent = `Total: ${money(total)}${q ? ` · ${list.length} result${list.length === 1 ? '' : 's'}` : ''}`;
}

function renderExpenseList(list) {
  const box = $('exp-list');
  if (!list.length && !EXPENSES.length) {
    box.innerHTML = `<table class="expense-sheet"><thead><tr><th>Date</th><th>Category</th><th>Type</th><th>Item / Notes</th><th class="num">Amount</th><th></th></tr></thead><tbody><tr><td colspan="6" class="empty">No expenses yet. Click <strong>+ Add row</strong>.</td></tr></tbody></table>`;
    return;
  }
  box.innerHTML = `<table class="expense-sheet"><thead><tr>
    <th>Date</th>
    <th style="width:38px"></th>
    <th>Category</th>
    <th>Type</th>
    <th>Item / Notes</th>
    <th class="num">Amount</th>
    <th style="width:60px"></th>
  </tr></thead><tbody>` +
    list.map(e => `<tr data-id="${e.id}">
      <td>${cell(e.id, 'date', fmtDate(e.date))}</td>
      <td class="ico">${expIcon(e.category)}</td>
      <td>${cell(e.id, 'category', e.category)}</td>
      <td>${cell(e.id, 'payment_method', e.payment_method || 'Card')}</td>
      <td>${cell(e.id, 'notes', e.notes || '')}</td>
      <td class="num bold">${cell(e.id, 'amount', money(e.amount).replace(/^AED\s*/, ''), 'right')}</td>
      <td class="num"><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteExpense(${e.id})">×</button></td>
    </tr>`).join('') +
    '</tbody></table>';
  attachCellHandlers();
}

function cell(id, field, text, align = '') {
  return `<div class="sheet-cell ${align}" data-id="${id}" data-field="${field}" tabindex="0">${esc(text)}</div>`;
}

function attachCellHandlers() {
  document.querySelectorAll('.sheet-cell').forEach(c => {
    c.addEventListener('click', startEditCell);
    c.addEventListener('focus', startEditCell);
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

  if (field === 'date') {
    el.innerHTML = `<input type="date" class="input input-sm" value="${dateKey(parseISO(expense.date))}" onblur="finishEdit()" onkeydown="editKey(event)">`;
    el.querySelector('input').focus();
  } else if (field === 'amount') {
    el.innerHTML = `<input type="number" step="0.01" class="input input-sm" style="text-align:right" value="${expense.amount}" onblur="finishEdit()" onkeydown="editKey(event)">`;
    el.querySelector('input').focus();
  } else if (field === 'category') {
    const opts = EXPENSE_CATS.map(c => `<option value="${esc(c)}">`).join('');
    el.innerHTML = `<input list="exp-cat-dl" class="input input-sm" value="${esc(expense.category)}" onblur="finishEdit()" onkeydown="editKey(event)"><datalist id="exp-cat-dl">${opts}</datalist>`;
    el.querySelector('input').focus();
  } else if (field === 'payment_method') {
    el.innerHTML = `<select class="input input-sm" onblur="finishEdit()" onkeydown="editKey(event)"><option value="Card" ${(expense.payment_method || 'Card') === 'Card' ? 'selected' : ''}>Card</option><option value="Cash" ${(expense.payment_method || 'Card') === 'Cash' ? 'selected' : ''}>Cash</option></select>`;
    el.querySelector('select').focus();
  } else {
    el.innerHTML = `<input type="text" class="input input-sm" value="${esc(expense.notes || '')}" onblur="finishEdit()" onkeydown="editKey(event)">`;
    el.querySelector('input').focus();
  }
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
  if (field === 'date') {
    if (!value) { el.textContent = original; return; }
    payload.date = zonedToDate(value, '12:00').toISOString();
  } else if (field === 'amount') {
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
  const [y, m] = val('exp-month').split('-').map(Number);
  const today = new Date(y, m - 1, 1);
  const payload = {
    date: zonedToDate(dateKey(today), '12:00').toISOString(),
    category: 'Other',
    payment_method: 'Card',
    amount: 0,
    notes: ''
  };
  const created = await api('POST', '/expenses/', payload);
  EXPENSES.unshift(created);
  renderExpenseFilter();
  setTimeout(() => {
    const cell = document.querySelector(`.sheet-cell[data-id="${created.id}"][data-field="amount"]`);
    if (cell) cell.click();
  }, 50);
}

async function deleteExpense(id) {
  if (!confirm('Delete this row?')) return;
  await api('DELETE', `/expenses/${id}`);
  EXPENSES = EXPENSES.filter(e => e.id !== id);
  renderExpenseFilter();
  renderExpenseCats(EXPENSES.reduce((acc, e) => {
    const existing = acc.find(x => x.category === e.category);
    if (existing) { existing.total += e.amount; existing.count += 1; }
    else acc.push({ category: e.category, total: e.amount, count: 1 });
    return acc;
  }, []));
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
