import { useMemo, useState } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { api, getErrorMessage } from '../services/api';
import { useFetch } from '../hooks/useFetch';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/common/ToastProvider';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import Modal from '../components/common/Modal';
import DataTable from '../components/tables/DataTable';
import { LoadingState, ErrorState } from '../components/common/States';
import { Field, Input, Select, SearchInput } from '../components/common/Input';
import { ORDER_STATUSES, humanize, ROLES } from '../data/mockData';
import { formatCurrency, formatDate } from '../utils/format';

const emptyForm = {
  client_id: '', package_name: '', contracted_video_count: 1, pricing: 0, gst_tax: 0,
  total_invoice_amount: '', amount_received: 0, start_date: '', due_date: '',
  assigned_employee_id: '', status: 'new',
};

export default function Orders() {
  const { user } = useAuth();
  const toast = useToast();
  const isOwnerAdmin = user.role === ROLES.OWNER || user.role === ROLES.ADMIN;

  const { data: orders, loading, error, reload } = useFetch(() => api.getOrders(), []);
  const { data: clients } = useFetch(() => api.getClients(), []);
  const { data: employees } = useFetch(() => api.getEmployees(), []);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const clientMap = useMemo(() => {
    const m = {};
    (clients || []).forEach((c) => { m[c.id] = c.client_name; });
    return m;
  }, [clients]);

  const filtered = useMemo(() => {
    if (!orders) return [];
    return orders.filter((o) => {
      if (statusFilter && o.status !== statusFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return o.package_name?.toLowerCase().includes(q) || (clientMap[o.client_id] || '').toLowerCase().includes(q);
      }
      return true;
    });
  }, [orders, search, statusFilter, clientMap]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  }

  function openEdit(order) {
    setEditing(order);
    setForm({
      client_id: order.client_id, package_name: order.package_name || '',
      contracted_video_count: order.contracted_video_count ?? 1, pricing: order.pricing ?? 0,
      gst_tax: order.gst_tax ?? 0, total_invoice_amount: order.total_invoice_amount ?? '',
      amount_received: order.amount_received ?? 0, start_date: order.start_date || '',
      due_date: order.due_date || '', assigned_employee_id: order.assigned_employee_id || '',
      status: order.status || 'new',
    });
    setFormError('');
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    const payload = {
      ...form,
      contracted_video_count: Number(form.contracted_video_count) || 0,
      pricing: Number(form.pricing) || 0,
      gst_tax: Number(form.gst_tax) || 0,
      amount_received: Number(form.amount_received) || 0,
      total_invoice_amount: form.total_invoice_amount === '' ? undefined : Number(form.total_invoice_amount),
      assigned_employee_id: form.assigned_employee_id || null,
      start_date: form.start_date || null,
      due_date: form.due_date || null,
    };
    try {
      if (editing) {
        const { client_id, ...updatePayload } = payload;
        await api.updateOrder(editing.id, updatePayload);
        toast.showToast('Order updated.', 'success');
      } else {
        await api.createOrder(payload);
        toast.showToast('Order created.', 'success');
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(order) {
    if (!window.confirm(`Delete order "${order.package_name}"? This cannot be undone.`)) return;
    try {
      await api.deleteOrder(order.id);
      toast.showToast('Order deleted.', 'success');
      reload();
    } catch (err) {
      toast.showToast(getErrorMessage(err), 'error');
    }
  }

  if (loading) return <LoadingState label="Loading orders…" />;
  if (error) return <ErrorState onRetry={reload} />;

  const columns = [
    { key: 'package_name', label: 'Package', sortable: true },
    { key: 'client_id', label: 'Client', render: (o) => clientMap[o.client_id] || '—' },
    { key: 'contracted_video_count', label: 'Videos', align: 'right' },
    { key: 'total_invoice_amount', label: 'Invoice', align: 'right', render: (o) => formatCurrency(o.total_invoice_amount) },
    { key: 'outstanding_balance', label: 'Outstanding', align: 'right', render: (o) => formatCurrency(o.outstanding_balance) },
    { key: 'status', label: 'Status', render: (o) => <Badge status={o.status} /> },
    { key: 'due_date', label: 'Due', sortable: true, render: (o) => formatDate(o.due_date) },
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Orders</div>
          <h1 className="page-title">Orders & Packages</h1>
          <p className="page-subtitle">{orders.length} order{orders.length === 1 ? '' : 's'} across all clients.</p>
        </div>
        <Button variant="primary" icon={Plus} onClick={openCreate}>New Order</Button>
      </div>

      <Card padded={false}>
        <div style={{ display: 'flex', gap: 10, padding: '14px 16px', borderBottom: '1px solid var(--border-soft)' }}>
          <SearchInput value={search} onChange={setSearch} placeholder="Search orders…" />
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ maxWidth: 200 }}>
            <option value="">All statuses</option>
            {ORDER_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        <div className="card-pad">
          <DataTable
            columns={columns}
            rows={filtered}
            emptyTitle="No orders found"
            renderRowActions={(o) => (
              <>
                {isOwnerAdmin && <button className="icon-btn" title="Edit" onClick={() => openEdit(o)}><Pencil size={14} /></button>}
                {isOwnerAdmin && <button className="icon-btn" title="Delete" onClick={() => handleDelete(o)}><Trash2 size={14} /></button>}
              </>
            )}
          />
        </div>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? 'Edit Order' : 'New Order'} width={640}>
        <form onSubmit={handleSubmit}>
          <div className="grid grid-2" style={{ gap: 14 }}>
            <Field label="Client" required>
              <Select value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} required disabled={!!editing}>
                <option value="">Select client…</option>
                {(clients || []).map((c) => <option key={c.id} value={c.id}>{c.client_name}</option>)}
              </Select>
            </Field>
            <Field label="Package Name" required>
              <Input value={form.package_name} onChange={(e) => setForm({ ...form, package_name: e.target.value })} required />
            </Field>
            <Field label="Contracted Video Count">
              <Input type="number" min="0" value={form.contracted_video_count} onChange={(e) => setForm({ ...form, contracted_video_count: e.target.value })} />
            </Field>
            <Field label="Pricing (₹)">
              <Input type="number" min="0" value={form.pricing} onChange={(e) => setForm({ ...form, pricing: e.target.value })} />
            </Field>
            <Field label="GST / Tax (₹)">
              <Input type="number" min="0" value={form.gst_tax} onChange={(e) => setForm({ ...form, gst_tax: e.target.value })} />
            </Field>
            <Field label="Total Invoice (₹)" hint="Leave blank to auto-derive from pricing + GST">
              <Input type="number" min="0" value={form.total_invoice_amount} onChange={(e) => setForm({ ...form, total_invoice_amount: e.target.value })} />
            </Field>
            <Field label="Amount Received (₹)">
              <Input type="number" min="0" value={form.amount_received} onChange={(e) => setForm({ ...form, amount_received: e.target.value })} />
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {ORDER_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
              </Select>
            </Field>
            <Field label="Start Date">
              <Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            </Field>
            <Field label="Due Date">
              <Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            </Field>
            <Field label="Assigned Employee">
              <Select value={form.assigned_employee_id} onChange={(e) => setForm({ ...form, assigned_employee_id: e.target.value })}>
                <option value="">Unassigned</option>
                {(employees || []).map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
              </Select>
            </Field>
          </div>
          {formError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 10 }}>{formError}</p>}
          <div className="flex gap-8" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>{editing ? 'Save Changes' : 'Create Order'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
