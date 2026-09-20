import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/common/ToastProvider';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import { Field, Input } from '../components/common/Input';
import { initialsOf } from '../utils/format';
import { humanize } from '../data/mockData';

const RBAC = [
  { role: 'Owner (Super Admin)', access: 'Unrestricted system-wide access, financials, RBAC configuration.' },
  { role: 'Admin / Operations Manager', access: 'Daily operations, client accounts, packages, script/shoot/editor management, reports.' },
  { role: 'Employee (role-specific)', access: 'Restricted to assigned submodules — Sales, Script Writers, Shoot Managers, or Editors.' },
  { role: 'Client (Portal)', access: 'Isolated portal — orders, script approvals, video reviews, invoices and support only.' },
];

const NOTIF_EVENTS = [
  'New client onboarding',
  'Script assigned or approved',
  'Script revision requested',
  'Shoot reminders',
  'Video assigned to editor',
  'Approaching deadlines',
  'Client feedback posted',
  'Final video approved',
  'Payment recorded',
  'Overdue invoices',
];

export default function Settings() {
  const { user } = useAuth();
  const { showToast } = useToast();
  const [name, setName] = useState(user.full_name);
  const [email, setEmail] = useState(user.email);
  const [prefs, setPrefs] = useState(() => Object.fromEntries(NOTIF_EVENTS.map((e) => [e, true])));

  function toggle(evt) {
    setPrefs((p) => ({ ...p, [evt]: !p[evt] }));
  }

  function save(e) {
    e.preventDefault();
    showToast('Settings saved.', 'success');
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">System</div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">Profile, role permissions and notification preferences.</p>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: 20 }}>
        <Card title="Profile">
          <div className="flex gap-12" style={{ marginBottom: 16 }}>
            <span className="avatar" style={{ width: 46, height: 46, fontSize: 15 }}>{initialsOf(user.full_name)}</span>
            <div>
              <div style={{ fontWeight: 600 }}>{user.full_name}</div>
              <div className="tmuted" style={{ fontSize: 12.5 }}>{humanize(user.role)}</div>
            </div>
            <span style={{ marginLeft: 'auto' }}>
              <Badge status={user.role} />
            </span>
          </div>
          <form onSubmit={save}>
            <Field label="Full name">
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <div className="form-actions">
              <Button type="submit" variant="primary">Save changes</Button>
            </div>
          </form>
        </Card>

        <Card title="Role-based access control">
          <div className="flex-col gap-12">
            {RBAC.map((r) => (
              <div key={r.role} style={{ paddingBottom: 12, borderBottom: '1px solid var(--border-soft)' }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{r.role}</div>
                <div className="tmuted" style={{ fontSize: 12 }}>{r.access}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Notification preferences" action={<span className="tmuted" style={{ fontSize: 11.5 }}>In-app alerts</span>}>
        <div className="grid grid-2">
          {NOTIF_EVENTS.map((evt) => (
            <label key={evt} className="flex gap-10" style={{ padding: '8px 0', cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={prefs[evt]} onChange={() => toggle(evt)} />
              {evt}
            </label>
          ))}
        </div>
      </Card>
    </div>
  );
}
