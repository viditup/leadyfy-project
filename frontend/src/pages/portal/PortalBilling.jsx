import { useState } from 'react';
import { Plus } from 'lucide-react';
import { api } from '../../services/api';
import { useFetch } from '../../hooks/useFetch';
import { useToast } from '../../components/common/ToastProvider';
import Card from '../../components/common/Card';
import Badge from '../../components/common/Badge';
import Button from '../../components/common/Button';
import Modal from '../../components/common/Modal';
import DataTable from '../../components/tables/DataTable';
import { Field, Input, Textarea } from '../../components/common/Input';
import { LoadingState, ErrorState } from '../../components/common/States';
import { formatCurrency, formatDate } from '../../utils/format';

// Client Portal billing + support (spec 7.3 client view + spec 8 ticketing).
// SupportTicketCreate only has subject/description on the backend (no
// priority field on the SupportTicket model), so the "Raise a ticket" form
// below intentionally has no priority selector — adding one client-side
// would silently be dropped by the API and mislead the client about what
// was recorded.
const emptyForm = { subject: '', message: '' };

export default function PortalBilling() {
  const payments = useFetch(() => api.getMyPortalPayments());
  const tickets = useFetch(() => api.getMyPortalTickets());
  const { showToast } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const loading = payments.loading || tickets.loading;
  const error = payments.error || tickets.error;
  if (loading) return <LoadingState label="Loading billing & support…" />;
  if (error) return <ErrorState onRetry={() => { payments.reload(); tickets.reload(); }} />;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.subject.trim() || !form.message.trim()) return;
    setSaving(true);
    try {
      const created = await api.createPortalTicket({ subject: form.subject, description: form.message });
      tickets.setData((prev) => [created, ...prev]);
      showToast('Support ticket raised. Our team will get back to you shortly.', 'success');
      setModalOpen(false);
      setForm(emptyForm);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Billing & Support</div>
          <h1 className="page-title">Invoices & Tickets</h1>
          <p className="page-subtitle">Your invoices, payment status and support history.</p>
        </div>
        <Button variant="primary" icon={Plus} onClick={() => setModalOpen(true)}>Raise a ticket</Button>
      </div>

      <Card title="Invoices" padded={false}>
        <DataTable
          rows={payments.data}
          emptyTitle="No invoices yet"
          columns={[
            { key: 'payment_date', label: 'Date', render: (p) => formatDate(p.payment_date) },
            { key: 'invoice_amount', label: 'Invoice', align: 'right', render: (p) => formatCurrency(p.invoice_amount) },
            { key: 'amount_received', label: 'Paid', align: 'right', render: (p) => formatCurrency(p.amount_received) },
            { key: 'pending_balance', label: 'Balance', align: 'right', render: (p) => formatCurrency(p.pending_balance) },
            { key: 'status', label: 'Status', render: (p) => <Badge status={p.status} /> },
          ]}
        />
      </Card>

      <div style={{ height: 20 }} />

      <Card title="Support tickets" padded={false}>
        <DataTable
          rows={tickets.data}
          emptyTitle="No tickets raised yet"
          columns={[
            { key: 'subject', label: 'Subject' },
            { key: 'created_at', label: 'Raised', render: (t) => formatDate(t.created_at) },
            { key: 'status', label: 'Status', render: (t) => <Badge status={t.status} /> },
          ]}
        />
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Raise a support ticket">
        <form onSubmit={handleSubmit}>
          <Field label="Subject" required>
            <Input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} placeholder="e.g. Invoice copy needed" />
          </Field>
          <Field label="Message" required>
            <Textarea value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} placeholder="Describe the issue…" />
          </Field>
          <div className="form-actions">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>Submit ticket</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
