import { Package, FileText, Clapperboard, LifeBuoy } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import { useFetch } from '../../hooks/useFetch';
import KpiCard from '../../components/dashboard/KpiCard';
import Card from '../../components/common/Card';
import Badge from '../../components/common/Badge';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/States';
import { formatDate } from '../../utils/format';

// Client Portal home. Spec 2.D: clients see order/production progress,
// script & video items awaiting their review, and open ticket count — never
// internal data like creators or costs. KPI counts come straight from the
// backend's own aggregate (GET /api/dashboard/portal), so they can never
// drift from what the "Your orders" / "Needs your attention" lists below
// compute from the raw portal-scoped lists.
export default function PortalDashboard() {
  const { user } = useAuth();
  const summary = useFetch(() => api.getPortalDashboard());
  const orders = useFetch(() => api.getMyPortalOrders());
  const scripts = useFetch(() => api.getMyPortalScripts());
  const videos = useFetch(() => api.getMyPortalVideos());

  const loading = summary.loading || orders.loading || scripts.loading || videos.loading;
  const error = summary.error || orders.error || scripts.error || videos.error;

  if (loading) return <LoadingState label="Loading your workspace…" />;
  if (error) return <ErrorState onRetry={() => { summary.reload(); orders.reload(); scripts.reload(); videos.reload(); }} />;

  const activeOrders = orders.data.filter((o) => !['completed', 'cancelled'].includes(o.status));

  const pendingScripts = scripts.data
    .filter((s) => s.status === 'sent_to_client')
    .map((s) => ({ id: s.id, label: `Script — Video #${s.video_number}`, status: s.status }));
  const pendingVideos = videos.data
    .filter((v) => v.status === 'client_review')
    .map((v) => ({ id: v.id, label: `Video review — due ${formatDate(v.deadline)}`, status: v.status }));
  const pendingApprovals = [...pendingScripts, ...pendingVideos];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Client Workspace</div>
          <h1 className="page-title">Welcome back, {user.full_name.split(' ')[0]}</h1>
          <p className="page-subtitle">A live view of your orders, scripts and videos in production.</p>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 20 }}>
        <KpiCard icon={Package} label="Active Orders" value={summary.data.active_orders} tint="amber" />
        <KpiCard icon={Clapperboard} label="Videos Delivered" value={summary.data.videos_delivered} tint="green" />
        <KpiCard
          icon={FileText}
          label="Awaiting Your Review"
          value={summary.data.pending_script_approvals + summary.data.pending_video_approvals}
          tint="purple"
        />
        <KpiCard icon={LifeBuoy} label="Open Tickets" value={summary.data.open_support_tickets} tint="blue" />
      </div>

      <div className="grid" style={{ gridTemplateColumns: '1.4fr 1fr' }}>
        <Card title="Your orders">
          {orders.data.length === 0 ? (
            <EmptyState title="No orders yet" description="Your active packages will appear here once one is set up." />
          ) : (
            <div className="flex-col gap-12">
              {orders.data.map((o) => {
                const delivered = videos.data.filter((v) => v.order_id === o.id && v.status === 'delivered').length;
                const ordered = o.contracted_video_count || 0;
                const pct = ordered > 0 ? Math.min(100, Math.round((delivered / ordered) * 100)) : 0;
                return (
                  <div key={o.id} style={{ paddingBottom: 12, borderBottom: '1px solid var(--border-soft)' }}>
                    <div className="flex justify-between">
                      <b style={{ fontSize: 13 }}>{o.package_name}</b>
                      <Badge status={o.status} />
                    </div>
                    <div className="tmuted" style={{ fontSize: 12, margin: '6px 0' }}>
                      {delivered} of {ordered} videos delivered · Due {formatDate(o.due_date)}
                    </div>
                    <div style={{ height: 5, borderRadius: 999, background: 'var(--bg-surface)', overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${pct}%`, background: 'var(--amber)' }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card title="Needs your attention">
          {pendingApprovals.length === 0 ? (
            <p className="tmuted" style={{ fontSize: 12.5 }}>Nothing pending — you're all caught up.</p>
          ) : (
            <div className="flex-col gap-10">
              {pendingApprovals.map((item) => (
                <div key={item.id} className="flex justify-between" style={{ fontSize: 12.5 }}>
                  <span>{item.label}</span>
                  <Badge status={item.status} />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {activeOrders.length === 0 && orders.data.length > 0 && (
        <p className="tmuted" style={{ fontSize: 12, marginTop: 16 }}>
          All your orders are completed or on hold — reach out to your account manager for a new package.
        </p>
      )}
    </div>
  );
}
