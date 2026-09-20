import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Pencil, Trash2, ArrowRight } from 'lucide-react';
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
import { CLIENT_STATUSES, humanize, ROLES } from '../data/mockData';
import { formatDate } from '../utils/format';

const emptyForm = {
  client_name: '', company_name: '', email: '', phone: '', whatsapp: '',
  brand_name: '', industry: '', gst_tax_id: '', source: '', status: 'lead',
  assigned_employee_id: '', notes: '',
};

export default function Clients() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const isOwnerAdmin = user.role === ROLES.OWNER || user.role === ROLES.ADMIN;

  const { data: clients, loading, error, reload } = useFetch(() => api.getClients(), []);
  const { data: employees } = useFetch(() => api.getEmployees(), []);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const employeeMap = useMemo(() => {
    const m = {};
    (employees || []).forEach((e) => { m[e.id] = e.full_name; });
    return m;
  }, [employees]);

  const filtered = useMemo(() => {
    if (!clients) return [];
    return clients.filter((c) => {
      if (statusFilter && c.status !== statusFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          c.client_name?.toLowerCase().includes(q) ||
          c.company_name?.toLowerCase().includes(q) ||
          c.brand_name?.toLowerCase().includes(q) ||
          c.email?.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [clients, search, statusFilter]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  }

  function openEdit(client) {
    setEditing(client);
    setForm({
      client_name: client.client_name || '', company_name: client.company_name || '',
      email: client.email || '', phone: client.phone || '', whatsapp: client.whatsapp || '',
      brand_name: client.brand_name || '', industry: client.industry || '',
      gst_tax_id: client.gst_tax_id || '', source: client.source || '',
      status: client.status || 'lead', assigned_employee_id: client.assigned_employee_id || '',
      notes: client.notes || '',
    });
    setFormError('');
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    const payload = { ...form, assigned_employee_id: form.assigned_employee_id || null };
    try {
      if (editing) {
        await api.updateClient(editing.id, payload);
        toast.showToast('Client updated.', 'success');
      } else {
        await api.createClient(payload);
        toast.showToast('Client created.', 'success');
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(client) {
    if (!window.confirm(`Delete ${client.client_name}? This cannot be undone.`)) return;
    try {
      await api.deleteClient(client.id);
      toast.showToast('Client deleted.', 'success');
      reload();
    } catch (err) {
      toast.showToast(getErrorMessage(err), 'error');
    }
  }

  if (loading) return <LoadingState label="Loading clients…" />;
  if (error) return <ErrorState onRetry={reload} />;

  const columns = [
    { key: 'client_name', label: 'Client', sortable: true, render: (c) => (
      <div>
        <div style={{ fontWeight: 600 }}>{c.client_name}</div>
        <div className="tmuted" style={{ fontSize: 11.5 }}>{c.company_name || '—'}</div>
      </div>
    ) },
    { key: 'brand_name', label: 'Brand', render: (c) => c.brand_name || '—' },
    { key: 'industry', label: 'Industry', render: (c) => c.industry || '—' },
    { key: 'status', label: 'Status', render: (c) => <Badge status={c.status} /> },
    { key: 'assigned_employee_id', label: 'Assigned To', render: (c) => employeeMap[c.assigned_employee_id] || '—' },
    { key: 'created_at', label: 'Onboarded', sortable: true, render: (c) => formatDate(c.created_at) },
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Clients</div>
          <h1 className="page-title">Client Management</h1>
          <p className="page-subtitle">{clients.length} client{clients.length === 1 ? '' : 's'} on record.</p>
        </div>
        <Button variant="primary" icon={Plus} onClick={openCreate}>New Client</Button>
      </div>

      <Card padded={false}>
        <div style={{ display: 'flex', gap: 10, padding: '14px 16px', borderBottom: '1px solid var(--border-soft)' }}>
          <SearchInput value={search} onChange={setSearch} placeholder="Search clients…" />
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ maxWidth: 180 }}>
            <option value="">All statuses</option>
            {CLIENT_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        <div className="card-pad">
          <DataTable
            columns={columns}
            rows={filtered}
            emptyTitle="No clients found"
            emptyDescription="Try adjusting your search or filters."
            renderRowActions={(c) => (
              <>
                <button className="icon-btn" title="View" onClick={() => navigate(`/clients/${c.id}`)}><ArrowRight size={14} /></button>
                {isOwnerAdmin && <button className="icon-btn" title="Edit" onClick={() => openEdit(c)}><Pencil size={14} /></button>}
                {isOwnerAdmin && <button className="icon-btn" title="Delete" onClick={() => handleDelete(c)}><Trash2 size={14} /></button>}
              </>
            )}
          />
        </div>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? 'Edit Client' : 'New Client'} width={640}>
        <form onSubmit={handleSubmit}>
          <div className="grid grid-2" style={{ gap: 14 }}>
            <Field label="Client Name" required>
              <Input value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} required />
            </Field>
            <Field label="Company Name">
              <Input value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} />
            </Field>
            <Field label="Email" required>
              <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
            </Field>
            <Field label="Phone">
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            <Field label="WhatsApp">
              <Input value={form.whatsapp} onChange={(e) => setForm({ ...form, whatsapp: e.target.value })} />
            </Field>
            <Field label="Brand / Business Name">
              <Input value={form.brand_name} onChange={(e) => setForm({ ...form, brand_name: e.target.value })} />
            </Field>
            <Field label="Industry">
              <Input value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} />
            </Field>
            <Field label="GST / Tax ID">
              <Input value={form.gst_tax_id} onChange={(e) => setForm({ ...form, gst_tax_id: e.target.value })} />
            </Field>
            <Field label="Source">
              <Input value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder="Referral, Instagram, …" />
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {CLIENT_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
              </Select>
            </Field>
            <Field label="Assigned Employee">
              <Select value={form.assigned_employee_id} onChange={(e) => setForm({ ...form, assigned_employee_id: e.target.value })}>
                <option value="">Unassigned</option>
                {(employees || []).map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Notes" hint="Internal notes, brand kit links, etc.">
            <textarea className="input" rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </Field>
          {formError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 10 }}>{formError}</p>}
          <div className="flex gap-8" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>{editing ? 'Save Changes' : 'Create Client'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
