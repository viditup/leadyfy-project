import { useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { api } from '../services/api';
import { useFetch } from '../hooks/useFetch';
import { useToast } from '../components/common/ToastProvider';
import Button from '../components/common/Button';
import Modal from '../components/common/Modal';
import Badge from '../components/common/Badge';
import { Field, Input, Select } from '../components/common/Input';
import { LoadingState, ErrorState } from '../components/common/States';
import { formatDate, isOverdue } from '../utils/format';
import { TASK_STATUSES, TASK_PRIORITIES, humanize } from '../data/mockData';
const emptyForm = { title: '', assignee_id: '', priority: 'med', deadline: '' };

export default function Tasks() {
  const { data: tasks, loading, error, reload, setData } = useFetch(api.getTasks);
  const { data: employees } = useFetch(() => api.getEmployees(), []);
  const { showToast } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  // id -> full_name lookup so kanban cards can show a readable name even
  // though TaskResponse only ever gives us assignee_id.
  const employeeMap = useMemo(() => {
    const m = {};
    (employees || []).forEach((emp) => { m[emp.id] = emp.full_name; });
    return m;
  }, [employees]);

  function assigneeName(assigneeId) {
    if (!assigneeId) return 'Unassigned';
    return employeeMap[assigneeId] || 'Unassigned';
  }

  async function moveTask(id, status) {
    setData((prev) => prev.map((t) => (t.id === id ? { ...t, status } : t)));
    await api.updateTask(id, { status });
  }

  function validate() {
    const e = {};
    if (!form.title.trim()) e.title = 'Task title is required.';
    if (!form.assignee_id) e.assignee_id = 'Assign this task to someone.';
    if (!form.deadline) e.deadline = 'Pick a deadline.';
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!validate()) return;
    setSaving(true);
    try {
      const created = await api.createTask(form);
      setData((prev) => [created, ...prev]);
      showToast('Task created.', 'success');
      setModalOpen(false);
      setForm(emptyForm);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingState label="Loading tasks…" />;
  if (error) return <ErrorState onRetry={reload} />;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Internal Task Management</div>
          <h1 className="page-title">Tasks</h1>
          <p className="page-subtitle">Assignees, priorities and deadlines across the whole team.</p>
        </div>
        <Button variant="primary" icon={Plus} onClick={() => setModalOpen(true)}>New Task</Button>
      </div>

      <div className="kanban">
        {TASK_STATUSES.map((status) => {
          const items = tasks.filter((t) => t.status === status);
          return (
            <div className="kanban-col" key={status}>
              <div className="kanban-col-head">
                <span>{humanize(status)}</span>
                <span className="tmuted">{items.length}</span>
              </div>
              <div className="kanban-col-body">
                {items.length === 0 && <p className="tmuted" style={{ fontSize: 11.5, padding: '4px 2px' }}>Nothing here.</p>}
                {items.map((t) => (
                  <div className="kanban-card" key={t.id}>
                    <div className="title">{t.title}</div>
                    <div className="tmuted">Assigned to {assigneeName(t.assignee_id)}</div>
                    <div className="meta">
                      <Badge status={t.priority} />
                      <span style={{ color: isOverdue(t.deadline) && t.status !== 'done' ? 'var(--red)' : 'inherit' }}>
                        {formatDate(t.deadline)}
                      </span>
                    </div>
                    <Select value={t.status} onChange={(e) => moveTask(t.id, e.target.value)} style={{ marginTop: 8, fontSize: 11.5, padding: '5px 8px' }}>
                      {TASK_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
                    </Select>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Create a new task">
        <form onSubmit={handleSubmit}>
          <Field label="Task title" required error={errors.title}>
            <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Confirm shoot location permit" error={errors.title} />
          </Field>
          <div className="form-grid">
            <Field label="Assignee" required error={errors.assignee_id}>
              <Select value={form.assignee_id} onChange={(e) => setForm({ ...form, assignee_id: e.target.value })} error={errors.assignee_id}>
                <option value="">Select employee…</option>
                {(employees || []).map((emp) => <option key={emp.id} value={emp.id}>{emp.full_name}</option>)}
              </Select>
            </Field>
            <Field label="Priority">
              <Select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                {TASK_PRIORITIES.map((p) => <option key={p} value={p}>{humanize(p)}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Deadline" required error={errors.deadline}>
            <Input type="date" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} error={errors.deadline} />
          </Field>
          <div className="form-actions">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>Create task</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
