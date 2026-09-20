import { useMemo, useState } from 'react';
import { Plus, Pencil, Trash2, ListChecks } from 'lucide-react';
import { api, getErrorMessage } from '../services/api';
import { useFetch } from '../hooks/useFetch';
import { useToast } from '../components/common/ToastProvider';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import Modal from '../components/common/Modal';
import DataTable from '../components/tables/DataTable';
import { LoadingState, ErrorState } from '../components/common/States';
import { Field, Input, Select, SearchInput } from '../components/common/Input';
import { SHOOT_STATUSES, humanize } from '../data/mockData';
import { formatDateTimeISO } from '../utils/format';

const emptyForm = {
  client_id: '', order_id: '', date_time: '', location: '', creator_id: '',
  cameraman: '', shoot_manager_id: '', shooting_assistant: '', special_notes: '', status: 'scheduled',
};

const CHECKLIST_ITEMS = [
  { key: 'checklist_script_approved', label: 'Script approved' },
  { key: 'checklist_creator_confirmed', label: 'Creator confirmed' },
  { key: 'checklist_location_permission', label: 'Location permission' },
  { key: 'checklist_client_product_received', label: 'Client product received' },
  { key: 'checklist_team_briefed', label: 'Team briefed' },
  { key: 'footage_uploaded', label: 'Footage uploaded' },
  { key: 'raw_file_integrity_checked', label: 'Raw file integrity checked' },
  { key: 'reshoot_flagged', label: 'Reshoot flagged' },
];

export default function Shoots() {
  const toast = useToast();
  const { data: shoots, loading, error, reload } = useFetch(() => api.getShoots(), []);
  const { data: clients } = useFetch(() => api.getClients(), []);
  const { data: orders } = useFetch(() => api.getOrders(), []);
  const { data: creators } = useFetch(() => api.getCreators(), []);
  const { data: employees } = useFetch(() => api.getEmployees(), []);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [checklistShoot, setChecklistShoot] = useState(null);

  const clientMap = useMemo(() => {
    const m = {}; (clients || []).forEach((c) => { m[c.id] = c.client_name; }); return m;
  }, [clients]);
  const managers = useMemo(() => (employees || []).filter((e) => e.sub_role === 'shoot_manager' || e.role === 'owner' || e.role === 'admin'), [employees]);
  const ordersForClient = useMemo(() => (orders || []).filter((o) => o.client_id === form.client_id), [orders, form.client_id]);

  const filtered = useMemo(() => {
    if (!shoots) return [];
    return shoots.filter((s) => {
      if (statusFilter && s.status !== statusFilter) return false;
      if (search) return (clientMap[s.client_id] || '').toLowerCase().includes(search.toLowerCase()) || (s.location || '').toLowerCase().includes(search.toLowerCase());
      return true;
    });
  }, [shoots, search, statusFilter, clientMap]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  }

  function openEdit(shoot) {
    setEditing(shoot);
    setForm({
      client_id: shoot.client_id, order_id: shoot.order_id,
      date_time: shoot.date_time ? shoot.date_time.slice(0, 16) : '', location: shoot.location || '',
      creator_id: shoot.creator_id || '', cameraman: shoot.cameraman || '',
      shoot_manager_id: shoot.shoot_manager_id || '', shooting_assistant: shoot.shooting_assistant || '',
      special_notes: shoot.special_notes || '', status: shoot.status || 'scheduled',
    });
    setFormError('');
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      const iso = form.date_time ? new Date(form.date_time).toISOString() : null;
      if (editing) {
        await api.updateShoot(editing.id, {
          date_time: iso, location: form.location, creator_id: form.creator_id || null,
          cameraman: form.cameraman, shoot_manager_id: form.shoot_manager_id || null,
          shooting_assistant: form.shooting_assistant, special_notes: form.special_notes, status: form.status,
        });
        toast.showToast('Shoot updated.', 'success');
      } else {
        await api.createShoot({
          client_id: form.client_id, order_id: form.order_id, date_time: iso, location: form.location,
          creator_id: form.creator_id || null, cameraman: form.cameraman,
          shoot_manager_id: form.shoot_manager_id || null, shooting_assistant: form.shooting_assistant,
          special_notes: form.special_notes,
        });
        toast.showToast('Shoot scheduled.', 'success');
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(shoot) {
    if (!window.confirm('Cancel and delete this shoot?')) return;
    try {
      await api.deleteShoot(shoot.id);
      toast.showToast('Shoot deleted.', 'success');
      reload();
    } catch (err) {
      toast.showToast(getErrorMessage(err), 'error');
    }
  }

  async function toggleChecklistItem(key) {
    const next = !checklistShoot[key];
    try {
      const updated = await api.updateShootChecklist(checklistShoot.id, { [key]: next });
      setChecklistShoot(updated);
      reload();
    } catch (err) {
      toast.showToast(getErrorMessage(err), 'error');
    }
  }

  if (loading) return <LoadingState label="Loading shoots…" />;
  if (error) return <ErrorState onRetry={reload} />;

  const columns = [
    { key: 'date_time', label: 'Date & Time', sortable: true, render: (s) => formatDateTimeISO(s.date_time) },
    { key: 'client_id', label: 'Client', render: (s) => clientMap[s.client_id] || '—' },
    { key: 'location', label: 'Location', render: (s) => s.location || '—' },
    { key: 'status', label: 'Status', render: (s) => <Badge status={s.status} /> },
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Shoots</div>
          <h1 className="page-title">Shoot Scheduling & Calendar</h1>
          <p className="page-subtitle">{shoots.length} shoot{shoots.length === 1 ? '' : 's'} tracked.</p>
        </div>
        <Button variant="primary" icon={Plus} onClick={openCreate}>New Shoot</Button>
      </div>

      <Card padded={false}>
        <div style={{ display: 'flex', gap: 10, padding: '14px 16px', borderBottom: '1px solid var(--border-soft)' }}>
          <SearchInput value={search} onChange={setSearch} placeholder="Search shoots…" />
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ maxWidth: 200 }}>
            <option value="">All statuses</option>
            {SHOOT_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        <div className="card-pad">
          <DataTable
            columns={columns}
            rows={filtered}
            emptyTitle="No shoots found"
            renderRowActions={(s) => (
              <>
                <button className="icon-btn" title="Checklist" onClick={() => setChecklistShoot(s)}><ListChecks size={14} /></button>
                <button className="icon-btn" title="Edit" onClick={() => openEdit(s)}><Pencil size={14} /></button>
                <button className="icon-btn" title="Delete" onClick={() => handleDelete(s)}><Trash2 size={14} /></button>
              </>
            )}
          />
        </div>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? 'Edit Shoot' : 'New Shoot'} width={680}>
        <form onSubmit={handleSubmit}>
          <div className="grid grid-2" style={{ gap: 14 }}>
            <Field label="Client" required>
              <Select value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value, order_id: '' })} required disabled={!!editing}>
                <option value="">Select client…</option>
                {(clients || []).map((c) => <option key={c.id} value={c.id}>{c.client_name}</option>)}
              </Select>
            </Field>
            <Field label="Order" required>
              <Select value={form.order_id} onChange={(e) => setForm({ ...form, order_id: e.target.value })} required disabled={!!editing || !form.client_id}>
                <option value="">Select order…</option>
                {ordersForClient.map((o) => <option key={o.id} value={o.id}>{o.package_name}</option>)}
              </Select>
            </Field>
            <Field label="Date & Time" required>
              <Input type="datetime-local" value={form.date_time} onChange={(e) => setForm({ ...form, date_time: e.target.value })} required />
            </Field>
            <Field label="Location">
              <Input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
            </Field>
            <Field label="Creator">
              <Select value={form.creator_id} onChange={(e) => setForm({ ...form, creator_id: e.target.value })}>
                <option value="">Unassigned</option>
                {(creators || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </Field>
            <Field label="Cameraman">
              <Input value={form.cameraman} onChange={(e) => setForm({ ...form, cameraman: e.target.value })} />
            </Field>
            <Field label="Shoot Manager">
              <Select value={form.shoot_manager_id} onChange={(e) => setForm({ ...form, shoot_manager_id: e.target.value })}>
                <option value="">Unassigned</option>
                {managers.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
              </Select>
            </Field>
            <Field label="Shooting Assistant">
              <Input value={form.shooting_assistant} onChange={(e) => setForm({ ...form, shooting_assistant: e.target.value })} />
            </Field>
            {editing && (
              <Field label="Status">
                <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  {SHOOT_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
                </Select>
              </Field>
            )}
          </div>
          <Field label="Special Notes">
            <textarea className="input" rows={2} value={form.special_notes} onChange={(e) => setForm({ ...form, special_notes: e.target.value })} />
          </Field>
          {formError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 10 }}>{formError}</p>}
          <div className="flex gap-8" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>{editing ? 'Save Changes' : 'Schedule Shoot'}</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!checklistShoot} onClose={() => setChecklistShoot(null)} title="Pre/Post-Shoot Checklist" width={420}>
        {checklistShoot && (
          <div className="flex-col gap-10">
            {CHECKLIST_ITEMS.map((item) => (
              <label key={item.key} className="flex gap-8" style={{ fontSize: 13, cursor: 'pointer' }}>
                <input type="checkbox" checked={!!checklistShoot[item.key]} onChange={() => toggleChecklistItem(item.key)} />
                {item.label}
              </label>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
}
