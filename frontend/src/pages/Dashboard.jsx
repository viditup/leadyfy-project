import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Package, FileClock, Camera, IndianRupee, AlertTriangle, CalendarClock, Clapperboard, ListChecks } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import KpiCard from '../components/dashboard/KpiCard';
import ActivityFeed from '../components/dashboard/ActivityFeed';
import PipelineWidget from '../components/dashboard/PipelineWidget';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import { LoadingState, ErrorState } from '../components/common/States';
import { formatCurrency, formatDateTimeISO, formatRelativeTime } from '../utils/format';
import { ROLES, VIDEO_STATUSES, humanize } from '../data/mockData';

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isFinance = user.role === ROLES.OWNER || user.role === ROLES.ADMIN;

  const [data, setData] = useState(null);
  const [videoStages, setVideoStages] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  function load() {
    setLoading(true);
    setError(null);
    const dashboardCall = isFinance ? api.getExecutiveDashboard() : api.getMyWorkDashboard();
    const calls = [dashboardCall];
    if (isFinance) calls.push(api.getVideos());

    Promise.all(calls)
      .then(([dash, videos]) => {
        setData(dash);
        if (videos) {
          const counts = VIDEO_STATUSES.map((key) => ({
            key: humanize(key),
            count: videos.filter((v) => v.status === key).length,
          }));
          setVideoStages(counts);
        }
      })
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFinance]);

  if (loading) return <LoadingState label="Loading dashboard…" />;
  if (error || !data) return <ErrorState onRetry={load} />;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Overview</div>
          <h1 className="page-title">Welcome back, {user.full_name.split(' ')[0]}</h1>
          <p className="page-subtitle">
            {isFinance ? "Here's what's moving across the agency today." : "Here's what's on your plate today."}
          </p>
        </div>
      </div>

      {isFinance ? <ExecutiveView data={data} videoStages={videoStages} navigate={navigate} /> : <EmployeeView data={data} navigate={navigate} />}
    </div>
  );
}

function ExecutiveView({ data, videoStages, navigate }) {
  const netProfit = data.financial_summary.estimated_net_profit;
  const activityItems = (data.activity_feed || []).map((a, i) => ({
    id: i,
    type: a.type,
    text: a.description,
    time: formatRelativeTime(a.timestamp),
  }));

  return (
    <>
      <div className="grid grid-4" style={{ marginBottom: 20 }}>
        <KpiCard icon={Users} label="Active Clients" value={data.client_metrics.total_active_clients} tint="amber" />
        <KpiCard icon={Package} label="Active Orders" value={data.production_volumes.active_orders} tint="blue" />
        <KpiCard icon={FileClock} label="Pending Scripts" value={data.production_volumes.pending_scripts} tint="purple" />
        <KpiCard icon={Camera} label="Upcoming Shoots" value={data.production_volumes.upcoming_shoots} tint="green" />
      </div>

      <div className="grid grid-4" style={{ marginBottom: 20 }}>
        <KpiCard icon={IndianRupee} label="Total Receivables" value={formatCurrency(data.financial_summary.total_receivables)} tint="red" />
        <KpiCard icon={IndianRupee} label="Monthly Revenue" value={formatCurrency(data.financial_summary.monthly_revenue)} tint="green" />
        <KpiCard icon={IndianRupee} label="Monthly Expenses" value={formatCurrency(data.financial_summary.monthly_expenses)} tint="amber" />
        <KpiCard icon={IndianRupee} label="Est. Net Profit" value={formatCurrency(netProfit)} tint={netProfit >= 0 ? 'blue' : 'red'} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: '1.6fr 1fr', marginBottom: 20 }}>
        <Card title="Video production pipeline">
          <PipelineWidget stages={videoStages || []} />
        </Card>
        <Card title="Recent activity">
          <ActivityFeed items={activityItems} />
        </Card>
      </div>

      <div className="grid grid-3">
        <Card title="Today's schedule" action={<CalendarClock size={15} className="tmuted" />}>
          {data.todays_shoots.length === 0 ? (
            <p className="muted" style={{ fontSize: 12.5 }}>No shoots scheduled right now.</p>
          ) : (
            <div className="flex-col gap-10">
              {data.todays_shoots.map((s) => (
                <div key={s.shoot_id} className="flex justify-between" style={{ fontSize: 12.5, cursor: 'pointer' }} onClick={() => navigate('/shoots')} role="button">
                  <span>
                    <b>{s.client_name}</b>
                    <div className="tmuted">{s.location || '—'} · {formatDateTimeISO(s.date_time)}</div>
                  </span>
                  <Badge status={s.status} />
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Bottleneck trackers" action={<AlertTriangle size={15} className="tmuted" />}>
          <div className="flex-col gap-12">
            <BottleneckRow label="Overdue tasks" count={data.bottlenecks.overdue_tasks} onClick={() => navigate('/tasks')} />
            <BottleneckRow label="Pending script approvals" count={data.bottlenecks.pending_script_approvals} onClick={() => navigate('/scripts')} />
            <BottleneckRow label="Pending edits" count={data.bottlenecks.pending_edits} onClick={() => navigate('/videos')} />
          </div>
        </Card>

        <Card title="Client action required" action={<Clapperboard size={15} className="tmuted" />}>
          <BottleneckRow label="Pending client video approvals" count={data.pending_client_video_approvals} onClick={() => navigate('/videos')} />
        </Card>
      </div>
    </>
  );
}

function EmployeeView({ data, navigate }) {
  return (
    <div className="grid grid-3">
      <KpiCard icon={ListChecks} label="My Open Tasks" value={data.my_open_tasks} tint="amber" />
      <KpiCard icon={AlertTriangle} label="My Overdue Tasks" value={data.my_overdue_tasks} tint="red" />
      <KpiCard icon={FileClock} label="My Pending Scripts" value={data.my_pending_scripts} tint="purple" />
      <KpiCard icon={Camera} label="My Upcoming Shoots" value={data.my_upcoming_shoots} tint="blue" />
      <KpiCard icon={Clapperboard} label="My Editing Queue" value={data.my_editing_queue} tint="green" />

      <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 10, marginTop: 4 }}>
        <button className="btn btn-secondary btn-sm" onClick={() => navigate('/tasks')}>View my tasks</button>
        <button className="btn btn-secondary btn-sm" onClick={() => navigate('/scripts')}>View scripts</button>
        <button className="btn btn-secondary btn-sm" onClick={() => navigate('/shoots')}>View shoots</button>
        <button className="btn btn-secondary btn-sm" onClick={() => navigate('/videos')}>View videos</button>
      </div>
    </div>
  );
}

function BottleneckRow({ label, count, onClick }) {
  return (
    <div className="flex justify-between" style={{ cursor: 'pointer' }} onClick={onClick}>
      <span style={{ fontSize: 13 }}>{label}</span>
      <span className={`badge ${count > 0 ? 'badge-red' : 'badge-green'}`}>{count}</span>
    </div>
  );
}
