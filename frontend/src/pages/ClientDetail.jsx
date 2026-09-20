import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Package, FileText, Camera, Clapperboard, IndianRupee, LifeBuoy, Image, Plus, ExternalLink } from 'lucide-react';
import { api, getErrorMessage } from '../services/api';
import { useFetch } from '../hooks/useFetch';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/common/ToastProvider';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import Modal from '../components/common/Modal';
import DataTable from '../components/tables/DataTable';
import { LoadingState, ErrorState } from '../components/common/States';
import { Field, Input } from '../components/common/Input';
import { ROLES, humanize } from '../data/mockData';
import { formatCurrency, formatDate, formatDateTimeISO } from '../utils/format';

const TABS = [
  { key: 'orders', label: 'Orders', icon: Package },
  { key: 'scripts', label: 'Scripts', icon: FileText },
  { key: 'shoots', label: 'Shoots', icon: Camera },
  { key: 'videos', label: 'Videos', icon: Clapperboard },
  { key: 'payments', label: 'Invoices', icon: IndianRupee, ownerAdminOnly: true },
  { key: 'tickets', label: 'Support', icon: LifeBuoy },
  { key: 'assets', label: 'Assets', icon: Image },
];

// Backend `Asset.asset_type` (schemas/client.py: AssetCreate.asset_type) is a
// free nullable string, not a DB enum -- these are only input suggestions
// (via <datalist>, which never restricts what can be typed/submitted), taken
// from the example values in the model's own docstring comment
// (models/client.py: "e.g. logo, brand_guideline, product_photo").
const ASSET_TYPE_SUGGESTIONS = ['logo', 'brand_guideline', 'product_photo'];

const emptyAssetForm = { name: '', file_url: '', asset_type: '' };

export default function ClientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const toast = useToast();
  const isOwnerAdmin = user.role === ROLES.OWNER || user.role === ROLES.ADMIN;
  const [tab, setTab] = useState('orders');

  const { data: client, loading, error } = useFetch(() => api.getClient(id), [id]);
  const { data: orders } = useFetch(() => api.getOrders({ client_id: id }), [id]);
  const { data: scripts } = useFetch(() => api.getScripts({ client_id: id }), [id]);
  const { data: shoots } = useFetch(() => api.getShoots({ client_id: id }), [id]);
  const { data: videos } = useFetch(() => api.getVideos({ client_id: id }), [id]);
  const { data: payments } = useFetch(
    () => (isOwnerAdmin ? api.getPayments({ client_id: id }) : Promise.resolve([])),
    [id, isOwnerAdmin]
  );
  const { data: tickets } = useFetch(() => api.getTickets({ client_id: id }), [id]);
  const {
    data: assets,
    loading: assetsLoading,
    error: assetsError,
    reload: reloadAssets,
  } = useFetch(() => api.getClientAssets(id), [id]);

  const [assetModalOpen, setAssetModalOpen] = useState(false);
  const [assetForm, setAssetForm] = useState(emptyAssetForm);
  const [assetSaving, setAssetSaving] = useState(false);
  const [assetFormError, setAssetFormError] = useState('');

  function openAddAsset() {
    setAssetForm(emptyAssetForm);
    setAssetFormError('');
    setAssetModalOpen(true);
  }

  async function handleAddAsset(e) {
    e.preventDefault();
    setAssetFormError('');
    setAssetSaving(true);
    const payload = {
      name: assetForm.name.trim(),
      file_url: assetForm.file_url.trim(),
      asset_type: assetForm.asset_type.trim() || null,
    };
    try {
      await api.addClientAsset(id, payload);
      toast.showToast('Asset added.', 'success');
      setAssetModalOpen(false);
      reloadAssets();
    } catch (err) {
      setAssetFormError(getErrorMessage(err));
    } finally {
      setAssetSaving(false);
    }
  }

  if (loading) return <LoadingState label="Loading client…" />;
  if (error || !client) return <ErrorState onRetry={() => window.location.reload()} />;

  return (
    <div>
      <button className="btn btn-ghost btn-sm" style={{ marginBottom: 14 }} onClick={() => navigate('/clients')}>
        <ArrowLeft size={14} /> Back to Clients
      </button>

      <div className="page-header">
        <div>
          <div className="page-eyebrow">{client.company_name || 'Client'}</div>
          <h1 className="page-title">{client.client_name}</h1>
          <p className="page-subtitle">
            {client.industry || '—'} · {client.email} · {client.phone || 'No phone on file'}
          </p>
        </div>
        <Badge status={client.status} />
      </div>

      <Card padded={false} style={{ marginBottom: 20 }}>
        <div className="tab-strip">
          {TABS.filter((t) => !t.ownerAdminOnly || isOwnerAdmin).map((t) => (
            <button key={t.key} className={`tab-btn ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
              <t.icon size={14} /> {t.label}
            </button>
          ))}
        </div>
      </Card>

      <Card>
        {tab === 'orders' && (
          <DataTable
            rows={orders || []}
            emptyTitle="No orders yet"
            columns={[
              { key: 'package_name', label: 'Package' },
              { key: 'contracted_video_count', label: 'Videos', align: 'right' },
              { key: 'total_invoice_amount', label: 'Invoice', align: 'right', render: (o) => formatCurrency(o.total_invoice_amount) },
              { key: 'outstanding_balance', label: 'Outstanding', align: 'right', render: (o) => formatCurrency(o.outstanding_balance) },
              { key: 'status', label: 'Status', render: (o) => <Badge status={o.status} /> },
              { key: 'due_date', label: 'Due', render: (o) => formatDate(o.due_date) },
            ]}
          />
        )}
        {tab === 'scripts' && (
          <DataTable
            rows={scripts || []}
            emptyTitle="No scripts yet"
            columns={[
              { key: 'video_number', label: 'Video #' },
              { key: 'language', label: 'Language', render: (s) => s.language || '—' },
              { key: 'status', label: 'Status', render: (s) => <Badge status={s.status} /> },
              { key: 'revision_count', label: 'Revisions', align: 'right' },
              { key: 'deadline', label: 'Deadline', render: (s) => formatDate(s.deadline) },
            ]}
          />
        )}
        {tab === 'shoots' && (
          <DataTable
            rows={shoots || []}
            emptyTitle="No shoots scheduled"
            columns={[
              { key: 'date_time', label: 'Date', render: (s) => formatDateTimeISO(s.date_time) },
              { key: 'location', label: 'Location', render: (s) => s.location || '—' },
              { key: 'status', label: 'Status', render: (s) => <Badge status={s.status} /> },
            ]}
          />
        )}
        {tab === 'videos' && (
          <DataTable
            rows={videos || []}
            emptyTitle="No videos yet"
            columns={[
              { key: 'id', label: 'Video', render: (v) => `#${v.id.slice(0, 8)}` },
              { key: 'status', label: 'Stage', render: (v) => <Badge status={v.status} /> },
              { key: 'revision_count', label: 'Revisions', align: 'right' },
              { key: 'deadline', label: 'Deadline', render: (v) => formatDate(v.deadline) },
              { key: 'final_delivery_link', label: 'Delivery Link', render: (v) => v.final_delivery_link ? <a href={v.final_delivery_link} target="_blank" rel="noreferrer" style={{ color: 'var(--amber-text)' }}>Open</a> : '—' },
            ]}
          />
        )}
        {tab === 'payments' && isOwnerAdmin && (
          <DataTable
            rows={payments || []}
            emptyTitle="No invoices yet"
            columns={[
              { key: 'invoice_amount', label: 'Invoice', align: 'right', render: (p) => formatCurrency(p.invoice_amount) },
              { key: 'amount_received', label: 'Received', align: 'right', render: (p) => formatCurrency(p.amount_received) },
              { key: 'pending_balance', label: 'Pending', align: 'right', render: (p) => formatCurrency(p.pending_balance) },
              { key: 'status', label: 'Status', render: (p) => <Badge status={p.status} /> },
              { key: 'payment_date', label: 'Date', render: (p) => formatDate(p.payment_date) },
            ]}
          />
        )}
        {tab === 'tickets' && (
          <DataTable
            rows={tickets || []}
            emptyTitle="No support tickets"
            columns={[
              { key: 'subject', label: 'Subject' },
              { key: 'status', label: 'Status', render: (t) => <Badge status={t.status} /> },
              { key: 'created_at', label: 'Opened', render: (t) => formatDate(t.created_at) },
            ]}
          />
        )}
        {tab === 'assets' && (
          <div>
            <div className="flex" style={{ justifyContent: 'flex-end', marginBottom: 14 }}>
              <Button variant="primary" size="sm" icon={Plus} onClick={openAddAsset}>Add Asset</Button>
            </div>
            {assetsLoading ? (
              <LoadingState label="Loading assets…" />
            ) : assetsError ? (
              <ErrorState
                title="Couldn't load assets"
                description="Try refreshing this tab."
                onRetry={reloadAssets}
              />
            ) : (
              <DataTable
                rows={assets || []}
                emptyTitle="No brand assets yet"
                emptyDescription="Add the client's logo files, brand guidelines, or reference photos so the team has a single source of truth."
                columns={[
                  { key: 'name', label: 'Asset' },
                  { key: 'asset_type', label: 'Type', render: (a) => (a.asset_type ? <Badge label={humanize(a.asset_type)} color="blue" /> : '—') },
                  {
                    key: 'file_url',
                    label: 'File',
                    render: (a) => (
                      <a href={a.file_url} target="_blank" rel="noreferrer" style={{ color: 'var(--amber-text)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        Open <ExternalLink size={12} />
                      </a>
                    ),
                  },
                  { key: 'created_at', label: 'Added', render: (a) => formatDate(a.created_at) },
                ]}
              />
            )}
          </div>
        )}
      </Card>

      <Modal open={assetModalOpen} onClose={() => setAssetModalOpen(false)} title="Add Client Asset" width={520}>
        <form onSubmit={handleAddAsset}>
          <Field label="Asset Name" required>
            <Input
              value={assetForm.name}
              onChange={(e) => setAssetForm({ ...assetForm, name: e.target.value })}
              placeholder="Primary Logo"
              required
            />
          </Field>
          <Field label="File URL" required hint="Link to the file (Drive, Dropbox, S3, etc.) — this project doesn't host uploads directly.">
            <Input
              type="url"
              value={assetForm.file_url}
              onChange={(e) => setAssetForm({ ...assetForm, file_url: e.target.value })}
              placeholder="https://…"
              required
            />
          </Field>
          <Field label="Asset Type" hint="Optional, e.g. logo, brand_guideline, product_photo.">
            <Input
              list="asset-type-suggestions"
              value={assetForm.asset_type}
              onChange={(e) => setAssetForm({ ...assetForm, asset_type: e.target.value })}
              placeholder="logo"
            />
            <datalist id="asset-type-suggestions">
              {ASSET_TYPE_SUGGESTIONS.map((t) => <option key={t} value={t} />)}
            </datalist>
          </Field>
          {assetFormError && <p style={{ color: 'var(--red)', fontSize: 12.5, marginBottom: 10 }}>{assetFormError}</p>}
          <div className="flex gap-8" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
            <Button type="button" variant="ghost" onClick={() => setAssetModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={assetSaving}>Add Asset</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
