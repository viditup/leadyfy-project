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
import { Field, Input, Select, Textarea, SearchInput } from '../components/common/Input';
import { SCRIPT_STATUSES, humanize, ROLES } from '../data/mockData';
import { formatDate } from '../utils/format';

const emptyForm = {
  client_id: '', order_id: '', video_number: '', writer_id: '', creator_id: '',
  language: 'English', script_text: '', reference_links: '', deadline: '', status: 'draft', comments: '',
};

export default function Scripts() {
  const { user } = useAuth();
  const toast = useToast();
  const isOwnerAdmin = user.role === ROLES.OWNER || user.role === ROLES.ADMIN;

  const { data: scripts, loading, error, reload } = useFetch(() => api.getScripts(), []);
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

  const clientMap = useMemo(() => {
    const m = {}; (clients || []).forEach((c) => { m[c.id] = c.client_name; }); return m;
  }, [clients]);
  const writers = useMemo(() => (employees || []).filter((e) => e.sub_role === 'script_writer' || e.role === 'owner' || e.role === 'admin'), [employees]);

  const ordersForClient = useMemo(() => (orders || []).filter((o) => o.client_id === form.client_id), [orders, form.client_id]);

  const filtered = useMemo(() => {
    if (!scripts) return [];
    return scripts.filter((s) => {
      if (statusFilter && s.status !== statusFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return (clientMap[s.client_id] || '').toLowerCase().includes(q) || String(s.video_number || '').includes(q);
      }
      return true;
    });
  }, [scripts, search, statusFilter, clientMap]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  }

  function openEdit(script) {
    setEditing(script);
    setForm({
      client_id: script.client_id, order_id: script.order_id, video_number: script.video_number ?? '',
      writer_id: script.writer_id || '', creator_id: script.creator_id || '', language: script.language || '',
      script_text: script.script_text || '', reference_links: script.reference_links || '',
      deadline: script.deadline ? script.deadline.slice(0, 10) : '', status: script.status || 'draft',
      comments: script.comments || '',
    });
    setFormError('');
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      if (editing) {
        const { writer_id, creator_id, language, script_text, reference_links, deadline, comments, status } = form;
        await api.updateScript(editing.id, {
          writer_id: writer_id || null, creator_id: creator_id || null, language, script_text,
          reference_links, deadline: deadline || null, comments, status,
        });
        toast.showToast('Script updated.', 'success');
      } else {
        await api.createScript({
          client_id: form.client_id, order_id: form.order_id,
          video_number: form.video_number ? Number(form.video_number) : null,
          writer_id: form.writer_id || null, creator_id: form.creator_id || null,
          language: form.language, script_text: form.script_text,
          reference_links: form.reference_links, deadline: form.deadline || null,
        });
        toast.showToast('Script created.', 'success');
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(script) {
    if (!window.confirm('Delete this script? This cannot be undone.')) return;
    try {
      await api.deleteScript(script.id);
      toast.showToast('Script deleted.', 'success');
      reload();
    } catch (err) {
      toast.showToast(getErrorMessage(err), 'error');
    }
  }

  if (loading) return <LoadingState label="Loading scripts…" />;
  if (error) return <ErrorState onRetry={reload} />;

  const columns = [
    { key: 'client_id', label: 'Client', render: (s) => clientMap[s.client_id] || '—' },
    { key: 'video_number', label: 'Video #', render: (s) => s.video_number ?? '—' },
    { key: 'language', label: 'Language', render: (s) => s.language || '—' },
    { key: 'status', label: 'Status', render: (s) => <Badge status={s.status} /> },
    { key: 'revision_count', label: 'Revisions', align: 'right' },
    { key: 'deadline', label: 'Deadline', sortable: true, render: (s) => formatDate(s.deadline) },
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Scripts</div>
          <h1 className="page-title">Script Repository</h1>
          <p className="page-subtitle">{scripts.length} script{scripts.length === 1 ? '' : 's'} across all clients.</p>
        </div>
        <Button variant="primary" icon={Plus} onClick={openCreate}>New Script</Button>
      </div>

      <Card padded={false}>
        <div style={{ display: 'flex', gap: 10, padding: '14px 16px', borderBottom: '1px solid var(--border-soft)' }}>
          <SearchInput value={search} onChange={setSearch} placeholder="Search scripts…" />
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ maxWidth: 200 }}>
            <option value="">All statuses</option>
            {SCRIPT_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        <div className="card-pad">
          <DataTable
            columns={columns}
            rows={filtered}
            emptyTitle="No scripts found"
            emptyDescription="Create a script once an order is in production."
            renderRowActions={(s) => (
              <>
                <button className="icon-btn" title="Edit" onClick={() => openEdit(s)}><Pencil size={14} /></button>
                {isOwnerAdmin && <button className="icon-btn" title="Delete" onClick={() => handleDelete(s)}><Trash2 size={14} /></button>}
              </>
            )}
          />
        </div>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? 'Edit Script' : 'New Script'} width={680}>
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
            <Field label="Video #">
              <Input type="number" min="1" value={form.video_number} onChange={(e) => setForm({ ...form, video_number: e.target.value })} />
            </Field>
            <Field label="Language">
              <Input value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })} />
            </Field>
            <Field label="Writer">
              <Select value={form.writer_id} onChange={(e) => setForm({ ...form, writer_id: e.target.value })}>
                <option value="">Unassigned</option>
                {writers.map((w) => <option key={w.id} value={w.id}>{w.full_name}</option>)}
              </Select>
            </Field>
            <Field label="Creator">
              <Select value={form.creator_id} onChange={(e) => setForm({ ...form, creator_id: e.target.value })}>
                <option value="">Unassigned</option>
                {(creators || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </Field>
            <Field label="Deadline">
              <Input type="date" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} />
            </Field>
            {editing && (
              <Field label="Status">
                <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  {SCRIPT_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
                </Select>
              </Field>
            )}
          </div>
          <Field label="Script Text">
            <Textarea value={form.script_text} onChange={(e) => setForm({ ...form, script_text: e.target.value })} rows={6} />
          </Field>
          <Field label="Reference Links">
            <Input value={form.reference_links} onChange={(e) => setForm({ ...form, reference_links: e.target.value })} placeholder="https://…" />
          </Field>
          {editing && (
            <Field label="Comments">
              <Textarea value={form.comments} onChange={(e) => setForm({ ...form, comments: e.target.value })} rows={2} />
            </Field>
          )}
          {formError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 10 }}>{formError}</p>}
          <div className="flex gap-8" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>{editing ? 'Save Changes' : 'Create Script'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
