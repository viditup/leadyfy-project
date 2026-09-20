import { useMemo, useState } from 'react';
import { api, getErrorMessage } from '../services/api';
import { useFetch } from '../hooks/useFetch';
import { useToast } from '../components/common/ToastProvider';
import { Select, SearchInput } from '../components/common/Input';
import DataTable from '../components/tables/DataTable';
import Badge from '../components/common/Badge';
import Card from '../components/common/Card';
import { LoadingState, ErrorState } from '../components/common/States';
import { formatDate, isOverdue, daysUntil } from '../utils/format';
import { VIDEO_STATUSES, humanize } from '../data/mockData';

// Mirrors ALLOWED_TRANSITIONS in backend/app/services/video_service.py
// exactly (spec 6.2's linear pipeline, plus its two legal "send back"
// edges: Raw Footage -> back to Shoot Pending for a reshoot, and Internal
// QA -> back to Video Editing). DELIVERED is terminal (empty set). The
// backend is the source of truth and will still 400 an illegal jump even
// if this table ever drifts, but restricting the dropdown to these edges
// means staff never see an option the API will reject.
const ALLOWED_TRANSITIONS = {
  script_approved: ['shoot_pending'],
  shoot_pending: ['raw_footage_received'],
  raw_footage_received: ['video_editing', 'shoot_pending'],
  video_editing: ['internal_qa'],
  internal_qa: ['client_review', 'video_editing'],
  client_review: ['revision', 'final_approved'],
  revision: ['video_editing'],
  final_approved: ['delivered'],
  delivered: [],
};

function urgency(video) {
  if (video.status === 'delivered') return 'Completed';
  const days = daysUntil(video.deadline);
  if (days < 0) return 'Overdue';
  if (days === 0) return 'Due Today';
  if (days === 1) return 'Due Tomorrow';
  return 'Upcoming';
}

const URGENCY_COLOR = { Overdue: 'red', 'Due Today': 'amber', 'Due Tomorrow': 'blue', Completed: 'green', Upcoming: 'gray' };

export default function Videos() {
  const { data: videos, loading, error, reload, setData } = useFetch(() => api.getVideos(), []);
  const { data: clients } = useFetch(() => api.getClients(), []);
  const { data: employees } = useFetch(() => api.getEmployees(), []);
  const { showToast } = useToast();
  const [view, setView] = useState('pipeline');
  const [search, setSearch] = useState('');
  const [moving, setMoving] = useState(null);

  const clientMap = useMemo(() => {
    const m = {};
    (clients || []).forEach((c) => { m[c.id] = c.client_name; });
    return m;
  }, [clients]);
  const employeeMap = useMemo(() => {
    const m = {};
    (employees || []).forEach((e) => { m[e.id] = e.full_name; });
    return m;
  }, [employees]);

  const filtered = useMemo(() => {
    if (!videos) return [];
    if (!search) return videos;
    const q = search.toLowerCase();
    return videos.filter((v) => (clientMap[v.client_id] || '').toLowerCase().includes(q) || v.id.toLowerCase().includes(q));
  }, [videos, search, clientMap]);

  async function moveStage(video, nextStatus) {
    const prevVideos = videos;
    setMoving(video.id);
    setData((prev) => prev.map((v) => (v.id === video.id ? { ...v, status: nextStatus } : v)));
    try {
      await api.transitionVideo(video.id, nextStatus);
      showToast(`Video moved to "${humanize(nextStatus)}".`, 'success');
    } catch (err) {
      // Backend enforces cross-entity gates on top of the status graph
      // (e.g. a linked script must actually be Approved) — a 400 here is
      // a real rejection, so roll the optimistic move back and surface
      // the backend's own message rather than guessing why it failed.
      setData(prevVideos);
      showToast(getErrorMessage(err), 'error');
    } finally {
      setMoving(null);
    }
  }

  if (loading) return <LoadingState label="Loading video pipeline…" />;
  if (error) return <ErrorState onRetry={reload} />;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Core Video Production Pipeline</div>
          <h1 className="page-title">Video Pipeline</h1>
          <p className="page-subtitle">Every video asset, from script approval through final delivery.</p>
        </div>
        <div className="toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="Search client or video ID…" />
          <button className={`btn btn-sm ${view === 'pipeline' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setView('pipeline')}>Pipeline</button>
          <button className={`btn btn-sm ${view === 'editor' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setView('editor')}>Editor View</button>
        </div>
      </div>

      {videos.length === 0 ? (
        <Card>
          <p className="tmuted" style={{ fontSize: 13, textAlign: 'center', padding: '24px 0' }}>
            No videos yet. Videos are created once a script is approved and moved into production.
          </p>
        </Card>
      ) : view === 'pipeline' ? (
        <div className="kanban">
          {VIDEO_STATUSES.map((stage) => {
            const items = filtered.filter((v) => v.status === stage);
            return (
              <div className="kanban-col" key={stage}>
                <div className="kanban-col-head">
                  <span>{humanize(stage)}</span>
                  <span className="tmuted">{items.length}</span>
                </div>
                <div className="kanban-col-body">
                  {items.length === 0 && <p className="tmuted" style={{ fontSize: 11.5, padding: '4px 2px' }}>Empty.</p>}
                  {items.map((v) => {
                    const nextOptions = ALLOWED_TRANSITIONS[v.status] || [];
                    return (
                      <div className="kanban-card" key={v.id}>
                        <div className="title">#{v.id.slice(0, 8)} · {clientMap[v.client_id] || '—'}</div>
                        <div className="tmuted">Editor: {employeeMap[v.assigned_editor_id] || 'Unassigned'}</div>
                        <div className="meta">
                          <span style={{ color: isOverdue(v.deadline) && v.status !== 'delivered' ? 'var(--red)' : 'inherit' }}>
                            Due {formatDate(v.deadline)}
                          </span>
                          {v.revision_count > 0 && <span>Rev {v.revision_count}</span>}
                        </div>
                        {nextOptions.length > 0 ? (
                          <Select
                            value={v.status}
                            disabled={moving === v.id}
                            onChange={(e) => e.target.value !== v.status && moveStage(v, e.target.value)}
                            style={{ marginTop: 8, fontSize: 11.5, padding: '5px 8px' }}
                          >
                            <option value={v.status} disabled>{humanize(v.status)} (current)</option>
                            {nextOptions.map((st) => <option key={st} value={st}>Move to: {humanize(st)}</option>)}
                          </Select>
                        ) : (
                          <div className="tmuted" style={{ marginTop: 8, fontSize: 11 }}>Delivered — no further stages.</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Card padded={false}>
          <DataTable
            emptyTitle="No videos assigned"
            rows={filtered}
            columns={[
              { key: 'id', label: 'Video ID', render: (v) => <span className="cell-primary">#{v.id.slice(0, 8)}</span> },
              { key: 'client_id', label: 'Client', render: (v) => clientMap[v.client_id] || '—' },
              { key: 'assigned_editor_id', label: 'Editor', render: (v) => employeeMap[v.assigned_editor_id] || 'Unassigned' },
              { key: 'deadline', label: 'Deadline', sortable: true, render: (v) => formatDate(v.deadline) },
              { key: 'status', label: 'Stage', render: (v) => <Badge status={v.status} /> },
              { key: 'urgency', label: 'Urgency', render: (v) => <Badge label={urgency(v)} color={URGENCY_COLOR[urgency(v)]} /> },
            ]}
          />
        </Card>
      )}
    </div>
  );
}
