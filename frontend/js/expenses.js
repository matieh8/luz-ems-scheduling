/* Monthly expense tracker */
let EXPENSE_CATS = [];

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
  EXPENSE_CATS = cats;
  renderExpenseList(summary.expenses);
  renderExpenseCats(summary.by_category, summary.grand_total);
  $('exp-month-label').textContent = new Date(y, m - 1).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  $('exp-grand').textContent = `Total: ${money(summary.grand_total)}`;
}

function renderExpenseList(list) {
  const box = $('exp-list');
  if (!list.length) { box.innerHTML = '<div class="card empty">No expenses this month.</div>'; return; }
  box.innerHTML = `<table><thead><tr><th>Date</th><th>Category</th><th>Notes</th><th class="num">Amount</th><th></th></tr></thead><tbody>` +
    list.map(e => `<tr>
      <td class="mono">${fmtDate(e.date)}</td>
      <td><span class="chip">${esc(e.category)}</span></td>
      <td class="small muted">${esc(e.notes || '')}</td>
      <td class="num bold">${money(e.amount)}</td>
      <td class="num"><button class="btn btn-ghost btn-xs" onclick="editExpense(${e.id})">Edit</button><button class="btn btn-ghost btn-xs" style="color:var(--bad)" onclick="deleteExpense(${e.id})">Delete</button></td>
    </tr>`).join('') + '</tbody></table>';
}

function renderExpenseCats(cats, grand) {
  const box = $('exp-cats');
  if (!cats.length) { box.innerHTML = '<div class="empty small">No spending yet.</div>'; return; }
  box.innerHTML = `<table><thead><tr><th>Category</th><th class="num">Total</th></tr></thead><tbody>` +
    cats.map(c => `<tr>
      <td><span class="chip">${esc(c.category)}</span></td>
      <td class="num bold">${money(c.total)}</td>
    </tr>`).join('') +
    `<tr style="border-top:2px solid var(--border);font-weight:700"><td>Total</td><td class="num">${money(grand)}</td></tr>` +
    '</tbody></table>';
}

function openExpenseModal() {
  $('expense-modal-title').textContent = 'Add expense';
  setVal('expense-id', '');
  setVal('expense-date', todayKey());
  setVal('expense-amount', '');
  setVal('expense-category', '');
  setVal('expense-notes', '');
  updateExpenseCatOptions();
  openModal('expense-modal');
}

async function editExpense(id) {
  const list = await api('GET', `/expenses/?year=${val('exp-month').split('-')[0]}&month=${val('exp-month').split('-')[1]}`);
  const e = list.find(x => x.id === id);
  if (!e) return toast('Expense not found', true);
  $('expense-modal-title').textContent = 'Edit expense';
  setVal('expense-id', e.id);
  setVal('expense-date', dateKey(parseISO(e.date)));
  setVal('expense-amount', e.amount);
  setVal('expense-category', e.category);
  setVal('expense-notes', e.notes || '');
  updateExpenseCatOptions();
  openModal('expense-modal');
}

function updateExpenseCatOptions() {
  const dl = $('expense-cat-options');
  dl.innerHTML = EXPENSE_CATS.map(c => `<option value="${esc(c)}">`).join('');
}

async function saveExpense() {
  guard(async () => {
    const id = val('expense-id');
    const date = val('expense-date');
    const amount = parseFloat(val('expense-amount'));
    const category = val('expense-category').trim();
    const notes = val('expense-notes').trim() || null;
    if (!date) throw new Error('Date is required');
    if (!category) throw new Error('Category is required');
    if (!amount || amount <= 0) throw new Error('Enter a positive amount');
    const payload = { date: zonedToDate(date, '12:00').toISOString(), category, amount, notes };
    if (id) await api('PUT', `/expenses/${id}`, payload);
    else await api('POST', '/expenses/', payload);
    closeModal('expense-modal');
    toast(id ? 'Expense updated' : 'Expense added');
    loadExpenses();
  });
}

function deleteExpense(id) {
  confirmBox('Delete expense', '<p>Delete this expense?</p>', 'Delete', async () => {
    await api('DELETE', `/expenses/${id}`);
    toast('Expense deleted');
    loadExpenses();
  }, 'btn-danger');
}
