import { useMemo, useState } from 'react';
import { Plus, IndianRupee, Wallet, Users2, TrendingUp } from 'lucide-react';
import { api, getErrorMessage } from '../services/api';
import { useFetch } from '../hooks/useFetch';
import { useToast } from '../components/common/ToastProvider';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import Modal from '../components/common/Modal';
import KpiCard from '../components/dashboard/KpiCard';
import DataTable from '../components/tables/DataTable';
import { Field, Input, Select } from '../components/common/Input';
import { LoadingState, ErrorState } from '../components/common/States';
import { EXPENSE_CATEGORIES, PAYOUT_STATUSES, humanize } from '../data/mockData';
import { formatCurrency, formatDate } from '../utils/format';

const TABS = [
  { key: 'payments', label: 'Client Payments' },
  { key: 'expenses', label: 'Agency Expenses' },
  { key: 'payouts', label: 'Creator Payouts' },
];

const emptyPaymentForm = { client_id: '', order_id: '', invoice_amount: '', amount_received: '', payment_date: '', method: '', transaction_ref: '', notes: '' };
const emptyExpenseForm = { category: 'other', amount: '', date: '', receipt_file: '', notes: '' };
const emptyPayoutForm = { creator_id: '', order_id: '', video_count: '', contracted_rate: '', reference: '' };

export default function Financials() {
  const [tab, setTab] = useState('payments');
  const payments = useFetch(() => api.getPayments(), []);
  const expenses = useFetch(() => api.getExpenses(), []);
  const payouts = useFetch(() => api.getPayouts(), []);
  const summary = useFetch(() => api.getFinancialSummary(), []);
  const clients = useFetch(() => api.getClients(), []);
  const orders = useFetch(() => api.getOrders(), []);
  const creators = useFetch(() => api.getCreators(), []);
  const { showToast } = useToast();

  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const [expenseModalOpen, setExpenseModalOpen] = useState(false);
  const [payoutModalOpen, setPayoutModalOpen] = useState(false);
  const [paymentForm, setPaymentForm] = useState(emptyPaymentForm);
  const [expenseForm, setExpenseForm] = useState(emptyExpenseForm);
  const [payoutForm, setPayoutForm] = useState(emptyPayoutForm);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  const clientMap = useMemo(() => {
    const m = {};
    (clients.data || []).forEach((c) => { m[c.id] = c.client_name; });
    return m;
  }, [clients.data]);
  const creatorMap = useMemo(() => {
    const m = {};
    (creators.data || []).forEach((c) => { m[c.id] = c.name; });
    return m;
  }, [creators.data]);
  const ordersForPaymentClient = useMemo(
    () => (orders.data || []).filter((o) => o.client_id === paymentForm.client_id),
    [orders.data, paymentForm.client_id]
  );

  const loading = payments.loading || expenses.loading || payouts.loading || summary.loading;
  const error = payments.error || expenses.error || payouts.error || summary.error;
  if (loading) return <LoadingState label="Loading financials…" />;
  if (error) return <ErrorState />;

  async function handleCreatePayment(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await api.createPayment({
        client_id: paymentForm.client_id,
        order_id: paymentForm.order_id,
        invoice_amount: Number(paymentForm.invoice_amount),
        amount_received: paymentForm.amount_received ? Number(paymentForm.amount_received) : 0,
        payment_date: paymentForm.payment_date || null,
        method: paymentForm.method || null,
        transaction_ref: paymentForm.transaction_ref || null,
        notes: paymentForm.notes || null,
      });
      showToast('Payment recorded.', 'success');
      setPaymentModalOpen(false);
      setPaymentForm(emptyPaymentForm);
      payments.reload();
      summary.reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateExpense(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await api.createExpense({
        category: expenseForm.category,
        amount: Number(expenseForm.amount),
        date: expenseForm.date,
        receipt_file: expenseForm.receipt_file || null,
        notes: expenseForm.notes || null,
      });
      showToast('Expense logged.', 'success');
      setExpenseModalOpen(false);
      setExpenseForm(emptyExpenseForm);
      expenses.reload();
      summary.reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleCreatePayout(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await api.createPayout({
        creator_id: payoutForm.creator_id,
        order_id: payoutForm.order_id || null,
        video_count: payoutForm.video_count ? Number(payoutForm.video_count) : 0,
        contracted_rate: payoutForm.contracted_rate ? Number(payoutForm.contracted_rate) : 0,
        reference: payoutForm.reference || null,
      });
      showToast('Creator payout created.', 'success');
      setPayoutModalOpen(false);
      setPayoutForm(emptyPayoutForm);
      payouts.reload();
      summary.reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function updatePayoutStatus(id, status) {
    try {
      await api.updatePayout(id, { status });
      showToast(`Payout marked "${humanize(status)}".`, 'success');
      payouts.reload();
      summary.reload();
    } catch (err) {
      showToast(getErrorMessage(err), 'error');
    }
  }

  function openCreateModal() {
    setFormError('');
    if (tab === 'payments') setPaymentModalOpen(true);
    else if (tab === 'expenses') setExpenseModalOpen(true);
    else setPayoutModalOpen(true);
  }

  const s = summary.data;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Financial Modules</div>
          <h1 className="page-title">Financials</h1>
          <p className="page-subtitle">Receivables, agency expenses and creator payouts in one ledger.</p>
        </div>
        <Button variant="primary" icon={Plus} onClick={openCreateModal}>
          {tab === 'payments' ? 'Record Payment' : tab === 'expenses' ? 'Log Expense' : 'New Payout'}
        </Button>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 20 }}>
        <KpiCard icon={IndianRupee} label="Total Receivables" value={formatCurrency(s.total_receivables)} tint="red" />
        <KpiCard icon={Wallet} label="Expenses (This Month)" value={formatCurrency(s.monthly_expenses)} tint="amber" />
        <KpiCard icon={Users2} label="Creator Payouts (This Month)" value={formatCurrency(s.creator_payouts_total)} tint="purple" />
        <KpiCard icon={TrendingUp} label="Est. Net Profit (This Month)" value={formatCurrency(s.estimated_net_profit)} tint="green" />
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <div key={t.key} className={`tab ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>{t.label}</div>
        ))}
      </div>

      {tab === 'payments' && (
        <Card padded={false}>
          <DataTable
            rows={payments.data}
            emptyTitle="No payments recorded"
            columns={[
              { key: 'client_id', label: 'Client', render: (p) => clientMap[p.client_id] || '—' },
              { key: 'invoice_amount', label: 'Invoice', align: 'right', render: (p) => formatCurrency(p.invoice_amount) },
              { key: 'amount_received', label: 'Received', align: 'right', render: (p) => formatCurrency(p.amount_received) },
              { key: 'pending_balance', label: 'Pending', align: 'right', sortable: true, render: (p) => formatCurrency(p.pending_balance) },
              { key: 'payment_date', label: 'Last Payment', render: (p) => formatDate(p.payment_date) },
              { key: 'method', label: 'Method', render: (p) => p.method || '—' },
              { key: 'status', label: 'Status', render: (p) => <Badge status={p.status} /> },
            ]}
          />
        </Card>
      )}

      {tab === 'expenses' && (
        <Card padded={false}>
          <DataTable
            rows={expenses.data}
            emptyTitle="No expenses recorded"
            columns={[
              { key: 'category', label: 'Category', sortable: true, render: (e) => <Badge status={e.category} /> },
              { key: 'amount', label: 'Amount', align: 'right', sortable: true, render: (e) => formatCurrency(e.amount) },
              { key: 'date', label: 'Date', render: (e) => formatDate(e.date) },
              { key: 'notes', label: 'Note', render: (e) => e.notes || '—' },
            ]}
          />
        </Card>
      )}

      {tab === 'payouts' && (
        <Card padded={false}>
          <DataTable
            rows={payouts.data}
            emptyTitle="No payouts recorded"
            columns={[
              { key: 'creator_id', label: 'Creator', sortable: true, render: (p) => creatorMap[p.creator_id] || '—' },
              { key: 'order_id', label: 'Order', render: (p) => p.order_id ? `#${p.order_id.slice(0, 8)}` : '—' },
              { key: 'video_count', label: 'Videos', align: 'right' },
              { key: 'total_payout', label: 'Total Payout', align: 'right', sortable: true, render: (p) => formatCurrency(p.total_payout) },
              { key: 'payment_date', label: 'Paid On', render: (p) => formatDate(p.payment_date) },
              {
                key: 'status',
                label: 'Status',
                render: (p) => (
                  <Select value={p.status} onChange={(e) => updatePayoutStatus(p.id, e.target.value)} style={{ padding: '5px 8px', fontSize: 12 }}>
                    {PAYOUT_STATUSES.map((st) => <option key={st} value={st}>{humanize(st)}</option>)}
                  </Select>
                ),
              },
            ]}
          />
        </Card>
      )}

      {/* --- Record payment --- */}
      <Modal open={paymentModalOpen} onClose={() => setPaymentModalOpen(false)} title="Record a payment" width={560}>
        <form onSubmit={handleCreatePayment}>
          <div className="grid grid-2" style={{ gap: 14 }}>
            <Field label="Client" required>
              <Select value={paymentForm.client_id} onChange={(e) => setPaymentForm({ ...paymentForm, client_id: e.target.value, order_id: '' })} required>
                <option value="">Select client…</option>
                {(clients.data || []).map((c) => <option key={c.id} value={c.id}>{c.client_name}</option>)}
              </Select>
            </Field>
            <Field label="Order" required>
              <Select value={paymentForm.order_id} onChange={(e) => setPaymentForm({ ...paymentForm, order_id: e.target.value })} required disabled={!paymentForm.client_id}>
                <option value="">Select order…</option>
                {ordersForPaymentClient.map((o) => <option key={o.id} value={o.id}>{o.package_name}</option>)}
              </Select>
            </Field>
            <Field label="Invoice Amount" required>
              <Input type="number" min="0" value={paymentForm.invoice_amount} onChange={(e) => setPaymentForm({ ...paymentForm, invoice_amount: e.target.value })} required />
            </Field>
            <Field label="Amount Received">
              <Input type="number" min="0" value={paymentForm.amount_received} onChange={(e) => setPaymentForm({ ...paymentForm, amount_received: e.target.value })} />
            </Field>
            <Field label="Payment Date">
              <Input type="date" value={paymentForm.payment_date} onChange={(e) => setPaymentForm({ ...paymentForm, payment_date: e.target.value })} />
            </Field>
            <Field label="Method">
              <Input value={paymentForm.method} onChange={(e) => setPaymentForm({ ...paymentForm, method: e.target.value })} placeholder="UPI, Bank Transfer…" />
            </Field>
            <Field label="Transaction Ref">
              <Input value={paymentForm.transaction_ref} onChange={(e) => setPaymentForm({ ...paymentForm, transaction_ref: e.target.value })} />
            </Field>
          </div>
          <Field label="Notes">
            <Input value={paymentForm.notes} onChange={(e) => setPaymentForm({ ...paymentForm, notes: e.target.value })} />
          </Field>
          {formError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 10 }}>{formError}</p>}
          <div className="form-actions">
            <Button type="button" variant="ghost" onClick={() => setPaymentModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>Record payment</Button>
          </div>
        </form>
      </Modal>

      {/* --- Log expense --- */}
      <Modal open={expenseModalOpen} onClose={() => setExpenseModalOpen(false)} title="Log an expense" width={480}>
        <form onSubmit={handleCreateExpense}>
          <div className="grid grid-2" style={{ gap: 14 }}>
            <Field label="Category" required>
              <Select value={expenseForm.category} onChange={(e) => setExpenseForm({ ...expenseForm, category: e.target.value })}>
                {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
              </Select>
            </Field>
            <Field label="Amount" required>
              <Input type="number" min="0.01" step="0.01" value={expenseForm.amount} onChange={(e) => setExpenseForm({ ...expenseForm, amount: e.target.value })} required />
            </Field>
            <Field label="Date" required>
              <Input type="date" value={expenseForm.date} onChange={(e) => setExpenseForm({ ...expenseForm, date: e.target.value })} required />
            </Field>
            <Field label="Receipt File (optional)">
              <Input value={expenseForm.receipt_file} onChange={(e) => setExpenseForm({ ...expenseForm, receipt_file: e.target.value })} placeholder="https://…" />
            </Field>
          </div>
          <Field label="Notes">
            <Input value={expenseForm.notes} onChange={(e) => setExpenseForm({ ...expenseForm, notes: e.target.value })} />
          </Field>
          {formError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 10 }}>{formError}</p>}
          <div className="form-actions">
            <Button type="button" variant="ghost" onClick={() => setExpenseModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>Log expense</Button>
          </div>
        </form>
      </Modal>

      {/* --- New creator payout --- */}
      <Modal open={payoutModalOpen} onClose={() => setPayoutModalOpen(false)} title="Create a creator payout" width={520}>
        <form onSubmit={handleCreatePayout}>
          <div className="grid grid-2" style={{ gap: 14 }}>
            <Field label="Creator" required>
              <Select value={payoutForm.creator_id} onChange={(e) => setPayoutForm({ ...payoutForm, creator_id: e.target.value })} required>
                <option value="">Select creator…</option>
                {(creators.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </Field>
            <Field label="Order (optional)">
              <Select value={payoutForm.order_id} onChange={(e) => setPayoutForm({ ...payoutForm, order_id: e.target.value })}>
                <option value="">No order</option>
                {(orders.data || []).map((o) => <option key={o.id} value={o.id}>{o.package_name}</option>)}
              </Select>
            </Field>
            <Field label="Video Count">
              <Input type="number" min="0" value={payoutForm.video_count} onChange={(e) => setPayoutForm({ ...payoutForm, video_count: e.target.value })} />
            </Field>
            <Field label="Contracted Rate">
              <Input type="number" min="0" value={payoutForm.contracted_rate} onChange={(e) => setPayoutForm({ ...payoutForm, contracted_rate: e.target.value })} />
            </Field>
          </div>
          <Field label="Reference">
            <Input value={payoutForm.reference} onChange={(e) => setPayoutForm({ ...payoutForm, reference: e.target.value })} />
          </Field>
          {formError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 10 }}>{formError}</p>}
          <div className="form-actions">
            <Button type="button" variant="ghost" onClick={() => setPayoutModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>Create payout</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
