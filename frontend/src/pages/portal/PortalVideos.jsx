import { useState } from 'react';
import { CheckCircle2, MessageSquareWarning, Download } from 'lucide-react';
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

// Client Portal video review (spec 7.1: client approves or requests
// revision on a draft video; timestamped feedback is logged, the video
// re-enters the editor's queue on revision, or moves to Final Approved on
// approval). The backend does this through a client-feedback POST, not a
// direct status write, and doesn't hand back the updated video on that
// call — so we reload() the list after submitting rather than guessing the
// new state client-side.
// Per spec 2.D ("Client Portal: Zero access to internal data, creators, or
// costs") this view deliberately never shows creator/editor names.
export default function PortalVideos() {
  const { data: videos, loading, error, reload } = useFetch(() => api.getMyPortalVideos());
  const { showToast } = useToast();
  const [feedbackFor, setFeedbackFor] = useState(null);
  const [feedback, setFeedback] = useState('');
  const [submitting, setSubmitting] = useState(false);

  function label(v) {
    return `Video ${v.id.slice(0, 8).toUpperCase()}`;
  }

  async function approve(video) {
    setSubmitting(true);
    try {
      await api.submitVideoFeedback(video.id, { feedback_text: 'Approved by client.', revision_requested: false });
      showToast(`${label(video)} approved for delivery.`, 'success');
      reload();
    } finally {
      setSubmitting(false);
    }
  }

  async function requestRevision() {
    setSubmitting(true);
    try {
      await api.submitVideoFeedback(feedbackFor.id, { feedback_text: feedback, revision_requested: true });
      showToast(`Revision requested on ${label(feedbackFor)}.`, 'success');
      setFeedbackFor(null);
      setFeedback('');
      reload();
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <LoadingState label="Loading your videos…" />;
  if (error) return <ErrorState onRetry={reload} />;

  const reviewable = videos.filter((v) => v.status === 'client_review');
  const delivered = videos.filter((v) => v.status === 'delivered');
  const inProgress = videos.filter((v) => !['client_review', 'delivered'].includes(v.status));

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Video Review</div>
          <h1 className="page-title">Videos</h1>
          <p className="page-subtitle">Approve final cuts or request a revision — no back and forth on WhatsApp needed.</p>
        </div>
      </div>

      {reviewable.length > 0 && (
        <Card title="Ready for your review">
          <div className="grid grid-3">
            {reviewable.map((v) => (
              <div key={v.id} className="card card-pad" style={{ background: 'var(--bg-surface)' }}>
                <div className="flex justify-between" style={{ marginBottom: 8 }}>
                  <b>{label(v)}</b>
                  <Badge status={v.status} />
                </div>
                <p className="tmuted" style={{ fontSize: 12, marginBottom: 12 }}>
                  Deadline {formatDate(v.deadline)} · Revisions: {v.revision_count}
                </p>
                <div className="flex gap-8">
                  <Button variant="primary" size="sm" icon={CheckCircle2} disabled={submitting} onClick={() => approve(v)}>Approve</Button>
                  <Button variant="secondary" size="sm" icon={MessageSquareWarning} disabled={submitting} onClick={() => setFeedbackFor(v)}>Revise</Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div style={{ height: 20 }} />
      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <Card title="In production">
          {inProgress.length === 0 ? (
            <EmptyState title="Nothing in production right now" />
          ) : (
            inProgress.map((v) => (
              <div key={v.id} className="flex justify-between" style={{ fontSize: 13, padding: '8px 0', borderBottom: '1px solid var(--border-soft)' }}>
                <span>{label(v)}</span>
                <Badge status={v.status} />
              </div>
            ))
          )}
        </Card>
        <Card title="Delivered">
          {delivered.length === 0 ? (
            <EmptyState title="No deliveries yet" />
          ) : (
            delivered.map((v) => (
              <div key={v.id} className="flex justify-between" style={{ fontSize: 13, padding: '8px 0', borderBottom: '1px solid var(--border-soft)' }}>
                <span>{label(v)} · {formatDate(v.delivered_at)}</span>
                {v.final_delivery_link ? (
                  <a href={v.final_delivery_link} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">
                    <Download size={13} /> Download
                  </a>
                ) : (
                  <span className="tmuted" style={{ fontSize: 12 }}>Link pending</span>
                )}
              </div>
            ))
          )}
        </Card>
      </div>

      <Modal open={!!feedbackFor} onClose={() => setFeedbackFor(null)} title={`Request revision — ${feedbackFor ? label(feedbackFor) : ''}`}>
        <Field label="What needs to change?" required>
          <Textarea value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. Trim the first 3 seconds and boost the music volume." />
        </Field>
        <div className="form-actions">
          <Button variant="ghost" onClick={() => setFeedbackFor(null)}>Cancel</Button>
          <Button variant="primary" onClick={requestRevision} disabled={!feedback.trim() || submitting}>Send feedback</Button>
        </div>
      </Modal>
    </div>
  );
}
