import { useState } from 'react';
import { CheckCircle2, MessageSquareWarning } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import { useFetch } from '../../hooks/useFetch';
import { useToast } from '../../components/common/ToastProvider';
import Card from '../../components/common/Card';
import Badge from '../../components/common/Badge';
import Button from '../../components/common/Button';
import Modal from '../../components/common/Modal';
import { Field, Textarea } from '../../components/common/Input';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/States';
import { formatDate } from '../../utils/format';

export default function PortalScripts() {
  const { user } = useAuth();
  const { data: scripts, loading, error, reload, setData } = useFetch(() => api.getMyPortalScripts());
  const { showToast } = useToast();
  const [feedbackFor, setFeedbackFor] = useState(null);
  const [feedback, setFeedback] = useState('');

  async function approve(script) {
    const updated = await api.clientReviewScript(script.id, { approve: true });
    setData((prev) => prev.map((s) => (s.id === script.id ? updated : s)));
    showToast(`Script for video #${script.video_number} approved.`, 'success');
  }

  async function requestRevision() {
    const updated = await api.clientReviewScript(feedbackFor.id, { approve: false, comments: feedback });
    setData((prev) => prev.map((s) => (s.id === feedbackFor.id ? updated : s)));
    showToast(`Revision requested on video #${feedbackFor.video_number}.`, 'success');
    setFeedbackFor(null);
    setFeedback('');
  }

  if (loading) return <LoadingState label="Loading your scripts…" />;
  if (error) return <ErrorState onRetry={reload} />;

  const reviewable = scripts.filter((s) => s.status === 'sent_to_client');
  const others = scripts.filter((s) => s.status !== 'sent_to_client');

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Script Approvals</div>
          <h1 className="page-title">Scripts</h1>
          <p className="page-subtitle">Review scripts written for your videos and leave feedback.</p>
        </div>
      </div>

      {reviewable.length > 0 && (
        <Card title="Awaiting your review" className="card" >
          <div className="flex-col gap-12">
            {reviewable.map((s) => (
              <div key={s.id} className="card card-pad" style={{ background: 'var(--bg-surface)' }}>
                <div className="flex justify-between" style={{ marginBottom: 8 }}>
                  <b>Video #{s.video_number}</b>
                  <Badge status={s.status} />
                </div>
                <p className="tmuted" style={{ fontSize: 12.5, marginBottom: 12 }}>
                  Language: {s.language || '—'} · Deadline {formatDate(s.deadline)} · Revisions so far: {s.revision_count}
                </p>
                <div className="flex gap-8">
                  <Button variant="primary" size="sm" icon={CheckCircle2} onClick={() => approve(s)}>Approve</Button>
                  <Button variant="secondary" size="sm" icon={MessageSquareWarning} onClick={() => setFeedbackFor(s)}>Request Revision</Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div style={{ height: 20 }} />

      <Card title="All scripts">
        {others.length === 0 && reviewable.length === 0 ? (
          <EmptyState title="No scripts yet" description="Scripts will appear here once your writer starts drafting." />
        ) : (
          <div className="flex-col gap-10">
            {[...reviewable, ...others].map((s) => (
              <div key={s.id} className="flex justify-between" style={{ fontSize: 13, padding: '8px 0', borderBottom: '1px solid var(--border-soft)' }}>
                <span>Video #{s.video_number} · {s.language || '—'}</span>
                <Badge status={s.status} />
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal open={!!feedbackFor} onClose={() => setFeedbackFor(null)} title={`Request revision — Video #${feedbackFor?.video_number ?? ''}`}>
        <Field label="What should change?" required hint="Be as specific as possible — this goes straight to the writer.">
          <Textarea value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. Please shorten the intro and add a stronger CTA at the end." />
        </Field>
        <div className="form-actions">
          <Button variant="ghost" onClick={() => setFeedbackFor(null)}>Cancel</Button>
          <Button variant="primary" onClick={requestRevision} disabled={!feedback.trim()}>Send feedback</Button>
        </div>
      </Modal>
    </div>
  );
}
