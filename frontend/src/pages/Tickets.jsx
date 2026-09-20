import { useMemo, useState } from 'react';
import { api } from '../services/api';
import { useFetch } from '../hooks/useFetch';
import { useToast } from '../components/common/ToastProvider';
import Card from '../components/common/Card';
import DataTable from '../components/tables/DataTable';
import { Select, SearchInput } from '../components/common/Input';
import { LoadingState, ErrorState } from '../components/common/States';
import { formatDate } from '../utils/format';
import { TICKET_STATUSES, humanize } from '../data/mockData';

export default function Tickets() {
  const { data: tickets, loading, error, reload, setData } = useFetch(api.getTickets);
  const { data: clients } = useFetch(() => api.getClients(), []);
  const { showToast } = useToast();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('All');

  // id -> client_name lookup, same pattern as Scripts.jsx's clientMap.
  // SupportTicketResponse only ever gives us client_id, never a name.
  const clientMap = useMemo(() => {
    const m = {};
    (clients || []).forEach((c) => { m[c.id] = c.client_name; });
    return m;
  }, [clients]);

  function clientName(clientId) {
    if (!clientId) return 'Unknown client';
    return clientMap[clientId] || 'Unknown client';
  }

  const filtered = useMemo(() => {
    if (!tickets) return [];
    return tickets.filter((t) => {
      const q = search.toLowerCase();
      const matchSearch = !search || clientName(t.client_id).toLowerCase().includes(q) || t.subject.toLowerCase().includes(q);
      const matchStatus = status === 'All' || t.status === status;
      return matchSearch && matchStatus;
    });
  }, [tickets, search, status, clientMap]);

  async function updateStatus(id, next) {
    setData((prev) => prev.map((t) => (t.id === id ? { ...t, status: next } : t)));
    await api.updateTicket(id, { status: next });
    showToast(`Ticket marked "${humanize(next)}".`, 'success');
  }

  if (loading) return <LoadingState label="Loading tickets…" />;
  if (error) return <ErrorState onRetry={reload} />;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Client Support</div>
          <h1 className="page-title">Support Tickets</h1>
          <p className="page-subtitle">In-portal queries and issues raised by clients.</p>
        </div>
      </div>

      <Card padded={false}>
        <div className="table-toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="Search client or subject…" />
          <Select value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 170 }}>
            <option value="All">All statuses</option>
            {TICKET_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        <DataTable
          emptyTitle="No tickets match your filters"
          rows={filtered}
          columns={[
            { key: 'client_id', label: 'Client', render: (t) => clientName(t.client_id) },
            { key: 'subject', label: 'Subject' },
            { key: 'created_at', label: 'Raised', sortable: true, render: (t) => formatDate(t.created_at) },
            {
              key: 'status',
              label: 'Status',
              render: (t) => (
                <Select value={t.status} onChange={(e) => updateStatus(t.id, e.target.value)} style={{ padding: '5px 8px', fontSize: 12 }}>
                  {TICKET_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
                </Select>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
