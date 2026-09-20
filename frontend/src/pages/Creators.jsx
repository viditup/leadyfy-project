import { useMemo, useState } from 'react';
import { Plus, Pencil, Trash2, CalendarDays } from 'lucide-react';
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
import { CREATOR_AVAILABILITY, humanize } from '../data/mockData';
import { formatCurrency, formatDate } from '../utils/format';

const emptyForm = {
  name: '', gender: '', age_group: '', languages: '', location: '', niches: '',
  demographics: '', contact: '', rates: 0, bank_upi_info: '', portfolio_links: '', availability_status: 'available',
};

const emptyAvailabilityForm = { date: '', status: 'available', notes: '' };

export default function Creators() {
  const toast = useToast();
  const { data: creators, loading, error, reload } = useFetch(() => api.getCreators(), []);

  const [search, setSearch] = useState('');
  const [availFilter, setAvailFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const filtered = useMemo(() => {
    if (!creators) return [];
    return creators.filter((c) => {
      if (availFilter && c.availability_status !== availFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return c.name?.toLowerCase().includes(q) || c.niches?.toLowerCase().includes(q) || c.location?.toLowerCase().includes(q);
      }
      return true;
    });
  }, [creators, search, availFilter]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  }

  function openEdit(creator) {
    setEditing(creator);
    setForm({
      name: creator.name || '', gender: creator.gender || '', age_group: creator.age_group || '',
      languages: creator.languages || '', location: creator.location || '', niches: creator.niches || '',
      demographics: creator.demographics || '', contact: creator.contact || '', rates: creator.rates ?? 0,
      bank_upi_info: creator.bank_upi_info || '', portfolio_links: creator.portfolio_links || '',
      availability_status: creator.availability_status || 'available',
    });
    setFormError('');
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    const payload = { ...form, rates: Number(form.rates) || 0 };
    try {
      if (editing) {
        await api.updateCreator(editing.id, payload);
        toast.showToast('Creator updated.', 'success');
      } else {
        await api.createCreator(payload);
        toast.showToast('Creator added.', 'success');
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(creator) {
    if (!window.confirm(`Remove ${creator.name} from the roster?`)) return;
    try {
      await api.deleteCreator(creator.id);
      toast.showToast('Creator removed.', 'success');
      reload();
    } catch (err) {
      toast.showToast(getErrorMessage(err), 'error');
    }
  }

  // --- Per-date availability calendar (spec 5.2) ---------------------------
  // Separate from `availability_status` above, which is the creator's
  // current at-a-glance state on the roster. These are day-level records
  // (`CreatorAvailability`) used by shoot scheduling to avoid double-booking.
  const [availModalOpen, setAvailModalOpen] = useState(false);
  const [availCreator, setAvailCreator] = useState(null);
  const [availRecords, setAvailRecords] = useState(null);
  const [availLoading, setAvailLoading] = useState(false);
  const [availError, setAvailError] = useState(null);
  const [availForm, setAvailForm] = useState(emptyAvailabilityForm);
  const [availSaving, setAvailSaving] = useState(false);
  const [availFormError, setAvailFormError] = useState('');

  function loadAvailability(creatorId) {
    setAvailLoading(true);
    setAvailError(null);
    api
      .getCreatorAvailability(creatorId)
      .then((res) => setAvailRecords(res))
      .catch((err) => setAvailError(err))
      .finally(() => setAvailLoading(false));
  }

  function openAvailability(creator) {
    setAvailCreator(creator);
    setAvailForm(emptyAvailabilityForm);
    setAvailFormError('');
    setAvailModalOpen(true);
    loadAvailability(creator.id);
  }

  async function handleSetAvailability(e) {
    e.preventDefault();
    if (!availForm.date) {
      setAvailFormError('Pick a date.');
      return;
    }
    setAvailFormError('');
    setAvailSaving(true);
    try {
      await api.addCreatorAvailability(availCreator.id, {
        date: availForm.date,
        status: availForm.status,
        notes: availForm.notes.trim() || null,
      });
      toast.showToast(`Availability set for ${formatDate(availForm.date)}.`, 'success');
      setAvailForm({ ...emptyAvailabilityForm, status: availForm.status });
      loadAvailability(availCreator.id);
    } catch (err) {
      setAvailFormError(getErrorMessage(err));
    } finally {
      setAvailSaving(false);
    }
  }

  const sortedAvailRecords = useMemo(() => {
    if (!availRecords) return [];
    return [...availRecords].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  }, [availRecords]);

  if (loading) return <LoadingState label="Loading creators…" />;
  if (error) return <ErrorState onRetry={reload} />;

  const columns = [
    { key: 'name', label: 'Creator', sortable: true },
    { key: 'niches', label: 'Niches', render: (c) => c.niches || '—' },
    { key: 'location', label: 'Location', render: (c) => c.location || '—' },
    { key: 'languages', label: 'Languages', render: (c) => c.languages || '—' },
    { key: 'rates', label: 'Rate', align: 'right', render: (c) => formatCurrency(c.rates) },
    { key: 'availability_status', label: 'Availability', render: (c) => <Badge status={c.availability_status} /> },
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Creators</div>
          <h1 className="page-title">Creator Management Hub</h1>
          <p className="page-subtitle">{creators.length} creator{creators.length === 1 ? '' : 's'} in the roster.</p>
        </div>
        <Button variant="primary" icon={Plus} onClick={openCreate}>New Creator</Button>
      </div>

      <Card padded={false}>
        <div style={{ display: 'flex', gap: 10, padding: '14px 16px', borderBottom: '1px solid var(--border-soft)' }}>
          <SearchInput value={search} onChange={setSearch} placeholder="Search creators…" />
          <Select value={availFilter} onChange={(e) => setAvailFilter(e.target.value)} style={{ maxWidth: 180 }}>
            <option value="">All availability</option>
            {CREATOR_AVAILABILITY.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        <div className="card-pad">
          <DataTable
            columns={columns}
            rows={filtered}
            emptyTitle="No creators found"
            renderRowActions={(c) => (
              <>
                <button className="icon-btn" title="Availability" onClick={() => openAvailability(c)}><CalendarDays size={14} /></button>
                <button className="icon-btn" title="Edit" onClick={() => openEdit(c)}><Pencil size={14} /></button>
                <button className="icon-btn" title="Remove" onClick={() => handleDelete(c)}><Trash2 size={14} /></button>
              </>
            )}
          />
        </div>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? 'Edit Creator' : 'New Creator'} width={640}>
        <form onSubmit={handleSubmit}>
          <div className="grid grid-2" style={{ gap: 14 }}>
            <Field label="Name" required>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </Field>
            <Field label="Gender">
              <Input value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })} />
            </Field>
            <Field label="Age Group">
              <Input value={form.age_group} onChange={(e) => setForm({ ...form, age_group: e.target.value })} placeholder="18-24" />
            </Field>
            <Field label="Languages">
              <Input value={form.languages} onChange={(e) => setForm({ ...form, languages: e.target.value })} placeholder="English, Hindi" />
            </Field>
            <Field label="Location">
              <Input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
            </Field>
            <Field label="Niches">
              <Input value={form.niches} onChange={(e) => setForm({ ...form, niches: e.target.value })} placeholder="Beauty, Fashion" />
            </Field>
            <Field label="Contact">
              <Input value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} />
            </Field>
            <Field label="Rate (₹)">
              <Input type="number" min="0" value={form.rates} onChange={(e) => setForm({ ...form, rates: e.target.value })} />
            </Field>
            <Field label="Bank / UPI Info">
              <Input value={form.bank_upi_info} onChange={(e) => setForm({ ...form, bank_upi_info: e.target.value })} />
            </Field>
            <Field label="Availability">
              <Select value={form.availability_status} onChange={(e) => setForm({ ...form, availability_status: e.target.value })}>
                {CREATOR_AVAILABILITY.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Demographics">
            <Input value={form.demographics} onChange={(e) => setForm({ ...form, demographics: e.target.value })} />
          </Field>
          <Field label="Portfolio Links">
            <Input value={form.portfolio_links} onChange={(e) => setForm({ ...form, portfolio_links: e.target.value })} placeholder="https://instagram.com/…" />
          </Field>
          {formError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 10 }}>{formError}</p>}
          <div className="flex gap-8" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>{editing ? 'Save Changes' : 'Add Creator'}</Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={availModalOpen}
        onClose={() => setAvailModalOpen(false)}
        title={availCreator ? `Availability — ${availCreator.name}` : 'Availability'}
        width={640}
      >
        <form onSubmit={handleSetAvailability} className="grid grid-3" style={{ gap: 10, alignItems: 'end', marginBottom: 16 }}>
          <Field label="Date" required>
            <Input
              type="date"
              value={availForm.date}
              onChange={(e) => setAvailForm({ ...availForm, date: e.target.value })}
              required
            />
          </Field>
          <Field label="Status">
            <Select value={availForm.status} onChange={(e) => setAvailForm({ ...availForm, status: e.target.value })}>
              {CREATOR_AVAILABILITY.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </Select>
          </Field>
          <Field label="Notes">
            <Input
              value={availForm.notes}
              onChange={(e) => setAvailForm({ ...availForm, notes: e.target.value })}
              placeholder="Optional"
            />
          </Field>
          <div style={{ gridColumn: '1 / -1' }}>
            {availFormError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 8 }}>{availFormError}</p>}
            <Button type="submit" variant="primary" size="sm" loading={availSaving}>Set Availability</Button>
            <span className="tmuted" style={{ fontSize: 11.5, marginLeft: 10 }}>
              Setting a date that's already recorded overwrites its status.
            </span>
          </div>
        </form>

        {availLoading ? (
          <LoadingState label="Loading availability…" />
        ) : availError ? (
          <ErrorState
            title="Couldn't load availability"
            description="Try again."
            onRetry={() => loadAvailability(availCreator.id)}
          />
        ) : (
          <DataTable
            rows={sortedAvailRecords}
            emptyTitle="No dates recorded"
            emptyDescription="Unlisted dates are treated as available when scheduling shoots. Add a date above to mark it booked, unavailable, or on hold."
            columns={[
              { key: 'date', label: 'Date', render: (r) => formatDate(r.date) },
              { key: 'status', label: 'Status', render: (r) => <Badge status={r.status} /> },
              { key: 'notes', label: 'Notes', render: (r) => r.notes || '—' },
            ]}
          />
        )}
      </Modal>
    </div>
  );
}
