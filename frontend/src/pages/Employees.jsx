import { useMemo, useState } from 'react';
import { api } from '../services/api';
import { useFetch } from '../hooks/useFetch';
import { useAuth } from '../context/AuthContext';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import DataTable from '../components/tables/DataTable';
import { SearchInput } from '../components/common/Input';
import { LoadingState, ErrorState } from '../components/common/States';
import { formatCurrency, formatDate } from '../utils/format';
import { ROLES } from '../data/mockData';

export default function Employees() {
  const { data: employees, loading, error, reload } = useFetch(api.getEmployees);
  const { user } = useAuth();
  const [search, setSearch] = useState('');
  const canSeeSalary = user.role === ROLES.OWNER;

  const filtered = useMemo(() => {
    if (!employees) return [];
    if (!search) return employees;
    return employees.filter((e) => e.name.toLowerCase().includes(search.toLowerCase()) || e.role.toLowerCase().includes(search.toLowerCase()));
  }, [employees, search]);

  if (loading) return <LoadingState label="Loading employee directory…" />;
  if (error) return <ErrorState onRetry={reload} />;

  const columns = [
    {
      key: 'name',
      label: 'Employee',
      sortable: true,
      render: (e) => (
        <div>
          <div className="cell-primary">{e.name}</div>
          <div className="cell-secondary">{e.email}</div>
        </div>
      ),
    },
    { key: 'role', label: 'Role' },
    { key: 'dept', label: 'Department' },
    { key: 'joined', label: 'Joined', render: (e) => formatDate(e.joined) },
    {
      key: 'performance',
      label: 'Performance',
      sortable: true,
      render: (e) => (
        <div style={{ minWidth: 90 }}>
          <div style={{ height: 5, borderRadius: 999, background: 'var(--bg-surface)', overflow: 'hidden', marginBottom: 4 }}>
            <div style={{ height: '100%', width: `${e.performance}%`, background: e.performance >= 85 ? 'var(--green)' : 'var(--amber)' }} />
          </div>
          <span className="tmuted" style={{ fontSize: 11.5 }}>{e.performance}/100</span>
        </div>
      ),
    },
    { key: 'status', label: 'Status', render: (e) => <Badge status={e.status === 'Active' ? 'Active' : 'On Hold'} label={e.status} /> },
  ];

  if (canSeeSalary) {
    columns.splice(4, 0, { key: 'salary', label: 'Salary', align: 'right', render: (e) => formatCurrency(e.salary) });
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Operational Support</div>
          <h1 className="page-title">Employee Directory</h1>
          <p className="page-subtitle">{employees.length} staff profiles with real-time production performance.</p>
        </div>
        <SearchInput value={search} onChange={setSearch} placeholder="Search by name or role…" />
      </div>
      <Card padded={false}>
        <DataTable rows={filtered} columns={columns} emptyTitle="No employees match your search" />
      </Card>
    </div>
  );
}
